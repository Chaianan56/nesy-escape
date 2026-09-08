"""
test_invariants.py — ตรวจตัวตรวจสถานะของ Nocturne Express 1938

รันด้วย: python -m pytest -v
"""

import pytest

from app.invariants import is_reachable, violations
from app.scenario import STEPS
from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine, apply_changes


@pytest.fixture(scope="module")
def engine():
    return SymbolicEngine()


@pytest.fixture(scope="module")
def world(engine):
    return engine.world


def test_initial_state_is_reachable(world):
    assert is_reachable(GameState(), world)


def test_every_state_along_the_official_walkthrough_is_reachable(engine, world):
    """ไม่มี false positive — สถานะที่ผ่านกฎมาแล้วต้องไม่ถูกจับว่าผิด"""
    s = GameState()
    for i, (action, target) in enumerate(STEPS, 1):
        d = engine.decide(
            ParsedCommand(action=ActionType(action), target=target, raw_text="", confidence=1.0), s
        )
        assert d.allowed, f"ขั้นที่ {i} ({action} {target}) ถูกปฏิเสธ: {d.message}"
        s = apply_changes(s, d.state_changes)
        bad = violations(s, world)
        assert not bad, f"หลังขั้นที่ {i} ({action} {target}) ตัวตรวจฟ้องผิด: {bad}"


def test_catches_invalid_location(world):
    s = GameState(current_location="non_existent_car")
    assert not is_reachable(s, world)
    assert any("ไม่มีอยู่จริง" in v for v in violations(s, world))


def test_catches_invalid_ending(world):
    s = GameState(ending_id="non_existent_ending")
    assert not is_reachable(s, world)
    assert any("ไม่มีอยู่ในฉาก" in v for v in violations(s, world))
