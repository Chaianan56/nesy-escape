"""
tests/test_narrative_api.py — ทดสอบการเปิดฉากบรรยายและสิทธิการเข้าถึงผ่าน API (Narrative Presentation API)

หน้าที่:
- ทดสอบว่าการเปิดฉาก (Opening Scene), ฉากเผชิญหน้า (Confrontation), และฉากทบทวนคดี (Reconstruction)
  แสดงผลตามสถานะความรู้และหลักฐานที่ค้นพบจริงบนเซิร์ฟเวอร์
- ทดสอบการตัดรอบเวลา (Timing) และการจัดการ Session ในการเข้าถึงฉากบรรยาย
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.schemas import ActionType, GameState, ParsedCommand
from app.sessions import COOKIE, sessions


WALKTHROUGH = json.loads(
    (Path(__file__).resolve().parents[1] / "data/walkthrough.json").read_text(encoding="utf-8")
)
SUPPORT = WALKTHROUGH["inference_evidence"]
LIE_EVIDENCE = ["postponed_meeting_claim", "staff_no_message"]


@pytest.fixture
def client(monkeypatch):
    sessions.clear()
    monkeypatch.setattr(main.time, "time", lambda: 1000)

    def no_remote_parser(*args):
        raise AssertionError("Narrative API tests must not call a model")

    monkeypatch.setattr(main, "interpret", no_remote_parser)
    with TestClient(main.app) as test_client:
        assert test_client.get("/scene").status_code == 200
        yield test_client
    sessions.clear()


def session(client):
    return sessions[client.cookies[COOKIE]]


def earned_state():
    return GameState(
        discovered_evidence=SUPPORT + LIE_EVIDENCE,
        validated_claims=["claim_two_times"],
        claim_evidence={"claim_two_times": list(SUPPORT)},
    )


def parse_as(monkeypatch, action, target=None, **kwargs):
    monkeypatch.setattr(main, "interpret", lambda text, state: ParsedCommand(
        action=action, target=target, raw_text=text, confidence=1, **kwargs
    ))


def test_opening_is_read_only_before_start_and_not_replayed_on_resume(client):
    before = session(client).state.model_dump()
    opening = client.get("/scene").json()["opening_scene"]
    assert opening["id"] == "boarding"
    assert len(opening["pages"]) == 4
    assert {item["id"] for page in opening["pages"] for item in page["evidence"]} == {
        "postponed_meeting_claim", "gideon_blackout_alibi"
    }
    assert session(client).state.model_dump() == before
    assert client.get("/scene").json()["opening_scene"] == opening
    assert client.post("/clock").json()["new_state"]["elapsed_seconds"] == 0
    assert client.post("/start").json()["new_state"]["started_at"] == 1000
    assert client.get("/scene").json()["opening_scene"] is None
    assert client.post("/journal").json()["scene_followups"] == []
    assert client.get("/reconstruction").json() == {"scene": None}


def test_forged_client_knowledge_does_not_unlock_scenes(client, monkeypatch):
    forged = earned_state().model_dump()
    forged["ending_id"] = "true_ending"
    forged["discovered_evidence"] = list(main.engine.world["objects"])
    before = session(client).state.model_dump()
    parse_as(monkeypatch, ActionType.INTERROGATE, "gideon_hart", topic="confrontation")
    result = client.post("/command", json={"text": "confront", "state": forged}).json()
    assert result["decision"]["allowed"] is False
    assert result["narrative_scene"] is None
    assert result["new_state"] == before
    assert client.post("/journal", json={"state": forged}).json()["scene_followups"] == []
    assert client.get("/reconstruction", params={"ending_id": "true_ending"}).json() == {"scene": None}


@pytest.mark.parametrize("missing", ["validated_claim", "claim_record", "clock", "lie_source"])
def test_raw_or_incomplete_knowledge_never_exposes_confrontation(client, monkeypatch, missing):
    state = earned_state()
    if missing == "validated_claim":
        state.validated_claims = []
        state.claim_evidence = {}
    elif missing == "claim_record":
        state.claim_evidence = {}
    else:
        state.discovered_evidence.remove("wall_clock" if missing == "clock" else "staff_no_message")
    session(client).state = state
    parse_as(monkeypatch, ActionType.INTERROGATE, "gideon_hart", topic="confrontation")
    assert client.post("/journal").json()["scene_followups"] == []
    result = client.post("/command", json={"text": "confront"}).json()
    assert result["decision"]["allowed"] is False
    assert result["narrative_scene"] is None
    assert result["new_state"] == state.model_dump()


def test_earned_followup_survives_other_location_and_is_consumed_by_dialogue(client, monkeypatch):
    state = earned_state()
    state.current_location = "first_class_car"
    session(client).state = state
    followups = client.post("/journal").json()["scene_followups"]
    assert len(followups) == 1
    assert followups[0]["person_id"] == "gideon_hart"
    assert followups[0]["location"] == "lounge_car"
    assert followups[0]["topic"] == "confrontation"
    assert "pages" not in followups[0]
    parse_as(monkeypatch, ActionType.INTERROGATE, "gideon_hart", topic="confrontation")
    denied = client.post("/command", json={"text": "confront from another car"}).json()
    assert not denied["decision"]["allowed"]
    assert denied["narrative_scene"] is None

    parse_as(monkeypatch, ActionType.MOVE, "lounge_car")
    assert client.post("/command", json={"text": "go back"}).json()["decision"]["allowed"]
    before = session(client).state.model_copy(deep=True)
    parse_as(monkeypatch, ActionType.INTERROGATE, "gideon_hart", topic="confrontation")
    result = client.post("/command", json={"text": "confront"}).json()
    assert result["decision"]["allowed"]
    assert result["narrative_scene"]["id"] == "gideon_confrontation"
    assert len(result["narrative_scene"]["pages"]) == 4
    assert all(item["id"] in before.discovered_evidence
               for page in result["narrative_scene"]["pages"] for item in page["evidence"])
    assert result["new_state"]["discovered_evidence"] == before.discovered_evidence
    assert result["new_state"]["validated_claims"] == before.validated_claims
    assert result["new_state"]["claim_evidence"] == before.claim_evidence
    assert result["new_state"]["turn_count"] == before.turn_count + 1
    assert "gideon_hart:confrontation" in result["new_state"]["dialogue_history"]
    assert result["new_state"]["ending_id"] is None
    assert client.post("/journal").json()["scene_followups"] == []
    assert client.get("/scene").json()["opening_scene"] is None


def test_ordinary_dialogue_does_not_attach_an_earned_but_unrequested_scene(client, monkeypatch):
    session(client).state = earned_state()
    parse_as(monkeypatch, ActionType.INTERROGATE, "gideon_hart", topic="account")
    result = client.post("/command", json={"text": "ask his account"}).json()
    assert result["decision"]["allowed"]
    assert result["narrative_scene"] is None
    assert client.post("/journal").json()["scene_followups"][0]["topic"] == "confrontation"


def test_true_ending_recap_uses_all_discovered_evidence(client, monkeypatch):
    state = earned_state()
    state.discovered_evidence = [eid for eid, obj in main.engine.world["objects"].items()
                                 if obj.get("type") == "evidence"]
    session(client).state = state
    parse_as(monkeypatch, ActionType.ACCUSE, "gideon_hart")
    result = client.post("/command", json={"text": "accuse"}).json()
    assert result["decision"]["allowed"]
    assert result["new_state"]["ending_id"] == "true_ending"
    assert result["narrative_scene"] is None  # Recap remains opt-in.
    assert session(client).submitted_evidence == state.discovered_evidence
    before = session(client).state.model_dump()
    recap = client.get("/reconstruction").json()["scene"]
    assert recap["id"] == "case_reconstruction"
    assert len(recap["pages"]) == 8
    assert {page["id"] for page in recap["pages"] if page["id"].startswith("contact_")} == {
        "contact_button_wax", "contact_tea_button", "contact_tea_wax"
    }
    assert all(item["id"] in state.discovered_evidence for page in recap["pages"] for item in page["evidence"])
    assert all(not any(key.startswith("requires_") for key in page) for page in recap["pages"])
    assert session(client).state.model_dump() == before
    assert client.post("/journal").json()["scene_followups"] == []
    assert client.get("/scene").json()["opening_scene"] is None
    assert client.post("/new-game").status_code == 200
    assert client.get("/reconstruction").json() == {"scene": None}


@pytest.mark.parametrize("ending", [None, "cold_arrival", "cold_justice", "the_scapegoat", "paranoia"])
def test_recap_is_unavailable_before_success_even_with_submitted_facts(client, ending):
    state = earned_state()
    state.ending_id = ending
    session(client).state = state
    session(client).submitted_evidence = WALKTHROUGH["winning_cases"]["button_wax"]
    assert client.get("/reconstruction").json() == {"scene": None}


def test_true_ending_without_submission_does_not_fall_back_to_full_inventory(client):
    state = earned_state()
    state.ending_id = "true_ending"
    session(client).state = state
    assert client.get("/reconstruction").json() == {"scene": None}


def test_scene_access_is_isolated_between_sessions(client):
    session(client).state = earned_state()
    assert client.post("/journal").json()["scene_followups"]
    with TestClient(main.app) as other:
        assert other.get("/reconstruction").status_code == 401
        assert other.get("/scene").status_code == 200
        assert other.post("/journal").json()["scene_followups"] == []
        assert other.get("/reconstruction").json() == {"scene": None}


def test_sequence_stops_at_scene_and_returns_unexecuted_remaining_steps(client, monkeypatch):
    state = earned_state()
    state.dialogue_history = ["gideon_hart:account", "gideon_hart:message"]
    session(client).state = state
    parse_as(monkeypatch, ActionType.SEQUENCE,
             alternatives=["interrogate gideon_hart", "move first_class_car"])
    result = client.post("/command", json={"text": "ask him, then go to the room"}).json()
    assert result["decision"]["allowed"]
    assert result["narrative_scene"]["id"] == "gideon_confrontation"
    assert result["pending_steps"] == ["move first_class_car"]
    assert result["new_state"]["current_location"] == "lounge_car"
    assert result["new_state"]["turn_count"] == 1
    assert result["new_state"]["discovered_evidence"] == state.discovered_evidence
    assert "gideon_hart:confrontation" in result["new_state"]["dialogue_history"]
    assert client.post("/journal").json()["scene_followups"] == []


def test_expired_case_cannot_receive_confrontation_even_with_earned_knowledge(client, monkeypatch):
    state = earned_state()
    state.started_at = 1000 - main.engine.time_limit_seconds
    session(client).state = state
    result = client.post("/command", json={"text": "confront"}).json()
    assert not result["decision"]["allowed"]
    assert result["new_state"]["ending_id"] == "cold_arrival"
    assert result["narrative_scene"] is None
    assert client.post("/journal").json()["scene_followups"] == []
    assert client.get("/reconstruction").json() == {"scene": None}
