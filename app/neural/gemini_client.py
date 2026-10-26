"""
gemini_client.py — ส่วนประสานงาน Gemini API (Neuro AI Layer)

หน้าที่เดียวคือแปลข้อความภาษาไทยของผู้เล่นให้เป็น ParsedCommand
โดยส่งไปให้ Gemini พร้อมบังคับรูปแบบผลลัพธ์ด้วย response_schema

⚠️ ไฟล์นี้ไม่ตัดสินว่าคำสั่งถูกกฎหรือไม่
   การตัดสินเป็นหน้าที่ของ app/symbolic/engine.py เท่านั้น
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# นำเข้า Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# นำเข้า Data Models จาก schemas.py
from app.schemas import ActionType, GameState, ParsedCommand
# นำเข้า Prompt Builder จาก prompts.py
from app.neural.prompts import build_interpret_system_prompt
from app.neural.repair import repair_parsed_command

# โหลดตัวแปรสภาพแวดล้อมจาก .env
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

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

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

_clients_cache: Optional[list] = None
_active_key_index: int = 1
_last_api_status: Optional[dict] = None


def get_api_status() -> dict:
    """คืนสถานะการเชื่อมต่อ API และหมายเลข Key ที่กำลังใช้งานอยู่"""
    clients = _clients()
    total = len(clients)
    if not GENAI_AVAILABLE or total == 0:
        return {
            "status": "offline",
            "online": False,
            "active_key": 0,
            "total_keys": 0,
            "key_label": "ไม่มี Key",
            "message": "ไม่มี GEMINI_API_KEY",
        }
    if _last_api_status is not None:
        st = dict(_last_api_status)
        st["total_keys"] = total
        return st
    return {
        "status": "ready",
        "online": True,
        "active_key": _active_key_index,
        "total_keys": total,
        "key_label": f"Key {_active_key_index}",
        "message": "พร้อมใช้งาน",
    }


class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""


class NeuralNotConfigured(NeuralUnavailable):
    """ไม่มีการตั้งค่า API Key หรือขาดการติดตั้ง google-genai SDK"""


class NeuralQuotaExceeded(NeuralUnavailable):
    """โควตาของ API Key ทั้งหมดในระบบถูกใช้จนเต็มขีดจำกัดแล้ว"""


def _is_quota_error(e: Exception) -> bool:
    """โควตาหมดของคีย์นี้หรือเปล่า ถ้าใช่ค่อยคุ้มที่จะเปลี่ยนไปคีย์อื่น"""
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def _is_transient(e: Exception) -> bool:
    """Gemini ค้างหรือล่มชั่วคราว ลองคีย์เดิมซ้ำมักผ่าน (วัดจริง ~1 ใน 4 ค้างจน 504)"""
    text = str(e)
    return any(s in text for s in ("DEADLINE_EXCEEDED", "504", "503", "UNAVAILABLE", "timed out", "Timeout"))


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


# ============================================================
# PUBLIC API — main.py เรียกใช้แค่สองฟังก์ชันนี้
# ============================================================

def interpret(
    text: str,
    state: GameState,
    prune: bool = True,
    use_knn: bool = True,
    zero_shot: bool = False,
    enable_repair: bool = True,
    use_mmr: bool = True,
) -> ParsedCommand:
    """แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand

    Args:
        text (str): ข้อความภาษาไทยดิบจากผู้เล่น (เช่น 'เดินไปตู้เสบียง', 'ตรวจดูบันทึก')
        state (GameState): สถานะเกมปัจจุบัน ใช้เป็นบริบทช่วยในการแกะคำกำกวม
        prune (bool): เปิดใช้ Semantic Entity Pruning ตัดทอนขนาด Prompt
        use_knn (bool): เปิดใช้ Dynamic kNN Retrieval จาก Memory Bank
        zero_shot (bool): โหมดทดลอง Zero-Shot Baseline
        enable_repair (bool): เปิดใช้วงจรซ่อมแซมเชิงสัญลักษณ์ (Symbolic Repair Loop)
        use_mmr (bool): เปิดใช้ Maximal Marginal Relevance (MMR) เพื่อความหลากหลายของตัวอย่าง

    Returns:
        ParsedCommand: โครงสร้างคำสั่งที่สกัดแล้ว (action, target, instrument, confidence)
    """
    global _active_key_index, _last_api_status
    clients = _clients()
    if not clients:
        raise NeuralNotConfigured("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai SDK")

    # ประกอบ Prompt พร้อมบริบทตำแหน่งของผู้เล่น ไอเทมในกระเป๋า และหลักฐานที่พบ
    prompt_content = (
        f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
        f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
        f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
        f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
    )

    # ไล่ใช้คีย์ทีละตัว คีย์ไหนโควตาหมดก็ข้ามไปตัวถัดไป
    last_error: Optional[Exception] = None
    # Allow one bounded retry for transient timeouts without retrying indefinitely.
    deadline = time.monotonic() + 20
    queue = list(clients)
    retried = False
    while queue:
        client = queue[0]
        remaining_ms = min(int((deadline - time.monotonic()) * 1000), 8000)
        if remaining_ms <= 500:
            break
        try:
            t_call_start = time.perf_counter()
            # ส่งคำร้องขอไปยัง Gemini API โดยบังคับ Structured Output Schema ตาม ParsedCommand
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    http_options=types.HttpOptions(
                        timeout=remaining_ms,
                        headers={"X-Server-Timeout": "15"},
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                    system_instruction=build_interpret_system_prompt(
                        STORY_DATA,
                        state=state,
                        user_text=text,
                        prune=prune,
                        use_knn=use_knn,
                        zero_shot=zero_shot,
                        use_mmr=use_mmr,
                    ),
                    response_mime_type="application/json",
                    response_schema=ParsedCommand,
                    temperature=0.0,
                ),
            )
            t_elapsed_ms = round((time.perf_counter() - t_call_start) * 1000, 2)
            if not response.text:
                raise RuntimeError("Gemini API คืนคำตอบว่าง")
            try:
                _active_key_index = clients.index(client) + 1
                _last_api_status = {
                    "status": "ready",
                    "online": True,
                    "active_key": _active_key_index,
                    "total_keys": len(clients),
                    "key_label": f"Key {_active_key_index}",
                    "message": "พร้อมใช้งาน",
                }
            except Exception:
                pass
            parsed_result = ParsedCommand.model_validate_json(response.text)
            parsed_result.raw_text = text
            parsed_result.latency_ms = t_elapsed_ms
            parsed_result.parser_mode = "gemini_knn" if use_knn else "gemini_static"
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                parsed_result.prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
                parsed_result.completion_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

            # Symbolic-Guided Self-Correction (Repair Loop)
            if enable_repair:
                repaired_result, repair_note = repair_parsed_command(parsed_result, STORY_DATA, state=state, raw_text=text)
                if repair_note:
                    logger.info("Symbolic Repair applied: %s", repair_note)
                    # Closed-Loop NeSy Active Co-Learning: บันทึกตัวอย่างที่ซ่อมแล้วเข้าสู่ Memory Bank
                    if repaired_result.action not in (ActionType.UNKNOWN, ActionType.AMBIGUOUS):
                        from app.neural.retriever import get_retriever
                        retriever = get_retriever()
                        new_exemplar = {
                            "query": text,
                            "action": repaired_result.action.value,
                            "target": repaired_result.target,
                            "confidence": round(repaired_result.confidence, 2),
                            "source": "active_learning_repair",
                        }
                        if repaired_result.instrument:
                            new_exemplar["instrument"] = repaired_result.instrument
                        if repaired_result.code:
                            new_exemplar["code"] = repaired_result.code
                        retriever.add_example(new_exemplar, persist=False)
                        logger.info("Active Learning: Added repaired exemplar to memory bank [%s -> %s %s]", text, repaired_result.action.value, repaired_result.target)
                return repaired_result

            return parsed_result
        except Exception as e:
            last_error = e
            if _is_quota_error(e):
                queue.pop(0)
                retried = False
            elif _is_transient(e) and not retried:
                retried = True
            else:
                break
    is_quota = _is_quota_error(last_error)
    _last_api_status = {
        "status": "quota_exceeded" if is_quota else "error",
        "online": False,
        "active_key": _active_key_index,
        "total_keys": len(clients),
        "key_label": f"Key {_active_key_index}",
        "message": "โควตาเต็มชั่วคราว (Rate Limit / Quota)" if is_quota else "API ขัดข้องชั่วคราว",
        "error_detail": str(last_error)[:120],
    }
    error_type = NeuralQuotaExceeded if is_quota else NeuralUnavailable
    raise error_type(
        f"เรียก Gemini API ล้มเหลว: {last_error}") from last_error
