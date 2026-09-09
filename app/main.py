"""
main.py — Interaction Layer / ท่อเชื่อมระบบ

ไฟล์นี้ไม่มีตรรกะของเกมและไม่มีตรรกะของ LLM
หน้าที่มีอย่างเดียวคือกำหนดเส้นทางของข้อมูล

    ข้อความไทย -> Neural ตีความ -> Symbolic ตัดสิน -> อัปเดตสถานะ -> ตอบ

รันด้วย:  uvicorn app.main:app --reload
เอกสาร API:  http://127.0.0.1:8000/docs
"""

from pathlib import Path
import time

from fastapi import FastAPI, HTTPException
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
from app.symbolic.engine import SymbolicEngine, apply_changes


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

from app.neural.gemini_client import _clients, interpret, llm_online


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
            interpret("ดูรอบๆ", GameState())
            info["llm_reachable"] = True
        except Exception as e:
            info["llm_reachable"] = False
            info["llm_error"] = str(e)[:200]
    return info


@app.get("/scene")
def scene():
    """ให้ frontend และ Neural Layer ดึงทะเบียน id จากแหล่งเดียวกัน

    ใช้ endpoint นี้ (หรืออ่าน story.json ตรงๆ) สร้างรายการ id
    แทนการพิมพ์มือ — กัน id ไม่ตรงกันระหว่างสองฝั่ง
    """
    w = engine.world
    return {
        "title": w.get("title"),
        "briefing": w.get("briefing"),
        "time_limit_seconds": w.get("time_limit_seconds"),
        "locations": {k: v.get("name_th") for k, v in w["locations"].items()},
        "objects": {k: v.get("name_th") for k, v in w["objects"].items()},
        "suspects": {k: v.get("name_th") for k, v in w["suspects"].items()},
        "actions": [a.value for a in ActionType],
        "rules_count": len(engine.rules),
        "initial_state": GameState(started_at=time.time()).model_dump(),
    }


@app.post("/pillars")
def pillars(state: GameState):
    """ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน — ใช้วาดแถบความคืบหน้าใน frontend

    เป็นการอ่านสถานะเท่านั้น ไม่เกี่ยวกับการตัดสิน
    """
    return {sid: engine.pillar_status(sid, state) for sid in engine.world["suspects"]}


@app.post("/journal")
def journal(state: GameState):
    """Player-facing information only; undiscovered evidence stays hidden."""
    w = engine.world
    return {
        "evidence": [{"id": eid, "name": w["objects"][eid]["name_th"],
                      "description": w["objects"][eid].get("description", "")}
                     for eid in state.discovered_evidence if eid in w["objects"]],
        "deductions": [{"id": did, "name": w["deductions"][did]["name_th"]}
                       for did in sorted(engine.deductions(state))],
        "visible": [{"id": eid, "name": obj["name_th"]} for eid, obj in w["objects"].items()
                    if not state.ending_id and obj.get("location") == state.current_location
                    and engine.offerable(eid, state)],
        "people": [{"id": sid, "name": sus["name_th"],
                    "here": sus.get("location") == state.current_location,
                    "interrogated": sid in state.interrogated_suspects}
                   for sid, sus in w["suspects"].items()],
        "pillars": {sid: engine.pillar_status(sid, state) for sid in w["suspects"]},
        "pillar_labels": w.get("pillar_labels", {}),
    }


@app.post("/command", response_model=CommandResponse)
def handle_command(req: CommandRequest):
    """ข้อความไทยหนึ่งประโยค -> คำตัดสินหนึ่งครั้ง -> สถานะใหม่หนึ่งก้อน"""

    req.state = sync_clock(req.state)
    if req.state.ending_id or engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text)
    # --- ขั้นที่ 1: ตีความ ---
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neural Layer ล้มเหลว: {e}")

    # Include time spent waiting for Gemini; expired commands cannot change the world.
    req.state = sync_clock(req.state)
    # --- ขั้นที่ 2: ตัดสินด้วยกฎ ---
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
                           if engine.offerable((a.split() or [""])[-1], req.state)]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)


def terminal_response(state: GameState, text: str = "") -> CommandResponse:
    parsed = ParsedCommand(action=ActionType.UNKNOWN, raw_text=text)
    decision = engine.decide(parsed, state)
    ending = decision.state_changes.get("ending")
    if ending:
        state = state.model_copy(update={"ending_id": ending})
    return CommandResponse(parsed=parsed, decision=decision, new_state=state)


@app.post("/clock")
def game_clock(state: GameState):
    state = sync_clock(state)
    if state.ending_id or engine.is_out_of_time(state):
        return terminal_response(state).model_dump()
    return {"new_state": state.model_dump(), "decision": None, "parsed": None}


# ------------------------------------------------------------
# FRONTEND STATIC FILES MOUNT
# ต้องอยู่ท้ายสุด เพราะ mount ที่ "/" จะกลืนทุก path ที่ประกาศหลังจากนี้
# ------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
