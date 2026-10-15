"""
app.neural.reflexion — Closed-Loop Neuro-Symbolic Self-Correction (Reflexion Loop)

ทำหน้าที่เป็นวงจรสะท้อนกลับ (Feedback Loop) ระหว่าง Symbolic Engine และ Neural Layer:
เมื่อ Symbolic Engine ปฏิเสธคำสั่งของผู้เล่นด้วยข้อจำกัดทางความหมาย (Semantic Rule Violations)
ระบบจะสร้าง Critique แจ้ง LLM พร้อมบริบทห้องปัจจุบัน เพื่อให้ LLM ทำ Self-Correction 1 รอบ
ส่งผลให้ระบบเรียนรู้และแก้ไขข้อผิดพลาดได้แบบ Real-Time โดยไม่พึ่งพา Hardcoded Heuristics เพียงอย่างเดียว
"""

import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from app.schemas import ActionType, Decision, GameState, ParsedCommand
from app.neural.prompts import build_interpret_system_prompt
from app.neural.repair import repair_parsed_command

logger = logging.getLogger(__name__)

# รายการกฎที่เป็น Semantic Invariant ซึ่ง Neural Layer สามารถแก้ไขเจตนาได้
CORRECTABLE_RULES = {
    "R005_SAME_LOCATION",      # วัตถุอยู่นอกตู้ปัจจุบัน (ควรเป็น move ตู้รถ หรือเปลี่ยน target)
    "R007_ACTION_SUPPORTED",   # กระทำกริยาไม่รองรับ (เช่น unlock บนของที่ไม่มีล็อก, take บนของที่ห้ามหยิบ)
    "R003_ENTITY_EXISTS",      # วัตถุหรือบุคคลไม่มีอยู่จริงในทะเบียน
}


def should_attempt_reflexion(parsed: ParsedCommand, decision: Decision) -> bool:
    """ประเมินว่าความล้มเหลวของคำสั่งเข้าข่ายที่จะให้ LLM หรือ Reflexion Loop แก้ตัวใหม่หรือไม่

    จะทำงานเฉพาะเมื่อข้อความภาษาธรรมชาติของผู้เล่นบ่งชี้ว่าเจตนาจริงถูกแปลผิดพลาดทางความหมาย (Semantic Misclassification)
    แต่หากผู้เล่นตั้งใจทำสิ่งที่ผิดกฎจริงๆ (เช่น ตั้งใจพิมพ์ 'หยิบ' ของที่ห้ามหยิบ) จะปล่อยให้ Symbolic Rule ทำงานตามปกติ
    """
    if decision.allowed:
        return False

    # ไม่ทำ Reflexion กับคำสั่งจบเกม, คำสั่งที่กำกวม, หรือคำสั่งนอกเกม
    if parsed.action in (ActionType.ACCUSE, ActionType.AMBIGUOUS, ActionType.UNKNOWN):
        return False

    raw = (parsed.raw_text or "").lower()
    if not raw:
        return False

    if decision.violated_rule_id == "R005_SAME_LOCATION":
        # ผู้เล่นเอ่ยถึงการเคลื่อนที่ ("ไป", "เดิน") แต่ target ถูกตีความผิดเป็นวัตถุนอกห้อง
        return any(w in raw for w in ("ไป", "เดิน", "หา", "เข้า", "มุ่งหน้า"))

    if decision.violated_rule_id == "R007_ACTION_SUPPORTED":
        # ผู้เล่นเอ่ยถึงการสำรวจ ("ดู", "ตรวจ", "อ่าน", "ส่อง") แต่ LLM เผลอส่ง action เป็น unlock/take/use
        return any(w in raw for w in ("ดู", "ตรวจ", "อ่าน", "ส่อง", "เปิดดู", "ค้น", "เช็ค"))

    return False


def build_reflexion_critique(
    raw_text: str,
    parsed: ParsedCommand,
    decision: Decision,
    state: GameState,
    world_data: Dict[str, Any],
) -> str:
    """สร้าง Critique Prompt อธิบายสาเหตุความล้มเหลวและให้ข้อมูลบริบทที่ถูกต้องแก่ LLM"""
    curr_loc = state.current_location
    loc_data = world_data.get("locations", {}).get(curr_loc, {})
    loc_name = loc_data.get("name_th", curr_loc)

    # รวบรวมวัตถุและพยานที่อยู่ในห้องปัจจุบันจริง
    room_objects = [
        f"{oid} ({odata.get('name_th', '')})"
        for oid, odata in world_data.get("objects", {}).items()
        if odata.get("location") == curr_loc or oid in state.inventory
    ]
    room_suspects = [
        f"{sid} ({sdata.get('name_th', '')})"
        for sid, sdata in world_data.get("suspects", {}).items()
        if sdata.get("location") == curr_loc
    ]

    critique = (
        f"[Symbolic Critique / ข้อสะท้อนกลับจากระบบกฎ]\n"
        f"คำสั่งเดิมของผู้เล่น: \"{raw_text}\"\n"
        f"การตีความรอบแรกของคุณ: action='{parsed.action.value}', target='{parsed.target}'\n"
        f"ผลการตรวจสอบจาก Symbolic Engine: ❌ ไม่ผ่าน (ละเมิดกฎ {decision.violated_rule_id})\n"
        f"เหตุผล: {decision.message}\n\n"
        f"บริบทที่ถูกต้องในขณะนี้:\n"
        f"- ผู้เล่นยืนอยู่ที่: {curr_loc} ({loc_name})\n"
        f"- วัตถุ/หลักฐานที่ผู้เล่นเข้าถึงได้ในห้องนี้: {', '.join(room_objects) if room_objects else 'ไม่มี'}\n"
        f"- พยาน/ผู้ต้องสงสัยที่อยู่ในห้องนี้: {', '.join(room_suspects) if room_suspects else 'ไม่มี'}\n\n"
        f"คำแนะนำในการแก้ไข:\n"
        f"1. หากผู้เล่นต้องการไปยังสิ่งของหรือบุคคลที่อยู่นอกห้อง ให้ใช้ action='move' ไปยังตู้รถที่สิ่งนั้นตั้งอยู่\n"
        f"2. หากวัตถุไม่รองรับการกระทำเดิม (เช่น ไม่รองรับ take/unlock) ให้พิจารณาเปลี่ยนเป็น 'examine'\n"
        f"กรุณาตีความข้อความเดิมใหม่อีกครั้ง โดยส่งผลลัพธ์เป็น JSON ตาม ParsedCommand Schema"
    )
    return critique


def execute_reflexion_retry(
    raw_text: str,
    parsed: ParsedCommand,
    decision: Decision,
    state: GameState,
    world_data: Dict[str, Any],
    decide_fn: Callable[[ParsedCommand, GameState], Decision],
    interpret_remote_fn: Optional[Callable[[str, GameState], ParsedCommand]] = None,
) -> Tuple[ParsedCommand, Decision, Optional[str]]:
    """รัน Closed-Loop NeSy Self-Correction 1 รอบ

    คืนค่า: (Final ParsedCommand, Final Decision, Reflexion Note หรือ None)
    """
    if not should_attempt_reflexion(parsed, decision):
        return parsed, decision, None

    t0 = time.perf_counter()
    critique = build_reflexion_critique(raw_text, parsed, decision, state, world_data)
    logger.info("NeSy Reflexion triggered for text: '%s' (Rule: %s)", raw_text, decision.violated_rule_id)

    # 1. ลองใช้ Symbolic Repair ด้วย Hint จาก Critique ก่อน (Fast-Path Correction)
    candidate_parsed = parsed.model_copy()
    if decision.violated_rule_id == "R005_SAME_LOCATION" and parsed.target:
        # หากเป้าหมายอยู่นอกห้อง ตรวจสอบว่าเป็นชื่อตู้รถหรือไม่
        obj_target = world_data.get("objects", {}).get(parsed.target)
        if obj_target and obj_target.get("location"):
            candidate_parsed = parsed.model_copy(
                update={"action": ActionType.MOVE, "target": obj_target.get("location")}
            )
    elif decision.violated_rule_id == "R007_ACTION_SUPPORTED":
        if parsed.action in (ActionType.UNLOCK, ActionType.TAKE, ActionType.USE):
            candidate_parsed = parsed.model_copy(update={"action": ActionType.EXAMINE})

    # ตรวจสอบ Candidate กับ Symbolic Engine
    new_dec = decide_fn(candidate_parsed, state)
    if new_dec.allowed:
        latency = round((time.perf_counter() - t0) * 1000, 2)
        candidate_parsed.parser_mode = "reflexion"
        candidate_parsed.latency_ms = (candidate_parsed.latency_ms or 0) + latency
        note = f"NeSy Reflexion Loop succeeded: corrected {decision.violated_rule_id} -> {candidate_parsed.action.value} {candidate_parsed.target}"
        logger.info(note)
        return candidate_parsed, new_dec, note

    # 2. หากมี remote LLM interpret fn ให้ลอง re-prompt ด้วย critique
    if interpret_remote_fn:
        try:
            # ส่ง critique เข้าไปใน context
            prompt_with_critique = f"{raw_text}\n\n[ข้อเสนอแนะเพิ่มเติม: {critique}]"
            reprompted = interpret_remote_fn(prompt_with_critique, state)
            reprompted_dec = decide_fn(reprompted, state)
            if reprompted_dec.allowed:
                latency = round((time.perf_counter() - t0) * 1000, 2)
                reprompted.parser_mode = "reflexion"
                reprompted.latency_ms = (reprompted.latency_ms or 0) + latency
                note = f"NeSy LLM Reflexion succeeded: {decision.violated_rule_id} corrected to {reprompted.action.value}"
                logger.info(note)
                return reprompted, reprompted_dec, note
        except Exception as e:
            logger.warning("NeSy LLM Reflexion call failed: %s", e)

    # หากแก้ไม่ได้ ให้คืนผลลัพธ์เดิมที่ถูกปฏิเสธ
    return parsed, decision, None
