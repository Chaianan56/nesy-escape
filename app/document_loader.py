"""
app/document_loader.py — ตัวโหลดเอกสารและบันทึกข้อความ Markdown ภายในเกม

ทำหน้าที่อ่านไฟล์เอกสารและพยานหลักฐานลายลักษณ์อักษรจาก data/documents/
เพื่อส่งให้ระบบแสดงผลแก่ผู้เล่นผ่านสมุดบันทึกหรือบทสนทนา
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"


def load_in_game_document(doc_filename: str) -> str:
    """
    อ่านไฟล์เอกสาร Markdown จาก data/documents/<doc_filename>

    พารามิเตอร์:
        doc_filename: ชื่อไฟล์เอกสารที่ต้องการอ่าน

    คืนค่า:
        เนื้อหาข้อความในเอกสาร หรือข้อความแจ้งเตือน fallback หากไม่พบไฟล์
    """
    file_path = BASE_DIR / doc_filename
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return f"[ไม่พบเอกสาร: {doc_filename}]"
