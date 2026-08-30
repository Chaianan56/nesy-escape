"""
app/main.py — Interaction Layer / ท่อเชื่อมระบบ (Main Pipeline)

หน้าที่:
- ทำหน้าที่เป็นจุดรับส่งข้อมูลหลัก (FastAPI Backend)
- เชื่อมต่อกระบวนการทำงาน 3 ขั้นตอน:
  1. Neural Layer (Gemini API)   : แปลงข้อความภาษาไทยของผู้เล่น -> ParsedCommand
  2. Symbolic Layer (Engine)     : ตรวจสอบกฎการเล่นและตัดสินผล -> Decision
  3. Game State Updates          : อัปเดตสถานะเกมหากคำสั่งได้รับการอนุมัติ
- บริการไฟล์เว็บ Frontend (HTML, CSS, JS) ที่เส้นทาง Root (`/`)
"""

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    ActionType,
    CommandRequest,
    CommandResponse,
    GameState,
)
from app.neural.gemini_client import interpret, llm_online
from app.symbolic.engine import SymbolicEngine, apply_changes

# สร้างแอปพลิเคชัน FastAPI สำหรับบริการ Web API
app = FastAPI(title="NeSy-Escape API", version="0.1")

# ตั้งค่า CORS Middleware เพื่อให้ Frontend เรียกใช้ API ได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# โหลด Symbolic Engine สำหรับตรวจกฎของเกม
engine = SymbolicEngine()


@app.get("/health")
def health():
    """ตรวจสอบความพร้อมของระบบ และเช็กสถานะการเชื่อมต่อ Gemini API"""
    return {
        "status": "ok",
        "llm_online": llm_online(),
        "rules_loaded": len(engine.rules),
        "objects_loaded": len(engine.world["objects"]),
    }


@app.get("/scene")
def scene():
    """ดึงข้อมูลฉากเริ่มต้น ทะเบียน ID และข้อความเกริ่นนำคดีสืบสวน"""
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


@app.post("/command", response_model=CommandResponse)
def handle_command(req: CommandRequest):
    """API หลักสำหรับรับคำสั่งผู้เล่น (Pipeline: Neural Interpret -> Symbolic Decide -> State Update)"""
    
    # ------------------------------------------------------------
    # ขั้นที่ 1: NEURAL LAYER — แปลงภาษาไทยดิบเป็นโครงสร้าง ParsedCommand
    # ------------------------------------------------------------
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neural Layer ตีความล้มเหลว: {e}")

    # ------------------------------------------------------------
    # ขั้นที่ 2: SYMBOLIC LAYER — ตรวจสอบกฎเกณฑ์ของเกมและตัดสินใจ
    # ------------------------------------------------------------
    decision = engine.decide(parsed, req.state)

    # ------------------------------------------------------------
    # ขั้นที่ 3: STATE UPDATE — อัปเดตสถานะเกมหากคำสั่งได้รับการอนุมัติ (allowed = True)
    # ------------------------------------------------------------
    new_state = apply_changes(req.state, decision.state_changes) if decision.allowed else req.state

    # ตัวเลือกที่ยื่นกลับไปต้องไม่เอ่ยชื่อของที่ผู้เล่นยังหาไม่เจอ
    # ไม่งั้นคำสั่งกว้างๆ อย่าง "ปลดทุกอย่าง" จะกลายเป็นเมนูเฉลยชื่อของทั้งขบวน
    # LLM มองเห็นตารางทั้งโลก แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหนแล้ว จึงต้องกรองที่ชั้นนี้
    parsed.alternatives = [a for a in parsed.alternatives
                           if engine.offerable((a.split() or [""])[-1], req.state)]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)


# ------------------------------------------------------------
# FRONTEND STATIC FILES MOUNT
# บริการไฟล์ HTML/CSS/JS สำหรับ Web UI
# ------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")