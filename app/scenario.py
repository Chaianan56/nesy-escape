"""
scenario.py — ตัวช่วยสร้าง GameState ณ จุดใดจุดหนึ่งของเส้นทางเฉลย

เส้นทางเฉลยเก็บอยู่ใน data/walkthrough.json ที่เดียว ใช้ร่วมกันสองที่:
  - tests/test_engine.py  ใช้เป็นเทสกันกฎขัดกันเองจนเกมตัน
  - run_experiment.py     ใช้เป็นจุดตั้งต้นของคำสั่งแต่ละข้อในชุดทดสอบ

สถานะถูกสร้างโดย "เดินผ่าน engine จริง" ไม่ใช่เขียน GameState ด้วยมือ
เพื่อกันไม่ให้สถานะตั้งต้นของการทดลองหลุดจากกฎที่ใช้ตัดสินจริง
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine, apply_changes

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
WALKTHROUGH = json.loads((DATA_DIR / "walkthrough.json").read_text(encoding="utf-8"))

STEPS: List[Tuple[str, str]] = [tuple(s) for s in WALKTHROUGH["steps"]]
CHECKPOINTS: dict = WALKTHROUGH["checkpoints"]


@lru_cache(maxsize=None)
def state_after(n_steps: int) -> GameState:
    """สถานะหลังเดินตามเส้นทางเฉลยไปแล้ว n ขั้น"""
    engine = SymbolicEngine()
    state = GameState()
    for action, target in STEPS[:n_steps]:
        cmd = ParsedCommand(action=ActionType(action), target=target,
                            raw_text=f"{action} {target}", confidence=1.0)
        decision = engine.decide(cmd, state)
        if not decision.allowed:
            raise RuntimeError(
                f"เส้นทางเฉลยขั้นที่ {STEPS.index((action, target)) + 1} "
                f"({action} {target}) ถูกปฏิเสธ: {decision.message}"
            )
        state = apply_changes(state, decision.state_changes)
    return state


def checkpoint(name: str) -> GameState:
    """สถานะ ณ checkpoint ที่ตั้งชื่อไว้ใน walkthrough.json"""
    if name not in CHECKPOINTS:
        raise KeyError(f"ไม่รู้จัก checkpoint '{name}' — มีให้เลือก: {list(CHECKPOINTS)}")
    return state_after(CHECKPOINTS[name])
