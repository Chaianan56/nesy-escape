"""
main.py — Interaction Layer / ท่อเชื่อมระบบ

ไฟล์นี้ไม่มีตรรกะของเกมและไม่มีตรรกะของ LLM
หน้าที่มีอย่างเดียวคือกำหนด "เส้นทางของข้อมูล" ตามโหมดการทดลอง

    โหมด A (baseline) : ข้อความ -> Neural ตีความ + ตัดสินเอง       -> ตอบ
    โหมด B (proposed) : ข้อความ -> Neural ตีความ -> Symbolic ตัดสิน -> ตอบ

⚠️ ข้อกำหนดเชิงการทดลอง (ห้ามละเมิด)
    สองเส้นทางนี้ต้องใช้ LLM ตัวเดียวกันและ prompt ตีความชุดเดียวกัน
    ตัวแปรที่ต่างกันต้องมีเพียงตัวเดียวคือ "ใครเป็นผู้ตัดสิน"
    ถ้ามีอะไรอย่างอื่นต่างกัน ผลการทดลองจะชี้กลับไปที่สถาปัตยกรรมไม่ได้

รันด้วย:  uvicorn app.main:app --reload
เอกสาร API:  http://127.0.0.1:8000/docs
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    ActionType,
    CommandRequest,
    CommandResponse,
    Decision,
    GameState,
    ParsedCommand,
    SystemMode,
)
from app.symbolic.engine import SymbolicEngine, apply_changes

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

app = FastAPI(title="NeSy-Escape API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: จำกัดโดเมนก่อน deploy จริง
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SymbolicEngine()


# ============================================================
# สะพานไปยัง NEURAL LAYER  ← งานของเพื่อน
# ============================================================
# main.py เรียกใช้แค่สองฟังก์ชันนี้เท่านั้น และไม่สนใจว่าข้างในทำอะไร
# ตราบใดที่คืนค่าตรงตาม schema เพื่อนจะเปลี่ยนโมเดล เปลี่ยน prompt
# หรือรื้อข้างในใหม่หมดก็ได้ โดยไม่กระทบไฟล์นี้
#
#   app/neural/gemini_client.py ต้องมี:
#
#   def interpret(text: str, state: GameState) -> ParsedCommand
#       ใช้ทั้งโหมด A และ B — แปลงภาษาธรรมชาติเป็นคำสั่งเชิงโครงสร้าง
#       ห้ามตัดสินว่าอนุญาตหรือไม่ (ParsedCommand ไม่มีฟิลด์นั้นโดยเจตนา)
#
#   def decide_autonomously(text: str, state: GameState,
#                           parsed: ParsedCommand) -> Decision
#       ใช้เฉพาะโหมด A — ให้ LLM ตัดสินเองว่าอนุญาตหรือไม่
#       ต้องส่งกฎจาก rules.json เข้าไปใน prompt ให้ LLM อ่านเอง
#       เพื่อความยุติธรรมของการเปรียบเทียบ (LLM ต้อง "รู้กฎ" เท่ากับ symbolic
#       ต่างกันแค่ว่ามันไม่ถูกบังคับให้ทำตาม)
# ============================================================

from app.neural.gemini_client import interpret, decide_autonomously, llm_online


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_online": llm_online(),   # False = Neural Layer กำลังเดินด้วย fallback heuristic
        "rules_loaded": len(engine.rules),
        "objects_loaded": len(engine.world["objects"]),
    }


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
        "initial_state": GameState().model_dump(),
    }


@app.post("/pillars")
def pillars(state: GameState):
    """ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน — ใช้วาดแถบความคืบหน้าใน frontend

    เป็นการอ่านสถานะเท่านั้น ไม่เกี่ยวกับการตัดสิน
    """
    return {sid: engine.pillar_status(sid, state) for sid in engine.world["suspects"]}


@app.post("/command", response_model=CommandResponse)
def handle_command(req: CommandRequest):
    started = time.perf_counter()

    # --- ขั้นที่ 1: ตีความ (เหมือนกันทั้งสองโหมด) ---
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neural Layer ล้มเหลว: {e}")

    # --- ขั้นที่ 2: ตัดสิน (จุดเดียวที่สองโหมดต่างกัน) ---
    if req.mode == SystemMode.A_BASELINE:
        decision = decide_autonomously(req.text, req.state, parsed)
    else:
        decision = engine.decide(parsed, req.state)

    # --- ขั้นที่ 3: อัปเดตสถานะ ---
    new_state = apply_changes(req.state, decision.state_changes) if decision.allowed else req.state

    latency_ms = int((time.perf_counter() - started) * 1000)
    _write_log(req, parsed, decision, latency_ms)

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)


# ============================================================
# LOGGING — บันทึกการเล่นสด ไม่ใช่ข้อมูลการทดลอง
#
# ⚠️ ห้ามใช้ ExperimentLog กับการเล่นสดเด็ดขาด
#    ExperimentLog บังคับให้มี expected_allowed ซึ่งเป็น ground truth ที่ label
#    ไว้ล่วงหน้า การเล่นสดไม่มีสิ่งนั้น เดิมโค้ดนี้เติมด้วย decision.allowed
#    ซึ่งแปลว่า "คำตอบที่ถูกต้องคือคำตอบที่ระบบตอบมา" ทุกแถวจึงถูก 100% เสมอ
#    ถ้ามีใครเผลอเอาไฟล์นี้ไปรวมกับผลการทดลอง ตัวเลขในเปเปอร์จะเพี้ยนทันที
#
#    ข้อมูลการทดลองมาจาก run_experiment.py เท่านั้น และออกที่ไฟล์คนละชื่อกัน
# ============================================================

def _write_log(req: CommandRequest, parsed: ParsedCommand,
               decision: Decision, latency_ms: int) -> None:
    entry = {
        "command_id": str(uuid.uuid4())[:8],
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "source": "live_play",          # กันสับสนกับ log ของการทดลอง
        "mode": req.mode.value,
        "raw_text": req.text,
        "parsed": parsed.model_dump(),
        "decision": decision.model_dump(),
        "latency_ms": latency_ms,
    }
    fname = LOG_DIR / f"{datetime.now():%Y%m%d}_play_mode_{req.mode.value}.jsonl"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")