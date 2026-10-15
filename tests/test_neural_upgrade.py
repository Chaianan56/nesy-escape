"""
tests/test_neural_upgrade.py — Unit Tests สำหรับ Dynamic kNN Few-shot, Semantic Pruning, และ Symbolic Repair
"""

import json
from pathlib import Path
from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.retriever import (
    KNNExampleRetriever,
    calculate_ngram_similarity,
    get_char_ngrams,
    score_entity_candidate,
)
from app.neural.prompts import prune_entities, build_interpret_system_prompt
from app.neural.repair import repair_parsed_command

ROOT = Path(__file__).resolve().parents[1]
STORY_DATA = json.loads((ROOT / "data/story.json").read_text(encoding="utf-8"))


def test_char_ngrams_extraction():
    """สกัด N-grams จากข้อความภาษาไทยที่ไม่มีช่องว่างได้อย่างถูกต้อง"""
    text = "ตรวจนาฬิกา"
    ngrams = get_char_ngrams(text, n_range=(2, 3))
    assert "ตร" in ngrams
    assert "นา" in ngrams
    assert "ตรว" in ngrams
    assert "ฬิก" in ngrams


def test_ngram_similarity_thai_typos_and_subwords():
    """คำนวณความคล้ายคลึงระหว่างคำย่อ/คำพ้องกับชื่อเต็ม"""
    sim_exact = calculate_ngram_similarity("นาฬิกาพก", "นาฬิกาพก")
    assert sim_exact == 1.0

    # คำย่อเทียบกับชื่อเต็ม
    sim_partial = calculate_ngram_similarity("นาฬิกา", "นาฬิกาพกกลไกทองเหลือง")
    assert sim_partial > 0.35

    # คำคนละเรื่องกัน
    sim_diff = calculate_ngram_similarity("นาฬิกา", "ตู้เสบียงอาหาร")
    assert sim_diff < 0.15


def test_knn_example_retriever():
    """ทดสอบการดึงตัวอย่างที่ตรงประเด็นจาก Memory Bank"""
    retriever = KNNExampleRetriever()
    
    # 1. ค้นหาคำสั่งที่เกี่ยวกับการตรวจดู
    results_examine = retriever.retrieve("ส่องดูนาฬิกาพกหน่อย", k=3)
    assert len(results_examine) == 3
    assert any(r.get("target") == "pocket_watch" for r in results_examine)

    # 2. ค้นหาคำสั่งพ่วง (Sequence)
    results_seq = retriever.retrieve("เดินไปตู้ 4 แล้วตรวจกระเป๋า", k=3)
    assert results_seq[0].get("action") == "sequence"

    # 3. ค้นหาคำสั่งปลดล็อกรหัส
    results_unlock = retriever.retrieve("ปลดกระเป๋า 1923", k=3)
    assert any(r.get("action") == "unlock" for r in results_unlock)


def test_semantic_candidate_scorer():
    """ทดสอบ Semantic Candidate Scorer กับชื่อสิ่งของและคำพ้อง"""
    obj_watch = STORY_DATA["objects"]["pocket_watch"]
    score_watch = score_entity_candidate("ดูนาฬิกาพกที่ตกอยู่", "pocket_watch", obj_watch)
    assert score_watch >= 0.4

    obj_cufflink = STORY_DATA["objects"]["obsidian_cufflink"]
    score_cuff = score_entity_candidate("ตรวจกระดุมสีดำ", "obsidian_cufflink", obj_cufflink)
    assert score_cuff >= 0.25


def test_upgraded_prune_entities_guaranteed_and_candidates():
    """คัดกรอง Entity: วัตถุในตู้ปัจจุบันอยู่ครบ + วัตถุที่ตรงกับ N-gram ในตู้อื่นถูกดึงเข้ามา"""
    state = GameState(current_location="first_class_car")
    # first_class_car มี second_teacup, obsidian_cufflink ฯลฯ
    
    # ผู้เล่นพูดถึง wire_cutters ซึ่งอยู่ใน luggage_van_electrical (คนละตู้)
    objs, suspects, locs = prune_entities(STORY_DATA, state=state, user_text="เผาคีมตัดสายไฟทิ้ง")
    
    # วัตถุในตู้ปัจจุบันต้องอยู่ครบ (Guaranteed Co-presence)
    current_room_objs = [
        oid for oid, o in STORY_DATA["objects"].items()
        if o.get("location") == "first_class_car"
    ]
    for oid in current_room_objs:
        assert oid in objs

    # วัตถุต่างตู้ที่ถูกเอ่ยถึง (wire_cutters) ต้องถูกดึงเข้ามาเป็น candidate ด้วย
    assert "wire_cutters" in objs


def test_build_system_prompt_modes():
    """สร้าง System Prompt ได้ทั้ง 3 โหมด: Zero-shot, Static Few-shot, และ Dynamic kNN"""
    state = GameState(current_location="lounge_car")
    
    # 1. Zero-shot
    p_zero = build_interpret_system_prompt(STORY_DATA, state=state, zero_shot=True)
    assert "โหมด Zero-Shot" in p_zero
    assert "FEW-SHOT EXAMPLES" in p_zero

    # 2. Dynamic kNN
    p_knn = build_interpret_system_prompt(
        STORY_DATA, state=state, user_text="ตรวจดูนาฬิกาพก", use_knn=True, k_examples=3
    )
    assert "Dynamic Few-Shot Examples" in p_knn

    # 3. Static Few-shot
    p_static = build_interpret_system_prompt(
        STORY_DATA, state=state, user_text=None, use_knn=False
    )
    assert "กลุ่ม A: คำสั่งปกติที่ถูกกฎ" in p_static


def test_symbolic_repair_unlock_to_examine():
    """ซ่อมคำสั่ง: ผู้เล่นสั่ง 'เปิดอ่าน' วัตถุที่ไม่ได้ล็อก -> แปลงเป็น EXAMINE อัตโนมัติ"""
    # สมมติ LLM แปลง 'เปิดอ่านเอกสารลับ' เป็น UNLOCK secret_file
    raw_cmd = ParsedCommand(
        action=ActionType.UNLOCK,
        target="secret_file",
        raw_text="เปิดอ่านเอกสารลับ",
        confidence=0.8,
    )
    repaired, note = repair_parsed_command(raw_cmd, STORY_DATA, raw_text="เปิดอ่านเอกสารลับ")
    
    assert repaired.action == ActionType.EXAMINE
    assert note is not None
    assert "Adjusted UNLOCK to EXAMINE" in note


def test_symbolic_repair_interrogate_on_object():
    """ซ่อมคำสั่ง: ผู้เล่นสั่ง INTERROGATE ใส่วัตถุ -> แปลงเป็น EXAMINE"""
    raw_cmd = ParsedCommand(
        action=ActionType.INTERROGATE,
        target="pocket_watch",
        raw_text="ถามนาฬิกา",
        confidence=0.7,
    )
    repaired, note = repair_parsed_command(raw_cmd, STORY_DATA)
    assert repaired.action == ActionType.EXAMINE
    assert note is not None


def test_symbolic_repair_move_to_object_container():
    """ซ่อมคำสั่ง: ผู้เล่นสั่ง MOVE ใส่ชื่อวัตถุ -> แปลงเป็นตู้รถที่วัตถุนั้นตั้งอยู่"""
    # pocket_watch อยู่ใน first_class_car
    raw_cmd = ParsedCommand(
        action=ActionType.MOVE,
        target="pocket_watch",
        raw_text="ไปที่นาฬิกาพก",
        confidence=0.8,
    )
    repaired, note = repair_parsed_command(raw_cmd, STORY_DATA)
    assert repaired.action == ActionType.MOVE
    assert repaired.target == "first_class_car"
    assert note is not None
