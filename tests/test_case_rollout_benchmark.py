import json

import pytest

from app.neural.game_master import NeuralGameError, ProviderReply, _pydantic_schema_for_gemini
from app.schemas import GameState
from scripts.run_case_rollout_benchmark import CompleteStateGameMaster, prepare, run_episode


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_full_walkthrough_reaches_expected_ending(letter):
    _, initial, commands, refs, oracle, _ = prepare(letter)
    rows = []
    result = run_episode("nesy_adjudicator", letter, 1, initial, commands, refs,
                         oracle, oracle, rows.append)
    assert result["completed_reference_solution"]
    assert result["attempted_turns"] == len(commands)
    assert result["first_state_divergence_step"] is None
    assert initial.ending_id is None


def test_rollout_preserves_mistakes_and_does_not_count_claimed_win_as_valid():
    _, initial, commands, refs, oracle, _ = prepare("A")
    received = []

    class Actor:
        def adjudicate(self, command, state):
            received.append(state.model_copy(deep=True))
            turn = oracle.adjudicate(command, state)
            if len(received) == 1:
                turn.output.new_state.visited_locations.append("invented_location")
            return turn

    rows = []
    result = run_episode("neural", "A", 1, initial, commands, refs, Actor(), oracle, rows.append)
    assert "invented_location" in received[1].visited_locations
    assert result["first_state_divergence_step"] == 1
    assert result["claimed_true_ending"]
    assert not result["completed_reference_solution"]
    assert result["own_state_transition_disagreements"] == 1
    assert result["trajectory_state_matches"] == 0
    assert "invented_location" not in initial.visited_locations


def test_service_error_stops_and_records_unexecuted_turns():
    _, initial, commands, refs, oracle, _ = prepare("A")

    class FailingActor:
        def adjudicate(self, command, state):
            raise NeuralGameError("provider", {"attempts": 1, "latency_ms": 10})

    rows = []
    result = run_episode("neural", "A", 1, initial, commands, refs, FailingActor(), oracle, rows.append)
    assert result["errors"] == {"provider": 1}
    assert result["unexecuted_turns"] == len(commands) - 1
    assert result["valid_responses"] == 0
    assert len(rows) == 1


def test_missing_state_fields_are_not_silently_repaired():
    _, initial, commands, refs, _, bundle = prepare("A")
    response = refs[0].model_dump(mode="json")
    del response["new_state"]["inventory"]

    def provider(system, content, schema):
        return ProviderReply(json.dumps(response), {})

    actor = CompleteStateGameMaster(bundle=bundle, provider=provider)
    with pytest.raises(NeuralGameError) as caught:
        actor.adjudicate(commands[0], initial)
    assert caught.value.kind == "incomplete_state"
    assert caught.value.metadata["missing_fields"] == ["inventory"]


def test_provider_schema_requires_all_state_fields_including_nullable_fields():
    _, initial, commands, refs, _, bundle = prepare("A")
    seen = []

    def provider(system, content, schema):
        state_schema = _pydantic_schema_for_gemini(schema)["properties"]["new_state"]
        seen.append(state_schema)
        return ProviderReply(refs[0].model_dump_json(), {})

    actor = CompleteStateGameMaster(bundle=bundle, provider=provider)
    assert actor.adjudicate(commands[0], initial).output.allowed
    assert set(seen[0]["required"]) == set(GameState.model_fields)


def test_early_claimed_ending_stops_without_being_counted_as_complete():
    _, initial, commands, refs, oracle, _ = prepare("A")

    class EarlyEndingActor:
        def adjudicate(self, command, state):
            turn = oracle.adjudicate(command, state)
            turn.output.new_state.ending_id = "true_ending"
            return turn

    result = run_episode("neural", "A", 1, initial, commands, refs, EarlyEndingActor(), oracle, lambda r: None)
    assert result["attempted_turns"] == 1
    assert result["unexecuted_turns"] == len(commands) - 1
    assert result["claimed_true_ending"]
    assert not result["completed_reference_solution"]
