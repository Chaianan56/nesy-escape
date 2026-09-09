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
import time
import threading
import queue as input_queue

from app.neural import interpret
from app.neural.gemini_client import llm_online
from app.schemas import ActionType, GameState, ParsedCommand
from app.symbolic.engine import SymbolicEngine, apply_changes
from app.game_clock import sync_clock

# เทอร์มินัล Windows ปกติเป็น cp874 ถ้าไม่บังคับ utf-8 ภาษาไทยจะเพี้ยนทั้งเข้าและออก
sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

engine = SymbolicEngine()
state = GameState(started_at=time.time())
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


def clock() -> str:
    left = max(0, engine.seconds_left(sync_clock(state)))
    return f"{left // 60:02d}:{left % 60:02d}"


def timed_input(prompt):
    """Stop waiting for input when the real game deadline expires."""
    result = input_queue.Queue()
    def read():
        try:
            result.put(input(prompt))
        except EOFError as exc:
            result.put(exc)
    threading.Thread(target=read, daemon=True).start()
    left = max(0, state.started_at + world["time_limit_seconds"] - time.time())
    try:
        value = result.get(timeout=left)
    except input_queue.Empty:
        print(f"\n{engine.ending_message(sync_clock(state))}")
        raise SystemExit(0)
    if isinstance(value, Exception):
        raise value
    return value


def show_state():
    print(f"\n  เวลาที่เหลือ : {clock()} นาที")
    print(f"  อยู่ที่      : {th_name(state.current_location)}")
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

# คิวของขั้นตอนที่รอทำ — เกิดจากประโยคพ่วง เช่น "ไปห้องเก็บกระเป๋าและตรวจสอบศพ"
# ทุกขั้นในคิวยังผ่าน engine.decide ทีละอันเหมือนคำสั่งเดี่ยว
# หน่วยวัดจึงยังเป็น 1 คำสั่ง = 1 คำตัดสิน = 1 บรรทัด log เหมือนเดิม
queue = []

while True:
    state = sync_clock(state)
    # เกมจบเพราะหมดเวลา ต้องเช็คก่อนรับคำสั่งถัดไป ไม่งั้นผู้เล่นจะเจอแต่คำสั่งถูกปฏิเสธ
    # ไปเรื่อยๆ โดยไม่มีอะไรบอกว่าจบแล้ว
    if engine.is_out_of_time(state):
        print(f"\n  === หมดเวลา ===\n  {engine.ending_message(state)}\n")
        break

    if queue:
        parsed = queue.pop(0)
        print(f"  ขั้นต่อไป: {ACTION_TH.get(parsed.action, parsed.action.value)}{th_name(parsed.target)}")
    else:
        try:
            text = timed_input(f"[{clock()} | {th_name(state.current_location)}] > ").strip()
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

        # ประโยคพ่วงหลายขั้นถูกตีความเป็น ambiguous พร้อมลิสต์ขั้นตอน
        # ระบบแยกไม่ออกว่าผู้เล่นหมายถึง "ทำทั้งสองอย่าง" หรือ "เลือกอย่างใดอย่างหนึ่ง"
        # จึงไม่เดา — ให้ผู้เล่นบอกเอง เพราะเขารู้ว่าตัวเองหมายถึงอะไร
        choices = [a for a in (parsed.alternatives or []) if parse_alt(a)]
        if parsed.action in (ActionType.AMBIGUOUS, ActionType.UNKNOWN) and choices:
            print(f"\n  คำสั่งนี้แตกได้ {len(choices)} ขั้น")
            for i, alt in enumerate(choices, 1):
                print(f"    {i}. {describe_alt(alt)}")
            pick = timed_input("  [Enter = ทำทั้งหมดตามลำดับ / เลข = เอาข้อเดียว / n = ยกเลิก] > ").strip()
            print()
            if pick in ("n", "N"):
                continue
            if pick.isdigit():
                if not 1 <= int(pick) <= len(choices):
                    continue
                parsed = parse_alt(choices[int(pick) - 1])
            else:
                queue = [parse_alt(a) for a in choices]
                parsed = queue.pop(0)

    state = sync_clock(state)
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
    elif decision.state_changes.get("ending"):
        state.ending_id = decision.state_changes["ending"]
        break
    elif queue:
        # ขั้นถัดไปตั้งอยู่บนสมมติฐานว่าขั้นนี้สำเร็จ ทำต่อไปก็ผิดยกแถว
        print(f"  (ยกเลิกอีก {len(queue)} ขั้นที่รออยู่ เพราะขั้นนี้ทำไม่ได้)")
        queue.clear()
    print()
