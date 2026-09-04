"""
invariants.py — ตรวจว่า GameState หนึ่งๆ เป็นสถานะที่ "ไปถึงได้ตามกฎ" หรือไม่

ต่างจาก engine.decide ตรงที่
    engine.decide  ตอบว่า "คำสั่งนี้ทำได้ไหม"        (ตัดสินก่อนลงมือ)
    invariants     ตอบว่า "สถานะนี้เป็นไปได้ไหม"      (ตรวจหลังลงมือแล้ว)

ใช้ในการทดลองที่สอง เมื่อปล่อยให้แต่ละโหมดถือสถานะของตัวเองแล้วเล่นยาว
โหมด B ต้องไม่มีทางละเมิดเลยโดยโครงสร้าง เพราะทุกการเปลี่ยนสถานะผ่านกฎมาแล้ว
ส่วนโหมด A ให้ LLM ตัดสินเองและคืน state_changes เอง จึงพาไปสู่สถานะที่เป็นไปไม่ได้ได้

ต้องเรียกตรวจ "ทุกตา" ไม่ใช่ตรวจแค่ตอนจบ
เพราะเงื่อนไขนำหน้าเป็นเรื่องของลำดับ ถ้าดูแค่สถานะสุดท้ายจะแยกไม่ออกว่า
หลักฐาน X ถูกพบก่อนหรือหลังหลักฐาน Y ที่เป็นเงื่อนไขของมัน
"""

from typing import List

from app.schemas import GameState


def violations(state: GameState, world: dict) -> List[str]:
    """คืนรายการข้อที่สถานะนี้ละเมิด ถ้าว่างแปลว่าสถานะถูกต้องตามกฎ"""
    objects = world["objects"]
    suspects = world["suspects"]
    locations = world["locations"]
    bad: List[str] = []

    # ทุกฟิลด์ที่เก็บ id ต้องถูกตรวจ ไม่ใช่แค่บางฟิลด์
    # เดิมลืม interrogated_suspects กับ current_location ทำให้สอบปากคำคนที่ไม่มีอยู่จริง
    # หรือไปโผล่ในตู้ที่ไม่มีอยู่จริง แล้วตัวตรวจไม่ฟ้อง
    known = set(objects) | set(suspects) | set(locations)
    for field in ("inventory", "discovered_evidence", "unlocked_objects",
                  "visited_locations", "interrogated_suspects"):
        for eid in getattr(state, field):
            if eid not in known:
                bad.append(f"{field} มี id ที่ไม่มีอยู่จริง: '{eid}'")
    if state.current_location not in locations:
        bad.append(f"อยู่ในตู้รถที่ไม่มีอยู่จริง: '{state.current_location}'")

    # ของที่ถือติดตัวต้องหยิบได้ หรือได้มาจากการสอบปากคำ
    granted = {s.get("grants_object") for s in suspects.values() if s.get("grants_object")}
    for oid in state.inventory:
        obj = objects.get(oid)
        if obj is None:
            continue
        if not obj.get("takeable", False) and oid not in granted:
            bad.append(f"ถือ '{oid}' ทั้งที่หยิบไม่ได้และไม่มีใครมอบให้")

    # หลักฐานที่พบแล้ว ต้องมีเงื่อนไขนำหน้าครบตั้งแต่ตอนที่พบ
    found = set(state.discovered_evidence)
    for eid in state.discovered_evidence:
        obj = objects.get(eid)
        if obj is None:
            continue
        for need in obj.get("requires_evidence", []):
            if need not in found:
                bad.append(f"พบ '{eid}' ทั้งที่ยังไม่พบ '{need}' ซึ่งเป็นเงื่อนไขนำหน้า")
        who = obj.get("requires_suspect")
        if who and who not in state.interrogated_suspects:
            bad.append(f"ได้ '{eid}' ทั้งที่ยังไม่ได้สอบปากคำ '{who}'")
        box = obj.get("hidden_in")
        if box and box not in state.unlocked_objects:
            bad.append(f"พบ '{eid}' ทั้งที่ยังไม่ได้ตรวจ '{box}' ซึ่งเป็นที่ซ่อนของมัน")

    # การสอบปากคำต้องมีประเด็นเพียงพอตั้งแต่ตอนที่สอบ
    for sid in state.interrogated_suspects:
        sus = suspects.get(sid)
        if sus is None:
            continue
        for need in sus.get("requires_evidence", []):
            if need not in found:
                bad.append(f"สอบปากคำ '{sid}' ทั้งที่ยังไม่พบ '{need}'")
        prior = sus.get("requires_suspect")
        if prior and prior not in state.interrogated_suspects:
            bad.append(f"สอบปากคำ '{sid}' ทั้งที่ยังไม่ได้สอบ '{prior}' ก่อน")

    # อยู่ในตู้ที่ล็อกได้ก็ต่อเมื่อมีกุญแจ
    for loc_id in set(state.visited_locations) | {state.current_location}:
        loc = locations.get(loc_id)
        if loc is None or not loc.get("locked", False):
            continue
        need = loc.get("requires")
        if need and need not in state.inventory:
            bad.append(f"เข้าไปใน '{loc_id}' ซึ่งล็อกอยู่ ทั้งที่ไม่มี '{need}'")

    # เผาได้เฉพาะของที่ระบุว่าเผาได้ (R017)
    for oid in state.burned_objects:
        if oid not in objects:
            bad.append(f"เผา '{oid}' ซึ่งไม่มีอยู่บนขบวน")
        elif not objects[oid].get("burnable", False):
            bad.append(f"เผา '{oid}' ทั้งที่ไม่ใช่ของที่เผาได้")

    # ของที่ถูกเผาแล้วต้องไม่อยู่ในมืออีก (R016)
    # apply_changes ดึงออกจาก inventory ให้ตอนเผา ถ้ายังอยู่แปลว่ามีคนเซ็ตสถานะเอง
    both = set(state.burned_objects) & set(state.inventory)
    if both:
        bad.append(f"ถือของที่ถูกเผาไปแล้ว: {', '.join(sorted(both))}")

    # ฉากจบที่บันทึกไว้ต้องเป็นฉากจบที่มีอยู่จริง
    ending_ids = {e["id"] for e in world.get("endings", [])}
    if state.ending_id and state.ending_id not in ending_ids:
        bad.append(f"ปิดคดีด้วยฉากจบ '{state.ending_id}' ซึ่งไม่มีอยู่ในฉาก")

    # เล่นเกินกรอบเวลาไม่ได้
    # เวลาเดินเฉพาะตอนคำสั่งผ่าน โหมด A ซึ่งตัดสินเองจึงคุมนาฬิกาของตัวเองได้ทางอ้อม
    # และเล่นเลยกรอบเวลาไปได้ถ้ามันอนุมัติคำสั่งที่กฎจะปฏิเสธ
    limit = world.get("time_limit_seconds", 3600)
    if state.elapsed_seconds > limit:
        bad.append(f"ใช้เวลาไป {state.elapsed_seconds} วินาที เกินกรอบ {limit} วินาที")

    return bad


def is_reachable(state: GameState, world: dict) -> bool:
    return not violations(state, world)
