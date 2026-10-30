"""
app/sessions.py — ระบบจัดการเซสชันผู้เล่นบนเซิร์ฟเวอร์ (Server-side Session Management)

คุณสมบัติ:
- ควบคุมการเข้าถึงสถานะเกมแบบ Concurrency ด้วย per-session Lock
- จดจำเซสชันผ่าน HTTP-Only Cookie ป้องกันการปลอมแปลง
- รองรับ Read-only Snapshot สำหรับ Endpoint ที่อ่านอย่างเดียว (/journal, /hint, /pillars)
  เพื่อไม่ให้คำสั่งที่รอ LLM ประมวลผลไปบล็อกการเปิดสมุดคดีของผู้เล่น
- ล้างเซสชันที่หมดอายุ (TTL 24 ชม.) อัตโนมัติ
- รองรับการผูกคดีคู่ขนาน (Parallel Cases) ประจำเซสชัน
"""
from dataclasses import dataclass, field
from threading import Lock
import secrets
import time
from typing import Dict, List, Optional

from fastapi import HTTPException, Request, Response
from app.schemas import GameState
from app.game_setup import new_game_state

COOKIE = "nesy_session"
TTL = 24 * 60 * 60  # อายุเซสชัน 24 ชั่วโมง
MAX_SESSIONS = 1000  # เพดานจำนวนเซสชันพร้อมกันสูงสุด


@dataclass
class Session:
    """โครงสร้างข้อมูลจัดเก็บสถานะของผู้เล่นแต่ละคนในหน่วยความจำ"""
    state: GameState = field(default_factory=new_game_state)
    case_id: str = "case_01_gideon"
    submitted_evidence: Optional[List[str]] = None
    inference_attempts: List[dict] = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)
    lock: Lock = field(default_factory=Lock)


# ทะเบียนเก็บ Session ทั้งหมดในหน่วยความจำของโปรเซส
sessions: Dict[str, Session] = {}
registry_lock = Lock()


def session_for(request: Request, response: Response):
    """FastAPI Dependency: ค้นหาหรือสร้าง Session สำหรับคำร้องขอนี้

    - หากเป็น Endpoint อ่านอย่างเดียว (/journal, /hint, /pillars) จะคืนค่า Snapshot ทันที
      โดยไม่ต้องรอปลด Lock ของคำสั่งหลัก
    - สำหรับ Endpoint แก้ไขสถานะ จะถือ Lock ประจำ Session ไว้เพื่อป้องกัน Race Condition
    """
    token = request.cookies.get(COOKIE)
    now = time.monotonic()
    with registry_lock:
        # กวาดล้างเซสชันเก่าที่หมดอายุ
        for key, value in list(sessions.items()):
            if now - value.touched > TTL and value.lock.acquire(blocking=False):
                try:
                    del sessions[key]
                finally:
                    value.lock.release()

        session = sessions.get(token)
        if session is None:
            # อนุญาตให้สร้างเซสชันใหม่ได้เฉพาะเมื่อเรียก /scene เท่านั้น
            if request.url.path != "/scene":
                raise HTTPException(401, "เกมหมดอายุ กรุณาโหลดหน้าเกมใหม่")
            if len(sessions) >= MAX_SESSIONS:
                raise HTTPException(503, "มีเกมใช้งานเต็ม กรุณาลองใหม่ภายหลัง")
            token = secrets.token_urlsafe(32)

            from app.cases import get_random_case_id, should_randomize, load_case_data, AVAILABLE_CASES
            requested_case = request.query_params.get("case_id")
            if requested_case and requested_case in AVAILABLE_CASES:
                chosen_case = requested_case
            elif should_randomize():
                chosen_case = get_random_case_id()
            else:
                chosen_case = "case_01_gideon"

            case_world = load_case_data(chosen_case)
            session = sessions[token] = Session(
                case_id=chosen_case,
                state=new_game_state(case_world, case_id=chosen_case)
            )
            session.state = session.state.model_copy(update={"session_id": token, "case_id": chosen_case})
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=TTL,
            )
        session.touched = now

    # Endpoint เหล่านี้อ่านเฉพาะ Snapshot แบบ Immutable
    # การเรียก LLM ที่ช้าต้องไม่บล็อกผู้เล่นจากการเปิดสมุดคดีหรือขอดูคำใบ้
    if request.url.path in ("/journal", "/hint", "/pillars"):
        snapshot = Session(
            state=session.state.model_copy(deep=True),
            case_id=session.case_id,
            submitted_evidence=(
                list(session.submitted_evidence)
                if session.submitted_evidence is not None
                else None
            ),
        )
        yield snapshot
        return

    # ล็อกเฉพาะสำหรับคำสั่งที่เปลี่ยนแปลงสถานะ
    with session.lock:
        yield session
        session.touched = time.monotonic()
