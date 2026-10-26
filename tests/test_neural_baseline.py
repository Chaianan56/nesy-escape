"""
tests/test_neural_baseline.py — ทดสอบระบบ Pure Neural Adjudicator Baseline แบบออฟไลน์ 100%

หน้าที่:
- จำลองการตัดสินของโมเดล Neural Game Master โดยไม่มี Symbolic Engine
- ตรวจสอบโครงสร้างคำตอบ (NeuralGameOutput), การให้เหตุผล, และการจัดการข้อผิดพลาด
- รันแบบออฟไลน์ 100% โดยจำลอง ProviderReply ไม่ยิงเครือข่ายภายนอก
"""
import json
from pathlib import Path

import pytest

from app.schemas import GameState, ParsedCommand
from app.neural.game_master import (NeuralGameError, NeuralGameMaster, ProviderReply)
from scripts.evaluate_modes import run_corpus, score_output, summarize


def response(state=None, **updates):
    payload = dict(allowed=True, message="คำตอบจากโมเดล", new_state=(state or GameState()).model_dump(mode="json"),
                   visible_objects=[], visible_people=[], deductions=[], pillar_status={},
                   claimed_rule_id=None, explanation="generated claim")
    payload.update(updates)
    return payload


def command(**changes):
    return ParsedCommand.model_validate({"action": "move", "target": "first_class_car", "raw_text": "ไปตู้ 4", **changes})


def test_model_receives_raw_world_and_state_without_symbolic_answers():
    seen = {}
    bundle = {"world": {"objects": {"secret": {"description": "hidden source fact"}}},
              "rules": {"rules": []}, "mechanics": "no repair", "documents": {}}
    def provider(system, content, schema):
        seen.update(system=system, input=json.loads(content))
        return ProviderReply(json.dumps(response()), {"total_token_count": 10}, "test-model")
    game = NeuralGameMaster(bundle=bundle, provider=provider)
    state = GameState(discovered_evidence=["one-known-fact"])
    turn = game.adjudicate(command(), state)
    assert "hidden source fact" in seen["system"]
    assert seen["input"]["state"] == state.model_dump(mode="json")
    assert set(seen["input"]) == {"command", "state", "submitted_evidence"}
    assert turn.metadata["usage"]["total_token_count"] == 10
    assert turn.metadata["explanation_provenance"] == "model_claim_not_executed_trace"


def test_semantically_wrong_full_response_is_preserved():
    state = GameState(current_location="invented_room", discovered_evidence=["never_found"], ending_id="invented_ending")
    payload = response(state, deductions=["unsupported"], visible_objects=["hidden"], claimed_rule_id="invented_rule")
    game = NeuralGameMaster(bundle={}, provider=lambda *_: ProviderReply(json.dumps(payload), {}))
    turn = game.adjudicate(command(), GameState())
    assert turn.output.new_state == state
    assert turn.output.deductions == ["unsupported"]
    assert turn.output.claimed_rule_id == "invented_rule"
    assert not score_output(turn.output, {"allowed": False})["passed"]


@pytest.mark.parametrize("payload", ["not-json", json.dumps({"allowed": True}),
    json.dumps(response(allowed="true")), json.dumps(response(message=12345))])
def test_format_failure_is_not_a_symbolic_rejection(payload):
    calls = []
    def provider(*args):
        calls.append(args)
        return ProviderReply(payload, {})
    game = NeuralGameMaster(bundle={}, provider=provider)
    with pytest.raises(NeuralGameError) as error:
        game.adjudicate(command(), GameState())
    assert error.value.kind == "schema"
    assert len(calls) == 1
    assert error.value.raw_response == payload


def test_transport_error_is_recorded_once_without_exception_secret():
    def provider(*_):
        raise RuntimeError("sensitive-provider-url-secret")
    with pytest.raises(NeuralGameError) as error:
        NeuralGameMaster(bundle={}, provider=provider).adjudicate(command(), GameState())
    assert error.value.kind == "provider"
    assert "sensitive-provider" not in str(error.value) + json.dumps(error.value.metadata)
    assert error.value.metadata["attempts"] == 1


def test_rollout_propagates_wrong_state_without_repair():
    seen = []
    def provider(_, content, __):
        payload = json.loads(content)
        seen.append(payload["state"])
        returned = GameState.model_validate(payload["state"])
        returned.current_location = "invented_room"
        returned.discovered_evidence.append("invented_evidence")
        return ProviderReply(json.dumps(response(returned)), {})
    game = NeuralGameMaster(bundle={}, provider=provider)
    step = {"id": "step", "command": command().model_dump(mode="json"), "expected": {"allowed": False}}
    corpus = {"cases": [], "rollouts": [{"id": "r", "initial_state": GameState().model_dump(mode="json"), "steps": [step, step]}]}
    rows = run_corpus(game, corpus)
    assert seen[1]["current_location"] == "invented_room"
    assert seen[1]["discovered_evidence"] == ["invented_evidence"]
    assert rows[1]["previous_reference_divergence"]


def test_rollout_stops_on_format_failure_and_metrics_separate_errors():
    game = NeuralGameMaster(bundle={}, provider=lambda *_: ProviderReply("bad", {}))
    step = {"id": "step", "command": command().model_dump(mode="json"), "expected": {"allowed": False}}
    corpus = {"cases": [], "rollouts": [{"id": "r", "initial_state": {}, "steps": [step, step]}]}
    rows = run_corpus(game, corpus)
    assert len(rows) == 1
    assert rows[0]["scoring"] is None
    assert rows[0]["unexecuted_steps"] == 1
    summary = summarize(rows)
    assert summary["provider_or_schema_errors"] == {"schema": 1}
    assert summary["legality_confusion"] == {}
    assert summary["declared_check_accuracy_on_well_formed"] is None


def test_neural_runtime_does_not_import_symbolic_code():
    import ast
    source = (Path(__file__).resolve().parents[1] / "app/neural/game_master.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert "symbolic" not in (node.module or "")
        if isinstance(node, ast.Import):
            assert all("symbolic" not in alias.name for alias in node.names)


def test_checked_in_corpus_has_explicit_expected_and_review_basis():
    corpus_path = Path(__file__).resolve().parents[1] / "data/research/adjudication-corpus-v1.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert corpus["status"] == "reviewed-development-corpus-not-held-out"
    assert corpus["source_hashes"]
    for case in corpus["cases"]:
        assert case["review_basis"]
        assert isinstance(case["expected"]["allowed"], bool)
        assert "new_state" in case["expected"]
        GameState.model_validate(case["state"])
        GameState.model_validate(case["expected"]["new_state"])
        ParsedCommand.model_validate(case["command"])
