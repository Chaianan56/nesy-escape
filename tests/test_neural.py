"""
test_neural.py — ไฟล์ยูนิตเทสสำหรับทดสอบ Neuro AI Layer

หน้าที่:
- ทดสอบการทำ Text Preprocessing (Language Detection, Normalization, Tokenization)
- ทดสอบฟังก์ชัน interpret และ decide_autonomously
"""

import pytest
from app.schemas import ActionType, GameState
from app.neural import interpret, decide_autonomously, preprocess_text


def test_preprocessor_thai():
    """ทดสอบ Preprocessor กับภาษาไทย"""
    feat = preprocess_text("  ลอง ตรวจสอบ   terminal_01  ")
    assert feat.language in ("th", "mixed")
    assert feat.normalized_text == "ลอง ตรวจสอบ terminal_01"
    assert len(feat.tokens) > 0


def test_preprocessor_english():
    """ทดสอบ Preprocessor กับภาษาอังกฤษ"""
    feat = preprocess_text("examine terminal_01")
    assert feat.language in ("en", "mixed")
    assert "terminal_01" in feat.normalized_text


def test_interpret_basic():
    """ทดสอบฟังก์ชัน interpret ว่าสกัด Action และ Target ออกมาถูกต้องหรือไม่"""
    state = GameState()
    cmd = interpret("examine terminal_01", state)
    
    assert cmd.action == ActionType.EXAMINE
    assert cmd.target == "terminal_01"
    assert cmd.confidence > 0.0


def test_decide_autonomously_basic():
    """ทดสอบฟังก์ชัน decide_autonomously ในโหมด Baseline"""
    state = GameState()
    cmd = interpret("examine terminal_01", state)
    decision = decide_autonomously("examine terminal_01", state, cmd)
    
    assert decision.allowed is True
    assert len(decision.reasoning_chain) > 0
