"""
app/case_notes.py — ระบบบันทึกและประเด็นคำถามในสมุดคดี (Case Notes & Questions)

รวบรวมข้อมูลหลักฐานและประเด็นข้อสงสัยที่ผู้เล่นค้นพบแล้วเท่านั้น
โดยไม่เฉลยคำตอบหรือใบ้ข้อมูลล่วงหน้า เพื่อคงความเที่ยงตรงของการสืบสวน
"""

# ประเด็นคำถามที่ผู้เล่นควรนำไปคิดต่อเมื่อพบหลักฐานที่เกี่ยวข้อง
QUESTIONS = {
    "gideon_no_early_alibi": "คำบอกเล่าเรื่องที่อยู่ช่วง 20:00–20:40 ของกิเดียนมีข้อมูลอื่นรองรับหรือไม่?",
    "vincent_body_testimony": "คำให้การเรื่องการพบร่างอธิบายร่องรอยที่พบได้อย่างไร?",
    "vincent_blackout_confession": "คำรับสารภาพเรื่องไฟดับบอกอะไร และยังไม่บอกอะไรเกี่ยวกับการเสียชีวิต?",
    "liora_time_estimate": "สิ่งที่แพทย์ตรวจพบช่วยอธิบายอะไร และเรื่องใดต้องตรวจจากแหล่งอื่น?",
    "postponed_meeting_claim": "ใครเป็นต้นทางข่าวเลื่อนนัด และคุณได้ตรวจสอบกับคนนั้นแล้วหรือยัง?",
    "staff_impact_testimony": "เสียงที่พนักงานได้ยินสัมพันธ์กับช่วงใดของการเดินรถ และวัตถุในห้องบันทึกเหตุอะไร?",
    "file_c_initials": "เลขเอกสารและข้อความที่เหลือเชื่อมกับทะเบียนฉบับใด?",
}


def evidence_entry(world: dict, eid: str) -> dict:
    """สร้างข้อมูลสรุปหลักฐานสำหรับแสดงผลในสมุดคดีของผู้เล่น

    Args:
        world: โครงสร้างข้อมูลโลกของเกม (story.json)
        eid: รหัส ID ของหลักฐาน/วัตถุ

    Returns:
        dict: ข้อมูลหลักฐานพร้อมชื่อไทย, คำอธิบาย, แหล่งที่มา, และหมายเหตุ
    """
    obj = world["objects"][eid]
    owner = obj.get("from_testimony")
    return {
        "id": eid,
        "name": obj["name_th"],
        "description": obj.get("description", ""),
        "kind": "testimony" if owner else "observation",
        "source": world["suspects"][owner]["name_th"] if owner else "สิ่งที่ตรวจพบ",
        "source_note": (
            "ข้อมูลจากการสอบปากคำ ยังไม่ใช่การยืนยันความจริงทุกประเด็น"
            if owner
            else "สิ่งที่ตรวจพบ ยังไม่ยืนยันว่าใครเป็นผู้กระทำ"
        ),
    }


def case_questions(world: dict, state) -> list:
    """ดึงรายการประเด็นคำถามที่เปิดขึ้นตามหลักฐานที่ผู้เล่นพบแล้วในปัจจุบัน

    Args:
        world: โครงสร้างข้อมูลโลกของเกม
        state: สถานะเกมปัจจุบัน (GameState)

    Returns:
        list: รายการคำถามพร้อมชื่อหลักฐานต้นทาง
    """
    found = set(state.discovered_evidence)
    return [
        {
            "id": eid,
            "question": question,
            "source": world["objects"][eid]["name_th"],
            "status": "ประเด็นให้ผู้เล่นตรวจสอบ",
        }
        for eid, question in QUESTIONS.items()
        if eid in found
    ]


def conversation_summaries(world: dict, before, after) -> list:
    """สรุปข้อมูลหลักฐานชิ้นใหม่ที่ได้รับจากการสนทนาล่าสุด (เทียบก่อน-หลังเทิร์น)

    Args:
        world: โครงสร้างข้อมูลโลกของเกม
        before: สถานะเกมก่อนดำเนินการ (GameState)
        after: สถานะเกมหลังดำเนินการ (GameState)

    Returns:
        list: รายการสรุปคำให้การใหม่แยกตามบุคคล
    """
    old = set(before.discovered_evidence)
    summaries = []
    for sid, suspect in world["suspects"].items():
        entries = [
            evidence_entry(world, eid)
            for eid in after.discovered_evidence
            if eid not in old
            and eid in world["objects"]
            and world["objects"][eid].get("from_testimony") == sid
        ]
        if entries:
            summaries.append({"person": suspect["name_th"], "entries": entries})
    return summaries
