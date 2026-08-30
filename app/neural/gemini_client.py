"""
gemini_client.py — โค้ดหลักส่วนประสานงาน Gemini API (Neuro AI Layer)
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from app.schemas import ParsedCommand, GameState
from app.neural.prompts import build_interpret_system_prompt

load_dotenv()
logger = logging.getLogger(__name__)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STORY_DATA: dict = json.loads((DATA_DIR / "story.json").read_text(encoding="utf-8"))

SYSTEM_INTERPRET_PROMPT = build_interpret_system_prompt(STORY_DATA)
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

_client_instance: Optional[object] = None


class NeuralUnavailable(RuntimeError):
    """เรียก LLM ไม่สำเร็จ"""


def get_genai_client():
    """สร้างหรือคืนค่า Singleton Client ของ Gemini"""
    global _client_instance
    if not GENAI_AVAILABLE:
        return None
    if _client_instance is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key:
            _client_instance = genai.Client(api_key=api_key)
    return _client_instance


def llm_online() -> bool:
    """ตรวจสอบว่า Gemini API พร้อมใช้งานหรือไม่"""
    return get_genai_client() is not None


def interpret(text: str, state: GameState) -> ParsedCommand:
    """แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand"""
    client = get_genai_client()
    if client is None:
        raise NeuralUnavailable("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai SDK")

    try:
        prompt_content = (
            f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
            f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
            f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
            f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
        )

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
        if response.text:
            parsed_result = ParsedCommand.model_validate_json(response.text)
            parsed_result.raw_text = text
            return parsed_result
        raise NeuralUnavailable("Gemini API คืนคำตอบว่าง")
    except Exception as e:
        raise NeuralUnavailable(f"เรียก Gemini API ล้มเหลว: {e}")
