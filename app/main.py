"""
main.py — Interaction Layer / ท่อเชื่อมระบบ

ไฟล์นี้เชื่อมระบบและจัดการ session เวลา และข้อมูลที่แสดงแก่ผู้เล่น
กฎการอนุญาตคำสั่งอยู่ใน Symbolic Engine

    ข้อความไทย -> Neural ตีความ -> Symbolic ตัดสิน -> อัปเดตสถานะ -> ตอบ

รันด้วย:  uvicorn app.main:app --reload
เอกสาร API:  http://127.0.0.1:8000/docs
"""

from pathlib import Path
import logging
import time

from fastapi import FastAPI, HTTPException, Depends
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
from app.case_notes import evidence_entry, case_questions, conversation_summaries
from app.game_clock import sync_clock
from app.game_setup import new_game_state
from app.sessions import Session, session_for
from app.symbolic.engine import SymbolicEngine, apply_changes, accusation_submission
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
MAX_SEQUENCE_STEPS = 4
adaptation_engine = DynamicAdaptationEngine()
trackers: dict[str, BehaviorTracker] = {}
latest_profiles: dict[str, dict] = {}


def get_tracker(session_id: str | None = None) -> BehaviorTracker:
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
    return {sid: engine.pillar_status(sid, state) for sid, person in engine.world["suspects"].items() if person.get("accusable", True)}


@app.post("/new-game")
def new_game(session: Session = Depends(session_for)):
    """Explicit restart; a normal page reload resumes the existing game."""
    session_id = session.state.session_id
    session.state = new_game_state(engine.world).model_copy(update={"session_id": session_id})
    if session_id:
        trackers.pop(session_id, None)
        latest_profiles.pop(session_id, None)
    session.submitted_evidence = None
    session.inference_attempts.clear()
    return {"new_state": session.state.model_dump()}


@app.post("/start")
def start_game(session: Session = Depends(session_for)):
    if session.state.started_at is None and not session.state.ending_id:
        session.state = session.state.model_copy(update={"started_at": time.time()})
    return {"new_state": session.state.model_dump()}


@app.post("/journal")
def journal(session: Session = Depends(session_for)):
    """Player-facing information only; undiscovered evidence stays hidden."""
    state = session.state
    w = engine.world
    case = state.model_copy(update={"discovered_evidence": session.submitted_evidence}) if session.submitted_evidence is not None else state
    return {
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
                    "topics": engine.dialogue_options(sid, state) if not state.ending_id else [],
                    "interrogated": sid in state.interrogated_suspects}
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
    if result.decision.allowed and result.parsed.action == ActionType.INTERROGATE:
        result.narrative_scene = engine.dialogue_scene(result.parsed, req.state)
    result.conversation_summaries = conversation_summaries(engine.world, req.state, result.new_state)
    session.state = result.new_state
    session_id = result.new_state.session_id or "default"
    tracker = get_tracker(session_id)
    recent_violation_count = sum(1 for turn in tracker.turns[-3:] if not turn.allowed)
    pillars_status = {sid: engine.pillar_status(sid, result.new_state) for sid in engine.world["suspects"]}
    profile = tracker.record_turn(
        raw_input=req.text,
        parsed=result.parsed,
        decision=result.decision,
        state=result.new_state,
        pillars_status=pillars_status,
    )
    is_looping = tracker.turns[-1].is_looping if tracker.turns else False
    result.decision, adaptive_note = adaptation_engine.adapt(
        decision=result.decision,
        parsed=result.parsed,
        state=result.new_state,
        profile=profile,
        is_looping=is_looping,
        recent_violation_count=recent_violation_count,
    )
    if adaptive_note and tracker.turns:
        tracker.turns[-1].adaptive_note = adaptive_note
    latest_profiles[session_id] = profile.model_dump()
    result.profile = latest_profiles[session_id]
    if result.new_state.ending_id:
        save_session_telemetry(tracker.get_summary(result.new_state))
    if result.parsed.action == ActionType.ACCUSE and result.decision.allowed:
        session.submitted_evidence = list(req.submitted_evidence or [])
    if result.parsed.action == ActionType.INFER and req.submitted_evidence is not None:
        session.inference_attempts.append({"claim": result.parsed.target,
            "evidence": list(req.submitted_evidence or []), "accepted": result.decision.allowed,
            "elapsed_seconds": result.new_state.elapsed_seconds})
        session.inference_attempts = session.inference_attempts[-200:]
    return result


@app.get("/reconstruction")
def reconstruction(session: Session = Depends(session_for)):
    """An opt-in recap of the submitted successful case, never a pre-ending hint."""
    if session.state.ending_id != "true_ending" or session.submitted_evidence is None:
        return {"scene": None}
    return {"scene": engine.narrative_scene("case_reconstruction", session.state,
                                           evidence_scope=session.submitted_evidence)}


@app.get("/study-export")
def study_export(session: Session = Depends(session_for)):
    """Local session record, distinct from a claim that the player understood the case."""
    return {"story_version": engine.world.get("content_version", engine.world.get("scene_id")),
            "mode": "nesy", "ending": session.state.ending_id,
            "elapsed_seconds": session.state.elapsed_seconds,
            "inference_attempts": list(session.inference_attempts),
            "submitted_evidence": session.submitted_evidence}


@app.get("/profiler/profile")
def get_player_profile(session_id: str = "default"):
    """ดึงข้อมูลโปรไฟล์ผู้เล่นล่าสุดและสถิติสะสม"""
    if session_id in latest_profiles:
        return latest_profiles[session_id]
    tracker = get_tracker(session_id)
    state = GameState()
    dimensions = tracker._calculate_dimensions(state)
    scores, primary = tracker._classify_archetype(dimensions, state)
    metadata = ARCHETYPE_METADATA.get(primary, ARCHETYPE_METADATA[PlayerArchetype.BALANCED_INVESTIGATOR])
    return {
        "session_id": session_id,
        "primary_archetype": primary.value,
        "archetype_name_th": metadata["name_th"],
        "archetype_badge": metadata["badge"],
        "archetype_description_th": metadata["description_th"],
        "scores": scores.model_dump(),
        "dimensions": dimensions.model_dump(),
        "total_turns": 0,
    }


@app.get("/research/telemetry")
def get_research_telemetry(session_id: str = "default"):
    tracker = get_tracker(session_id)
    return {"session_id": tracker.session_id, "total_turns": len(tracker.turns),
            "turns": [turn.model_dump() for turn in tracker.turns]}


@app.get("/research/export")
def export_research_data():
    return {"count": len(load_all_session_summaries()), "sessions": load_all_session_summaries()}


def _handle_command(req: CommandRequest):
    """ข้อความไทยหนึ่งประโยค -> คำตัดสินหนึ่งครั้ง -> สถานะใหม่หนึ่งก้อน"""

    req.state = sync_clock(req.state)
    if req.state.ending_id or engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text)
    # --- ขั้นที่ 1: ตีความ ---
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        logging.getLogger(__name__).warning("interpret failed: %s", e)
        raise HTTPException(status_code=502, detail="Neural: บริการแปลคำสั่งไม่ตอบกลับ กรุณาลองคำสั่งสั้น เช่น ไปตู้ 4 หรือตรวจตามชื่อในสมุดคดี") from e

    # Include time spent waiting for Gemini; expired commands cannot change the world.
    req.state = sync_clock(req.state)
    if req.state.ending_id or engine.is_out_of_time(req.state):
        return terminal_response(req.state, req.text)
    # Accept the previous wire format, but execute a sequence in one place only.
    if parsed.action == ActionType.SEQUENCE or (
        parsed.action == ActionType.AMBIGUOUS and parsed.sequence
    ):
        return execute_sequence(parsed, req.state)
    # --- ขั้นที่ 2: ตัดสินด้วยกฎ ---
    if parsed.action == ActionType.ACCUSE and not engine.is_out_of_time(req.state):
        decision = accusation_submission(engine, parsed, req.state, req.submitted_evidence)
    else:
        if parsed.action == ActionType.INFER:
            parsed = parsed.model_copy(update={"evidence": list(req.submitted_evidence or [])})
        decision = engine.decide(parsed, req.state)

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
    parsed.alternatives = [a for a in parsed.alternatives
                           if len(a.split()) == 2 and a.split()[0] in {v.value for v in ActionType}
                           and (parsed.sequence or engine.offerable(a.split()[1], req.state))]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)


def execute_sequence(parsed: ParsedCommand, state: GameState) -> CommandResponse:
    parsed = parsed.model_copy(update={"action": ActionType.SEQUENCE, "sequence": False})
    actions = {a.value for a in ActionType} - {"sequence", "ambiguous", "unknown"}
    steps = parsed.alternatives
    # Validate the whole list before any mutation; never silently skip malformed steps.
    if not steps or len(steps) > MAX_SEQUENCE_STEPS or any(
        len(step.split()) != 2 or step.split()[0] not in actions for step in steps
    ):
        parsed = parsed.model_copy(update={"alternatives": []})
        return CommandResponse(parsed=parsed, new_state=state, decision=Decision(
            allowed=False, message="คำสั่งต่อเนื่องยาวเกินไปหรือรูปแบบไม่ถูกต้อง กรุณาแบ่งเป็นคำสั่งสั้น ๆ",
            violated_rule_id="R_SEQUENCE_FORMAT"))
    messages, reasoning = [], []
    for index, step in enumerate(steps):
        state = sync_clock(state)
        if state.ending_id or engine.is_out_of_time(state):
            return terminal_response(state, parsed.raw_text)
        action, target = step.split()
        if action in {"accuse", "burn", "infer"}:
            return CommandResponse(parsed=parsed, new_state=state, pending_steps=steps[index:],
                decision=Decision(allowed=True,
                    message="\n\n".join(messages + ["ขั้นต่อไปต้องยืนยันก่อนดำเนินการ"]),
                    reasoning_chain=reasoning))
        command = ParsedCommand(action=ActionType(action), target=target, raw_text=step, confidence=1)
        decision = engine.decide(command, state)
        scene_playback = engine.dialogue_scene(command, state) if decision.allowed else None
        messages.append(decision.message)
        reasoning.extend(decision.reasoning_chain)
        if decision.allowed:
            state = apply_changes(state, decision.state_changes)
            if state.started_at is None:
                state = state.model_copy(update={"started_at": time.time()})
            if scene_playback:
                return CommandResponse(parsed=parsed, new_state=state,
                    narrative_scene=scene_playback, pending_steps=steps[index + 1:],
                    decision=Decision(allowed=True, message="\n\n".join(messages), reasoning_chain=reasoning))
        elif decision.state_changes.get("ending"):
            state = state.model_copy(update={"ending_id": decision.state_changes["ending"]})
        if not decision.allowed or state.ending_id:
            remaining = len(steps) - index - 1
            if remaining and not state.ending_id:
                messages.append(f"จึงข้ามอีก {remaining} ขั้นตอนที่รออยู่")
            return CommandResponse(parsed=parsed, new_state=state, decision=Decision(
                allowed=decision.allowed, message="\n\n".join(messages),
                reasoning_chain=reasoning, violated_rule_id=decision.violated_rule_id))
    return CommandResponse(parsed=parsed, new_state=state, decision=Decision(
        allowed=True, message="\n\n".join(messages), reasoning_chain=reasoning))


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
    if state.ending_id:
        result = terminal_response(state)
        return result.model_dump()
    if engine.is_out_of_time(state):
        result = terminal_response(state)
        session.state = result.new_state
        session_id = result.new_state.session_id or "default"
        tracker = get_tracker(session_id)
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
