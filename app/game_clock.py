"""
app/game_clock.py — ตัวประสานเวลานาฬิกาคดี (Game Clock Synchronizer)

ทำหน้าที่คำนวณและซิงโครไนซ์เวลาจริง (Wall-clock Time) ที่ผ่านไปในเกม
เวลาเป็นส่วนหนึ่งของ Interaction Layer ไม่ใช่ตรรกะภายใน Symbolic Engine
"""
import time

from app.schemas import GameState


def sync_clock(state: GameState) -> GameState:
    """ซิงค์เวลาที่ผ่านไป (elapsed_seconds) กับเวลาจริงในระบบ

    หากคดีจบลงแล้ว หรือยังไม่ได้เริ่ม จะไม่คำนวณเวลาเพิ่ม
    """
    if state.ending_id or state.started_at is None:
        return state
    elapsed = max(state.elapsed_seconds, int(time.time() - state.started_at), 0)
    return state.model_copy(update={"elapsed_seconds": elapsed})
