"""
app/game_setup.py — ตัวเริ่มต้นสถานะเกมใหม่ (Game State Initializer)

สร้าง GameState เริ่มต้นจากข้อมูลโลก (story.json หรือ cases/case_XX.json) โดยคัดลอกแบบ Deep Copy
เพื่อไม่ให้เกิดการแชร์ mutable list หรือ dict ระหว่างหลาย session
"""
import json
from pathlib import Path
from typing import Optional

from app.schemas import GameState


def new_game_state(world: Optional[dict] = None, case_id: Optional[str] = None) -> GameState:
    """สร้าง GameState เริ่มต้นชุดใหม่จาก initial_state ในคดีที่ระบุ"""
    cid = case_id or "case_01_gideon"
    if world is None:
        try:
            from app.cases import load_case_data
            world = load_case_data(cid)
        except Exception:
            world = json.loads(
                (Path(__file__).resolve().parents[1] / "data/story.json").read_text(encoding="utf-8")
            )
    init_dict = dict(world.get("initial_state", {}))
    init_dict["case_id"] = cid
    return GameState.model_validate(init_dict).model_copy(deep=True)
