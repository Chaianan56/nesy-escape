"""Player notes derived only from already discovered information; no hint grants."""
QUESTIONS = {
    "gideon_no_early_alibi": "คำบอกเล่าเรื่องที่อยู่ช่วง 20:00–20:40 ของกิเดียนมีข้อมูลอื่นรองรับหรือไม่?",
    "vincent_body_testimony": "คำให้การเรื่องการพบร่างอธิบายร่องรอยที่พบได้อย่างไร?",
    "vincent_blackout_confession": "คำรับสารภาพเรื่องไฟดับบอกอะไร และยังไม่บอกอะไรเกี่ยวกับการเสียชีวิต?",
    "liora_time_estimate": "คำประเมินเวลาตายสอดคล้องกับเวลาที่พบในหลักฐานอื่นหรือไม่?",
}


def evidence_entry(world, eid):
    obj = world["objects"][eid]
    owner = obj.get("from_testimony")
    return {"id": eid, "name": obj["name_th"], "description": obj.get("description", ""),
            "kind": "testimony" if owner else "observation",
            "source": world["suspects"][owner]["name_th"] if owner else "สิ่งที่ตรวจพบ",
            "source_note": "ข้อมูลจากการสอบปากคำ ยังไม่ใช่การยืนยันความจริงทุกประเด็น" if owner else
                           "สิ่งที่ตรวจพบ ยังไม่ยืนยันว่าใครเป็นผู้กระทำ"}


def case_questions(world, state):
    found = set(state.discovered_evidence)
    return [{"id": eid, "question": question, "source": world["objects"][eid]["name_th"],
             "status": "ประเด็นให้ผู้เล่นตรวจสอบ"}
            for eid, question in QUESTIONS.items() if eid in found]


def conversation_summaries(world, before, after):
    old = set(before.discovered_evidence)
    summaries = []
    for sid, suspect in world["suspects"].items():
        entries = [evidence_entry(world, eid) for eid in after.discovered_evidence
                   if eid not in old and eid in world["objects"]
                   and world["objects"][eid].get("from_testimony") == sid]
        if entries:
            summaries.append({"person": suspect["name_th"], "entries": entries})
    return summaries
