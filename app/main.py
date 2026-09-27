"""
main.py — Interaction Layer / ท่อเชื่อมระบบ

ไฟล์นี้เชื่อมระบบและจัดการ session เวลา และข้อมูลที่แสดงแก่ผู้เล่น
กฎการอนุญาตคำสั่งอยู่ใน Symbolic Engine

    ข้อความไทย -> Neural ตีความ -> Symbolic ตัดสิน -> อัปเดตสถานะ -> ตอบ

รันด้วย:  uvicorn app.main:app --reload
เอกสาร API:  http://127.0.0.1:8000/docs
"""

from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    ActionType,
    CommandRequest,
    CommandResponse,
    GameState,
    ParsedCommand,
)
from app.game_clock import sync_clock
from app.sessions import Session, session_for
from app.symbolic.engine import SymbolicEngine, apply_changes, accusation_submission


app = FastAPI(title="NeSy-Escape API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: จำกัดโดเมนก่อน deploy จริง
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SymbolicEngine()


# ============================================================
# สะพานไปยัง NEURAL LAYER
# main.py เรียกใช้แค่ interpret() และไม่สนใจว่าข้างในทำอะไร
# ตราบใดที่คืนค่าตรงตาม schema จะเปลี่ยนโมเดลหรือ prompt ก็ได้โดยไม่กระทบไฟล์นี้
# ห้ามให้ชั้นนั้นตัดสินว่าอนุญาตหรือไม่ ParsedCommand จึงไม่มีฟิลด์นั้นโดยเจตนา
# ============================================================

from app.neural.gemini_client import _clients, interpret as interpret_remote, llm_online
from app.neural.typed_commands import interpret_game as interpret


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
def health(probe: bool = False):
    """ตรวจความพร้อมของระบบ

    llm_configured บอกแค่ว่าตั้งคีย์ไว้แล้ว ไม่ได้แปลว่าเรียกได้จริง
    เดิมฟิลด์นี้ชื่อ llm_online ซึ่งทำให้เข้าใจผิด เพราะโควตาหมดแล้วมันก็ยังตอบ true
    ถ้าอยากรู้ว่าเรียกได้จริงไหม ต้องส่ง ?probe=true ซึ่งจะยิง API จริงหนึ่งครั้ง
    ไม่ทำให้เป็นค่าเริ่มต้น เพราะทุกครั้งที่เรียกจะกินโควตารายวัน
    """
    info = {
        "status": "ok",
        "llm_configured": llm_online(),
        "llm_keys": len(_clients()),
        "rules_loaded": len(engine.rules),
        "objects_loaded": len(engine.world["objects"]),
        "suspects_loaded": len(engine.world["suspects"]),
        "endings_loaded": len(engine.world.get("endings", [])),
    }
    if probe:
        try:
            interpret_remote("ดูรอบๆ", GameState())
            info["llm_reachable"] = True
        except Exception as e:
            info["llm_reachable"] = False
            info["llm_error"] = str(e)[:200]
    return info


@app.get("/scene")
def scene(session: Session = Depends(session_for)):
    """ให้ frontend อ่านสถานะเกมและทะเบียนที่ผู้เล่นมีสิทธิ์เห็น

    Neural อ่าน story.json โดยตรง ส่วน endpoint นี้กรองวัตถุที่ยังไม่พบ
    """
    w = engine.world
    session.state = sync_clock(session.state)
    if engine.is_out_of_time(session.state):
        session.state = terminal_response(session.state).new_state
    return {
        "title": w.get("title"),
        "briefing": w.get("briefing"),
        "time_limit_seconds": engine.time_limit_seconds,
        "locations": {k: v.get("name_th") for k, v in w["locations"].items()},
        "objects": {k: v.get("name_th") for k, v in w["objects"].items() if engine.offerable(k, session.state)},
        "suspects": {k: v.get("name_th") for k, v in w["suspects"].items()},
        "actions": [a.value for a in ActionType],
        "rules_count": len(engine.rules),
        "initial_state": session.state.model_dump(),
    }


@app.post("/pillars")
def pillars(session: Session = Depends(session_for)):
    """ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน — ใช้วาดแถบความคืบหน้าใน frontend

    เป็นการอ่านสถานะเท่านั้น ไม่เกี่ยวกับการตัดสิน
    """
    if not session.state.ending_id:
        return {}
    state = session.state.model_copy(update={"discovered_evidence": session.submitted_evidence}) if session.submitted_evidence is not None else session.state
    return {sid: engine.pillar_status(sid, state) for sid in engine.world["suspects"]}


@app.post("/new-game")
def new_game(session: Session = Depends(session_for)):
    """Explicit restart; a normal page reload resumes the existing game."""
    session.state = GameState(started_at=time.time())
    session.submitted_evidence = None
    return {"new_state": session.state.model_dump()}


@app.post("/journal")
def journal(session: Session = Depends(session_for)):
    """Player-facing information only; undiscovered evidence stays hidden."""
    state = session.state
    w = engine.world
    case = state.model_copy(update={"discovered_evidence": session.submitted_evidence}) if session.submitted_evidence is not None else state
    return {
        "evidence": [{"id": eid, "name": w["objects"][eid]["name_th"],
                      "description": w["objects"][eid].get("description", "")}
                     for eid in state.discovered_evidence if eid in w["objects"]],
        "deductions": [{"id": did, "name": w["deductions"][did]["name_th"]}
                       for did in sorted(engine.deductions(case)) if state.ending_id],
        "visible": [{"id": eid, "name": obj["name_th"]} for eid, obj in w["objects"].items()
                    if not state.ending_id and obj.get("location") == state.current_location
                    and engine.offerable(eid, state)],
        "people": [{"id": sid, "name": sus["name_th"],
                    "here": sus.get("location") == state.current_location,
                    "interrogated": sid in state.interrogated_suspects}
                   for sid, sus in w["suspects"].items()],
        "pillars": {sid: engine.pillar_status(sid, case) for sid in w["suspects"]} if state.ending_id else {},
        "submitted_evidence": session.submitted_evidence,
        "case_closed": bool(state.ending_id),
        "background": [entry for entry in CASE_BACKGROUND
                       if all(e in state.discovered_evidence for e in entry["requires_evidence"])],
        "pillar_labels": w.get("pillar_labels", {}),
    }


CASE_BACKGROUND = [
    {"title": "สำนวนเบลล์เวเธอร์ ปี 1923", "requires_evidence": ["dossier_missing_file_c"],
     "text": "ปกสำนวนระบุเหตุรถไฟชนที่เบลล์เวเธอร์เมื่อสิบห้าปีก่อน คดีถูกปิดเป็นอุบัติเหตุ เอกสารแบ่งเป็นแฟ้ม A ถึง D แต่ช่อง C ว่างอยู่"},
    {"title": "คำให้การที่ไม่ตรงกับบัญชีผู้โดยสาร", "requires_evidence": ["secret_file"],
     "text": "เอเลียส เวนน์ บิดาของลิโอรา ให้การว่าเห็นผู้โดยสารคนที่แปดขึ้นขบวนในปี 1923 แต่บัญชีทางการระบุเจ็ดคน เอกสารนี้บันทึกความขัดแย้งของข้อมูล ยังไม่ได้อธิบายว่าเกิดจากอะไร"},
    {"title": "การรื้อคดีในปี 1938", "requires_evidence": ["judicial_transfer_order"],
     "text": "แคสเซียนกำลังนำสำนวนเบลล์เวเธอร์ส่งให้หน่วยงานตุลาการ หนังสือนำส่งลงวันที่ 14 พฤศจิกายน 1938 เป็นการนำคดีที่ปิดไปแล้วกลับเข้าสู่การตรวจสอบ"},
]


@app.post("/hint")
def hint(session: Session = Depends(session_for)):
    """A requested thinking prompt, never an automatic deduction or evidence grant."""
    found = set(session.state.discovered_evidence)
    if session.state.ending_id:
        return {"text": "คดีปิดแล้ว อ่านข้อสรุปในสมุดคดีได้"}
    if {"pocket_watch", "wall_clock"} <= found:
        return {"text": "นาฬิกาสองเรือนทำงานด้วยอะไร และอะไรทำให้แต่ละเรือนหยุด? ลองแยกเวลาที่วัตถุบันทึกออกจากเวลาที่พยานกล่าวถึง"}
    if "secret_file" in found:
        return {"text": "แยกสิ่งที่เอกสารเล่าเกี่ยวกับปี 1923 ออกจากสิ่งที่ยืนยันตำแหน่งของคนในคืนนี้"}
    if "vincent_blood" in found:
        return {"text": "คราบเลือดยืนยันการสัมผัสได้แค่ไหน? คำให้การเรื่องสภาพร่างอาจช่วยตรวจสอบลำดับเหตุการณ์"}
    return {"text": "จดสิ่งที่เห็นแยกจากคำบอกเล่า แล้วหาข้อมูลอีกแหล่งมาตรวจสอบเรื่องเดียวกัน"}


@app.post("/command", response_model=CommandResponse)
def handle_command(req: CommandRequest, session: Session = Depends(session_for)):
    # Legacy client snapshots are ignored; only the server can change this state.
    req.state = session.state.model_copy(deep=True)
    result = _handle_command(req)
    session.state = result.new_state
    if result.parsed.action == ActionType.ACCUSE and result.decision.allowed:
        session.submitted_evidence = list(req.submitted_evidence or [])
    return result


def _handle_command(req: CommandRequest):
    """ข้อความไทยหนึ่งประโยค -> คำตัดสินหนึ่งครั้ง -> สถานะใหม่หนึ่งก้อน"""

    req.state = sync_clock(req.state)
    if req.state.ending_id or engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text)
    # --- ขั้นที่ 1: ตีความ ---
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail="Neural: บริการแปลคำสั่งไม่ตอบกลับ กรุณาลองคำสั่งสั้น เช่น ไปตู้ 4 หรือตรวจตามชื่อในสมุดคดี") from e

    # Include time spent waiting for Gemini; expired commands cannot change the world.
    req.state = sync_clock(req.state)
    # --- ขั้นที่ 2: ตัดสินด้วยกฎ ---
    if parsed.action == ActionType.ACCUSE and not engine.is_out_of_time(req.state):
        decision = accusation_submission(engine, parsed, req.state, req.submitted_evidence)
    else:
        decision = engine.decide(parsed, req.state)

    # --- ขั้นที่ 3: อัปเดตสถานะเฉพาะเมื่อคำสั่งผ่าน ---
    if decision.allowed:
        new_state = apply_changes(req.state, decision.state_changes)
    elif decision.state_changes.get("ending"):
        # คำสั่งที่ถูกปฏิเสธไม่กินเวลาและไม่เปลี่ยนอะไร ยกเว้นกรณีที่ตัวกฎเองเป็นคนปิดคดี
        # (หมดเวลา) ตรงนั้นสถานะต้องปิดจริง ไม่ใช่แค่ขึ้นข้อความฉากจบแล้วเล่นต่อได้เรื่อยๆ
        # เช็คจาก state_changes ไม่ใช่จากชื่อกฎ เพิ่มกฎที่ปิดคดีได้ในอนาคตจึงไม่ต้องแก้ไฟล์นี้
        new_state = req.state.model_copy(update={"ending_id": decision.state_changes["ending"]})
    else:
        new_state = req.state

    # ตัวเลือกที่ยื่นกลับไปต้องไม่เอ่ยชื่อของที่ผู้เล่นยังหาไม่เจอ
    # ไม่งั้นคำสั่งกว้างๆ อย่าง "ปลดทุกอย่าง" จะกลายเป็นเมนูเฉลยชื่อของทั้งขบวน
    # LLM มองเห็นตารางทั้งโลก แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหนแล้ว จึงต้องกรองที่ชั้นนี้
    parsed.alternatives = [a for a in parsed.alternatives
                           if len(a.split()) == 2 and a.split()[0] in {v.value for v in ActionType}
                           and engine.offerable(a.split()[1], req.state)]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)


def terminal_response(state: GameState, text: str = "") -> CommandResponse:
    parsed = ParsedCommand(action=ActionType.UNKNOWN, raw_text=text)
    decision = engine.decide(parsed, state)
    ending = decision.state_changes.get("ending")
    if ending:
        state = state.model_copy(update={"ending_id": ending})
    return CommandResponse(parsed=parsed, decision=decision, new_state=state)


@app.post("/clock")
def game_clock(session: Session = Depends(session_for)):
    state = sync_clock(session.state)
    session.state = state
    if state.ending_id or engine.is_out_of_time(state):
        result = terminal_response(state)
        session.state = result.new_state
        return result.model_dump()
    return {"new_state": state.model_dump(), "decision": None, "parsed": None}


# ------------------------------------------------------------
# FRONTEND STATIC FILES MOUNT
# ต้องอยู่ท้ายสุด เพราะ mount ที่ "/" จะกลืนทุก path ที่ประกาศหลังจากนี้
# ------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
