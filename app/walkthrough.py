"""
walkthrough.py — เส้นทางเฉลยของฉาก อ่านจาก data/walkthrough.json

มีไว้ให้เทสพิสูจน์ว่าเกมเดินได้จนจบจริง กันกฎที่ขัดกันเองจนเกมตัน
"""

import json
from pathlib import Path
from typing import List, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
STEPS: List[Tuple[str, str]] = [
    tuple(s) for s in json.loads((DATA_DIR / "walkthrough.json").read_text(encoding="utf-8"))["steps"]
]
