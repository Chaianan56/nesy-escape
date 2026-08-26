"""
play.py — โหมดเล่นในเทอร์มินัล ใช้ลองพิมพ์ภาษาธรรมชาติโดยไม่ต้องเปิดเซิร์ฟเวอร์

รันด้วย:  python play.py
คำสั่งพิเศษ:  /สถานะ  /หลักฐาน  /ช่วย  /ออก

หมายเหตุ: id (เช่น service_pantry) และรหัสกฎ (เช่น R005_SAME_LOCATION) ยังเป็นอังกฤษ
เพราะเป็นสัญญาระหว่าง Neural กับ Symbolic Layer และต้องตรงกับ rules.json
ส่วนที่ผู้เล่นอ่านเป็นภาษาไทยทั้งหมด
"""

import re
import sys

from app.neural import interpret
from app.neural.gemini_client import llm_online
from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine, apply_changes

# เทอร์มินัล Windows ปกติเป็น cp874 ถ้าไม่บังคับ utf-8 ภาษาไทยจะเพี้ยนทั้งเข้าและออก
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

engine = SymbolicEngine()
state = GameState()
world = engine.world

ACTION_TH = {
    ActionType.EXAMINE: "ตรวจสอบ",
    ActionType.TAKE: "เก็บ",
    ActionType.USE: "ใช้",
    ActionType.UNLOCK: "ปลดล็อก",
    ActionType.MOVE: "เคลื่อนที่",
    ActionType.INTERROGATE: "สอบปากคำ",
    ActionType.ACCUSE: "กล่าวหา",
    ActionType.AMBIGUOUS: "คำสั่งกำกวม",
    ActionType.UNKNOWN: "ไม่เข้าใจคำสั่ง",
}

PILLAR_TH = {
    "motive": "แรงจูงใจ",
    "means": "วิธีการ",
    "opportunity": "โอกาส",
    "corroboration": "หลักฐานสนับสนุน",
}


def th_name(eid):
    """ชื่อไทยของ id ใดก็ได้ ตัดวงเล็บอธิบายท้ายชื่อออก"""
    if eid is None:
        return "—"
    for group in ("locations", "objects", "suspects"):
        info = world[group].get(eid)
        if info:
            return re.sub(r"\s*\(.*?\)\s*", "", info.get("name_th", eid)).strip()
    return eid


def show_help():
    print("\n  พิมพ์เป็นภาษาไทยได้เลย เช่น")
    print("    ดูรอบๆ ห้องนี้มีอะไรบ้าง")
    print("    ไปที่จุดเกิดเหตุ")
    print("    ตรวจดูสมุดบันทึกของผู้ตาย")
    print("    ขอสอบปากคำพนักงานควบคุมรถหน่อย")
    print("    กล่าวหา<ชื่อผู้ต้องสงสัย>")
    print("\n  คำสั่งระบบ:  /สถานะ  /หลักฐาน  /ช่วย  /ออก\n")


def show_state():
    print(f"\n  อยู่ที่      : {th_name(state.current_location)}")
    print(f"  ของติดตัว   : {', '.join(th_name(i) for i in state.inventory) or '(ไม่มี)'}")
    print(f"  หลักฐานที่พบ: {len(state.discovered_evidence)} ชิ้น")
    for e in state.discovered_evidence:
        print(f"      - {th_name(e)}")
    print(f"  สอบปากคำแล้ว: {', '.join(th_name(s) for s in state.interrogated_suspects) or '(ยังไม่มี)'}")
    print(f"  ผ่านมาแล้ว   : {state.turn_count} ตา\n")


def parse_alt(alt: str):
    """แปลงตัวเลือกรูป '<action> <id>' ที่ตัวตีความเสนอมา ให้เป็น ParsedCommand

    แปลงเองแทนการยิง interpret ซ้ำ เพราะรูปแบบตายตัวอยู่แล้วและโควตา LLM มีจำกัด
    """
    parts = alt.split()
    try:
        action = ActionType(parts[0].lower())
    except (ValueError, IndexError):
        return None
    target = parts[1] if len(parts) > 1 else None
    if target and target not in {*world["locations"], *world["objects"], *world["suspects"]}:
        return None
    return ParsedCommand(action=action, target=target, raw_text=alt, confidence=1.0)


def describe_alt(alt: str) -> str:
    p = parse_alt(alt)
    if p is None:
        return alt
    return f"{ACTION_TH.get(p.action, p.action.value)}{th_name(p.target)}"


def show_pillars():
    print()
    for sid in world["suspects"]:
        found = engine.pillar_status(sid, state)
        marks = "  ".join(f"{PILLAR_TH[k]}{'✓' if v else '✗'}" for k, v in found.items())
        print(f"  {th_name(sid):18} {marks}")
    print()


print(f"\n=== {world['title']} ===")
print("ตัวตีความ: " + ("Gemini" if llm_online() else "ตัวสำรอง (ไม่มี API key — ต้องพิมพ์ชื่อให้ตรง)"))
print(f"\n{world['briefing']}\n")
print(engine.look_around(state.current_location, state))
show_help()

while True:
    try:
        text = input(f"[{th_name(state.current_location)}] > ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not text:
        continue
    if text in ("/ออก", "/quit", "/q"):
        break
    if text in ("/สถานะ", "/state"):
        show_state()
        continue
    if text in ("/หลักฐาน", "/pillars"):
        show_pillars()
        continue
    if text in ("/ช่วย", "/help", "/?"):
        show_help()
        continue

    parsed = interpret(text, state)

    # คำสั่งพ่วงหลายขั้น (เช่น "ไปที่จุดเกิดเหตุแล้วดูบันทึก") จะถูกตีความเป็น ambiguous
    # พร้อมลิสต์ขั้นตอน — ระบบตัดสินได้ทีละคำสั่ง จึงให้ผู้เล่นเลือกว่าจะเอาขั้นไหนก่อน
    # แต่ละครั้งที่เลือกยังนับเป็นหนึ่งคำสั่งหนึ่งคำตัดสินเหมือนเดิม
    choices = [a for a in (parsed.alternatives or []) if parse_alt(a)]
    if parsed.action in (ActionType.AMBIGUOUS, ActionType.UNKNOWN) and choices:
        print("\n  คำสั่งนี้ทำได้หลายอย่าง จะเอาข้อไหนก่อน")
        for i, alt in enumerate(choices, 1):
            print(f"    {i}. {describe_alt(alt)}")
        pick = input("  เลือกหมายเลข (หรือ Enter เพื่อพิมพ์ใหม่) > ").strip()
        if not pick.isdigit() or not 1 <= int(pick) <= len(choices):
            print()
            continue
        parsed = parse_alt(choices[int(pick) - 1])

    decision = engine.decide(parsed, state)

    action_th = ACTION_TH.get(parsed.action, parsed.action.value)
    detail = f" → {th_name(parsed.target)}" if parsed.target else ""
    if parsed.instrument:
        detail += f" (ใช้ {th_name(parsed.instrument)})"
    print(f"  ระบบเข้าใจว่า: {action_th}{detail}")

    for step in decision.reasoning_chain:
        print(f"    [{'ผ่าน  ' if step.passed else 'ไม่ผ่าน'}] {step.description}")
    print(f"\n  {decision.message}")

    if decision.allowed:
        state = apply_changes(state, decision.state_changes)
        if parsed.action == ActionType.ACCUSE:
            print(f"\n  === คดีปิดแล้ว — ผู้ลงมือคือ{th_name(parsed.target)} ===")
            break
    print()
