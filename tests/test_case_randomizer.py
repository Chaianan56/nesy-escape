"""
tests/test_case_randomizer.py — การทดสอบระบบคดีคู่ขนานและตัวสุ่มคดี (Parallel Cases & Randomizer Tests)
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ActionType, GameState, ParsedCommand
from app.cases import (
    AVAILABLE_CASES,
    CASE_METADATA,
    get_available_cases,
    get_engine,
    get_random_case_id,
    load_case_data,
    should_randomize,
)
from app.symbolic.validation import validate_world
from app.symbolic.engine import CHECKERS

client = TestClient(app)


def test_all_cases_are_valid():
    """ตรวจสอบว่าไฟล์คดีทุกคดี (case_01, case_02, case_03) ผ่าน validate_world 100%"""
    rules = json.loads(Path("data/rules.json").read_text(encoding="utf-8"))["rules"]
    for cid in AVAILABLE_CASES:
        world = load_case_data(cid)
        validate_world(rules, world, CHECKERS, {a.value for a in ActionType})
        assert world["scene_id"], f"Case {cid} must have a scene_id"
        assert world["suspects"], f"Case {cid} must have suspects"
        assert world["endings"], f"Case {cid} must have endings"
        assert "true_ending" in world["endings"], f"Case {cid} must have a true_ending"


def test_cases_metadata_and_endpoint():
    """ตรวจสอบรายการคดีและ Endpoint /cases"""
    cases = get_available_cases()
    assert len(cases) == 3
    case_ids = {c["id"] for c in cases}
    assert case_ids == {"case_01_gideon", "case_02_vincent", "case_03_liora"}

    res = client.get("/cases")
    assert res.status_code == 200
    data = res.json()
    assert "cases" in data
    assert len(data["cases"]) == 3


def test_random_case_id_logic():
    """ตรวจสอบฟังก์ชันสุ่มคดี และการ exclude คดีที่ไม่ต้องการ"""
    for _ in range(20):
        cid = get_random_case_id()
        assert cid in AVAILABLE_CASES

    # ทดสอบการไม่เลือกคดีเดิม
    for target in AVAILABLE_CASES:
        for _ in range(10):
            cid = get_random_case_id(exclude=target)
            assert cid != target
            assert cid in AVAILABLE_CASES


def test_new_game_switch_to_case_02():
    """ทดสอบเริ่มคดีใหม่โดยเจาะจง Case 02 (Vincent Gray)"""
    client.get("/scene")  # สร้าง session ก่อน
    res = client.post("/new-game", json={"case_id": "case_02_vincent"})
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "case_02_vincent"
    assert data["new_state"]["case_id"] == "case_02_vincent"

    # ตรวจสอบว่า /scene สะท้อนข้อมูลของ Case 02
    scene_res = client.get("/scene")
    assert scene_res.status_code == 200
    scene_data = scene_res.json()
    assert scene_data["case_id"] == "case_02_vincent"
    assert "The Strike in the Dark" in scene_data["title"]


def test_new_game_switch_to_case_03():
    """ทดสอบเริ่มคดีใหม่โดยเจาะจง Case 03 (Dr. Liora Venn)"""
    client.get("/scene")
    res = client.post("/new-game", json={"case_id": "case_03_liora"})
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == "case_03_liora"
    assert data["new_state"]["case_id"] == "case_03_liora"

    scene_res = client.get("/scene")
    assert scene_res.status_code == 200
    scene_data = scene_res.json()
    assert scene_data["case_id"] == "case_03_liora"
    assert "The Doctor's Retribution" in scene_data["title"]


def test_new_game_random_flag():
    """ทดสอบการส่ง random: true ใน /new-game"""
    client.get("/scene")
    res = client.post("/new-game", json={"random": True})
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] in AVAILABLE_CASES
    assert data["new_state"]["case_id"] == data["case_id"]


def test_case_02_solve_true_ending():
    """ทดสอบการไขคดี Case 02 สำเร็จด้วย True Ending เมื่อมัดตัววินเซนต์ เกรย์"""
    eng = get_engine("case_02_vincent")
    state = GameState(case_id="case_02_vincent", discovered_evidence=[
        "wall_clock", "liora_time_estimate",      # -> D01_BLACKOUT_MURDER_WINDOW (timeline)
        "wire_cutters", "cut_copper_wire", "tool_marks",  # -> D02_VINCENT_SABOTAGE (opportunity)
        "mara_job_note", "vincent_theft_motive",  # -> D03_VINCENT_MOTIVE (motive)
        "vincent_blood", "letter_opener",         # -> D04_VINCENT_BLOOD_SPATTER (opportunity)
        "gideon_blackout_alibi",                  # -> D05_GIDEON_ALIBI_SOLID (corroboration)
    ])

    # ตรวจสอบว่า 4 เสาของวินเซนต์ครบถ้วน
    pillars = eng.pillar_status("vincent_gray", state)
    for p in ("timeline", "motive", "opportunity", "corroboration"):
        assert len(pillars.get(p, [])) > 0, f"Pillar {p} must be complete"

    # กล่าวหาวินเซนต์
    cmd = ParsedCommand(action=ActionType.ACCUSE, target="vincent_gray", raw_text="กล่าวหาวินเซนต์")
    decision = eng.decide(cmd, state)
    assert decision.allowed is True
    assert decision.state_changes.get("ending") == "true_ending"


def test_case_02_scapegoat_ending():
    """ทดสอบว่าใน Case 02 หากกล่าวหากิเดียนโดยมีเพียงหลักฐานแวดล้อมแต่ไม่มีหลักฐานแก้ต่าง จะได้ฉากจบ the_scapegoat"""
    eng = get_engine("case_02_vincent")
    state = GameState(case_id="case_02_vincent", discovered_evidence=[
        "burnt_folder_c",
        "file_c_initials",
    ])
    cmd = ParsedCommand(action=ActionType.ACCUSE, target="gideon_hart", raw_text="กล่าวหากิเดียน")
    decision = eng.decide(cmd, state)
    assert decision.state_changes.get("ending") == "the_scapegoat"


def test_case_03_solve_true_ending():
    """ทดสอบการไขคดี Case 03 สำเร็จด้วย True Ending เมื่อมัดตัว พญ. ลิโอรา เวนน์"""
    eng = get_engine("case_03_liora")
    state = GameState(case_id="case_03_liora", discovered_evidence=[
        "pocket_watch", "liora_time_estimate", "second_teacup",  # -> D01_POISON_DEATH_WINDOW (timeline)
        "secret_file", "dossier_missing_file_c",                # -> D02_LIORA_MOTIVE (motive)
        "tea_lozenge_trace", "liora_patient_log",               # -> D03_LIORA_POISON_TRACE (opportunity)
        "liora_patient_witness", "tunnel_schedule",             # -> D04_LIORA_ALIBI_BROKEN (corroboration)
    ])

    # ตรวจสอบว่า 4 เสาของลิโอราครบถ้วน
    pillars = eng.pillar_status("dr_liora_venn", state)
    for p in ("timeline", "motive", "opportunity", "corroboration"):
        assert len(pillars.get(p, [])) > 0, f"Pillar {p} must be complete"

    # กล่าวหาลิโอรา
    cmd = ParsedCommand(action=ActionType.ACCUSE, target="dr_liora_venn", raw_text="กล่าวหาลิโอรา")
    decision = eng.decide(cmd, state)
    assert decision.allowed is True
    assert decision.state_changes.get("ending") == "true_ending"


def test_case_03_scapegoat_ending():
    """ทดสอบว่าใน Case 03 หากกล่าวหาวินเซนต์ด้วยหลักฐานตัดไฟ จะได้ฉากจบ the_scapegoat (วินเซนต์ตกเป็นแพะ)"""
    eng = get_engine("case_03_liora")
    state = GameState(case_id="case_03_liora", discovered_evidence=[
        "cut_copper_wire",
        "wire_cutters",
        "vincent_blood",
    ])
    cmd = ParsedCommand(action=ActionType.ACCUSE, target="vincent_gray", raw_text="กล่าวหาวินเซนต์")
    decision = eng.decide(cmd, state)
    assert decision.state_changes.get("ending") == "the_scapegoat"


def test_all_cases_block_turn1_accusation():
    """ทดสอบว่าทุกคดี (Case 01, Case 02, Case 03) ปฏิเสธการกล่าวหาพล่อยๆ ในเทิร์นแรกเมื่อไม่มีหลักฐาน"""
    for case_id in AVAILABLE_CASES:
        eng = get_engine(case_id)
        empty_state = GameState(case_id=case_id, discovered_evidence=[])
        for target in ("gideon_hart", "vincent_gray", "dr_liora_venn"):
            cmd = ParsedCommand(action=ActionType.ACCUSE, target=target, raw_text=f"กล่าวหา {target}")
            dec = eng.decide(cmd, empty_state)
            assert dec.allowed is False, f"{case_id} allowed accusing {target} with zero evidence!"
            assert dec.violated_rule_id == "R012_ACCUSE_ENDING_REQUIREMENTS"

