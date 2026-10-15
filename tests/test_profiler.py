"""
tests/test_profiler.py — ทดสอบระบบ Behavior Profiler, Dynamic Adaptation, และ Research Telemetry
"""

from fastapi.testclient import TestClient

from app import main
from app.schemas import ActionType, Decision, GameState, ParsedCommand
from app.profiler.schemas import PlayerArchetype
from app.profiler.tracker import BehaviorTracker
from app.profiler.adaptation import DynamicAdaptationEngine
from app.profiler.telemetry import save_session_telemetry

client = TestClient(main.app)


def test_behavior_tracker_records_turns_and_calculates_metrics():
    """ทดสอบว่า BehaviorTracker บันทึกเทิร์นและคำนวณ Metrics เชิงพฤติกรรมถูกต้อง"""
    tracker = BehaviorTracker(session_id="test_sess_01")
    state = GameState(current_location="lounge_car", discovered_evidence=["clue_pocket_watch"])

    # เทิร์นที่ 1: ตรวจดูของ (ผ่าน)
    parsed1 = ParsedCommand(action=ActionType.EXAMINE, target="second_teacup", raw_text="ตรวจดูถ้วยชา")
    dec1 = Decision(allowed=True, message="พบถ้วยชา")
    prof1 = tracker.record_turn("ตรวจดูถ้วยชา", parsed1, dec1, state)

    assert prof1.total_turns == 1
    assert prof1.allowed_turns == 1
    assert prof1.denied_turns == 0
    assert prof1.rule_violation_rate == 0.0

    # เทิร์นที่ 2: สั่งผิดกฎ (ไม่ผ่าน)
    parsed2 = ParsedCommand(action=ActionType.EXAMINE, target="burnt_folder_c", raw_text="ตรวจแฟ้ม")
    dec2 = Decision(allowed=False, message="อยู่คนละตู้", violated_rule_id="R005_SAME_LOCATION")
    prof2 = tracker.record_turn("ตรวจแฟ้ม", parsed2, dec2, state)

    assert prof2.total_turns == 2
    assert prof2.allowed_turns == 1
    assert prof2.denied_turns == 1
    assert prof2.rule_violation_rate == 0.5


def test_archetype_classification_forensic_analyst():
    """ผู้เล่นที่เน้นตรวจดูวัตถุ ละเอียดรอบคอบ และไม่ละเมิดกฎ ควรได้ Forensic Analyst"""
    tracker = BehaviorTracker(session_id="test_forensic")
    state = GameState(current_location="first_class_car", discovered_evidence=["clue_1", "clue_2", "clue_3"])

    for i in range(5):
        parsed = ParsedCommand(action=ActionType.EXAMINE, target=f"obj_{i}", raw_text="ตรวจดู")
        dec = Decision(allowed=True, message="พบเบาะแส")
        profile = tracker.record_turn("ตรวจดู", parsed, dec, state)

    assert profile.primary_archetype == PlayerArchetype.FORENSIC_ANALYST
    assert profile.dimensions.methodical_score > 0.5
    assert profile.dimensions.caution_score == 1.0


def test_archetype_classification_psychological_interrogator():
    """ผู้เล่นที่เน้นสอบปากคำคน ควรได้ Psychological Interrogator"""
    tracker = BehaviorTracker(session_id="test_interrogator")
    state = GameState(
        current_location="lounge_car",
        interrogated_suspects=["gideon_hart", "dr_liora_venn", "vincent_gray"],
    )

    for sus in ["gideon_hart", "dr_liora_venn", "vincent_gray", "gideon_hart"]:
        parsed = ParsedCommand(action=ActionType.INTERROGATE, target=sus, raw_text="คุย")
        dec = Decision(allowed=True, message="คำให้การ")
        profile = tracker.record_turn("คุย", parsed, dec, state)

    assert profile.primary_archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR
    assert profile.dimensions.social_score > 0.5


def test_archetype_classification_maverick_trailblazer():
    """ผู้เล่นที่ทำผิดกฎบ่อย หรือสั่งทำลายสิ่งของ ควรได้ Maverick Trailblazer"""
    tracker = BehaviorTracker(session_id="test_maverick")
    state = GameState(burned_objects=["secret_folder"])

    for _ in range(4):
        parsed = ParsedCommand(action=ActionType.BURN, target="item", raw_text="เผาทิ้ง")
        dec = Decision(allowed=False, message="ไม่อนุญาต", violated_rule_id="R007_ACTION_SUPPORTED")
        profile = tracker.record_turn("เผาทิ้ง", parsed, dec, state)

    assert profile.primary_archetype == PlayerArchetype.MAVERICK_TRAILBLAZER
    assert profile.rule_violation_rate == 1.0
    assert profile.dimensions.caution_score < 0.2


def test_dynamic_adaptation_suspect_reactions():
    """ตรวจสอบว่าน้ำเสียงของ NPC ปรับเปลี่ยนตาม Archetype ของผู้เล่น"""
    adaptation = DynamicAdaptationEngine()
    state = GameState(current_location="lounge_car", discovered_evidence=["clue_obsidian_cufflink"])

    # สร้าง Profile จำลอง
    forensic_tracker = BehaviorTracker(session_id="demo_forensic")
    for _ in range(3):
        forensic_tracker.record_turn(
            "ตรวจ",
            ParsedCommand(action=ActionType.EXAMINE, target="obj", raw_text="ตรวจ"),
            Decision(allowed=True, message="ok"),
            state,
        )
    profile = forensic_tracker.record_turn(
        "ตรวจ",
        ParsedCommand(action=ActionType.EXAMINE, target="obj2", raw_text="ตรวจ"),
        Decision(allowed=True, message="ok"),
        state,
    )

    base_decision = Decision(allowed=True, message="ผมไม่มีส่วนเกี่ยวข้องกับเรื่องนี้ครับ")
    cmd = ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", raw_text="ถามกิเดียน")

    adapted, note = adaptation.adapt(base_decision, cmd, state, profile)

    assert "กิเดียนชะงักไปเล็กน้อย" in adapted.message
    assert "ผมไม่มีส่วนเกี่ยวข้องกับเรื่องนี้ครับ" in adapted.message
    assert note is not None


def test_dynamic_adaptation_scaffolding_nudge():
    """ตรวจว่าระบบแทรกคำแนะนำช่วยเหลือ (Scaffolding Nudge) เมื่อทำผิดกฎหรือติดขัด"""
    adaptation = DynamicAdaptationEngine()
    state = GameState(current_location="lounge_car")

    tracker = BehaviorTracker(session_id="demo_scaffold")
    profile = tracker.record_turn(
        "ไป",
        ParsedCommand(action=ActionType.MOVE, target="lounge_car", raw_text="ไป"),
        Decision(allowed=True, message="ok"),
        state,
    )

    # ละเมิดกฎ R007_ACTION_SUPPORTED (เช่น พยายามหยิบของที่ห้ามหยิบ)
    denied_decision = Decision(
        allowed=False,
        message="วัตถุนี้ไม่ได้ประกาศว่ารองรับ take",
        violated_rule_id="R007_ACTION_SUPPORTED",
    )
    cmd = ParsedCommand(action=ActionType.TAKE, target="clock", raw_text="หยิบนาฬิกา")

    adapted, note = adaptation.adapt(denied_decision, cmd, state, profile)

    assert "💡 *[ข้อสังเกตของผู้สืบสวน]*" in adapted.message
    assert "ไม่ควรเคลื่อนย้ายหรือแตะต้อง" in adapted.message
    assert "Scaffolding nudge triggered" in note


def test_telemetry_json_and_csv_export(tmp_path):
    """ทดสอบการบันทึก Session Telemetry ทั้งไฟล์ JSON และ CSV"""
    tracker = BehaviorTracker(session_id="test_export_99")
    state = GameState(ending_id="ending_true_justice")

    tracker.record_turn(
        "ตรวจ",
        ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="ตรวจ"),
        Decision(allowed=True, message="ok"),
        state,
    )
    summary = tracker.get_summary(state)

    saved_path = save_session_telemetry(summary)
    assert saved_path.exists()

    # ตรวจสอบว่ามีไฟล์ CSV ถูกสร้างขึ้นใน telemetry dir
    csv_file = saved_path.parent / "research_dataset.csv"
    assert csv_file.exists()


def test_api_profiler_and_research_endpoints():
    """ทดสอบ Endpoints /profiler/profile, /research/telemetry, /research/export ผ่าน API"""
    res_prof = client.get("/profiler/profile?session_id=default")
    assert res_prof.status_code == 200
    data_prof = res_prof.json()
    assert "primary_archetype" in data_prof
    assert "scores" in data_prof
    assert "dimensions" in data_prof

    res_tele = client.get("/research/telemetry?session_id=default")
    assert res_tele.status_code == 200
    data_tele = res_tele.json()
    assert "session_id" in data_tele
    assert "turns" in data_tele

    res_exp = client.get("/research/export")
    assert res_exp.status_code == 200
    data_exp = res_exp.json()
    assert "count" in data_exp
    assert "sessions" in data_exp


def test_true_ending_marks_case_solved():
    """ตรวจว่า true_ending บันทึก is_solved เป็น True เสมอ"""
    tracker = BehaviorTracker(session_id="test_true_ending")
    state = GameState(ending_id="true_ending")
    summary = tracker.get_summary(state)
    assert summary.case_solved_successfully is True


def test_interrogate_different_topics_not_looping():
    """สอบถามคนเดิมคนละหัวข้อต้องไม่ถือว่าวนลูป แต่ซ้ำหัวข้อเดิมถือว่าลูป"""
    tracker = BehaviorTracker(session_id="test_topics")
    state = GameState(current_location="lounge_car")

    # ถามเรื่อง account ครั้งที่ 1
    p1 = tracker.record_turn(
        "ถามกิเดียนเรื่องบัญชี",
        ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", topic="account", raw_text="..."),
        Decision(allowed=True, message="..."),
        state,
    )
    assert p1.looping_count == 0

    # ถามเรื่อง message ครั้งที่ 2 (คนเดิม แต่คนละหัวข้อ -> ไม่ใช่ลูป)
    p2 = tracker.record_turn(
        "ถามกิเดียนเรื่องข้อความ",
        ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", topic="message", raw_text="..."),
        Decision(allowed=True, message="..."),
        state,
    )
    assert p2.looping_count == 0
    assert tracker.turns[-1].is_looping is False

    # ถามเรื่อง message ครั้งที่ 3 ซ้ำเดิม -> เป็นลูป
    p3 = tracker.record_turn(
        "ถามกิเดียนเรื่องข้อความซ้ำ",
        ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", topic="message", raw_text="..."),
        Decision(allowed=True, message="..."),
        state,
    )
    assert p3.looping_count == 1
    assert tracker.turns[-1].is_looping is True


def test_r012_scaffolding_nudge_triggered():
    """ตรวจว่าเมื่อผิดกฎ R012_ACCUSE_ENDING_REQUIREMENTS จะได้รับคำแนะนำกระดานคดี 4 เสา"""
    adaptation = DynamicAdaptationEngine()
    state = GameState(current_location="lounge_car")
    tracker = BehaviorTracker(session_id="test_r012")
    profile = tracker.record_turn(
        "เริ่ม",
        ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="..."),
        Decision(allowed=True, message="ok"),
        state,
    )

    denied = Decision(
        allowed=False,
        message="ยังไม่พร้อมกล่าวหา",
        violated_rule_id="R012_ACCUSE_ENDING_REQUIREMENTS",
    )
    cmd = ParsedCommand(action=ActionType.ACCUSE, target="gideon_hart", raw_text="กล่าวหากิเดียน")
    adapted, note = adaptation.adapt(denied, cmd, state, profile)

    assert "การชี้ตัวคนร้ายต้องการเสาหลักฐาน" in adapted.message
    assert note is not None


def test_move_loop_pattern_detection():
    """การเดินสำรวจตู้ 1 -> 2 -> 3 -> 2 ไม่ถือเป็นลูป แต่ 1 -> 2 -> 1 -> 2 ถือเป็นลูป"""
    tracker = BehaviorTracker(session_id="test_move_loop")
    state = GameState(current_location="lounge_car")
    dec = Decision(allowed=True, message="เดินสำเร็จ")

    # 1 -> 2 -> 3 -> 2 (เดินตู้ใหม่เรื่อยๆ แล้วย้อน 1 ก้าว)
    tracker.record_turn("เดินตู้ 1", ParsedCommand(action=ActionType.MOVE, target="car_1", raw_text="..."), dec, state)
    tracker.record_turn("เดินตู้ 2", ParsedCommand(action=ActionType.MOVE, target="car_2", raw_text="..."), dec, state)
    tracker.record_turn("เดินตู้ 3", ParsedCommand(action=ActionType.MOVE, target="car_3", raw_text="..."), dec, state)
    p_return = tracker.record_turn("เดินตู้ 2", ParsedCommand(action=ActionType.MOVE, target="car_2", raw_text="..."), dec, state)

    # ต้องไม่ถูกตัดสินว่าติดลูป เพราะเป็นการเดินย้อนทางธรรมดา ไม่ใช่ A -> B -> A -> B
    assert tracker.turns[-1].is_looping is False
    assert p_return.looping_count == 0

    # ตอนนี้ทดสอบ A -> B -> A -> B จริงๆ
    tracker_ab = BehaviorTracker(session_id="test_ab_loop")
    tracker_ab.record_turn("เดินตู้ A", ParsedCommand(action=ActionType.MOVE, target="car_a", raw_text="..."), dec, state)
    tracker_ab.record_turn("เดินตู้ B", ParsedCommand(action=ActionType.MOVE, target="car_b", raw_text="..."), dec, state)
    tracker_ab.record_turn("เดินตู้ A", ParsedCommand(action=ActionType.MOVE, target="car_a", raw_text="..."), dec, state)
    p_ab = tracker_ab.record_turn("เดินตู้ B", ParsedCommand(action=ActionType.MOVE, target="car_b", raw_text="..."), dec, state)

    # 4 ตาเดินสลับ A -> B -> A -> B ต้องตรวจพบลูป
    assert tracker_ab.turns[-1].is_looping is True
    assert p_ab.looping_count == 1
    assert p_ab.consecutive_looping_count == 1


def test_consecutive_looping_scaffolding():
    """Scaffolding สำหรับ Looping ต้องเด้งเฉพาะเมื่อติดลูปติดต่อกัน 2 ครั้ง ไม่เด้งเมื่อลูปครั้งเดียวหลังผ่านไปนาน"""
    adaptation = DynamicAdaptationEngine()
    state = GameState(current_location="lounge_car")
    dec = Decision(allowed=True, message="ok")
    tracker = BehaviorTracker(session_id="test_consec_scaffold")

    # เทิร์นที่ 1: ตรวจของ
    tracker.record_turn("ตรวจ", ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="..."), dec, state)
    # เทิร์นที่ 2: ตรวจของซ้ำ (ลูปครั้งที่ 1, consec=1)
    p2 = tracker.record_turn("ตรวจซ้ำ", ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="..."), dec, state)
    assert p2.looping_count == 1
    assert p2.consecutive_looping_count == 1

    cmd_loop = ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="ตรวจซ้ำ")
    adapted, note = adaptation.adapt(dec, cmd_loop, state, p2, is_looping=True)
    # ลูปแค่ 1 ครั้งติด ยังไม่ควรเด้งเตือน
    assert note is None
    assert "คุณตรวจสอบบริเวณนี้อย่างถี่ถ้วนแล้ว" not in adapted.message

    # เทิร์นที่ 3: ตรวจของซ้ำอีก (ลูปครั้งที่ 2 ติดต่อกัน, consec=2)
    p3 = tracker.record_turn("ตรวจซ้ำอีก", ParsedCommand(action=ActionType.EXAMINE, target="watch", raw_text="..."), dec, state)
    assert p3.looping_count == 2
    assert p3.consecutive_looping_count == 2

    adapted_consec, note_consec = adaptation.adapt(dec, cmd_loop, state, p3, is_looping=True)
    # ลูปติดต่อกัน 2 ครั้ง ต้องเด้งเตือนทันที
    assert note_consec is not None
    assert "Scaffolding nudge triggered" in note_consec
    assert "คุณตรวจสอบบริเวณนี้อย่างถี่ถ้วนแล้ว" in adapted_consec.message


