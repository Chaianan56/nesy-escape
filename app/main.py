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
    ExperimentLog,
    GameState,
    ParsedCommand,
    ReasoningStep,
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

try:
    from app.neural.gemini_client import interpret, decide_autonomously
    NEURAL_READY = True
except ImportError:
    NEURAL_READY = False

    def interpret(text: str, state: GameState) -> ParsedCommand:
        """MOCK ชั่วคราว — ให้ระบบเดินได้ก่อนที่ Neural Layer จะเสร็จ

        รับรูปแบบ 'action target [instrument]' ตรงๆ เช่น 'unlock cabinet_03'
        ลบฟังก์ชันนี้ทิ้งได้เมื่อของจริงพร้อม
        """
        parts = text.strip().split()
        try:
            action = ActionType(parts[0].lower())
        except (ValueError, IndexError):
            return ParsedCommand(action=ActionType.UNKNOWN, raw_text=text, confidence=0.0)
        return ParsedCommand(
            action=action,
            target=parts[1] if len(parts) > 1 else None,
            instrument=parts[2] if len(parts) > 2 else None,
            raw_text=text,
            confidence=1.0,
        )

    def decide_autonomously(text, state, parsed) -> Decision:
        """MOCK ชั่วคราว — อนุญาตทุกอย่าง

        จงใจให้หลวมเพื่อให้เห็นภาพว่าโหมด A ต่างจาก B อย่างไร
        ห้ามใช้ค่านี้ในการทดลองจริงเด็ดขาด
        """
        return Decision(
            allowed=True,
            message="(mock) อนุมัติโดย Neural Layer",
            reasoning_chain=[
                ReasoningStep(rule_id="LLM_SELF", description="LLM ตัดสินด้วยตนเอง", passed=True)
            ],
            state_changes={},
        )


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "neural_ready": NEURAL_READY,
        "rules_loaded": len(engine.rules),
        "objects_loaded": len(engine.world["objects"]),
    }


@app.get("/scene")
def scene():
    """ให้ frontend และ Neural Layer ดึงทะเบียนวัตถุจากแหล่งเดียวกัน

    เพื่อนควรใช้ endpoint นี้ (หรืออ่าน story.json ตรงๆ) สร้างรายการ id
    ใส่ prompt แทนการพิมพ์มือ — กัน id ไม่ตรงกันระหว่างสองฝั่ง
    """
    return {
        "objects": {k: v.get("name_th") for k, v in engine.world["objects"].items()},
        "suspects": {k: v.get("name_th") for k, v in engine.world["suspects"].items()},
        "actions": [a.value for a in ActionType],
    }


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
# LOGGING — ทุกคำสั่งต้องถูกบันทึกเพื่อนำไปวิเคราะห์ด้วย pandas
# ============================================================

def _write_log(req: CommandRequest, parsed: ParsedCommand,
               decision: Decision, latency_ms: int) -> None:
    entry = ExperimentLog(
        command_id=str(uuid.uuid4())[:8],
        group="live",          # ตอนรันชุดทดสอบให้แทนที่ด้วย A/B/C/D
        mode=req.mode,
        raw_text=req.text,
        parsed=parsed,
        decision=decision,
        expected_allowed=decision.allowed,  # live ยังไม่มี ground truth
        latency_ms=latency_ms,
    )
    fname = LOG_DIR / f"{datetime.now():%Y%m%d}_mode_{req.mode.value}.jsonl"
    with fname.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")