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
_last_env_mtime: float = 0.0
_active_key_index: int = 1
_last_api_status: Optional[dict] = None
_key_statuses: dict[int, dict] = {}


def get_api_status() -> dict:
    """คืนสถานะการเชื่อมต่อ API, หมายเลข Key ปัจจุบัน และรายการสถานะของแต่ละ Key"""
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
            "keys": [],
        }

    keys_list = []
    for idx in range(1, total + 1):
        st = _key_statuses.get(idx, {"state": "ready", "message": "พร้อมใช้งาน", "error": None})
        is_active = (idx == _active_key_index)
        keys_list.append({
            "index": idx,
            "label": f"Key {idx}",
            "is_active": is_active,
            "role": "กำลังใช้งาน" if is_active else "สำรอง",
            "state": st.get("state", "ready"),
            "message": st.get("message", "พร้อมใช้งาน"),
            "error": st.get("error"),
        })

    key_label = f"Key {_active_key_index}"
    if _last_api_status is not None:
        st = dict(_last_api_status)
        st["total_keys"] = total
        st["key_label"] = key_label
        st["keys"] = keys_list
        return st

    return {
        "status": "ready",
        "online": True,
        "active_key": _active_key_index,
        "total_keys": total,
        "key_label": key_label,
        "message": "พร้อมใช้งาน",
        "keys": keys_list,
    }


class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""


class NeuralNotConfigured(NeuralUnavailable):
    """ไม่มีการตั้งค่า API Key หรือขาดการติดตั้ง google-genai SDK"""


class NeuralQuotaExceeded(NeuralUnavailable):
    """โควตาของ API Key ทั้งหมดในระบบถูกใช้จนเต็มขีดจำกัดแล้ว"""


def _is_quota_error(e: Exception) -> bool:
    """ตรวจสอบว่าข้อผิดพลาดเกิดจากโควตาเต็ม (Quota / Rate Limit) หรือไม่ ทั้งรายนาที (RPM) และรายวัน (RPD)"""
    if getattr(e, "code", None) == 429 or getattr(e, "status_code", None) == 429:
        return True
    text = str(e).upper()
    return any(s in text for s in ("RESOURCE_EXHAUSTED", "429", "QUOTA_EXCEEDED", "RATE_LIMIT", "QUOTA"))


def _is_transient(e: Exception) -> bool:
    """ตรวจสอบว่าข้อผิดพลาดเป็นปัญหาชั่วคราวของเซิร์ฟเวอร์หรือเครือข่ายหรือไม่"""
    text = str(e).upper()
    return any(s in text for s in (
        "DEADLINE_EXCEEDED", "504", "503", "502", "500", "UNAVAILABLE", "TIMED OUT", "TIMEOUT", "CONNECTION"
    ))


def _clients() -> list:
    """คืนไคลเอนต์ของทุกคีย์ตามลำดับที่เขียนไว้

    ใส่คีย์สำรองได้โดยคั่นด้วยจุลภาคในตัวแปร GEMINI_API_KEY ตัวเดิม
    เช่น  GEMINI_API_KEY=AIzaคีย์หลัก,AIzaคีย์สำรอง
    ตั้งตัวแปรชื่ออื่นเพิ่มไม่มีผล เพราะไม่มีโค้ดตรงไหนอ่าน

    โควตาฟรีนับต่อโปรเจกต์ ไม่ใช่ต่อคีย์ คีย์สำรองจึงต้องมาจากโปรเจกต์อื่นถึงจะได้โควตาเพิ่ม
    ตรวจจับการแก้ไขไฟล์ .env อัตโนมัติเพื่อรีโหลดคีย์ใหม่โดยไม่ต้องรีสตาร์ตเซิร์ฟเวอร์
    """
    global _clients_cache, _last_env_mtime
    if not GENAI_AVAILABLE:
        return []
    current_mtime = ENV_PATH.stat().st_mtime if ENV_PATH.exists() else 0.0
    if _clients_cache is None or current_mtime != _last_env_mtime:
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        _last_env_mtime = current_mtime
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
    from app.cases import get_engine
    case_world = get_engine(state.case_id).world
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

    # ไล่ใช้คีย์ตามลำดับ โดยเริ่มจาก Active Key ล่าสุดและสลับคีย์อัตโนมัติหากคีย์ปัจจุบันมีปัญหา (Auto-Failover)
    last_error: Optional[Exception] = None
    deadline = time.monotonic() + 20

    start_idx = (_active_key_index - 1) % len(clients) if len(clients) > 0 else 0
    ordered_clients = clients[start_idx:] + clients[:start_idx]

    for client in ordered_clients:
        current_key_idx = clients.index(client) + 1
        _active_key_index = current_key_idx
        has_backup = (len(ordered_clients) > 1 and client != ordered_clients[-1])

        # หากมีคีย์สำรองอยู่และเกิดข้อผิดพลาด ให้สลับคีย์ทันทีเพื่อไม่ให้เสียเวลา deadline
        # หากเป็นคีย์เดียวที่เหลืออยู่ ให้ลองซ้ำได้ 1 ครั้ง
        max_attempts = 1 if has_backup else 2
        for attempt in range(max_attempts):
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
                            case_world,
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

                _active_key_index = current_key_idx
                _key_statuses[current_key_idx] = {
                    "state": "ready",
                    "message": "พร้อมใช้งาน",
                    "error": None,
                }
                key_tag = f"Key {_active_key_index}"
                _last_api_status = {
                    "status": "ready",
                    "online": True,
                    "active_key": _active_key_index,
                    "total_keys": len(clients),
                    "key_label": key_tag,
                    "message": "พร้อมใช้งาน",
                }
                parsed_result = ParsedCommand.model_validate_json(response.text)
                parsed_result.raw_text = text
                parsed_result.latency_ms = t_elapsed_ms
                parsed_result.parser_mode = "gemini_knn" if use_knn else "gemini_static"
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    parsed_result.prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
                    parsed_result.completion_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

                # วงจรตรวจสอบและซ่อมแซมคำสั่งเชิงสัญลักษณ์ (Symbolic Repair Loop)
                if enable_repair:
                    repaired_result, repair_note = repair_parsed_command(parsed_result, case_world, state=state, raw_text=text)
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
                # หากเป็น Quota error ไม่ต้องลองซ้ำที่คีย์เดิม บันทึกสถานะและสลับไปคีย์ถัดไปทันที
                if _is_quota_error(e):
                    _key_statuses[current_key_idx] = {
                        "state": "quota_exceeded",
                        "message": "ติดโควตา (Rate Limit / Quota)",
                        "error": str(e)[:120],
                    }
                    logger.warning("[Gemini Auto-Failover] Key %d ติดข้อจำกัดโควตา (429 Rate Limit / Quota): %s -> กำลังสลับไปคีย์สำรองถัดไปทันที", current_key_idx, e)
                    break
                # หากเป็น transient error (เช่น timeout, 503)
                if _is_transient(e):
                    _key_statuses[current_key_idx] = {
                        "state": "transient_error",
                        "message": "เซิร์ฟเวอร์ขัดข้อง/ตอบช้า (503/Timeout)",
                        "error": str(e)[:120],
                    }
                    # หากไม่มีคีย์สำรอง และยังเป็น attempt แรก ให้ลองซ้ำอีกครั้ง
                    if attempt == 0 and not has_backup:
                        logger.info("[Gemini Retry] Key %d เกิดข้อผิดพลาดชั่วคราว (%s) กำลังลองซ้ำอีก 1 ครั้ง...", current_key_idx, e)
                        continue
                else:
                    _key_statuses[current_key_idx] = {
                        "state": "error",
                        "message": "ข้อผิดพลาด",
                        "error": str(e)[:120],
                    }
                # หากลองซ้ำแล้วหรือมีคีย์สำรอง ให้สลับไปลองคีย์ถัดไปทันที
                logger.warning("[Gemini Auto-Failover] Key %d ล้มเหลว (%s) -> กำลังสลับไปคีย์สำรองถัดไป...", current_key_idx, e)
                break
    is_quota = _is_quota_error(last_error)
    key_tag = f"Key {_active_key_index}"
    _last_api_status = {
        "status": "quota_exceeded" if is_quota else "error",
        "online": False,
        "active_key": _active_key_index,
        "total_keys": len(clients),
        "key_label": key_tag,
        "message": "โควตาเต็มชั่วคราว (Rate Limit / Quota)" if is_quota else "API ขัดข้องชั่วคราว",
        "error_detail": str(last_error)[:120],
    }
    logger.error("[Gemini Auto-Failover] ทุกคีย์ในระบบ (%d คีย์) ไม่สามารถใช้งานได้ ข้อผิดพลาดล่าสุด: %s", len(clients), last_error)
    error_type = NeuralQuotaExceeded if is_quota else NeuralUnavailable
    raise error_type(
        f"เรียก Gemini API ล้มเหลว: {last_error}") from last_error
