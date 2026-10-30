"""
main.py — Interaction Layer / ท่อเชื่อมระบบ

ไฟล์นี้เชื่อมระบบและจัดการ session เวลา และข้อมูลที่แสดงแก่ผู้เล่น
กฎการอนุญาตคำสั่งอยู่ใน Symbolic Engine

    ข้อความไทย -> Neural ตีความ -> Symbolic ตัดสิน -> อัปเดตสถานะ -> ตอบ

รันด้วย:  uvicorn app.main:app --reload
เอกสาร API:  http://127.0.0.1:8000/docs
"""

from pathlib import Path
from typing import Optional, Dict, List, Any
import logging
import time

from dotenv import load_dotenv
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.schemas import (
    ActionType,
    CommandRequest,
    CommandResponse,
    Decision,
    GameState,
    ParsedCommand,
    ReasoningStep,
    NewGameRequest,
)
from app.case_notes import evidence_entry, case_questions, conversation_summaries
from app.game_clock import sync_clock
from app.game_setup import new_game_state
from app.sessions import Session, session_for
from app.symbolic.engine import SymbolicEngine, apply_changes, accusation_submission
from app.profiler.tracker import BehaviorTracker
from app.profiler.adaptation import DynamicAdaptationEngine
from app.profiler.telemetry import save_session_telemetry, load_all_session_summaries
from app.cases import (
    AVAILABLE_CASES,
    CASE_METADATA,
    get_available_cases,
    get_engine,
    get_random_case_id,
    load_case_data,
    should_randomize,
)


app = FastAPI(title="NeSy-Escape API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: จำกัดโดเมนก่อน deploy จริง
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".html", ".js", ".css")) or path in ("/", ""):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


engine = SymbolicEngine()
MAX_SEQUENCE_STEPS = 4
adaptation_engine = DynamicAdaptationEngine()
trackers: dict[str, BehaviorTracker] = {}
latest_profiles: dict[str, dict] = {}


def engine_for_session(session: Session) -> SymbolicEngine:
    """ดึง SymbolicEngine ที่ถูกต้องสำหรับคดีของเซสชันนี้"""
    cid = getattr(session.state, "case_id", None) or getattr(session, "case_id", "case_01_gideon")
    return get_engine(cid)


def engine_for_state(state: GameState) -> SymbolicEngine:
    """ดึง SymbolicEngine ที่ถูกต้องสำหรับ GameState นี้"""
    cid = getattr(state, "case_id", None) or "case_01_gideon"
    return get_engine(cid)


def get_tracker(session_id: str | None = None, eng: SymbolicEngine | None = None) -> BehaviorTracker:
    """ดึงหรือสร้างตัวติดตามพฤติกรรมผู้เล่น (BehaviorTracker) ประจำเซสชัน"""
    sid = session_id or "default"
    active_engine = eng or engine
    if sid not in trackers:
        trackers[sid] = BehaviorTracker(
            session_id=sid,
            total_locations=len(active_engine.world.get("locations", {})),
            total_evidence=sum(1 for v in active_engine.world.get("objects", {}).values() if v.get("type") == "evidence"),
        )
    return trackers[sid]


def get_current_profile(session_id: str | None = None, state: GameState | None = None) -> dict:
    """ดึงข้อมูลโปรไฟล์ผู้เล่นล่าสุดพร้อมอัปเดตสถิติพฤติกรรม"""
    sid = session_id or "default"
    if sid in latest_profiles:
        return latest_profiles[sid]
    tracker = get_tracker(sid)
    if state is None:
        state = GameState()
    profile = tracker.update_profile(state)
    latest_profiles[sid] = profile.model_dump()
    return latest_profiles[sid]


# ============================================================
# สะพานไปยัง NEURAL LAYER
# main.py เรียกใช้แค่ interpret() และไม่สนใจว่าข้างในทำอะไร
# ตราบใดที่คืนค่าตรงตาม schema จะเปลี่ยนโมเดลหรือ prompt ก็ได้โดยไม่กระทบไฟล์นี้
# ห้ามให้ชั้นนั้นตัดสินว่าอนุญาตหรือไม่ ParsedCommand จึงไม่มีฟิลด์นั้นโดยเจตนา
# ============================================================

from app.neural.gemini_client import (
    NeuralQuotaExceeded,
    NeuralUnavailable,
    _clients,
    get_api_status,
    interpret as interpret_remote,
    llm_online,
)
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
        "api_status": get_api_status(),
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


@app.get("/cases")
def list_cases():
    """คืนรายการคดีคู่ขนานทั้งหมดที่มีในระบบ"""
    return {"cases": get_available_cases()}


@app.get("/scene")
def scene(session: Session = Depends(session_for)):
    """ให้ frontend อ่านสถานะเกมและทะเบียนที่ผู้เล่นมีสิทธิ์เห็น"""
    engine = engine_for_session(session)
    w = engine.world
    session.state = sync_clock(session.state)
    if engine.is_out_of_time(session.state):
        session.state = terminal_response(session.state, engine=engine).new_state
    return {
        "case_id": session.case_id,
        "case_info": CASE_METADATA.get(session.case_id, {}),
        "title": w.get("title"),
        "briefing": w.get("briefing"),
        "opening_scene": engine.narrative_scene("boarding", session.state)
                         if session.state.started_at is None and not session.state.ending_id else None,
        "time_limit_seconds": engine.time_limit_seconds,
        "locations": {k: v.get("name_th") for k, v in w["locations"].items()},
        "objects": {k: v.get("name_th") for k, v in w["objects"].items() if engine.offerable(k, session.state)},
        "suspects": {k: v.get("name_th") for k, v in w["suspects"].items()},
        "suspect_locations": {k: v.get("location") for k, v in w["suspects"].items()},
        "accusable_suspects": [k for k, v in w["suspects"].items() if v.get("accusable", True)],
        "max_submitted_evidence": w.get("max_submitted_evidence", 15),
        "restricted_locations": [k for k, v in w["locations"].items() if v.get("restricted")],
        "actions": [a.value for a in ActionType],
        "rules_count": len(engine.rules),
        "api_status": get_api_status(),
        "initial_state": session.state.model_dump(),
        "profile": get_current_profile(session.state.session_id or "default", session.state),
    }


@app.post("/pillars")
def pillars(session: Session = Depends(session_for)):
    """ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน — ใช้วาดแถบความคืบหน้าใน frontend"""
    if not session.state.ending_id:
        return {}
    engine = engine_for_session(session)
    state = session.state.model_copy(update={"discovered_evidence": session.submitted_evidence}) if session.submitted_evidence is not None else session.state
    return {sid: engine.pillar_status(sid, state) for sid, person in engine.world["suspects"].items() if person.get("accusable", True)}


@app.post("/new-game")
def new_game(
    req: Optional[NewGameRequest] = None,
    case_id: Optional[str] = None,
    session: Session = Depends(session_for),
):
    """เริ่มเล่นคดีใหม่: สุ่มคดีหรือเลือกคดีที่กำหนด รีเซ็ตสถานะเกม ประวัติการอนุมาน และข้อมูลโปรไฟล์ผู้เล่น"""
    session_id = session.state.session_id
    chosen_case = None
    if req and req.case_id:
        chosen_case = req.case_id
    elif case_id:
        chosen_case = case_id

    if chosen_case == "random" or (req and req.random):
        chosen_case = get_random_case_id(exclude=session.case_id)
    elif not chosen_case:
        if should_randomize():
            chosen_case = get_random_case_id(exclude=session.case_id)
        else:
            chosen_case = getattr(session, "case_id", "case_01_gideon") or "case_01_gideon"

    if chosen_case not in AVAILABLE_CASES:
        chosen_case = "case_01_gideon"

    session.case_id = chosen_case
    case_engine = get_engine(chosen_case)
    session.state = new_game_state(case_engine.world, case_id=chosen_case).model_copy(
        update={"session_id": session_id, "case_id": chosen_case}
    )
    if session_id:
        trackers.pop(session_id, None)
        latest_profiles.pop(session_id, None)
    session.submitted_evidence = None
    session.inference_attempts.clear()
    return {
        "new_state": session.state.model_dump(),
        "case_id": chosen_case,
        "case_info": CASE_METADATA.get(chosen_case, {}),
    }


@app.post("/start")
def start_game(session: Session = Depends(session_for)):
    """เริ่มนับเวลานาฬิกาคดี: ทำงานเมื่อผู้เล่นอ่านบทนำจบและเริ่มสืบสวนจริง"""
    if session.state.started_at is None and not session.state.ending_id:
        session.state = session.state.model_copy(update={"started_at": time.time()})
    return {"new_state": session.state.model_dump()}


@app.post("/journal")
def journal(session: Session = Depends(session_for)):
    """ดึงข้อมูลสมุดคดีของผู้เล่น: แสดงเฉพาะหลักฐานและข้อมูลที่ค้นพบแล้ว ไม่เฉลยข้อมูลลับ"""
    state = session.state
    engine = engine_for_session(session)
    w = engine.world
    case = state.model_copy(update={"discovered_evidence": session.submitted_evidence}) if session.submitted_evidence is not None else state
    return {
        "case_id": session.case_id,
        "case_info": CASE_METADATA.get(session.case_id, {}),
        "evidence": [evidence_entry(w, eid) for eid in state.discovered_evidence if eid in w["objects"]],
        "inventory": [{"id": oid, "name": w["objects"][oid]["name_th"],
                       "description": w["objects"][oid].get("description", "")}
                      for oid in state.inventory if oid in w["objects"]],
        "questions": case_questions(w, state),
        "deductions": [{"id": did, "name": w["deductions"][did]["name_th"]}
                       for did in sorted(engine.deductions(case)) if state.ending_id],
        "visible": [{"id": eid, "name": obj["name_th"]} for eid, obj in w["objects"].items()
                    if not state.ending_id and obj.get("location") == state.current_location
                    and engine.offerable(eid, state)],
        "people": [{"id": sid, "name": sus["name_th"],
                    "here": sus.get("location") == state.current_location,
                    "location": sus.get("location"),
                    "accusable": sus.get("accusable", True),
                    "interrogated": sid in state.interrogated_suspects,
                    "encountered": bool(
                        state.ending_id
                        or sus.get("location") == state.current_location
                        or sus.get("location") in state.visited_locations
                        or sid in state.interrogated_suspects
                        or any(d.startswith(sid) for d in state.dialogue_history)
                    ),
                    "discovered": bool(
                        state.ending_id
                        or sus.get("location") == state.current_location
                        or sus.get("location") in state.visited_locations
                        or sid in state.interrogated_suspects
                        or any(d.startswith(sid) for d in state.dialogue_history)
                    ),
                    "topics": engine.dialogue_options(sid, state) if (
                        not state.ending_id and bool(
                            state.ending_id
                            or sus.get("location") == state.current_location
                            or sus.get("location") in state.visited_locations
                            or sid in state.interrogated_suspects
                            or any(d.startswith(sid) for d in state.dialogue_history)
                        )
                    ) else []}
                   for sid, sus in w["suspects"].items()],
        "pillars": {sid: engine.pillar_status(sid, case) for sid, person in w["suspects"].items() if person.get("accusable", True)} if state.ending_id else {},
        "inference_questions": engine.inference_questions(state) if not state.ending_id else [],
        "scene_followups": engine.narrative_followups(state),
        "validated_claims": [{"id": cid, "name": w.get("claims", {}).get(cid, {}).get("name_th", cid)} for cid in state.validated_claims],
        "max_submitted_evidence": w.get("max_submitted_evidence", 15),
        "submitted_evidence": session.submitted_evidence,
        "case_closed": bool(state.ending_id),
        "background": [entry for entry in CASE_BACKGROUND
                       if all(e in state.discovered_evidence for e in entry["requires_evidence"])],
        "pillar_labels": w.get("pillar_labels", {}),
        "profile": get_current_profile(state.session_id or "default", state),
    }


CASE_BACKGROUND = [
    {"title": "สำนวนเบลล์เวเธอร์ ปี 1923", "requires_evidence": ["dossier_missing_file_c"],
     "text": "ปกสำนวนระบุเหตุรถไฟชนที่เบลล์เวเธอร์เมื่อสิบห้าปีก่อน คดีถูกปิดเป็นอุบัติเหตุ เอกสารแบ่งเป็นแฟ้ม A ถึง D แต่ช่อง C ว่างอยู่"},
    {"title": "คำให้การที่ถูกตัดออกจากสำนวน", "requires_evidence": ["secret_file"],
     "text": "เอเลียส เวนน์ บิดาของลิโอรา รอดชีวิตจากเหตุปี 1923 และให้การถึงคำเตือนก่อนปล่อยรถ คำให้การถูกตัดออกจากสำนวน เขาเสียชีวิตในปี 1931 ลิโอราเก็บสำเนาไว้เพื่อคืนความน่าเชื่อถือให้บิดา เอกสารนี้อธิบายอดีต ยังไม่ยืนยันว่าใครฆ่าแคสเซียนคืนนี้"},
    {"title": "การรื้อคดีในปี 1938", "requires_evidence": ["judicial_transfer_order"],
     "text": "แคสเซียนกำลังนำสำนวนเบลล์เวเธอร์ส่งให้หน่วยงานตุลาการ หนังสือนำส่งลงวันที่ 14 พฤศจิกายน 1938 เป็นการนำคดีที่ปิดไปแล้วกลับเข้าสู่การตรวจสอบ"},
]


@app.post("/hint")
def hint(session: Session = Depends(session_for)):
    """ขอคำใบ้กระตุ้นการคิด: ให้คำแนะนำเชื่อมโยงตามหลักฐานที่พบแล้ว โดยไม่เฉลยคำตอบตรงๆ"""
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
    """ประมวลผลคำสั่งหลักของผู้เล่น:
    
    ขั้นตอนการทำงาน (Pipeline):
    1. รับข้อความภาษาไทย -> ส่งตีความ (interpret)
    2. ส่งผลที่ตีความได้ (ParsedCommand) ให้ SymbolicEngine ตรวจสอบกฎ
    3. บันทึกและวิเคราะห์พฤติกรรมผู้เล่น (Behavior Tracker & Profiler)
    4. ปรับแต่งข้อความตอบสนองเชิงพลวัต (Dynamic Adaptation Engine)
    5. อัปเดตสถานะเกม (GameState) และส่งผลลัพธ์กลับสู่หน้าเว็บ
    """
    # ละเว้น snapshot จาก client เพื่อป้องกันการแทรกแซงสถานะ: ยึดสถานะบนเซิร์ฟเวอร์เป็นหลักเสมอ
    engine = engine_for_session(session)
    req.state = session.state.model_copy(deep=True)
    result = _handle_command(req, engine=engine)
    if result.decision.allowed and result.parsed.action == ActionType.INTERROGATE:
        result.narrative_scene = engine.dialogue_scene(result.parsed, req.state)
    result.conversation_summaries = conversation_summaries(engine.world, req.state, result.new_state)
    session.state = result.new_state
    session_id = result.new_state.session_id or "default"
    tracker = get_tracker(session_id, eng=engine)
    pillars_status = {sid: engine.pillar_status(sid, result.new_state) for sid in engine.world["suspects"]}
    profile = tracker.record_turn(
        raw_input=req.text,
        parsed=result.parsed,
        decision=result.decision,
        state=result.new_state,
        pillars_status=pillars_status,
    )
    recent_violation_count = sum(1 for turn in tracker.turns[-3:] if not turn.allowed)
    is_looping = tracker.turns[-1].is_looping if tracker.turns else False
    result.decision, adaptive_note = adaptation_engine.adapt(
        decision=result.decision,
        parsed=result.parsed,
        state=result.new_state,
        profile=profile,
        is_looping=is_looping,
        recent_violation_count=recent_violation_count,
        consecutive_looping_count=profile.consecutive_looping_count,
        engine=engine,
    )
    if adaptive_note and tracker.turns:
        tracker.turns[-1].adaptive_note = adaptive_note
        if "Scaffolding" in adaptive_note:
            tracker.scaffolding_triggers += 1
    latest_profiles[session_id] = profile.model_dump()
    result.profile = latest_profiles[session_id]
    if result.new_state.ending_id:
        save_session_telemetry(tracker.get_summary(result.new_state))
    if result.parsed.action == ActionType.ACCUSE and (result.decision.allowed or result.new_state.ending_id):
        session.submitted_evidence = list(result.new_state.discovered_evidence)
    if result.parsed.action == ActionType.INFER and req.submitted_evidence is not None:
        session.inference_attempts.append({"claim": result.parsed.target,
            "evidence": list(req.submitted_evidence or []), "accepted": result.decision.allowed,
            "elapsed_seconds": result.new_state.elapsed_seconds})
        session.inference_attempts = session.inference_attempts[-200:]
    result.api_status = get_api_status()
    return result


@app.get("/reconstruction")
def reconstruction(session: Session = Depends(session_for)):
    """ดึงฉากทบทวนคดี (Case Reconstruction): เปิดให้อ่านเมื่อไขคดีสำเร็จด้วย True Ending"""
    if session.state.ending_id != "true_ending" or session.submitted_evidence is None:
        return {"scene": None}
    engine = engine_for_session(session)
    return {"scene": engine.narrative_scene("case_reconstruction", session.state,
                                           evidence_scope=session.submitted_evidence)}


@app.get("/study-export")
def study_export(session: Session = Depends(session_for)):
    """ส่งออกบันทึกข้อมูลการเล่นของเซสชันปัจจุบันสำหรับเก็บสถิติ"""
    engine = engine_for_session(session)
    return {"story_version": engine.world.get("content_version", engine.world.get("scene_id")),
            "mode": "nesy", "ending": session.state.ending_id,
            "elapsed_seconds": session.state.elapsed_seconds,
            "inference_attempts": list(session.inference_attempts),
            "submitted_evidence": session.submitted_evidence}


@app.get("/profiler/profile")
def get_player_profile(session_id: str = "default"):
    """ดึงข้อมูลโปรไฟล์ผู้เล่นล่าสุดและสถิติสะสม"""
    return get_current_profile(session_id)


@app.get("/research/telemetry")
def get_research_telemetry(session_id: str = "default"):
    """ดึงข้อมูล Telemetry รายเทิร์นของเซสชันเพื่องานวิจัย"""
    tracker = get_tracker(session_id)
    return {"session_id": tracker.session_id, "total_turns": len(tracker.turns),
            "turns": [turn.model_dump() for turn in tracker.turns]}


@app.get("/research/export")
def export_research_data():
    """ส่งออกรายการสรุปผลการเล่นของทุกเซสชันทั้งหมดที่บันทึกไว้"""
    return {"count": len(load_all_session_summaries()), "sessions": load_all_session_summaries()}


def _handle_command(req: CommandRequest, engine: SymbolicEngine | None = None):
    """ข้อความไทยหนึ่งประโยค -> คำตัดสินหนึ่งครั้ง -> สถานะใหม่หนึ่งก้อน"""
    active_engine = engine or engine_for_state(req.state)
    req.state = sync_clock(req.state)
    if req.state.ending_id or active_engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text, engine=active_engine)
    # --- ขั้นที่ 1: ตีความ ---
    api_error_note = None
    try:
        parsed = interpret(req.text, req.state)
    except NeuralQuotaExceeded as e:
        logging.getLogger(__name__).warning("interpret quota exceeded: %s", e)
        parsed = ParsedCommand(
            action=ActionType.UNKNOWN,
            raw_text=req.text,
            confidence=0.0,
            parser_mode="fallback",
        )
        api_error_note = "⚠️ **[Gemini API ติดโควตา/Rate Limit ชั่วคราว]** ระบบสลับเข้าโหมดออฟไลน์อัตโนมัติ กรุณารอสักครู่ หรือใช้คำสั่งเดี่ยว เช่น 'ไป ตู้ 3' หรือ 'ดูรอบๆ'"
    except NeuralUnavailable as e:
        logging.getLogger(__name__).warning("interpret failed: %s", e)
        parsed = ParsedCommand(
            action=ActionType.UNKNOWN,
            raw_text=req.text,
            confidence=0.0,
            parser_mode="fallback",
        )
        api_error_note = "⚠️ **[Gemini API ขัดข้องชั่วคราว]** ระบบสลับเข้าโหมดออฟไลน์อัตโนมัติ กรุณาลองใช้คำสั่งเดี่ยว เช่น 'ไป ตู้ 3' หรือ 'ดูรอบๆ'"

    # Include time spent waiting for Gemini; expired commands cannot change the world.
    req.state = sync_clock(req.state)
    if req.state.ending_id or active_engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text, engine=active_engine)
    # Accept the previous wire format, but execute a sequence in one place only.
    if parsed.action == ActionType.SEQUENCE or (
        parsed.action == ActionType.AMBIGUOUS and parsed.sequence
    ):
        return execute_sequence(parsed, req.state, engine=active_engine)
    # --- ขั้นที่ 2: ตัดสินด้วยกฎ ---
    if parsed.action == ActionType.ACCUSE and not active_engine.is_out_of_time(req.state):
        decision = accusation_submission(active_engine, parsed, req.state, req.submitted_evidence)
    else:
        if parsed.action == ActionType.INFER:
            parsed = parsed.model_copy(update={"evidence": list(req.submitted_evidence or [])})
        decision = active_engine.decide(parsed, req.state)

    # --- ขั้นที่ 2.5: Closed-Loop NeSy Reflexion & Uncertainty Gating ---
    if not decision.allowed:
        from app.neural.reflexion import execute_reflexion_retry
        parsed, decision, _ = execute_reflexion_retry(
            raw_text=req.text,
            parsed=parsed,
            decision=decision,
            state=req.state,
            world_data=active_engine.world,
            decide_fn=lambda p, s: active_engine.decide(p, s),
            interpret_remote_fn=interpret_remote if llm_online() else None,
        )
        if parsed.confidence < 0.50 and parsed.action not in (ActionType.UNKNOWN, ActionType.AMBIGUOUS) and not decision.allowed:
            decision = decision.model_copy(
                update={"message": f"{decision.message}\n\n💡 *[ความเชื่อมั่นของ AI ต่ำ ({int(parsed.confidence * 100)}%)]*: ลองระบุชื่อเป้าหมายหรือคำสั่งให้ชัดเจนยิ่งขึ้น"}
            )

    # สะท้อนผลลัพธ์ของ Symbolic Constraint Repair สู่ Explainable Reasoning Chain (XAI)
    if parsed.repair_note and not any(r.rule_id == "SYMBOLIC_REPAIR" for r in decision.reasoning_chain):
        repair_step = ReasoningStep(
            rule_id="SYMBOLIC_REPAIR",
            description=f"Neuro-Symbolic Constraint Repair: {parsed.repair_note}",
            passed=True,
        )
        decision = decision.model_copy(
            update={"reasoning_chain": [repair_step] + decision.reasoning_chain}
        )

    if api_error_note and not decision.allowed:
        decision = decision.model_copy(
            update={"message": f"{decision.message}\n\n{api_error_note}"}
        )

    # --- ขั้นที่ 3: อัปเดตสถานะเฉพาะเมื่อคำสั่งผ่าน ---
    if decision.allowed:
        new_state = apply_changes(req.state, decision.state_changes)
        if new_state.started_at is None:
            new_state = new_state.model_copy(update={"started_at": time.time()})
    elif decision.state_changes.get("ending") or "failed_accusations" in decision.state_changes:
        # คำสั่งที่ถูกปฏิเสธไม่กินเวลาและไม่เปลี่ยนอะไร ยกเว้นสองอย่างที่ตัวกฎเองบันทึก
        # คือปิดคดี (หมดเวลา หรือกล่าวหาพลาดครบ) และนับครั้งที่กล่าวหาพลาด
        # เช็คจาก state_changes ไม่ใช่จากชื่อกฎ เพิ่มกฎที่ปิดคดีได้ในอนาคตจึงไม่ต้องแก้ไฟล์นี้
        new_state = req.state.model_copy(update={
            "ending_id": decision.state_changes.get("ending"),
            "failed_accusations": decision.state_changes.get("failed_accusations", req.state.failed_accusations)})
    else:
        new_state = req.state

    # ตัวเลือกที่ยื่นกลับไปต้องไม่เอ่ยชื่อของที่ผู้เล่นยังหาไม่เจอ
    # ไม่งั้นคำสั่งกว้างๆ อย่าง "ปลดทุกอย่าง" จะกลายเป็นเมนูเฉลยชื่อของทั้งขบวน
    # LLM มองเห็นตารางทั้งโลก แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหนแล้ว จึงต้องกรองที่ชั้นนี้
    # ยกเว้นคำสั่งพ่วง: ผู้เล่นเอ่ยชื่อเองทุกขั้น และของในขั้นหลังอาจมองเห็นได้หลังเดินไปถึงเท่านั้น
    # ทุกขั้นยังต้องผ่านกฎตอนทำจริงเหมือนพิมพ์เอง
    # แต่ sequence มาจาก LLM ถ้าเชื่อทั้งหมด "ไขคดีให้หน่อย" อาจได้ลิสต์ขั้นเฉลยยาวเหยียดที่หน้าเว็บทำให้เอง
    # จึงให้สิทธิ์นี้เฉพาะลิสต์สั้นแบบที่คนพิมพ์จริงในประโยคเดียว เกินกว่านั้นถือเป็นตัวเลือกธรรมดา
    if len(parsed.alternatives) > MAX_SEQUENCE_STEPS:
        parsed.sequence = False
    normalized_alts = []
    for a in parsed.alternatives:
        parts = a.split()
        if len(parts) == 1 and parts[0] in {v.value for v in ActionType}:
            normalized_alts.append(f"{parts[0]} null")
        elif len(parts) == 2:
            normalized_alts.append(a)
    parsed.alternatives = [a for a in normalized_alts
                           if a.split()[0] in {v.value for v in ActionType}
                           and (parsed.sequence or engine.offerable(a.split()[1], req.state))]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state, api_status=get_api_status())


def execute_sequence(parsed: ParsedCommand, state: GameState, engine: SymbolicEngine | None = None) -> CommandResponse:
    active_engine = engine or engine_for_state(state)
    """ประมวลผลคำสั่งพ่วงต่อเนื่องหลายขั้นตอน (Multi-step Command Sequence)

    คุณสมบัติ:
    1. ตรวจสอบความถูกต้องของทุกขั้นตอนล่วงหน้า (Fail-Fast Validation) ห้ามละเว้นหรือข้ามขั้นตอนที่ผิดรูปแบบ
    2. ดำเนินการคำสั่งทีละขั้นตอนตามลำดับ พร้อมบันทึกผลลัพธ์ลงใน sequence_steps สำหรับ Visual Playback
    3. หากพบคำสั่งที่มีผลกระทบย้อนกลับไม่ได้ (accuse, burn, infer) จะหยุดรอยืนยันจากผู้เล่นก่อน
    4. หากมีขั้นตอนใดไม่ผ่านกฎ จะหยุดการทำงานทันทีและยกเลิกขั้นตอนที่เหลือเพื่อป้องกัน State Corruption
    """
    parsed = parsed.model_copy(update={"action": ActionType.SEQUENCE, "sequence": False})
    actions = {a.value for a in ActionType} - {"sequence", "ambiguous", "unknown"}
    normalized_steps = []
    for step in parsed.alternatives:
        parts = step.strip().split()
        if len(parts) == 1 and parts[0] in actions:
            normalized_steps.append(f"{parts[0]} null")
        else:
            normalized_steps.append(step.strip())
    steps = normalized_steps
    parsed = parsed.model_copy(update={"alternatives": steps})
    # ตรวจสอบความถูกต้องของทุกขั้นตอนก่อนเริ่มเปลี่ยนสถานะ ห้ามแอบข้ามขั้นตอนที่ผิดรูปแบบเด็ดขาด
    if not steps or len(steps) > MAX_SEQUENCE_STEPS or any(
        len(step.split()) != 2 or step.split()[0] not in actions for step in steps
    ):
        parsed = parsed.model_copy(update={"alternatives": []})
        return CommandResponse(parsed=parsed, new_state=state, decision=Decision(
            allowed=False, message="คำสั่งต่อเนื่องยาวเกินไปหรือรูปแบบไม่ถูกต้อง กรุณาแบ่งเป็นคำสั่งสั้น ๆ",
            violated_rule_id="R_SEQUENCE_FORMAT"))
    messages, reasoning = [], []
    sequence_steps = []
    for index, step in enumerate(steps):
        state = sync_clock(state)
        if state.ending_id or active_engine.is_out_of_time(state):
            return terminal_response(state, parsed.raw_text, engine=active_engine)
        action, target = step.split()
        if action in {"accuse", "burn", "infer"}:
            return CommandResponse(parsed=parsed, new_state=state, pending_steps=steps[index:],
                sequence_steps=sequence_steps,
                decision=Decision(allowed=True,
                    message="\n\n".join(messages + ["ขั้นต่อไปต้องยืนยันก่อนดำเนินการ"]),
                    reasoning_chain=reasoning))
        from app.neural.repair import resolve_contextual_target
        resolved_target = resolve_contextual_target(action, target, state, active_engine.world, raw_text=parsed.raw_text)
        repair_note = None
        if resolved_target:
            if resolved_target != target:
                repair_note = f"ปรับเป้าหมายจาก '{target}' เป็น '{resolved_target}' เพื่อให้ตรงกับวัตถุที่มีอยู่ในห้อง"
            target = resolved_target

        command = ParsedCommand(action=ActionType(action), target=target, raw_text=step, confidence=1)
        decision = active_engine.decide(command, state)
        scene_playback = active_engine.dialogue_scene(command, state) if decision.allowed else None
        messages.append(decision.message)
        reasoning.extend(decision.reasoning_chain)

        if decision.allowed:
            state = apply_changes(state, decision.state_changes)
            if state.started_at is None:
                state = state.model_copy(update={"started_at": time.time()})
        elif decision.state_changes.get("ending"):
            state = state.model_copy(update={"ending_id": decision.state_changes["ending"]})

        sequence_steps.append({
            "step_index": index + 1,
            "action": action,
            "target": target,
            "location": state.current_location,
            "message": decision.message,
            "allowed": decision.allowed,
            "inventory": list(state.inventory),
            "discovered_evidence": list(state.discovered_evidence),
            "reasoning_chain": [r.model_dump() for r in decision.reasoning_chain],
            "violated_rule_id": decision.violated_rule_id,
            "repair_note": repair_note,
        })

        if decision.allowed and scene_playback:
            return CommandResponse(
                parsed=parsed,
                new_state=state,
                narrative_scene=scene_playback,
                pending_steps=steps[index + 1:],
                sequence_steps=sequence_steps,
                decision=Decision(allowed=True, message="\n\n".join(messages), reasoning_chain=reasoning),
            )
        if not decision.allowed or state.ending_id:
            remaining = len(steps) - index - 1
            if remaining and not state.ending_id:
                messages.append(f"จึงข้ามอีก {remaining} ขั้นตอนที่รออยู่")
            return CommandResponse(parsed=parsed, new_state=state, sequence_steps=sequence_steps,
                decision=Decision(allowed=decision.allowed, message="\n\n".join(messages),
                    reasoning_chain=reasoning, violated_rule_id=decision.violated_rule_id))
    return CommandResponse(parsed=parsed, new_state=state, sequence_steps=sequence_steps,
        decision=Decision(allowed=True, message="\n\n".join(messages), reasoning_chain=reasoning))


def terminal_response(state: GameState, text: str = "", engine: SymbolicEngine | None = None) -> CommandResponse:
    """สร้าง CommandResponse ปิดคดีเมื่อหมดเวลาหรือเกิดฉากจบของเกม"""
    active_engine = engine or engine_for_state(state)
    parsed = ParsedCommand(action=ActionType.UNKNOWN, raw_text=text)
    decision = active_engine.decide(parsed, state)
    ending = decision.state_changes.get("ending")
    if ending:
        state = state.model_copy(update={"ending_id": ending})
    return CommandResponse(parsed=parsed, decision=decision, new_state=state)


@app.post("/clock")
def game_clock(session: Session = Depends(session_for)):
    """ซิงค์เวลาและตรวจสอบการหมดเวลาของคดี (Investigation Deadline Check)"""
    engine = engine_for_session(session)
    state = sync_clock(session.state)
    session.state = state
    if state.ending_id:
        result = terminal_response(state, engine=engine)
        return result.model_dump()
    if engine.is_out_of_time(state):
        result = terminal_response(state, engine=engine)
        session.state = result.new_state
        session_id = result.new_state.session_id or "default"
        tracker = get_tracker(session_id, eng=engine)
        profile = tracker.record_turn(
            raw_input="timeout",
            parsed=result.parsed,
            decision=result.decision,
            state=result.new_state,
            pillars_status={sid: engine.pillar_status(sid, result.new_state) for sid in engine.world["suspects"]},
        )
        latest_profiles[session_id] = profile.model_dump()
        result.profile = latest_profiles[session_id]
        save_session_telemetry(tracker.get_summary(result.new_state))
        return result.model_dump()
    return {"new_state": state.model_dump(), "decision": None, "parsed": None}


# ------------------------------------------------------------
# FRONTEND STATIC FILES MOUNT
# ต้องอยู่ท้ายสุด เพราะ mount ที่ "/" จะกลืนทุก path ที่ประกาศหลังจากนี้
# ------------------------------------------------------------
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
ART_DIR = Path(__file__).resolve().parents[1] / "assets" / "nocturne-stylized-v2"
if ART_DIR.exists():
    app.mount("/game-art", StaticFiles(directory=str(ART_DIR)), name="game-art")
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
