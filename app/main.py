"""
app/main.py — Main API & Pipeline Layer
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    ActionType,
    CommandRequest,
    CommandResponse,
    GameState,
)
from app.neural.gemini_client import interpret, llm_online
from app.symbolic.engine import SymbolicEngine, apply_changes

app = FastAPI(title="NeSy-Escape API", version="0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = SymbolicEngine()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_online": llm_online(),
        "rules_loaded": len(engine.rules),
        "objects_loaded": len(engine.world["objects"]),
    }


@app.get("/scene")
def scene():
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
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neural Layer error: {e}")

    decision = engine.decide(parsed, req.state)
    new_state = apply_changes(req.state, decision.state_changes) if decision.allowed else req.state
    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)