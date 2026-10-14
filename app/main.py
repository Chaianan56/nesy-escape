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
    Decision,
    GameState,
    ParsedCommand,
)
from app.game_clock import sync_clock
from app.symbolic.engine import SymbolicEngine, apply_changes
from app.profiler.tracker import BehaviorTracker
from app.profiler.adaptation import DynamicAdaptationEngine
from app.profiler.telemetry import save_session_telemetry, load_all_session_summaries
from app.profiler.schemas import ARCHETYPE_METADATA, PlayerArchetype


app = FastAPI(title="NeSy-Escape API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: จำกัดโดเมนก่อน deploy จริง
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SymbolicEngine()
adaptation_engine = DynamicAdaptationEngine()
trackers: dict = {}


def get_tracker(session_id: str = None) -> BehaviorTracker:
    sid = session_id or "default"
    if sid not in trackers:
        trackers[sid] = BehaviorTracker(
            session_id=sid,
            total_locations=len(engine.world.get("locations", {})),
            total_evidence=len(engine.world.get("objects", {})),
        )
    return trackers[sid]


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
    import uuid
    session_id = str(uuid.uuid4())[:8]
    return {
        "title": w.get("title"),
        "briefing": w.get("briefing"),
        "time_limit_seconds": w.get("time_limit_seconds"),
        "locations": {k: v.get("name_th") for k, v in w["locations"].items()},
        "objects": {k: v.get("name_th") for k, v in w["objects"].items()},
        "suspects": {k: v.get("name_th") for k, v in w["suspects"].items()},
        "actions": [a.value for a in ActionType],
        "rules_count": len(engine.rules),
        "initial_state": GameState(started_at=time.time(), session_id=session_id).model_dump(),
    }


@app.post("/pillars")
def pillars(state: GameState):
    """ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน — ใช้วาดแถบความคืบหน้าใน frontend

    เป็นการอ่านสถานะเท่านั้น ไม่เกี่ยวกับการตัดสิน
    """
    return {sid: engine.pillar_status(sid, state) for sid in engine.world["suspects"]}


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

    # --- โหมดพิเศษ: SEQUENCE (รันหลายคำสั่งตามลำดับใน Request เดียวอย่างรวดเร็วและปลอดภัย) ---
    if parsed.action == ActionType.SEQUENCE and parsed.alternatives:
        current_state = req.state
        combined_messages = []
        combined_reasoning = []
        pipeline_allowed = True
        violated_rule = None

        for idx, alt in enumerate(parsed.alternatives, 1):
            parts = alt.split()
            if not parts:
                continue
            try:
                sub_action = ActionType(parts[0].lower())
            except ValueError:
                continue
            sub_target = parts[1] if len(parts) > 1 else None
            sub_parsed = ParsedCommand(
                action=sub_action,
                target=sub_target,
                raw_text=alt,
                confidence=1.0,
            )

            current_state = sync_clock(current_state)
            sub_decision = engine.decide(sub_parsed, current_state)
            combined_reasoning.extend(sub_decision.reasoning_chain)

            if sub_decision.allowed:
                combined_messages.append(sub_decision.message)
                current_state = apply_changes(current_state, sub_decision.state_changes)
                if current_state.ending_id:
                    break
            else:
                pipeline_allowed = False
                violated_rule = sub_decision.violated_rule_id
                remaining_count = len(parsed.alternatives) - idx
                fail_msg = f"{sub_decision.message}"
                if remaining_count > 0:
                    fail_msg += f"\n(⚠️ ไม่สามารถดำเนินการต่อได้ จึงข้ามอีก {remaining_count} ขั้นตอนที่รออยู่)"
                combined_messages.append(fail_msg)
                break

        final_decision = Decision(
            allowed=pipeline_allowed,
            message="\n\n".join(combined_messages) if combined_messages else "ดำเนินการตามลำดับเสร็จสิ้น",
            reasoning_chain=combined_reasoning,
            violated_rule_id=violated_rule,
        )

        # บันทึกพฤติกรรมในโหมด SEQUENCE
        session_id = current_state.session_id or "default"
        tracker = get_tracker(session_id)
        pillars_status = {sid: engine.pillar_status(sid, current_state) for sid in engine.world["suspects"]}
        profile = tracker.record_turn(
            raw_input=req.text,
            parsed=parsed,
            decision=final_decision,
            state=current_state,
            pillars_status=pillars_status,
        )
        if current_state.ending_id:
            save_session_telemetry(tracker.get_summary(current_state))

        return CommandResponse(
            parsed=parsed,
            decision=final_decision,
            new_state=current_state,
            profile=profile.model_dump(),
        )

    # --- ขั้นที่ 2: ตัดสินด้วยกฎ (คำสั่งเดี่ยวปกติ) ---
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

    # บันทึกพฤติกรรมและปรับน้ำเสียง/คำแนะนำ (Behavior Profiler & Adaptation)
    session_id = new_state.session_id or "default"
    tracker = get_tracker(session_id)
    recent_violation_count = sum(1 for t in tracker.turns[-3:] if not t.allowed)
    pillars_status = {sid: engine.pillar_status(sid, new_state) for sid in engine.world["suspects"]}

    profile = tracker.record_turn(
        raw_input=req.text,
        parsed=parsed,
        decision=decision,
        state=new_state,
        pillars_status=pillars_status,
    )
    is_loop = tracker.turns[-1].is_looping if tracker.turns else False

    adapted_decision, adaptive_note = adaptation_engine.adapt(
        decision=decision,
        parsed=parsed,
        state=new_state,
        profile=profile,
        is_looping=is_loop,
        recent_violation_count=recent_violation_count,
    )
    if adaptive_note and tracker.turns:
        tracker.turns[-1].adaptive_note = adaptive_note

    if new_state.ending_id:
        save_session_telemetry(tracker.get_summary(new_state))

    # ตัวเลือกที่ยื่นกลับไปต้องไม่เอ่ยชื่อของที่ผู้เล่นยังหาไม่เจอ
    # ไม่งั้นคำสั่งกว้างๆ อย่าง "ปลดทุกอย่าง" จะกลายเป็นเมนูเฉลยชื่อของทั้งขบวน
    # LLM มองเห็นตารางทั้งโลก แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหนแล้ว จึงต้องกรองที่ชั้นนี้
    parsed.alternatives = [a for a in parsed.alternatives
                           if engine.offerable((a.split() or [""])[-1], req.state)]

    return CommandResponse(
        parsed=parsed,
        decision=adapted_decision,
        new_state=new_state,
        profile=profile.model_dump(),
    )


def terminal_response(state: GameState, text: str = "") -> CommandResponse:
    parsed = ParsedCommand(action=ActionType.UNKNOWN, raw_text=text)
    decision = engine.decide(parsed, state)
    ending = decision.state_changes.get("ending")
    if ending:
        state = state.model_copy(update={"ending_id": ending})
    tracker = get_tracker(state.session_id)
    profile_dump = None
    if tracker.turns:
        profile = tracker.record_turn(
            raw_input=text or "timeout",
            parsed=parsed,
            decision=decision,
            state=state,
        )
        profile_dump = profile.model_dump()
        save_session_telemetry(tracker.get_summary(state))
    return CommandResponse(parsed=parsed, decision=decision, new_state=state, profile=profile_dump)


@app.post("/clock")
def game_clock(state: GameState):
    state = sync_clock(state)
    if state.ending_id or engine.is_out_of_time(state):
        return terminal_response(state).model_dump()
    return {"new_state": state.model_dump(), "decision": None, "parsed": None}


@app.get("/profiler/profile")
def get_player_profile(session_id: str = "default"):
    """ดึงข้อมูลโปรไฟล์ผู้เล่นล่าสุดและสถิติสะสม"""
    tracker = get_tracker(session_id)
    dims = tracker._calculate_dimensions(GameState())
    scores, primary = tracker._classify_archetype(dims, GameState())
    meta = ARCHETYPE_METADATA.get(primary, ARCHETYPE_METADATA[PlayerArchetype.BALANCED_INVESTIGATOR])
    if tracker.turns:
        last_t = tracker.turns[-1]
        dummy_state = GameState(
            current_location=last_t.location,
            turn_count=len(tracker.turns),
            elapsed_seconds=last_t.elapsed_seconds,
        )
        profile = tracker.record_turn(
            raw_input=last_t.raw_input,
            parsed=ParsedCommand(action=ActionType(last_t.action), target=last_t.target, raw_text=last_t.raw_input),
            decision=Decision(allowed=last_t.allowed, message=""),
            state=dummy_state,
        )
        return profile.model_dump()
    return {
        "session_id": session_id,
        "primary_archetype": primary.value,
        "archetype_name_th": meta["name_th"],
        "archetype_badge": meta["badge"],
        "archetype_description_th": meta["description_th"],
        "scores": scores.model_dump(),
        "dimensions": dims.model_dump(),
        "total_turns": 0,
    }


@app.get("/research/telemetry")
def get_research_telemetry(session_id: str = "default"):
    """ดึง Telemetry รายเทิร์นสำหรับเซสชันที่ระบุ"""
    tracker = get_tracker(session_id)
    return {
        "session_id": tracker.session_id,
        "total_turns": len(tracker.turns),
        "turns": [t.model_dump() for t in tracker.turns],
    }


@app.get("/research/export")
def export_research_data():
    """ดึงข้อมูลประมวลผลสรุปทุกเซสชันเพื่องานวิจัย"""
    summaries = load_all_session_summaries()
    return {
        "count": len(summaries),
        "sessions": summaries,
    }


# ------------------------------------------------------------
# FRONTEND STATIC FILES MOUNT
# ต้องอยู่ท้ายสุด เพราะ mount ที่ "/" จะกลืนทุก path ที่ประกาศหลังจากนี้
# ------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
