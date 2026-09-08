"""
gemini_client.py — โค้ดหลักส่วนประสานงาน Gemini API (Neuro AI Layer)

หน้าที่:
- นำข้อความดิบผ่าน TextPreprocessor (PyThaiNLP + spaCy) เพื่อสกัด Features
- ส่งข้อความที่ผ่าน Normalization พร้อม Features ไปให้ Gemini API (Google GenAI SDK)
- นำผลลัพธ์จาก Gemini มาแปลงกลับให้อยู่ในรูป Pydantic Models (ParsedCommand / Decision)
- มีระบบ Fallback ในกรณีที่ไม่ได้ใส่ API Key หรือ API ล้มเหลว เพื่อไม่ให้ระบบล่ม

⚠️ ไฟล์นี้ไม่ตัดสินว่าคำสั่งถูกกฎหรือไม่ (ยกเว้น decide_autonomously ซึ่งใช้เฉพาะโหมด A)
   การตัดสินของระบบที่นำเสนอเป็นหน้าที่ของ app/symbolic/engine.py เท่านั้น
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# นำเข้า Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# นำเข้า Data Models จาก schemas.py
from app.schemas import (
    ParsedCommand,
    Decision,
    GameState,
    ActionType,
    ReasoningStep,
)
# นำเข้า Prompt Builder จาก prompts.py
from app.neural.prompts import (
    build_interpret_system_prompt,
    build_baseline_decision_prompt,
)
# นำเข้า Preprocessor สำหรับล้างข้อความและสกัด Features
from app.neural.preprocessor import preprocess_text, PreprocessedFeature

# โหลดตัวแปรสภาพแวดล้อมจาก .env
load_dotenv()

logger = logging.getLogger(__name__)

# SDK เตือนเรื่อง automatic function calling ทุกครั้งที่เรียก generate_content
# เราไม่ได้ใช้ฟีเจอร์นั้น เป็นแค่เสียงรบกวนที่บังหน้าจอเวลาเล่นเกม
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

# ============================================================
# WORLD DATA — อ่านจากไฟล์ชุดเดียวกับ Symbolic Engine
# neural ไม่ import engine เพื่อไม่ให้สองเลเยอร์ผูกกัน แต่ต้องอ่านข้อมูลชุดเดียวกัน
# ไม่งั้น id ที่ LLM สกัดจะไม่ตรงกับที่ engine รู้จัก
# ============================================================
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STORY_DATA: dict = json.loads((DATA_DIR / "story.json").read_text(encoding="utf-8"))
RULES_DATA: dict = json.loads((DATA_DIR / "rules.json").read_text(encoding="utf-8"))

SYSTEM_INTERPRET_PROMPT = build_interpret_system_prompt(STORY_DATA)
SYSTEM_BASELINE_DECISION_PROMPT = build_baseline_decision_prompt(RULES_DATA, STORY_DATA)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

_clients_cache: Optional[list] = None

class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""


def _strict() -> bool:
    """โหมด strict: ห้ามตกไปใช้ fallback แบบเงียบๆ

    ตอนเก็บข้อมูลการทดลองต้องตั้ง NEURAL_STRICT=1 เสมอ
    ไม่งั้น 429 หรือ API ล่มจะทำให้ log ปนผลของ heuristic เข้ากับผลของ LLM
    โดยไม่มีอะไรบอกว่าแถวไหนเป็นของใคร ซึ่งทำให้ผลการทดลองใช้ไม่ได้
    """
    return os.getenv("NEURAL_STRICT", "").strip().lower() in ("1", "true", "yes")


def _fallback_or_raise(reason: str) -> None:
    if _strict():
        raise NeuralUnavailable(reason)
    # error ของ SDK ยาวหลายร้อยตัวอักษร ถ้าปล่อยเต็มจะบังหน้าจอตอนเล่นเกม
    short = reason if len(reason) <= 160 else reason[:157] + "..."
    logger.warning(f"{short} — ใช้นโยบาย Fallback")


# ============================================================
# RESPONSE SCHEMA ของโหมด A
# Decision.state_changes เป็น Dict[str, Any] ซึ่ง Gemini ไม่รับเป็น response_schema
# (additionalProperties ไม่รองรับ) จึงต้องประกาศรูปแบบแคบๆ ไว้ที่นี่
# ผลพลอยได้คือบังคับให้ LLM ใช้คีย์ชุดเดียวกับที่ apply_changes รู้จัก
# ไม่งั้นโหมด A จะ "อนุมัติ" แต่สถานะเกมไม่ขยับเลย
# ============================================================
class _StateChanges(BaseModel):
    move_to: Optional[str] = None
    inventory_add: Optional[str] = None
    discovered_evidence_add: Optional[str] = None
    unlocked_add: Optional[str] = None
    interrogated_add: Optional[str] = None


class _DecisionResponse(BaseModel):
    allowed: bool
    message: str
    reasoning_chain: List[ReasoningStep] = Field(default_factory=list)
    violated_rule_id: Optional[str] = None
    state_changes: _StateChanges = Field(default_factory=_StateChanges)

    def to_decision(self) -> Decision:
        return Decision(
            allowed=self.allowed,
            message=self.message,
            reasoning_chain=self.reasoning_chain,
            violated_rule_id=self.violated_rule_id,
            state_changes={k: v for k, v in self.state_changes.model_dump().items() if v},
        )


def _is_quota_error(e: Exception) -> bool:
    """โควตาหมดของคีย์นี้หรือเปล่า ถ้าใช่ค่อยคุ้มที่จะเปลี่ยนไปคีย์อื่น"""
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def _clients() -> list:
    """คืนไคลเอนต์ของทุกคีย์ตามลำดับที่เขียนไว้

    ใส่คีย์สำรองได้โดยคั่นด้วยจุลภาคในตัวแปร GEMINI_API_KEY ตัวเดิม
    เช่น  GEMINI_API_KEY=AIzaคีย์หลัก,AIzaคีย์สำรอง
    ตั้งตัวแปรชื่ออื่นเพิ่มไม่มีผล เพราะไม่มีโค้ดตรงไหนอ่าน

    โควตาฟรีนับต่อโปรเจกต์ ไม่ใช่ต่อคีย์ คีย์สำรองจึงต้องมาจากโปรเจกต์อื่นถึงจะได้โควตาเพิ่ม
    """
    global _clients_cache
    if not GENAI_AVAILABLE:
        return []
    if _clients_cache is None:
        _clients_cache = [
            genai.Client(api_key=key)
            for key in (k.strip() for k in os.getenv("GEMINI_API_KEY", "").split(","))
            if key
        ]
    return _clients_cache


def get_genai_client():
    """คืนไคลเอนต์ตัวแรก ใช้ตรวจว่าตั้งคีย์ไว้แล้วหรือยัง"""
    clients = _clients()
    return clients[0] if clients else None


def llm_online() -> bool:
    """ตั้งคีย์ไว้แล้วหรือยัง

    ชื่อฟังก์ชันชวนเข้าใจผิด มันไม่ได้ตรวจว่าเรียก API ได้จริง
    แค่ตรวจว่ามีคีย์และสร้างไคลเอนต์ได้ โควตาหมดแล้วมันก็ยังคืน True
    ถ้าอยากรู้ว่าเรียกได้จริงไหม ต้องลองเรียก interpret() แล้วดักข้อผิดพลาดเอง
    """
    return get_genai_client() is not None


_VERBS: Dict[ActionType, List[str]] = {
    ActionType.INTERROGATE: ["interrogate", "สอบปากคำ", "สอบสวน", "ซักถาม", "พูดกับ", "คุยกับ", "ถาม", "คุย"],
    ActionType.ACCUSE: ["accuse", "กล่าวหา", "ชี้ตัว", "จับกุม", "ระบุตัวคนร้าย"],
    ActionType.EXAMINE: ["examine", "inspect", "check", "look", "ตรวจสอบ", "ตรวจดู",
                         "พิสูจน์", "สำรวจ", "ตรวจ", "ดู"],
    ActionType.TAKE: ["take", "grab", "pick", "เก็บ", "หยิบ", "นำติดตัว"],
    ActionType.UNLOCK: ["unlock", "open", "ปลดล็อก", "ไข", "งัด", "เปิด"],
    ActionType.MOVE: ["move", "go", "walk", "เดินไป", "ย้ายไป", "เข้าไป", "ไปที่", "ไป"],
    ActionType.USE: ["use", "apply", "ใช้"],
}

_VERB_INDEX: List[tuple] = sorted(
    ((kw, act) for act, kws in _VERBS.items() for kw in kws),
    key=lambda pair: -len(pair[0]),
)

_ACTION_TH = {
    ActionType.EXAMINE: "ตรวจสอบ", ActionType.TAKE: "เก็บ", ActionType.USE: "ใช้",
    ActionType.UNLOCK: "ปลดล็อก", ActionType.MOVE: "ไปที่",
    ActionType.INTERROGATE: "สอบปากคำ", ActionType.ACCUSE: "กล่าวหา",
}

# action เหล่านี้ไร้ความหมายถ้าไม่มีเป้าหมาย -> ถือว่ากำกวม
_NEEDS_TARGET = {ActionType.EXAMINE, ActionType.TAKE, ActionType.USE,
                 ActionType.UNLOCK, ActionType.MOVE, ActionType.INTERROGATE,
                 ActionType.ACCUSE}


def _build_entity_index(world: dict) -> List[tuple]:
    """สร้างตาราง (ข้อความที่ผู้เล่นอาจพิมพ์ -> id จริง) เรียงยาวไปสั้น"""
    index: Dict[str, str] = {}
    for group in ("locations", "objects", "suspects"):
        for eid, info in world.get(group, {}).items():
            index.setdefault(eid.lower(), eid)
            name = info.get("name_th", "")
            if name:
                index.setdefault(name.lower(), eid)
                # "ห้องเก็บของบริการ (จุดเกิดเหตุ)" ผู้เล่นอาจเรียกด้วยชื่อไหนก็ได้
                # จึงลงทะเบียนทั้งชื่อเต็ม ชื่อที่ตัดวงเล็บออก และข้อความในวงเล็บ
                for part in [re.sub(r"\s*\(.*?\)\s*", "", name), *re.findall(r"\((.*?)\)", name)]:
                    for sub in part.split(":"):
                        sub = sub.strip().lower()
                        if sub:
                            index.setdefault(sub, eid)
            # คนมักเรียกผู้ต้องสงสัยด้วยตำแหน่งมากกว่าชื่อ เช่น "พนักงานควบคุมรถ"
            role = info.get("role", "").strip().lower()
            if role:
                index.setdefault(role, eid)
    return sorted(index.items(), key=lambda pair: -len(pair[0]))


_ENTITY_INDEX = _build_entity_index(STORY_DATA)
_LOCATION_IDS = set(STORY_DATA.get("locations", {}))
_SUSPECT_IDS = set(STORY_DATA.get("suspects", {}))


def _match_entities(text: str) -> List[str]:
    """หา id ทั้งหมดที่ปรากฏในข้อความ เรียงตามตำแหน่งที่พบ"""
    low = text.lower()
    hits, taken = [], []
    for phrase, eid in _ENTITY_INDEX:
        pos = low.find(phrase)
        if pos < 0 or eid in [h[1] for h in hits]:
            continue
        # กันการนับซ้ำเมื่อชื่อสั้นเป็นส่วนหนึ่งของชื่อยาวที่จับไปแล้ว
        if any(pos >= s and pos + len(phrase) <= e for s, e in taken):
            continue
        taken.append((pos, pos + len(phrase)))
        hits.append((pos, eid))
    return [eid for _, eid in sorted(hits)]


def _fallback_parse(text: str, clean_text: str, state: GameState) -> ParsedCommand:
    """ตีความแบบ heuristic เมื่อไม่มี LLM

    ponytail: จับคู่ด้วย substring ตรงๆ ยังพลาดกับประโยคซับซ้อนหรือคำพ้อง
    ถ้าต้องการความแม่นกว่านี้ให้ใช้ LLM (ตั้ง GEMINI_API_KEY) ซึ่งเป็นเส้นทางหลักอยู่แล้ว
    """
    action = next((act for kw, act in _VERB_INDEX if kw in clean_text.lower()), None)
    entities = _match_entities(clean_text)

    # ผู้ต้องสงสัยถูกเรียกด้วยตำแหน่งซึ่งมักมีคำว่า "ห้อง..." ของสถานที่ปนอยู่
    # เช่น "พนักงานควบคุมรถ" ชนกับ "ห้องพนักงานควบคุมรถ" — สอบปากคำต้องเลือกคน
    if action in (ActionType.INTERROGATE, ActionType.ACCUSE):
        entities = [e for e in entities if e in _SUSPECT_IDS] or entities

    if action is None:
        return ParsedCommand(action=ActionType.UNKNOWN, raw_text=text, confidence=0.0)

    # move ต้องชี้ไปที่สถานที่ ส่วน action อื่นต้องไม่ใช่สถานที่
    if action == ActionType.MOVE:
        entities = [e for e in entities if e in _LOCATION_IDS] or entities

    target = entities[0] if entities else None
    instrument = None
    if action in (ActionType.USE, ActionType.UNLOCK) and len(entities) > 1:
        # ผู้เล่นมักพูดถึงเครื่องมือก่อนเป้าหมาย เช่น "ใช้กุญแจเปิดห้อง"
        instrument, target = entities[0], entities[1]

    # "ดูรอบๆ" ไม่ระบุเป้าหมาย แต่ในเกมที่พิมพ์ล้วนคือคำสั่งพื้นฐานที่สุด
    if target is None and action == ActionType.EXAMINE:
        return ParsedCommand(action=action, target=state.current_location,
                             raw_text=text, confidence=0.5)

    if target is None and action in _NEEDS_TARGET:
        return ParsedCommand(
            action=ActionType.AMBIGUOUS,
            raw_text=text,
            confidence=0.4,
            alternatives=[f"ยังไม่ได้ระบุว่าจะ{_ACTION_TH.get(action, action.value)}อะไร"],
        )

    return ParsedCommand(
        action=action,
        target=target,
        instrument=instrument,
        raw_text=text,
        confidence=0.5,
    )


# ============================================================
# PUBLIC API — main.py เรียกใช้แค่สองฟังก์ชันนี้
# ============================================================

def interpret(text: str, state: GameState) -> ParsedCommand:
    """แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand

    Args:
        text (str): ข้อความภาษาไทยดิบจากผู้เล่น (เช่น 'เดินไปตู้เสบียง', 'ตรวจดูบันทึก')
        state (GameState): สถานะเกมปัจจุบัน ใช้เป็นบริบทช่วยในการแกะคำกำกวม

    Returns:
        ParsedCommand: โครงสร้างคำสั่งที่สกัดแล้ว (action, target, instrument, confidence)
    """
    clients = _clients()
    if not clients:
        raise NeuralUnavailable("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai SDK")

    # ประกอบ Prompt พร้อมบริบทตำแหน่งของผู้เล่น ไอเทมในกระเป๋า และหลักฐานที่พบ
    prompt_content = (
        f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
        f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
        f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
        f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
    )

    # ไล่ใช้คีย์ทีละตัว คีย์ไหนโควตาหมดก็ข้ามไปตัวถัดไป
    # ข้อผิดพลาดชนิดอื่นไม่ลองซ้ำ เพราะเปลี่ยนคีย์ก็ไม่ช่วย และจะกลบสาเหตุจริงไปเปล่าๆ
    last_error: Optional[Exception] = None
    for client in clients:
        try:
            # ส่งคำร้องขอไปยัง Gemini API โดยบังคับ Structured Output Schema ตาม ParsedCommand
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INTERPRET_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ParsedCommand,
                    temperature=0.0,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini API คืนคำตอบว่าง")
            parsed_result = ParsedCommand.model_validate_json(response.text)
            parsed_result.raw_text = text
            return parsed_result
        except Exception as e:
            last_error = e
            if not _is_quota_error(e):
                break
    raise NeuralUnavailable(
        f"เรียก Gemini API ล้มเหลว (ลองแล้ว {len(clients)} คีย์): {last_error}")


def decide_autonomously(text: str, state: GameState, parsed: ParsedCommand) -> Decision:
    """ให้ Gemini ตัดสินใจด้วยตนเองว่าอนุมัติให้ทำคำสั่งหรือไม่ (ใช้เฉพาะ Mode A Baseline)

    Args:
        text (str): ข้อความดิบของผู้เล่น
        state (GameState): สถานะเกมปัจจุบัน
        parsed (ParsedCommand): ผลลัพธ์ที่ตีความแล้วจาก interpret()

    Returns:
        Decision: คำตัดสินว่าอนุญาตหรือไม่ (allowed: bool) พร้อมเหตุผล
    """
    features = preprocess_text(text)
    client = get_genai_client()

    if client is not None:
        try:
            prompt_content = (
                f"ข้อความดิบ: {text}\n"
                f"ParsedCommand: {parsed.model_dump_json()}\n"
                f"GameState: {state.model_dump_json()}"
            )

            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_BASELINE_DECISION_PROMPT,
                    response_mime_type="application/json",
                    response_schema=_DecisionResponse,
                    temperature=0.2,
                ),
            )
            if response.text:
                return _DecisionResponse.model_validate_json(response.text).to_decision()
            _fallback_or_raise("Gemini คืนคำตอบว่างในโหมด Baseline")
        except NeuralUnavailable:
            raise
        except Exception as e:
            _fallback_or_raise(f"เรียก Gemini API ในโหมด Baseline ล้มเหลว: {e}")
    else:
        _fallback_or_raise("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai")

    # Fallback กรณีไม่มี API Key — จงใจให้หลวม เพื่อให้เห็นว่าโหมด A ไม่มีการบังคับตามกฎ
    return Decision(
        allowed=True,
        message="(Mode A Baseline - Fallback) คำสั่งได้รับอนุมัติ",
        reasoning_chain=[
            ReasoningStep(
                rule_id="LLM_BASELINE",
                description=f"ระบบ Fallback ตัดสินเบื้องต้น (ภาษารับเข้า: {features.language})",
                passed=True,
            )
        ],
        state_changes={},
    )
