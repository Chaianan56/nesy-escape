"""
test_invariants.py — ตรวจตัวตรวจสถานะ ไม่ต้องใช้ LLM

ตัววัดหลักของการทดลองที่สองคือ "โหมดไหนพาไปสู่สถานะที่เป็นไปไม่ได้ตามกฎ"
ถ้าตัวตรวจนี้ผิด ตัวเลขทั้งการทดลองก็ผิดตาม จึงต้องพิสูจน์สองทางให้ครบ
  1. ทุกสถานะที่เกิดจากการเดินผ่าน engine จริง ต้องผ่านเสมอ (ไม่มี false positive)
  2. สถานะที่จงใจทำให้ผิด ต้องถูกจับได้ทุกแบบ (ไม่มี false negative)
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
    """ไม่มี false positive — สถานะที่ผ่านกฎมาแล้วต้องไม่ถูกจับว่าผิด

    ถ้าเทสนี้ตก แปลว่าตัวตรวจเข้มกว่ากฎจริง ตัวเลขในการทดลองจะฟ้องโหมด B
    ทั้งที่โหมด B เดินตามกฎทุกก้าว
    """
    s = GameState()
    for i, (action, target) in enumerate(STEPS, 1):
        d = engine.decide(
            ParsedCommand(action=ActionType(action), target=target, raw_text="", confidence=1.0), s
        )
        assert d.allowed
        s = apply_changes(s, d.state_changes)
        bad = violations(s, world)
        assert not bad, f"หลังขั้นที่ {i} ({action} {target}) ตัวตรวจฟ้องผิด: {bad}"


# ---------- ไม่มี false negative: จงใจทำให้ผิดแล้วต้องจับได้ ----------

def test_catches_holding_something_that_cannot_be_taken(world):
    s = GameState(inventory=["fuse_panel"])          # แผงฟิวส์ takeable=false
    assert not is_reachable(s, world)
    assert any("หยิบไม่ได้" in v for v in violations(s, world))


def test_allows_holding_an_item_granted_by_a_suspect(world):
    """crew_key มี takeable=false แต่ได้มาจากการสอบปากคำ จึงถือได้"""
    s = GameState(inventory=["crew_key"], interrogated_suspects=["mara_voss"])
    assert is_reachable(s, world)


def test_catches_evidence_found_without_its_prerequisite(world):
    s = GameState(discovered_evidence=["latch_scratches"])   # ต้องมี crime_scene_record ก่อน
    assert any("เงื่อนไขนำหน้า" in v for v in violations(s, world))


def test_catches_evidence_taken_out_of_a_container_never_opened(world):
    """ไล่จากข้อมูลฉากเอง ไม่ฝัง id ไว้ในเทส ฉากเปลี่ยนแล้วยังใช้ได้"""
    hidden = [(o, v) for o, v in world["objects"].items() if v.get("hidden_in")]
    assert hidden, "ฉากนี้ควรมีของที่ซ่อนอยู่อย่างน้อยหนึ่งชิ้น"
    for oid, obj in hidden:
        s = GameState(discovered_evidence=list(obj.get("requires_evidence", [])) + [oid])
        assert any("ที่ซ่อน" in v for v in violations(s, world)),             f"{oid} ถูกพบทั้งที่ยังไม่เปิด {obj['hidden_in']} แต่ตัวตรวจไม่ฟ้อง"


def test_catches_testimony_obtained_without_interrogating(world):
    s = GameState(discovered_evidence=["elias_testimony"])
    assert any("สอบปากคำ" in v for v in violations(s, world))


def test_catches_interrogation_without_grounds(world):
    s = GameState(interrogated_suspects=["gideon_hart"])      # ต้องมี wine_receipt_2316 ก่อน
    assert any("ยังไม่พบ" in v for v in violations(s, world))


def test_catches_interrogation_out_of_order(world):
    """elias_venn ต้องสอบหลัง liora_venn"""
    s = GameState(
        discovered_evidence=["elias_ticket", "manifest_altered"],
        interrogated_suspects=["elias_venn"],
    )
    assert any("ยังไม่ได้สอบ" in v for v in violations(s, world))


def test_catches_being_inside_a_locked_car_without_the_key(world):
    s = GameState(current_location="electrical_compartment",
                  visited_locations=["passenger_car", "electrical_compartment"])
    assert any("ล็อกอยู่" in v for v in violations(s, world))


def test_catches_playing_past_the_time_limit(world):
    """โหมด A ตัดสินเองจึงเล่นเลยกรอบเวลาไปได้ ถ้าไม่ตรวจก็จะไม่มีใครจับ"""
    limit = world["time_limit_seconds"]
    assert is_reachable(GameState(elapsed_seconds=limit), world)
    s = GameState(elapsed_seconds=limit + 60)
    assert any("เกินกรอบ" in v for v in violations(s, world))


def test_invariant_coverage_is_documented(engine, world):
    """ตรวจว่ากฎที่ตรวจจากสถานะได้ ถูกตรวจครบทุกข้อ

    ข้ออ้างหลักของการทดลองที่สองคือโหมด B ละเมิดศูนย์ครั้ง
    ซึ่งจะกลวงทันทีถ้าตัวตรวจหละหลวม เทสนี้ล็อกไว้ว่ากฎข้อไหน
    ตรวจจากสถานะไม่ได้บ้าง และเพราะอะไร ถ้ามีคนเพิ่มกฎใหม่จะได้ทบทวน
    """
    # กฎเหล่านี้ตรวจจากสถานะไม่ได้โดยธรรมชาติ เพราะ action นั้นไม่ทิ้งร่องรอยลงสถานะ
    UNCHECKABLE = {
        "R000_KNOWN_ACTION",        # เป็นเรื่องของคำสั่ง ไม่ใช่ของสถานะ
        "R005_SAME_LOCATION",       # ต้องรู้ตำแหน่ง ณ ตอนที่ทำ สถานะสุดท้ายบอกไม่ได้
        "R011_INSTRUMENT_OWNED",    # use ไม่เปลี่ยนสถานะ
        "R012_NO_ACCUSE_COERCED",   # accuse ไม่เปลี่ยนสถานะ
        "R013_ACCUSE_FOUR_PILLARS", # accuse ไม่เปลี่ยนสถานะ ยกเว้นบันทึก ending_id
        "R015_GAME_NOT_OVER",       # เป็นเรื่องของลำดับ สถานะเดียวบอกไม่ได้ว่าสั่งหลังปิดคดีไปแล้วหรือเปล่า
    }
    all_rules = {r["id"] for r in engine.rules}
    checkable = all_rules - UNCHECKABLE
    assert len(checkable) == 12, "จำนวนกฎที่ตรวจได้เปลี่ยนไป ต้องทบทวนตัวตรวจ"

    # แต่ละกฎที่ตรวจได้ ต้องมีสถานะตัวอย่างที่ทำให้ตัวตรวจฟ้องจริง
    probes = {
        "R001_TARGET_EXISTS":      GameState(discovered_evidence=["ของปลอม"]),
        "R002_LOCATION_EXISTS":    GameState(visited_locations=["ห้องปลอม"]),
        "R003_SUSPECT_EXISTS":     GameState(interrogated_suspects=["คนปลอม"]),
        "R004_LOCATION_ACCESS":    GameState(current_location="electrical_compartment"),
        "R006_TAKEABLE":           GameState(inventory=["fuse_panel"]),
        "R007_CONTAINER_OPENED":   GameState(discovered_evidence=["removed_fuse"]),
        "R008_EVIDENCE_PREREQ":    GameState(discovered_evidence=["latch_scratches"]),
        "R009_TESTIMONY_PREREQ":   GameState(discovered_evidence=["elias_testimony"]),
        "R010_INTERROGATE_PREREQ": GameState(interrogated_suspects=["gideon_hart"]),
        "R014_TIME_LIMIT":         GameState(elapsed_seconds=99999),
        "R016_NOT_DESTROYED":      GameState(burned_objects=["narin_report_1931"],
                                             inventory=["narin_report_1931"]),
        "R017_BURNABLE":           GameState(burned_objects=["cassian_notebook"]),
    }
    assert set(probes) == checkable, "มีกฎที่ตรวจได้แต่ไม่มีตัวอย่างพิสูจน์"
    for rule_id, state in probes.items():
        assert violations(state, world), f"{rule_id} ตรวจได้แต่ตัวตรวจไม่ฟ้อง"


def test_catches_made_up_ids(world):
    s = GameState(inventory=["ปืนพก"], discovered_evidence=["engine_room_key"])
    bad = violations(s, world)
    assert sum("ไม่มีอยู่จริง" in v for v in bad) == 2


def test_reports_every_problem_not_just_the_first(world):
    """การทดลองต้องนับจำนวนการละเมิด ไม่ใช่แค่รู้ว่ามีหรือไม่มี"""
    s = GameState(inventory=["fuse_panel"], discovered_evidence=["latch_scratches"],
                  interrogated_suspects=["gideon_hart"])
    assert len(violations(s, world)) >= 3
