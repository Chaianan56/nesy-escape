"""
app/neural/repair.py — Symbolic-Guided Self-Correction (Neuro-Symbolic Constraint Repair Loop)

หน้าที่:
- ตรวจสอบความสอดคล้องเชิงตรรกะ (Domain Constraints) ของ ParsedCommand ที่ได้จาก Neural Layer
- ทำการปรับแก้ความคลุมเครือทางภาษา (Semantic Over-specification) อัตโนมัติ ก่อนส่งต่อให้ Symbolic Engine
- รักษาความถูกต้องตามหลักการ NeSy: ซ่อมเฉพาะความผิดเพี้ยนของการแปลงภาษา โดยไม่ข้ามกฎตรรกะโลก (Invariants)
"""

import re
from typing import Any, Dict, Optional, Tuple
from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.retriever import score_entity_candidate


def repair_parsed_command(
    parsed: ParsedCommand,
    world_data: Dict[str, Any],
    state: Optional[GameState] = None,
    raw_text: Optional[str] = None,
) -> Tuple[ParsedCommand, Optional[str]]:
    """ซ่อมแซมคำสั่งที่สกัดจาก LLM หากพบข้อขัดแย้งเชิงตรรกะกับ Domain Ontology

    Returns:
        (repaired_command, repair_note)
    """
    if parsed.action in (ActionType.UNKNOWN, ActionType.SEQUENCE, ActionType.AMBIGUOUS):
        return parsed, None

    raw = (raw_text or parsed.raw_text or "").lower()
    objects = world_data.get("objects", {})
    suspects = world_data.get("suspects", {})
    locations = world_data.get("locations", {})
    repair_notes = []
    updates = {}

    target = parsed.target
    action = parsed.action

    # ==========================================================================
    # กรณีที่ 1: การใช้คำว่า 'เปิด' (Semantic Over-specification: UNLOCK vs EXAMINE)
    # คนไทยมักพูดว่า "เปิดดูสมุด", "เปิดอ่านจดหมาย" แต่ LLM อาจสกัดเป็น action="unlock"
    # หากวัตถุนั้นไม่ได้ล็อกและรองรับแค่ "examine" ให้ปรับเป็น examine อัตโนมัติ
    # ==========================================================================
    if action == ActionType.UNLOCK and target in objects:
        obj_info = objects[target]
        supports = obj_info.get("supports", [])
        has_lock = bool(obj_info.get("code") or obj_info.get("requires_key"))
        
        # ถ้าไม่มีกลไกล็อก และไม่รองรับ unlock แต่รองรับ examine
        if "unlock" not in supports and not has_lock:
            if "examine" in supports or any(w in raw for w in ("เปิดดู", "เปิดอ่าน", "ตรวจ", "ส่อง", "ดู")):
                updates["action"] = ActionType.EXAMINE
                updates["code"] = None
                updates["instrument"] = None
                repair_notes.append(f"Adjusted UNLOCK to EXAMINE for non-lockable object '{target}'")

    # ==========================================================================
    # กรณีที่ 2: สับสนระหว่าง บุคคล (Person) กับ วัตถุ (Object)
    # เช่น "คุยกับนาฬิกา" หรือ "ตรวจดูกิเดียน" ขณะตั้งใจจะสอบถาม
    # ==========================================================================
    if action == ActionType.INTERROGATE and target in objects and target not in suspects:
        # สั่ง interrogate ใส่สิ่งของ -> ควรเป็น examine
        updates["action"] = ActionType.EXAMINE
        updates["topic"] = None
        repair_notes.append(f"Adjusted INTERROGATE to EXAMINE for object '{target}'")

    elif action == ActionType.EXAMINE and target in suspects and target not in objects:
        # สั่ง examine ใส่คน แต่ในประโยคมีเจตนาคุย/ถาม
        if any(w in raw for w in ("คุย", "ถาม", "สอบปากคำ", "ซัก")):
            updates["action"] = ActionType.INTERROGATE
            repair_notes.append(f"Adjusted EXAMINE to INTERROGATE for person '{target}'")

    # ==========================================================================
    # กรณีที่ 3: สั่ง 'move' โดยใส่ชื่อวัตถุแทนสถานที่
    # เช่น "ไปที่ตู้เซฟ" -> ควรแปลงเป้าหมายเป็นตู้รถที่วัตถุนั้นตั้งอยู่
    # ==========================================================================
    if action == ActionType.MOVE and target in objects and target not in locations:
        obj_loc = objects[target].get("location")
        if obj_loc and obj_loc in locations:
            updates["target"] = obj_loc
            repair_notes.append(f"Mapped object target '{target}' to its container location '{obj_loc}' for MOVE")

    # ==========================================================================
    # กรณีที่ 4: target เป็น None แต่ในข้อความระบุถึงวัตถุในตู้ปัจจุบันอย่างชัดเจน
    # (LLM อาจพลาดการ Match ID) -> กู้คืน target ด้วย N-gram Scorer
    # ==========================================================================
    if target is None and state and action in (ActionType.EXAMINE, ActionType.TAKE, ActionType.BURN):
        current_loc = state.current_location
        candidates = []
        for oid, o_data in objects.items():
            if o_data.get("location") == current_loc or oid in state.inventory:
                score = score_entity_candidate(raw, oid, o_data)
                if score >= 0.55:
                    candidates.append((score, oid))
        if len(candidates) == 1:
            best_oid = candidates[0][1]
            updates["target"] = best_oid
            repair_notes.append(f"Recovered missing target as '{best_oid}' from current room via N-gram matching")

    if not updates:
        return parsed, None

    repaired = parsed.model_copy(update=updates)
    note = "; ".join(repair_notes)
    return repaired, note
