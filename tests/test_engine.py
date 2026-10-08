"""
test_engine.py — ทดสอบ Symbolic Engine ของ Nocturne Express 1938 โดยไม่ต้องใช้ LLM

รันด้วย:  python -m pytest -v
"""

import json
from pathlib import Path

import pytest

STEPS = [tuple(x) for x in json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "walkthrough.json")
    .read_text(encoding="utf-8"))["steps"]]
from app.schemas import ActionType, ParsedCommand, GameState
from app.symbolic.engine import SymbolicEngine, apply_changes


@pytest.fixture
def engine():
    return SymbolicEngine()


def cmd(action, target=None, instrument=None, text="(mock)"):
    return ParsedCommand(action=action, target=target, instrument=instrument,
                         raw_text=text, confidence=1.0)


# เส้นทางเฉลยอยู่ใน data/walkthrough.json ที่เดียว
FULL_WALKTHROUGH = [(ActionType(a), t) for a, t in STEPS]


def run_walkthrough(engine, steps=None) -> GameState:
    s = GameState()
    for action, target in (steps or FULL_WALKTHROUGH):
        d = engine.decide(cmd(action, target), s)
        assert d.allowed, f"{action.value} {target} ควรผ่านแต่ถูกปฏิเสธ: {d.message}"
        s = apply_changes(s, d.state_changes)
    return s


@pytest.fixture
def solved(engine):
    return run_walkthrough(engine)


# ---------- กลุ่ม A: คำสั่งที่ถูกกฎ ----------

def test_move_to_open_car(engine):
    assert engine.decide(cmd(ActionType.MOVE, "first_class_car"), GameState()).allowed


def test_examine_evidence_in_same_car(engine):
    s = apply_changes(GameState(), {"move_to": "first_class_car"})
    d = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), s)
    assert d.allowed
    assert d.state_changes["discovered_evidence_add"] == "pocket_watch"


def test_examining_never_unlocks(engine):
    """ตรวจคือดู ปลดล็อกต้องมาจากคำสั่งปลดล็อกเท่านั้น"""
    s = apply_changes(GameState(), {"move_to": "first_class_car"})
    d = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), s)
    assert "unlocked_add" not in d.state_changes
    assert apply_changes(s, d.state_changes).unlocked_objects == []


def test_full_walkthrough_is_completable(engine):
    """เส้นทางหลักของเกมต้องเดินได้จนจบ — กันกฎที่ขัดกันเองจนเกมตัน"""
    s = run_walkthrough(engine)
    assert len(s.discovered_evidence) >= 5
    assert s.ending_id == "true_ending"


def test_cannot_examine_evidence_in_another_car(engine):
    # ยืนอยู่ตู้เลานจ์ (lounge_car) แต่จะตรวจนาฬิกาพกในตู้ 4 (first_class_car) ต้องไม่ผ่าน
    d = engine.decide(cmd(ActionType.EXAMINE, "pocket_watch"), GameState())
    assert not d.allowed
    assert d.violated_rule_id == "R005_SAME_LOCATION"


def test_unknown_object_denied(engine):
    d = engine.decide(cmd(ActionType.EXAMINE, "non_existent_item"), GameState())
    assert not d.allowed
    assert d.violated_rule_id == "R002_TARGET_EXISTS"


def test_time_limit_enforced(engine):
    s = GameState(elapsed_seconds=5460)  # เกิน 5400 วินาที
    d = engine.decide(cmd(ActionType.MOVE, "first_class_car"), s)
    assert not d.allowed
    assert d.violated_rule_id == "R014_TIME_LIMIT"


# ---------- ชั้น Deduction ----------

def ev(engine, *ids) -> GameState:
    """สถานะที่ผู้เล่นเจอหลักฐานตามที่ระบุแล้ว ใช้ทดสอบตรรกะโดยไม่ต้องเดินทั้งเกม"""
    return GameState(current_location="lounge_car", discovered_evidence=list(ids))


def test_every_deduction_needs_all_of_its_evidence(engine):
    """ข้อสรุปทุกข้อต้องมีหลักฐานครบถึงจะสรุปได้ ขาดชิ้นเดียวก็ไม่ได้

    นี่คือ R-SYS-03 ในสเปก ถ้าข้อไหนสรุปได้ทั้งที่ขาดหลักฐาน แปลว่ามีทางลัดที่ไม่ควรมี
    """
    for did, cond in engine.world["deductions"].items():
        need = cond.get("requires_evidence", [])
        if not need:
            continue
        assert did not in engine.deductions(ev(engine, *need[:-1])),             f"{did} สรุปได้ทั้งที่ขาดหลักฐาน {need[-1]}"


def test_true_murder_window_is_what_unlocks_the_case(engine):
    """นาฬิกาไฟฟ้าอย่างเดียวไม่พอ ต้องมีนาฬิกาพกกับคำประเมินของแพทย์

    แก่นของคดีคือการลวงเวลาตาย ถ้าสรุปเวลาจริงได้จากนาฬิกาไฟฟ้าอย่างเดียว คดีก็ไม่มีปริศนา
    """
    D01 = "D01_TRUE_MURDER_WINDOW"
    assert D01 not in engine.deductions(ev(engine, "wall_clock"))
    assert D01 not in engine.deductions(ev(engine, "pocket_watch"))
    assert D01 in engine.deductions(ev(engine, "pocket_watch", "liora_time_estimate"))


def test_opportunity_needs_at_least_two_independent_links(engine):
    """R-OPP-01 การไม่มีที่อยู่บวกร่องรอยเดียวยังไม่พอ ต้องสองทางขึ้นไป"""
    D07 = "D07_GIDEON_IN_CASSIAN_ROOM"
    one_link = ev(engine, "gideon_no_early_alibi",
                  "obsidian_cufflink", "gideon_missing_button")
    assert D07 not in engine.deductions(one_link)

    two_links = ev(engine, "gideon_no_early_alibi",
                   "obsidian_cufflink", "gideon_missing_button",
                   "wax_seal_imprint", "gideon_signet_ring")
    assert D07 in engine.deductions(two_links)


def test_no_alibi_alone_never_proves_opportunity(engine):
    """ไม่มีที่อยู่ ไม่ใช่หลักฐานว่าอยู่ในห้อง"""
    assert "D07_GIDEON_IN_CASSIAN_ROOM" not in engine.deductions(ev(engine, "gideon_no_early_alibi"))


# ---------- ฉากจบ ----------

ALL_EVIDENCE = None


def all_evidence(engine):
    return [o for o, v in engine.world["objects"].items() if v["type"] == "evidence"]


def test_walkthrough_reaches_the_true_ending(engine):
    s = run_walkthrough(engine)
    assert s.ending_id == "true_ending"


GIDEON_MINIMUM = ["dossier_missing_file_c", "burnt_folder_c", "file_c_initials"]
GIDEON_TRUE = GIDEON_MINIMUM + [
    "judicial_transfer_order",  # แรงจูงใจ D03 บังคับในฉากจบแท้
    "pocket_watch", "liora_time_estimate", "gideon_no_early_alibi",
    "red_soot", "gideon_sleeve_soot", "obsidian_cufflink", "gideon_missing_button",
    "wax_seal_imprint", "gideon_signet_ring",
]


def test_gideon_true_ending_matches_diagram_without_clearing_others(engine):
    state = ev(engine, *GIDEON_TRUE)
    held = engine.deductions(state)
    assert "D08_VINCENT_CLEARED" not in held
    assert "D09_LIORA_CLEARED" not in held
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), state)
    assert d.allowed
    assert d.state_changes["ending"] == "true_ending"


@pytest.mark.parametrize("missing", GIDEON_TRUE[len(GIDEON_MINIMUM):])
def test_gideon_missing_any_true_ending_clue_gets_incomplete(engine, missing):
    state = ev(engine, *[e for e in GIDEON_TRUE if e != missing])
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), state)
    assert d.allowed
    assert d.state_changes["ending"] == "cold_justice"


def test_file_c_link_alone_can_reach_incomplete_ending(engine):
    state = ev(engine, *GIDEON_MINIMUM)
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), state)
    assert d.allowed
    assert d.state_changes["ending"] == "cold_justice"
    assert "Ending C" in d.message


@pytest.mark.parametrize("missing", GIDEON_MINIMUM)
def test_gideon_missing_file_c_link_cannot_accuse(engine, missing):
    state = ev(engine, *[e for e in GIDEON_TRUE if e != missing])
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), state)
    assert not d.allowed
    assert d.state_changes == {}


def test_cold_justice_is_right_suspect_but_unproven_case(engine):
    """สามเสาครบแต่หลักฐานสนับสนุนไม่ครบ ต้องได้ฉากจบขมขื่น ไม่ใช่ฉากจบแท้"""
    short = ev(engine, *[x for x in all_evidence(engine) if x != "gideon_sleeve_soot"])
    assert engine.ending_for("gideon_hart", short)["id"] == "cold_justice"


def test_scapegoat_only_happens_before_the_timeline_is_broken(engine):
    """กล่าวหาวินเซนต์เป็นความผิดพลาดเชิงเหตุผล ไม่ใช่ผลของหลักฐาน

    ถ้าผู้เล่นหักล้างเวลาตายลวงตาไปแล้ว ความผิดพลาดนั้นหายไป
    การกล่าวหาเขาจึงไม่ควรได้ฉากจบเดิมอีก
    """
    ignorant = ev(engine, "vincent_blood", "wire_cutters", "cut_copper_wire", "wall_clock")
    assert engine.ending_for("vincent_gray", ignorant)["id"] == "the_scapegoat"

    knows_time = ev(engine, "vincent_blood", "wire_cutters",
                    "pocket_watch", "liora_time_estimate")
    assert engine.ending_for("vincent_gray", knows_time)["id"] != "the_scapegoat"


def test_paranoia_trap_treats_a_secret_as_if_it_were_proof(engine):
    ignorant = ev(engine, "secret_file", "liora_time_hesitation", "wall_clock")
    assert engine.ending_for("dr_liora_venn", ignorant)["id"] == "the_paranoia_trap"


def test_only_the_culprit_can_ever_close_the_case(engine):
    """ต่อให้เจอหลักฐานครบทุกชิ้น คนที่ไม่ใช่คนร้ายก็ต้องไม่ได้ฉากจบที่นับว่าคลี่คลาย

    SUSPICION != PROOF ตามที่สเปกเขียนไว้
    """
    full = ev(engine, *all_evidence(engine))
    for sid in engine.world["suspects"]:
        solved = engine.ending_for(sid, full).get("solved", False)
        assert solved == (sid == "gideon_hart"), f"{sid} ให้ผล solved={solved}"


def test_incomplete_proof_can_still_reach_cold_justice(engine):
    state = ev(engine, *[x for x in all_evidence(engine) if x != "gideon_sleeve_soot"])
    d = engine.decide(cmd(ActionType.ACCUSE, "gideon_hart"), state)
    assert d.allowed
    assert d.state_changes["ending"] == "cold_justice"
    assert not next(x for x in d.reasoning_chain if x.rule_id == "R013_ACCUSE_FOUR_PILLARS").passed


# ---------- กันทางตัน ----------

@pytest.mark.parametrize("mask", range(8))
def test_vincent_needs_all_three_clues(engine, mask):
    clues = ["cut_copper_wire", "wire_cutters", "vincent_blood"]
    state = ev(engine, *[clue for i, clue in enumerate(clues) if mask & (1 << i)])
    decision = engine.decide(cmd(ActionType.ACCUSE, "vincent_gray"), state)
    assert decision.allowed == (mask == 7)
    if mask == 7:
        assert decision.state_changes["ending"] == "the_scapegoat"
    else:
        assert decision.violated_rule_id == "R012_ACCUSE_ENDING_REQUIREMENTS"
        assert decision.state_changes == {}
        assert engine.decide(cmd(ActionType.MOVE, "first_class_car"), state).allowed


@pytest.mark.parametrize("mask", range(4))
def test_liora_needs_project_link_and_hesitation(engine, mask):
    clues = ["secret_file", "liora_time_hesitation"]
    state = ev(engine, *[clue for i, clue in enumerate(clues) if mask & (1 << i)])
    d = engine.decide(cmd(ActionType.ACCUSE, "dr_liora_venn"), state)
    assert d.allowed == (mask == 3)
    if d.allowed:
        assert d.state_changes["ending"] == "the_paranoia_trap"


@pytest.mark.parametrize("identified", [
    ["vincent_blackout_confession"],
    ["power_panel", "fuse_box", "cut_copper_wire", "tool_marks", "wire_cutters"],
])
def test_liora_cannot_be_accused_after_identifying_the_saboteur(engine, identified):
    state = ev(engine, "secret_file", "liora_time_hesitation", *identified)
    d = engine.decide(cmd(ActionType.ACCUSE, "dr_liora_venn"), state)
    assert not d.allowed
    assert d.violated_rule_id == "R012_ACCUSE_ENDING_REQUIREMENTS"


@pytest.mark.parametrize("suspect", ["vincent_gray", "dr_liora_venn", "gideon_hart"])
def test_empty_case_cannot_use_fallback_ending_to_accuse(engine, suspect):
    d = engine.decide(cmd(ActionType.ACCUSE, suspect), GameState())
    assert not d.allowed
    assert d.state_changes == {}


def test_liora_new_clues_are_obtainable_and_shown(engine):
    state = GameState(current_location="first_class_car")
    file = engine.decide(cmd(ActionType.EXAMINE, "secret_file"), state)
    assert "Project Nocturne" in file.message
    state = apply_changes(state, file.state_changes)
    interview = engine.decide(cmd(ActionType.INTERROGATE, "dr_liora_venn"), state)
    assert "ลังเล" in interview.message
    state = apply_changes(state, interview.state_changes)
    assert engine.decide(cmd(ActionType.ACCUSE, "dr_liora_venn"), state).allowed

def test_every_car_tells_you_where_else_you_can_go(engine):
    """เกมนี้พิมพ์ล้วนไม่มีปุ่ม ถ้าคำบรรยายไม่บอกชื่อตู้อื่น ผู้เล่นจะออกจากตู้แรกไม่เป็น"""
    locs = engine.world["locations"]
    for lid, loc in locs.items():
        desc = loc["description"]
        named = [x for x in locs if x != lid
                 and any(part in desc for part in locs[x]["name_th"].split(":")[0].split("(")[0].strip().split())]
        assert named, f"คำบรรยายของ {lid} ไม่ได้เอ่ยถึงตู้อื่นเลย"


def test_physical_clues_describe_observations_without_identifying_owner(engine):
    for key in ('second_teacup', 'wax_seal_imprint', 'obsidian_cufflink', 'red_soot'):
        description = engine.world['objects'][key]['description']
        assert 'Gideon' not in description
        assert 'กิเดียน' not in description
    # Matching observations remain available; the player makes the connection.
    for key in ('wax_seal_imprint', 'gideon_signet_ring'):
        assert 'สี่เหลี่ยมข้าวหลามตัด' in engine.world['objects'][key]['description']


def test_a_player_who_only_reads_the_game_can_finish(engine):
    """จำลองผู้เล่นที่ทำตามข้อความในเกมอย่างเดียว ไม่ใช้เฉลย ต้องเก็บหลักฐานได้ครบ

    เทสนี้จับทางตันที่เทสอื่นไม่เห็น เพราะมันไม่รู้ล่วงหน้าว่าอะไรอยู่ที่ไหน
    รู้เท่าที่เกมบอกเท่านั้น เหมือนคนเล่นจริง
    """
    w = engine.world
    s = GameState(**w.get("initial_state", {}))
    cars = {v["name_th"]: k for k, v in w["locations"].items()}
    cars.update({v["name_th"].split(":")[0].strip(): k for k, v in w["locations"].items()})
    seen = w["briefing"] + w["locations"][s.current_location]["description"]
    examined, progress = set(), True
    while progress:
        progress = False
        for th, loc in cars.items():
            if th not in seen and loc != s.current_location:
                continue
            if s.current_location != loc:
                d = engine.decide(cmd(ActionType.MOVE, loc), s)
                if not d.allowed:
                    continue
                s = apply_changes(s, d.state_changes)
            for _ in range(2):
                # ของที่ "มองเห็นตอนนี้" ต้องดูจากตู้ที่ยืนอยู่ ไม่ใช่ข้อความสะสมทั้งเกม
                view = engine.look_around(loc, s)
                seen += view
                for oid, o in w["objects"].items():
                    if o.get("name_th") in view and oid not in examined:
                        examined.add(oid)
                        d = engine.decide(cmd(ActionType.EXAMINE, oid), s)
                        if d.allowed and oid not in s.discovered_evidence:
                            s = apply_changes(s, d.state_changes)
                            seen += o["description"]
                            progress = True
                for sid, sus in w["suspects"].items():
                    if sus["name_th"] in view and sid not in s.interrogated_suspects:
                        d = engine.decide(cmd(ActionType.INTERROGATE, sid), s)
                        if d.allowed:
                            s = apply_changes(s, d.state_changes)
                            seen += sus.get("testimony", "") + " ".join(
                                w["objects"][x]["description"] for x in sus.get("grants_evidence", []))
                            progress = True

    missing = [o for o, v in w["objects"].items()
               if v["type"] == "evidence" and o not in s.discovered_evidence]
    assert not missing, f"ผู้เล่นที่อ่านข้อความอย่างเดียวหาไม่เจอ: {missing}"
    assert engine.ending_for("gideon_hart", s)["id"] == "true_ending"
    assert s.elapsed_seconds <= w["time_limit_seconds"], "เก็บครบแต่หมดเวลาก่อน"


# ---------- ตู้ 2 สายสืบสวนเรื่องไฟดับ ----------

def test_locomotive_is_on_the_map_but_cannot_be_entered(engine):
    """หัวรถจักรเห็นบนแผนที่ได้ แต่ไม่ใช่พื้นที่เล่น และไม่มีวันเข้าได้"""
    restricted = [k for k, v in engine.world["locations"].items() if v.get("restricted")]
    assert restricted, "ฉากนี้ควรมีพื้นที่หวงห้ามอย่างน้อยหนึ่งที่"
    for lid in restricted:
        d = engine.decide(cmd(ActionType.MOVE, lid), GameState())
        assert not d.allowed
        assert d.violated_rule_id == "R006_LOCATION_RESTRICTED"
        assert not any(o.get("location") == lid for o in engine.world["objects"].values()), \
            f"{lid} เข้าไม่ได้ แต่มีหลักฐานวางอยู่ ผู้เล่นจะเก็บไม่ได้"
        assert not any(s["location"] == lid for s in engine.world["suspects"].values())


def test_blackout_sabotage_chain_needs_the_whole_panel(engine):
    """ต้องตรวจทั้งแผงไฟ กล่องฟิวส์ และสายที่ถูกตัด ถึงจะสรุปว่าเป็นวินาศกรรม

    ถ้าดูอย่างเดียวแล้วสรุปได้ ผู้เล่นก็ไม่ต้องสืบ แค่เดินเข้าไปมองก็จบ
    """
    D12 = "D12_BLACKOUT_WAS_SABOTAGE"
    need = engine.world["deductions"][D12]["requires_evidence"]
    for drop in need:
        partial = ev(engine, *[x for x in need if x != drop])
        assert D12 not in engine.deductions(partial), f"ขาด {drop} แล้วยังสรุปได้"
    assert D12 in engine.deductions(ev(engine, *need))


def test_matching_the_tool_marks_is_what_names_the_saboteur(engine):
    """รอยเครื่องมือกับคีมต้องมาคู่กัน มีอย่างเดียวยังชี้ตัวใครไม่ได้"""
    D13 = "D13_VINCENT_CUT_THE_POWER"
    base = ["power_panel", "fuse_box", "cut_copper_wire"]
    assert D13 not in engine.deductions(ev(engine, *base, "tool_marks"))
    assert D13 not in engine.deductions(ev(engine, *base, "wire_cutters"))
    assert D13 in engine.deductions(ev(engine, *base, "tool_marks", "wire_cutters"))


def test_cutting_the_power_is_never_the_same_as_killing(engine):
    """แก่นของเรื่อง พิสูจน์ได้ว่าวินเซนต์ตัดไฟ ต้องไม่ทำให้เขากลายเป็นฆาตกร

    VINCENT CUT THE POWER = TRUE  ไม่ได้แปลว่า  VINCENT KILLED CASSIAN = TRUE
    """
    proved = ev(engine, "power_panel", "fuse_box", "cut_copper_wire",
                "tool_marks", "wire_cutters", "maintenance_log")
    assert "D13_VINCENT_CUT_THE_POWER" in engine.deductions(proved)
    assert not engine.ending_for("vincent_gray", proved).get("solved", False)
    assert not all(engine.pillar_status("vincent_gray", proved).values())


def test_blackout_window_does_not_overlap_the_murder_window(engine):
    """บันทึกเวลาของระบบไฟกับเวลาตายจริง ต้องประกอบกันเป็นข้อสรุปว่าสองช่วงนี้คนละช่วง"""
    D15 = "D15_BLACKOUT_IS_NOT_MURDER_TIME"
    only_blackout = ev(engine, "maintenance_log")
    only_murder = ev(engine, "pocket_watch", "liora_time_estimate")
    both = ev(engine, "maintenance_log", "pocket_watch", "liora_time_estimate")
    assert D15 not in engine.deductions(only_blackout)
    assert D15 not in engine.deductions(only_murder)
    assert D15 in engine.deductions(both)


def test_vincent_can_be_cleared_without_his_own_confession(engine):
    """ต้องล้างข้อสงสัยวินเซนต์ได้ด้วยหลักฐาน ไม่ใช่ต้องรอให้เขายอมพูดเท่านั้น

    ถ้าทางเดียวคือคำสารภาพ ผู้เล่นก็ต้องเชื่อคำพูดของผู้ต้องสงสัย ซึ่งขัดกับ PLAYER_CLAIM != FACT
    """
    D08 = "D08_VINCENT_CLEARED"
    by_evidence = ev(engine, "pocket_watch", "liora_time_estimate", "maintenance_log")
    by_confession = ev(engine, "pocket_watch", "liora_time_estimate", "vincent_blackout_confession")
    assert D08 in engine.deductions(by_evidence)
    assert D08 in engine.deductions(by_confession)


# ---------- บทพูดของผู้ต้องสงสัย ----------

def test_every_suspect_has_testimony(engine):
    """สอบปากคำแล้วต้องได้ยินอะไรสักอย่าง ไม่ใช่ข้อความสำรอง

    เคยพลาดมาแล้ว ผู้ต้องสงสัยไม่มีฟิลด์ testimony เลยสักคน
    ระบบแอบเติมหลักฐานเข้ากระเป๋าเงียบๆ แล้วตอบว่าไม่ได้ข้อมูลเพิ่ม
    ผู้เล่นได้ของโดยไม่รู้ว่าได้มายังไง
    """
    for sid, sus in engine.world["suspects"].items():
        assert sus.get("testimony", "").strip(), f"{sid} ไม่มีบทพูด"
        d = engine.decide(cmd(ActionType.INTERROGATE, sid),
                          GameState(current_location=sus["location"]))
        assert d.allowed
        assert "ไม่ได้ข้อมูลเพิ่ม" not in d.message, f"{sid} ยังตกไปใช้ข้อความสำรอง"


def test_testimony_does_not_name_evidence_the_speaker_does_not_give(engine):
    """บทพูดต้องไม่เอ่ยชื่อหลักฐานชิ้นอื่นที่ผู้เล่นอาจยังไม่เจอ

    ถ้าเอ่ยได้ ตัวละครก็เฉลยเกมแทนผู้เล่น ซึ่งเป็นสิ่งที่ R-SYS-01 ห้ามไว้
    บอกใบ้เป็นทิศทางได้ แต่ห้ามเรียกชื่อเต็มของหลักฐาน
    """
    w = engine.world
    for sid, sus in w["suspects"].items():
        mine = set(sus.get("grants_evidence", []))
        for oid, o in w["objects"].items():
            if oid in mine or o["type"] != "evidence":
                continue
            assert o["name_th"] not in sus["testimony"], \
                f"บทพูดของ {sid} เอ่ยชื่อ {oid} ซึ่งไม่ใช่หลักฐานที่เขาให้"


# ---------- กลุ่ม E: การกระทำที่ฉากนี้ไม่รองรับ ----------

UNSUPPORTED = [ActionType.TAKE, ActionType.USE, ActionType.UNLOCK, ActionType.BURN]


def _an_object_in(engine, loc):
    return next(oid for oid, o in engine.world["objects"].items()
                if o.get("location") == loc)


@pytest.mark.parametrize("action", UNSUPPORTED)
def test_nothing_in_this_scene_can_be_taken_used_unlocked_or_burned(engine, action):
    """สี่คำสั่งนี้เคยไม่มีกฎเฉพาะคุมเลย หยิบอะไรก็ได้ เผาอะไรก็ได้

    ฉากนี้ทุกอย่างเป็นหลักฐานที่ดูได้อย่างเดียว การปฏิเสธจึงต้องมาจากกฎที่ตรวจจริง
    ไม่ใช่ปล่อยผ่านเงียบๆ แล้วขึ้นข้อความว่าทำสำเร็จ
    """
    here = GameState().current_location
    s = GameState()
    d = engine.decide(cmd(action, _an_object_in(engine, here)), s)
    assert not d.allowed, f"{action.value} ไม่ควรผ่าน"
    assert d.violated_rule_id == "R007_ACTION_SUPPORTED"


def test_burning_something_in_another_car_is_caught_by_the_location_rule(engine):
    """burn เคยหลุดจากกฎตำแหน่ง เผาของข้ามขบวนได้โดยไม่ต้องเดินไปหา"""
    far = next(oid for oid, o in engine.world["objects"].items()
               if o.get("location") and o["location"] != GameState().current_location)
    d = engine.decide(cmd(ActionType.BURN, far), GameState())
    assert d.violated_rule_id == "R005_SAME_LOCATION"


def test_a_scene_can_re_enable_an_action_without_touching_the_code(engine):
    """กฎอ่านจากข้อมูล ฉากไหนอยากมีของที่หยิบได้ก็เติม supports ลง story.json พอ

    ข้อนี้คือหลักฐานว่ากฎ R007 ไม่ได้ปิดตายสี่คำสั่งนั้นไว้ในโค้ด
    """
    here = GameState().current_location
    oid = _an_object_in(engine, here)
    engine.world["objects"][oid]["supports"] = ["take"]
    try:
        assert engine.decide(cmd(ActionType.TAKE, oid), GameState()).allowed
        assert not engine.decide(cmd(ActionType.BURN, oid), GameState()).allowed
    finally:
        del engine.world["objects"][oid]["supports"]


def test_the_last_minute_of_the_clock_is_playable_and_the_next_one_is_not(engine):
    """ขอบเขตเวลาต้องอยู่ที่เดียวกับที่นาฬิกาบนหน้าเว็บขึ้น 00:00

    เดิมกฎใช้ > ผู้เล่นจึงสั่งได้อีกหนึ่งครั้งหลังนาฬิกาขึ้นหมดเวลาไปแล้ว
    """
    limit = engine.world["time_limit_seconds"]
    last = GameState(elapsed_seconds=limit - 1)
    assert engine.decide(cmd(ActionType.EXAMINE, last.current_location), last).allowed
    assert not engine.is_out_of_time(last)

    over = GameState(elapsed_seconds=limit)
    d = engine.decide(cmd(ActionType.EXAMINE, over.current_location), over)
    assert d.violated_rule_id == "R014_TIME_LIMIT"
    assert engine.is_out_of_time(over)


def test_running_out_of_time_hands_back_the_ending_that_closes_the_case(engine):
    """กฎหมดเวลาต้องส่งฉากจบกลับมาให้บันทึกลงสถานะ ไม่ใช่คืนแค่ข้อความ"""
    over = GameState(elapsed_seconds=engine.world["time_limit_seconds"])
    d = engine.decide(cmd(ActionType.EXAMINE, over.current_location), over)
    eid = d.state_changes.get("ending")
    assert eid, "หมดเวลาแล้วต้องมี ending ใน state_changes"
    assert engine.world["endings"][eid].get("on_timeout"), "ต้องเป็นฉากจบแบบหมดเวลา"


def test_time_runs_out_before_the_command_is_even_inspected(engine):
    """หมดเวลาแล้วพิมพ์อะไรมั่วๆ ก็ต้องได้ยินว่าหมดเวลา ไม่ใช่ว่าไม่รู้จักของชิ้นนั้น

    กฎที่ถามว่า 'ยังเล่นได้อยู่ไหม' ต้องมาก่อนกฎที่ถามว่า 'คำสั่งนี้สมเหตุสมผลไหม'
    """
    over = GameState(elapsed_seconds=engine.world["time_limit_seconds"])
    d = engine.decide(cmd(ActionType.EXAMINE, "ของที่ไม่มีอยู่จริง"), over)
    assert d.violated_rule_id == "R014_TIME_LIMIT"
