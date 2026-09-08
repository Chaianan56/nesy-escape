"""
app/neural/__init__.py — Neuro AI Layer

ชั้นนี้มีหน้าที่เดียวคือแปลข้อความภาษาไทยของผู้เล่นให้เป็น ParsedCommand
ไม่ตัดสินว่าคำสั่งถูกกฎหรือไม่ การตัดสินเป็นของ app/symbolic/engine.py เท่านั้น
"""

from app.neural.gemini_client import interpret

__all__ = ["interpret"]
