"""
app/neural/repair.py — Symbolic-Guided Self-Correction (Neuro-Symbolic Constraint Repair Loop)

หน้าที่:
- ตรวจสอบความสอดคล้องเชิงตรรกะ (Domain Constraints) ของ ParsedCommand ที่ได้จาก Neural Layer
- ทำการปรับแก้ความคลุมเครือทางภาษา (Semantic Over-specification) อัตโนมัติ ก่อนส่งต่อให้ Symbolic Engine
- รักษาความถูกต้องตามหลักการ NeSy: ซ่อมเฉพาะความผิดเพี้ยนของการแปลงภาษา โดยไม่ข้ามกฎตรรกะโลก (Invariants)
"""

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
    raw = (raw_text or parsed.raw_text or "").lower()
    objects = world_data.get("objects", {})
    suspects = world_data.get("suspects", {})
    locations = world_data.get("locations", {})
    repair_notes = []
    updates = {}

    # ==========================================================================
    # กรณีพิเศษ: SEQUENCE ที่ไม่มีขั้นตอนชัดเจน แต่มีเจตนาเดินทางไปยังสถานที่ (De-sequence)
    # เช่น "พาฉันไปตรวจดูที่ตู้สัมภาระ", "let's go back to the lounge car to check on gideon"
    # ==========================================================================
    if parsed.action == ActionType.SEQUENCE and (not parsed.alternatives or len(parsed.alternatives) < 2):
        loc_candidates = []
        for loc_id, loc_data in locations.items():
            name_th = loc_data.get("name_th", "").lower()
            if loc_id.lower() in raw or (name_th and name_th in raw):
                loc_candidates.append(loc_id)
            elif loc_id == "luggage_van_electrical" and any(w in raw for w in ("ตู้สัมภาระ", "ห้องระบบไฟ", "ตู้ไฟ", "luggage", "electrical")):
                loc_candidates.append(loc_id)
            elif loc_id == "lounge_car" and any(w in raw for w in ("เลานจ์", "lounge")):
                loc_candidates.append(loc_id)
            elif loc_id == "dining_car_staff" and any(w in raw for w in ("ตู้เสบียง", "dining")):
                loc_candidates.append(loc_id)
            elif loc_id == "first_class_car" and any(w in raw for w in ("ตู้ 4", "ห้องเกิดเหตุ", "ตู้โดยสารชั้นหนึ่ง", "first class")):
                loc_candidates.append(loc_id)
            elif loc_id == "second_class_car" and any(w in raw for w in ("ตู้ 6", "ตู้โดยสารชั้นสอง", "second class")):
                loc_candidates.append(loc_id)

        if len(loc_candidates) == 1:
            dest = loc_candidates[0]
            if any(m in raw for m in ("พา", "เดิน", "ไป", "มุ่งหน้า", "กลับ", "go", "head", "walk", "visit")):
                target = dest
                action = ActionType.MOVE
                updates["action"] = ActionType.MOVE
                updates["target"] = dest
                updates["sequence"] = False
                updates["alternatives"] = []
                repair_notes.append(f"De-sequenced movement intent to MOVE '{dest}'")

    if not updates and parsed.action in (ActionType.UNKNOWN, ActionType.SEQUENCE, ActionType.AMBIGUOUS):
        return parsed, None

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
            if "examine" in supports or any(w in raw for w in ("เปิด", "เปิดดู", "เปิดอ่าน", "ตรวจ", "ส่อง", "ดู", "open", "read", "check", "inspect")):
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
        if any(w in raw for w in ("คุย", "ถาม", "สอบปากคำ", "ซัก", "talk", "ask", "interrogate", "speak")):
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
    # กรณีพิเศษ: การอ้างอิงถึงแคสเซียน / ศพผู้ตาย (Victim Reference Mapping)
    # ==========================================================================
    if target in ("cassian", "cassian_body", "cassian reed", "body", "corpse", "ศพ", "ร่าง", "ร่างผู้ตาย", "แคสเซียน", "แคสเซียน รีด") and "cassian_reed" in objects:
        updates["target"] = "cassian_reed"
        repair_notes.append(f"Mapped victim reference '{target}' to entity 'cassian_reed'")

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
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            if len(candidates) == 1 or candidates[0][0] >= 0.85 or (candidates[0][0] - candidates[1][0] >= 0.25):
                best_oid = candidates[0][1]
                updates["target"] = best_oid
                repair_notes.append(f"Recovered missing target as '{best_oid}' from current room via N-gram matching")

    # ==========================================================================
    # กรณีที่ 5: target เป็นคำนามกว้างๆ (Generic Noun เช่น 'key', 'กุญแจ')
    # ที่ไม่ตรงกับ ID จริง แต่ในห้องปัจจุบันมีวัตถุประเภทนั้นเพียงชิ้นเดียว
    # ==========================================================================
    effective_target = updates.get("target", target)
    if (
        effective_target not in objects
        and state
        and action in (ActionType.EXAMINE, ActionType.TAKE, ActionType.BURN, ActionType.UNLOCK, ActionType.USE)
    ):
        resolved = resolve_contextual_target(action, effective_target, state, world_data, raw_text=raw)
        if resolved and resolved in objects and resolved != effective_target:
            updates["target"] = resolved
            repair_notes.append(f"Contextually resolved target '{effective_target}' to '{resolved}' in '{state.current_location}'")

    # ==========================================================================
    # กรณีที่ 6: คำสั่ง UNLOCK/USE บนประตูหรือวัตถุที่ต้องใช้กุญแจ (Key Requirement)
    # หากผู้เล่นพกกุญแจที่ตรงกันอยู่ในกระเป๋า (state.inventory) แต่ในคำสั่งไม่ได้ระบุ instrument
    # ทำการ Bind กุญแจดอกนั้นเป็น instrument อัตโนมัติ (Elliptic Instrument Resolution)
    # ==========================================================================
    if state and action in (ActionType.UNLOCK, ActionType.USE):
        final_target = updates.get("target", target)
        if final_target in objects:
            req_key = objects[final_target].get("unlock_requirements", {}).get("key")
            current_instrument = updates.get("instrument", parsed.instrument)
            if req_key and req_key in state.inventory and not current_instrument:
                updates["instrument"] = req_key
                repair_notes.append(f"Auto-bound held key '{req_key}' for unlocking '{final_target}'")

    if not updates:
        return parsed, None

    note = "; ".join(repair_notes)
    updates["repair_note"] = note
    repaired = parsed.model_copy(update=updates)
    return repaired, note


def resolve_contextual_target(
    action: Any,
    target: Optional[str],
    state: Optional[GameState],
    world_data: Dict[str, Any],
    raw_text: Optional[str] = None,
) -> Optional[str]:
    """แปลงคำนามกว้างๆ (Generic Noun) หรือ target ชั่วคราว ให้เป็น ID วัตถุจริงในตู้ปัจจุบัน

    เงื่อนไขความปลอดภัย:
    - ค้นหาเฉพาะในตู้ปัจจุบัน (state.current_location)
    - ต้องมีวัตถุที่ตรงตามหมวดหมู่เพียง 'ชิ้นเดียว' (Uniqueness Constraint)
    - หากมีหลายชิ้น หรือไม่มีเลย จะคืน target เดิมเพื่อส่งต่อให้ Symbolic Engine ตัดสิน
    """
    if not state:
        return target

    objects = world_data.get("objects", {})
    suspects = world_data.get("suspects", {})
    current_loc = state.current_location
    t_clean = (target or "").lower().strip()
    raw = (raw_text or "").lower()
    act_str = action.value if hasattr(action, "value") else str(action).lower()

    # หาก target เป็น ID ที่ถูกต้องและอยู่ในห้องปัจจุบันหรือกระเป๋า ไม่ต้องแปลง
    if target and (target in objects or target in suspects):
        if target in state.inventory:
            return target
        if target in objects and objects[target].get("location") == current_loc:
            return target
        if target in suspects and suspects[target].get("location") == current_loc:
            return target
        if act_str not in ("examine", "take", "use", "unlock", "interrogate"):
            return target

    # หมวดหมู่บุคคล/ผู้ต้องสงสัย (Suspects & Interrogation)
    if act_str == "interrogate" or any(s in t_clean for s in ("staff", "attendant", "พนักงาน", "doctor", "หมอ", "vincent", "gideon")):
        room_suspects = {sid: s for sid, s in suspects.items() if s.get("location") == current_loc}
        suspect_candidates = []
        # พนักงานตรวจตู้ (car_attendant / dining_staff / staff)
        if any(w in t_clean for w in ("staff", "attendant", "พนักงาน", "dining_staff", "ตู้เสบียง")):
            for sid, s in room_suspects.items():
                if sid == "car_attendant" or "พนักงาน" in s.get("name_th", ""):
                    suspect_candidates.append(sid)
        # แพทย์ (dr_liora_venn)
        elif any(w in t_clean for w in ("liora", "doctor", "หมอ", "แพทย์")):
            for sid, s in room_suspects.items():
                if sid == "dr_liora_venn" or "แพทย์" in s.get("name_th", "") or "หมอ" in s.get("name_th", ""):
                    suspect_candidates.append(sid)
        # วินเซนต์
        elif any(w in t_clean for w in ("vincent", "วินเซนต์")):
            for sid, s in room_suspects.items():
                if sid == "vincent_gray" or "วินเซนต์" in s.get("name_th", ""):
                    suspect_candidates.append(sid)
        # กิเดียน
        elif any(w in t_clean for w in ("gideon", "กิเดียน")):
            for sid, s in room_suspects.items():
                if sid == "gideon_hart" or "กิเดียน" in s.get("name_th", ""):
                    suspect_candidates.append(sid)
        # ผู้ป่วย
        elif any(w in t_clean for w in ("patient", "ผู้ป่วย")):
            for sid, s in room_suspects.items():
                if sid == "patient_witness" or "ผู้ป่วย" in s.get("name_th", ""):
                    suspect_candidates.append(sid)
        elif len(room_suspects) == 1:
            suspect_candidates.append(list(room_suspects.keys())[0])

        if len(suspect_candidates) == 1:
            return suspect_candidates[0]

    room_objects = {oid: obj for oid, obj in objects.items() if obj.get("location") == current_loc}
    if not room_objects:
        return target


    candidates = []

    # 1. หมวดหมู่กุญแจ (Keys: key, keys, กุญแจ)
    is_key = t_clean in ("key", "keys", "กุญแจ", "ลูกกุญแจ", "medical_key", "staff_key") or (
        t_clean in ("null", "none", "", "medical_key", "staff_key") and any(k in raw for k in ("กุญแจ", "key"))
    ) or any(k in t_clean for k in ("key", "กุญแจ"))
    if is_key:
        for oid, obj in room_objects.items():
            obj_type = obj.get("type", "").lower()
            name_th = obj.get("name_th", "").lower()
            if obj_type == "key" or "key" in oid.lower() or "กุญแจ" in name_th:
                candidates.append(oid)

    # 2. หมวดหมู่กระเป๋า (Bags: bag, กระเป๋า)
    elif t_clean in ("bag", "กระเป๋า", "ย่าม") or (
        t_clean in ("null", "none", "") and any(k in raw for k in ("กระเป๋า", "bag"))
    ):
        for oid, obj in room_objects.items():
            name_th = obj.get("name_th", "").lower()
            if "bag" in oid.lower() or "กระเป๋า" in name_th:
                candidates.append(oid)

    # 3. หมวดหมู่บันทึก / สมุด / จดหมาย (Documents / Notes / Letters)
    elif t_clean in ("note", "book", "บันทึก", "สมุด", "จดหมาย", "letter") or (
        t_clean in ("null", "none", "") and any(k in raw for k in ("บันทึก", "สมุด", "จดหมาย", "note", "letter"))
    ):
        for oid, obj in room_objects.items():
            name_th = obj.get("name_th", "").lower()
            if any(k in oid.lower() for k in ("note", "log", "book", "letter")) or any(k in name_th for k in ("บันทึก", "สมุด", "จดหมาย")):
                candidates.append(oid)

    # 4. หมวดหมู่นาฬิกา (Watch / Clock: watch, clock, นาฬิกา)
    elif t_clean in ("watch", "clock", "นาฬิกา") or (
        t_clean in ("null", "none", "") and any(k in raw for k in ("นาฬิกา", "watch", "clock"))
    ):
        for oid, obj in room_objects.items():
            name_th = obj.get("name_th", "").lower()
            if "watch" in oid.lower() or "clock" in oid.lower() or "นาฬิกา" in name_th:
                candidates.append(oid)

    # 5. หมวดหมู่ประตู / ห้องล็อก (Doors: door, doors, ประตู, บานประตู, doctor_compartment_door, electrical_door, etc.)
    elif any(d in t_clean for d in ("door", "doors", "ประตู", "บานประตู", "doctor_compartment_door", "electrical_door", "ห้องแพทย์", "ห้องพยาบาล", "ห้องระบบไฟ", "ห้องไฟฟ้า", "ห้องไฟ")) or (
        t_clean in ("null", "none", "") and any(d in raw for d in ("ประตู", "door"))
    ):
        for oid, obj in room_objects.items():
            obj_type = obj.get("type", "").lower()
            name_th = obj.get("name_th", "").lower()
            if obj_type == "door" or "door" in oid.lower() or "ประตู" in name_th:
                candidates.append(oid)

    # 6. หมวดหมู่ศพ / ร่างผู้เสียชีวิต / แคสเซียน (Corpse / Victim's Body: cassian, body, corpse, ศพ, ร่าง, ชันสูตร)
    elif any(k in t_clean for k in ("cassian", "body", "corpse", "ศพ", "ร่าง", "แคสเซียน")) or (
        t_clean in ("null", "none", "") and any(k in raw for k in ("cassian", "body", "corpse", "ศพ", "ร่าง", "แคสเซียน", "ชันสูตร"))
    ):
        for oid, obj in room_objects.items():
            name_th = obj.get("name_th", "").lower()
            if oid in ("cassian_reed", "cassian_body") or "ศพ" in name_th or "ร่าง" in name_th:
                candidates.append(oid)

    # 7. Generic substring match
    elif t_clean not in ("null", "none", ""):
        for oid, obj in room_objects.items():
            name_th = obj.get("name_th", "").lower()
            if t_clean in oid.lower() or t_clean in name_th:
                candidates.append(oid)

    # กฎความปลอดภัย: ต้องมีตรงเป๊ะชิ้นเดียวในห้องนี้
    if len(candidates) == 1:
        return candidates[0]

    return target

