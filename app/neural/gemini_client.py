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
from app.schemas import ParsedCommand, GameState
# นำเข้า Prompt Builder จาก prompts.py
from app.neural.prompts import build_interpret_system_prompt
from app.neural.repair import repair_parsed_command

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

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

_clients_cache: Optional[list] = None

class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""


class NeuralNotConfigured(NeuralUnavailable):
    """Missing credentials or SDK; live tests may skip."""


class NeuralQuotaExceeded(NeuralUnavailable):
    """All configured clients exhausted their quota."""


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
        raise NeuralNotConfigured("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai SDK")

    # ประกอบ Prompt พร้อมบริบทตำแหน่งของผู้เล่น ไอเทมในกระเป๋า และหลักฐานที่พบ
    prompt_content = (
        f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
        f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
        f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
        f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
    )

    # ไล่ใช้คีย์ทีละตัว คีย์ไหนโควตาหมดก็ข้ามไปตัวถัดไป
    # ค้าง/ล่มชั่วคราวลองคีย์เดิมซ้ำได้ครั้งเดียว ครั้งละไม่เกิน 3 วิ (ปกติตอบใน ~2 วิ) ในงบรวม 8 วิ
    # จำกัดจำนวนครั้งไว้ เพราะตอน Google ล่ม 503 กลับมาใน ~1 วิ ถ้าวนตามงบเวลาจะยิง 9 ครั้งต่อคำสั่ง
    # กินโควตารายนาทีจนโดน 429 ต่อแม้ Google จะกลับมาแล้ว
    # ข้อผิดพลาดชนิดอื่นไม่ลองซ้ำ เพราะเปลี่ยนคีย์ก็ไม่ช่วย และจะกลบสาเหตุจริงไปเปล่าๆ
    last_error: Optional[Exception] = None
    deadline = time.monotonic() + 8
    queue = list(clients)
    retried = False
    while queue:
        client = queue[0]
        remaining_ms = min(int((deadline - time.monotonic()) * 1000), 3000)
        if remaining_ms <= 500:
            break
        try:
            # ส่งคำร้องขอไปยัง Gemini API โดยบังคับ Structured Output Schema ตาม ParsedCommand
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    # SDK ส่ง timeout เป็น deadline ฝั่งเซิร์ฟเวอร์ซึ่งต้อง >=10 วิ จึงกำหนด header เอง
                    # แล้วใช้ timeout แค่ตัดฝั่งเรา
                    http_options=types.HttpOptions(timeout=remaining_ms,
                        headers={"X-Server-Timeout": "10"},
                        retry_options=types.HttpRetryOptions(attempts=1)),
                    system_instruction=build_interpret_system_prompt(STORY_DATA, state=state, user_text=text),
                    response_mime_type="application/json",
                    response_schema=ParsedCommand,
                    temperature=0.0,
                ),
            )
            if not response.text:
                raise RuntimeError("Gemini API คืนคำตอบว่าง")
            parsed_result = ParsedCommand.model_validate_json(response.text)
            parsed_result.raw_text = text
            repaired_result, repair_note = repair_parsed_command(parsed_result, STORY_DATA, state=state, raw_text=text)
            if repair_note:
                logger.info("Symbolic Repair applied: %s", repair_note)
            return repaired_result
        except Exception as e:
            last_error = e
            if _is_quota_error(e):
                queue.pop(0)
                retried = False
            elif _is_transient(e) and not retried:
                retried = True
            else:
                break
    error_type = NeuralQuotaExceeded if _is_quota_error(last_error) else NeuralUnavailable
    raise error_type(
        f"เรียก Gemini API ล้มเหลว: {last_error}") from last_error
