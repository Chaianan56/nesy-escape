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

_client_instance: Optional[object] = None

class NeuralUnavailable(RuntimeError):
    """Exception แจ้งเตือนเมื่อเรียกใช้งาน LLM ไม่สำเร็จ"""

    def get_genai_client():
        """สร้างหรือคืนค่า Singleton Client ของ Gemini API"""
        global _client_instance
        if not GENAI_AVAILABLE:
            return None
        if _client_instance is None:
            api_key = os.getenv("GEMINI_API_KEY", "").strip()
            if api_key:
                _client_instance = genai.Client(api_key=api_key)
        return _client_instance

    def llm_online() -> bool:
        """ตรวจสอบว่า Gemini API Key พร้อมใช้งานหรือไม่"""
        return get_genai_client() is not None

    def interpret(text: str, state: GameState) -> ParsedCommand:
        """แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand

        Args:
            text (str): ข้อความภาษาไทยดิบจากผู้เล่น (เช่น 'เดินไปตู้เสบียง', 'ตรวจดูบันทึก')
            state (GameState): สถานะเกมปัจจุบัน ใช้เป็นบริบทช่วยในการแกะคำกำกวม

        Returns:
            ParsedCommand: โครงสร้างคำสั่งที่สกัดแล้ว (action, target, instrument, confidence)
        """
        client = get_genai_client()
        if client is None:
            raise NeuralUnavailable("ไม่มี GEMINI_API_KEY หรือไม่ได้ติดตั้ง google-genai SDK")

        try:
            # ประกอบ Prompt พร้อมบริบทตำแหน่งของผู้เล่น ไอเทมในกระเป๋า และหลักฐานที่พบ
            prompt_content = (
                f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
                f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
                f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
                f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
            )

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
            if response.text:
                parsed_result = ParsedCommand.model_validate_json(response.text)
                parsed_result.raw_text = text
                return parsed_result
            raise NeuralUnavailable("Gemini API คืนคำตอบว่าง")
        except Exception as e:
            raise NeuralUnavailable(f"เรียก Gemini API ล้มเหลว: {e}")
