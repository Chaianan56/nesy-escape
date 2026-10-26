"""
app/game_setup.py — ตัวเริ่มต้นสถานะเกมใหม่ (Game State Initializer)

สร้าง GameState เริ่มต้นจากข้อมูลโลก (story.json) โดยคัดลอกแบบ Deep Copy
เพื่อไม่ให้เกิดการแชร์ mutable list หรือ dict ระหว่างหลาย session
"""
import json
from pathlib import Path
from typing import Optional

from app.schemas import GameState


def new_game_state(world: Optional[dict] = None) -> GameState:
    """สร้าง GameState เริ่มต้นชุดใหม่จาก initial_state ใน story.json"""
    if world is None:
        world = json.loads(
            (Path(__file__).resolve().parents[1] / "data/story.json").read_text(encoding="utf-8")
        )
    return GameState.model_validate(world.get("initial_state", {})).model_copy(deep=True)
