"""
app/neural/__init__.py — จุดเริ่มต้นของแพ็กเกจ Neuro AI Layer

หน้าที่:
- ประกาศให้ Python รับรู้ว่าโฟลเดอร์ `app/neural` เป็น Python Package
- นำเข้า (Export) โมดูลสำคัญ:
  1. interpret, decide_autonomously จาก gemini_client.py
  2. preprocess_text, preprocessor จาก preprocessor.py
"""

from app.neural.gemini_client import interpret, decide_autonomously
from app.neural.preprocessor import preprocess_text, preprocessor, PreprocessedFeature

__all__ = [
    "interpret",
    "decide_autonomously",
    "preprocess_text",
    "preprocessor",
    "PreprocessedFeature",
]
