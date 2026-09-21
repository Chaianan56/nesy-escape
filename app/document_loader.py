"""
app/document_loader.py — Document Loader for In-game Markdown Files
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"

# อ่านไฟล์ Markdown จาก data/documents/<doc_filename>
def load_in_game_document(doc_filename: str) -> str:
    file_path = BASE_DIR / doc_filename
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return f"[ไม่พบเอกสาร: {doc_filename}]"
