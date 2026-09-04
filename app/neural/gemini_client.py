"""
gemini_client.py — โค้ดหลักส่วนประสานงาน Gemini API (Neuro AI Layer)

หน้าที่:
- เชื่อมต่อกับ Gemini API (Google GenAI SDK)
- รับข้อความภาษาไทยดิบจากผู้เล่น พร้อมบริบทของสถานะเกม (GameState)
- ส่งไปตีความด้วย LLM แล้วแปลงผลลัพธ์กลับเป็น Pydantic Model (`ParsedCommand`)
- ทำหน้าที่สกัดความหมายภาษาธรรมชาติอย่างเดียว โดยไม่ตัดสินว่าถูกกฎของเกมหรือไม่
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# นำเข้า Google GenAI SDK (เช็กการติดตั้งล่วงหน้า)
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from app.schemas import ParsedCommand, GameState
from app.neural.prompts import build_interpret_system_prompt

# โหลด API Key จากไฟล์ .env
load_dotenv()
logger = logging.getLogger(__name__)

# ซ่อน Log เตือนที่ไม่จำเป็นจาก Google GenAI SDK
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

# ============================================================
# WORLD DATA & SYSTEM PROMPT INITIALIZATION
# อ่านไฟล์ข้อมูลฉาก (story.json) เพื่อสร้าง System Prompt และ Entity Grounding Table
# ============================================================
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STORY_DATA: dict = json.loads((DATA_DIR / "story.json").read_text(encoding="utf-8"))

SYSTEM_INTERPRET_PROMPT = build_interpret_system_prompt(STORY_DATA)
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

_clients_cache: Optional[list] = None

class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""


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
