"""
gemini_client.py — ส่วนประสานงาน Gemini API (Neuro AI Layer)

หน้าที่เดียวคือแปลข้อความภาษาไทยของผู้เล่นให้เป็น ParsedCommand
โดยส่งไปให้ Gemini พร้อมบังคับรูปแบบผลลัพธ์ด้วย response_schema

⚠️ ไฟล์นี้ไม่ตัดสินว่าคำสั่งถูกกฎหรือไม่
   การตัดสินเป็นหน้าที่ของ app/symbolic/engine.py เท่านั้น
"""

import json
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from app.schemas import ParsedCommand, GameState
from app.neural.prompts import build_interpret_system_prompt

# นำเข้า Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# โหลดตัวแปรสภาพแวดล้อมจาก .env
load_dotenv()

# ==============================================================================

#หาโฟลเดอร์ data ที่เก็บไฟล์เนื้อเรื่องเกม (story.json) และเปิดอ่านไฟล์ JSON
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STORY_DATA: dict = json.loads((DATA_DIR / "story.json").read_text(encoding="utf-8"))

SYSTEM_INTERPRET_PROMPT = build_interpret_system_prompt(STORY_DATA)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

# ==============================================================================

_clients_cache: Optional[list] = None

class NeuralUnavailable(RuntimeError):
    """ระบบ Neural Layer มีปัญหาและไม่สามารถติดต่อ Gemini LLM ได้"""

class NeuralNotConfigured(NeuralUnavailable):
    """ลืมใส่ API Key หรือไม่ได้ติดตั้ง google-genai SDK"""

class NeuralQuotaExceeded(NeuralUnavailable):
    """โควตาการใช้งานหมดเกลี้ยงแล้ว"""

# ==============================================================================

# เช็กว่าข้อผิดพลาดเกิดจากโควตาหมดหรือไม่
def _is_quota_error(e: Exception) -> bool:
    text = str(e)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def _clients() -> list:
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

# เรียกฟังก์ชัน _clients() เพื่อดึงรายชื่อตัวเชื่อม Client ทั้งหมดมา แล้วหยิบตัวแรกสุดออกมาใช้งาน
def get_genai_client():
    clients = _clients()
    return clients[0] if clients else None

# เช็กสถานะว่า Gemini LLM พร้อมใช้งานหรือไม่
def llm_online() -> bool:
    return get_genai_client() is not None

# ============================================================
# PUBLIC API — main.py เรียกใช้แค่สองฟังก์ชันนี้

"""แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand

    Args:
        text (str): ข้อความภาษาไทยดิบจากผู้เล่น (เช่น 'เดินไปตู้เสบียง', 'ตรวจดูบันทึก')
        state (GameState): สถานะเกมปัจจุบัน ใช้เป็นบริบทช่วยในการแกะคำกำกวม

    Returns:
        ParsedCommand: โครงสร้างคำสั่งที่สกัดแล้ว (action, target, items, confidence)
"""
def interpret(text: str, state: GameState) -> ParsedCommand:
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
    for client in clients:
        try:
            # ส่งคำร้องขอไปยัง Gemini API โดยบังคับ Structured Output Schema ตาม ParsedCommand
            response = client.models.generate_content(
                model = DEFAULT_MODEL,
                contents = prompt_content,
                config = types.GenerateContentConfig(
                    system_instruction = SYSTEM_INTERPRET_PROMPT,
                    response_mime_type = "application/json",
                    response_schema = ParsedCommand,
                    temperature = 0.0 #ตั้งค่าความเพ้อเจ้อ,
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
    error_type = NeuralQuotaExceeded if _is_quota_error(last_error) else NeuralUnavailable
    raise error_type(
        f"เรียก Gemini API ล้มเหลว: {last_error}") from last_error
