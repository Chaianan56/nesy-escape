"""
gemini_client.py — โค้ดหลักส่วนประสานงาน Gemini API (Neuro AI Layer)

หน้าที่:
- นำข้อความดิบผ่าน TextPreprocessor (PyThaiNLP + spaCy) เพื่อสกัด Features
- ส่งข้อความที่ผ่าน Normalization พร้อม Features ไปให้ Gemini API (Google GenAI SDK)
- นำผลลัพธ์จาก Gemini มาแปลงกลับให้อยู่ในรูป Pydantic Models (ParsedCommand / Decision)
- มีระบบ Fallback ในกรณีที่ไม่ได้ใส่ API Key หรือ API ล้มเหลว เพื่อไม่ให้ระบบล่ม
"""

import os
import logging
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
from app.schemas import (
    ParsedCommand,
    Decision,
    GameState,
    ActionType,
    ReasoningStep,
)
# นำเข้า Prompt คำสั่งจาก prompts.py
from app.neural.prompts import (
    SYSTEM_INTERPRET_PROMPT,
    SYSTEM_BASELINE_DECISION_PROMPT,
)
# นำเข้า Preprocessor สำหรับล้างข้อความและสกัด Features
from app.neural.preprocessor import preprocess_text, PreprocessedFeature

# โหลดตัวแปรสภาพแวดล้อมจาก .env
load_dotenv()

logger = logging.getLogger(__name__)

# ดึงตั้งค่าจาก .env (ใช้รุ่นโมเดล gemini-3.6-flash)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

_client_instance: Optional[object] = None


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


def interpret(text: str, state: GameState) -> ParsedCommand:
    """แกะความหมายจากข้อความภาษาธรรมชาติของผู้เล่น ให้กลายเป็น ParsedCommand

    Args:
        text (str): ข้อความป้อนเข้าจากผู้เล่น เช่น "ลองใช้ keycard_A เปิด cabinet_03 ดูหน่อย"
        state (GameState): สถานะเกมปัจจุบัน

    Returns:
        ParsedCommand: คำสั่งที่ผ่านการตีความเชิงโครงสร้างแล้ว
    """
    # Step 1: Preprocessing & Feature Extraction
    features: PreprocessedFeature = preprocess_text(text)
    clean_text = features.normalized_text

    client = get_genai_client()

    # Step 2: ถ้ามี Gemini API Key ให้เรียกใช้ Gemini จริง
    if client is not None:
        try:
            prompt_content = (
                f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
                f"ข้อความหลังล้าง (Normalized Text): '{clean_text}'\n"
                f"ภาษาที่ตรวจพบ (Language): {features.language}\n"
                f"คำสำคัญ (Keywords): {', '.join(features.keywords)}"
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
        except Exception as e:
            logger.warning(f"เรียก Gemini API ล้มเหลว (ใช้นโยบาย Fallback): {e}")

    # Step 3: Fallback Heuristic Parser (กรณีไม่มี API Key หรือ API ขัดข้อง)
    parts = clean_text.strip().split()
    try:
        action = ActionType(parts[0].lower())
    except (ValueError, IndexError):
        action = ActionType.UNKNOWN

    return ParsedCommand(
        action=action,
        target=parts[1] if len(parts) > 1 else None,
        instrument=parts[2] if len(parts) > 2 else None,
        raw_text=text,
        confidence=0.95,
    )


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
                    response_schema=Decision,
                    temperature=0.2,
                ),
            )
            if response.text:
                return Decision.model_validate_json(response.text)
        except Exception as e:
            logger.warning(f"เรียก Gemini API ในโหมด Baseline ล้มเหลว: {e}")

    # Fallback กรณีไม่มี API Key
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
