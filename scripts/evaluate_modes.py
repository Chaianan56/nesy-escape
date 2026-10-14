"""Controlled adjudicator comparison and structured-command neural-only play.

No API calls occur unless --mode neural is explicitly selected. Expected outcomes
come from the reviewed corpus, never from executing the symbolic comparator.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.game_master import (NeuralGameError, NeuralGameMaster,
                                    NeuralGameOutput, digest, load_game_bundle)

DEFAULT_CORPUS = ROOT / "data/research/adjudication-corpus-v1.json"


class SymbolicAdjudicator:
    """Comparator only. This object is never constructed in neural-only runs."""
    def __init__(self):
        from app.symbolic.engine import SymbolicEngine
        self.engine = SymbolicEngine()

    def adjudicate(self, command, state, submitted_evidence=None):
        from app.symbolic.engine import accusation_submission, apply_changes
        begin = time.perf_counter()
        # Same parsed-command boundary as the game, with a controlled clock.
        if (command.action == ActionType.ACCUSE and not state.ending_id
                and not self.engine.is_out_of_time(state)):
            decision = accusation_submission(self.engine, command, state, submitted_evidence)
        else:
            decision = self.engine.decide(command, state)
        if decision.allowed:
            new_state = apply_changes(state, decision.state_changes)
        else:
            new_state = state.model_copy(deep=True)
            if decision.state_changes.get("ending"):
                new_state.ending_id = decision.state_changes["ending"]
            if "failed_accusations" in decision.state_changes:
                new_state.failed_accusations = decision.state_changes["failed_accusations"]
        visible = [oid for oid, obj in self.engine.world["objects"].items()
                   if obj.get("location") == new_state.current_location
                   and oid not in new_state.inventory
                   and self.engine.decide(ParsedCommand(action=ActionType.EXAMINE,
                       target=oid, raw_text=""), new_state).allowed]
        people = [pid for pid, person in self.engine.world["suspects"].items()
                  if person.get("location") == new_state.current_location]
        output = NeuralGameOutput(
            allowed=decision.allowed, message=decision.message, new_state=new_state,
            visible_objects=visible, visible_people=people,
            deductions=sorted(self.engine.deductions(new_state)),
            pillar_status={pid: self.engine.pillar_status(pid, new_state)
                           for pid, person in self.engine.world["suspects"].items()
                           if person.get("accusable", True)},
            claimed_rule_id=decision.violated_rule_id,
            explanation="\n".join(f"{r.rule_id}: {r.passed}" for r in decision.reasoning_chain),
        )
        from app.neural.game_master import NeuralTurn
        return NeuralTurn(output, {
            "model": None, "attempts": 0, "usage": {}, "cost_usd": 0,
            "latency_ms": round((time.perf_counter() - begin) * 1000, 3),
            "explanation_provenance": "executed_symbolic_trace",
            "reasoning_chain": [r.model_dump(mode="json") for r in decision.reasoning_chain],
        }, "")


def score_output(output: NeuralGameOutput, expected: dict) -> dict:
    """Compare only manually declared assertions; never change a response."""
    checks = {"allowed": output.allowed == expected["allowed"]}
    if "rule_id" in expected:
        checks["rule_id"] = output.claimed_rule_id == expected["rule_id"]
    if "new_state" in expected:
        checks["complete_state"] = output.new_state.model_dump(mode="json") == expected["new_state"]
    for field, values in expected.get("state_fields", {}).items():
        checks[f"state.{field}"] = getattr(output.new_state, field) == values
    for field in ("deductions", "visible_objects", "visible_people"):
        actual = set(getattr(output, field))
        if field + "_contains" in expected:
            checks[field + "_contains"] = set(expected[field + "_contains"]) <= actual
        if field + "_excludes" in expected:
            checks[field + "_excludes"] = not set(expected[field + "_excludes"]) & actual
    # A corpus may audit specific source phrases. This is not a general semantic
    # leakage detector; the protocol requires blinded human review of prose too.
    for phrase in expected.get("message_excludes", []):
        checks[f"message_excludes:{phrase}"] = phrase not in output.message
    return {"checks": checks, "passed": all(checks.values()),
            "failed_checks": [key for key, value in checks.items() if not value]}


def run_turn(adjudicator, spec: dict, state: GameState) -> tuple[dict, GameState | None]:
    command = ParsedCommand.model_validate(spec["command"])
    before = state.model_dump(mode="json")
    row = {"id": spec["id"], "category": spec.get("category"),
           "complexity": spec.get("complexity"), "review_basis": spec.get("review_basis"),
           "command": command.model_dump(mode="json"), "state_before": before,
           "submitted_evidence": spec.get("submitted_evidence"),
           "expected": spec["expected"]}
    try:
        turn = adjudicator.adjudicate(command, state, spec.get("submitted_evidence"))
    except NeuralGameError as exc:
        row.update(status="error", error_kind=exc.kind, metadata=exc.metadata,
                   raw_response=exc.raw_response, scoring=None)
        return row, None
    row.update(status="ok", output=turn.output.model_dump(mode="json"),
               metadata=turn.metadata, raw_response=turn.raw_response,
               scoring=score_output(turn.output, spec["expected"]))
    return row, turn.output.new_state


def run_corpus(adjudicator, corpus: dict, suite: str = "all", case_filter: str | None = None) -> list[dict]:
    rows = []
    if suite in ("all", "one-step"):
        for case in corpus["cases"]:
            if case_filter and case_filter not in case["id"]:
                continue
            row, _ = run_turn(adjudicator, case, GameState.model_validate(case["state"]))
            row["suite"] = "one-step"
            rows.append(row)
    if suite in ("all", "rollout"):
        for rollout in corpus["rollouts"]:
            if case_filter and case_filter not in rollout["id"]:
                continue
            state = GameState.model_validate(rollout["initial_state"])
            diverged = False
            for index, step in enumerate(rollout["steps"]):
                row, next_state = run_turn(adjudicator, step, state)
                row.update(suite="rollout", rollout_id=rollout["id"], step_index=index,
                           previous_reference_divergence=diverged,
                           scoring_scope="authored_reference_trajectory")
                rows.append(row)
                if next_state is None:
                    row["rollout_aborted"] = True
                    row["unexecuted_steps"] = len(rollout["steps"]) - index - 1
                    break
                diverged |= not row["scoring"]["passed"]
                # Deliberately preserve mistakes: no symbolic reset or correction.
                state = next_state
    return rows


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    errors = Counter(r["error_kind"] for r in rows if r["status"] == "error")
    n_pass = sum(r["scoring"]["passed"] for r in ok)
    confusion = Counter()
    for row in ok:
        wanted, actual = row["expected"]["allowed"], row["output"]["allowed"]
        confusion[f"expected_{'allow' if wanted else 'deny'}_returned_{'allow' if actual else 'deny'}"] += 1
    latencies = sorted(r["metadata"]["latency_ms"] for r in rows if "latency_ms" in r["metadata"])
    return {"attempted_turns": len(rows), "well_formed_turns": len(ok),
            "provider_or_schema_errors": dict(errors), "passed_declared_checks": n_pass,
            "declared_check_accuracy_on_well_formed": n_pass / len(ok) if ok else None,
            "end_to_end_declared_check_success": n_pass / len(rows) if rows else None,
            "legality_confusion": dict(confusion),
            "mean_latency_ms": sum(latencies) / len(latencies) if latencies else None,
            "p95_latency_ms": latencies[min(len(latencies)-1, int(len(latencies)*0.95))] if latencies else None,
            "total_provider_attempts": sum(r["metadata"].get("attempts", 0) for r in rows),
            "note": "Prose semantics and player understanding are not automatically scored. Errors remain separate from semantic failures."}


def play(adjudicator, bundle: dict, output_path: Path) -> None:
    """No natural-language parser or symbolic offerability filtering is involved."""
    state = GameState.model_validate(bundle["world"].get("initial_state", {}))
    print(bundle["world"]["briefing"])
    print('Enter one JSON object per turn: {"action":"move","target":"first_class_car"}')
    print('Optional fields: raw_text, instrument, code, topic, evidence; accusations use submitted_evidence. /state or /quit.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as log:
        log.write(json.dumps({"session": "structured-command-play", "bundle_sha256": digest(bundle)}, ensure_ascii=False) + "\n")
        while True:
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if raw == "/quit":
                break
            if raw == "/state":
                print(state.model_dump_json(indent=2))
                continue
            try:
                fields = json.loads(raw)
                submitted = fields.pop("submitted_evidence", None)
                fields.setdefault("raw_text", raw)
                command = ParsedCommand.model_validate(fields)
            except (ValueError, TypeError, AttributeError) as exc:
                print(f"Input JSON/schema error: {type(exc).__name__}")
                continue
            before = state.model_dump(mode="json")
            try:
                turn = adjudicator.adjudicate(command, state, submitted)
            except NeuralGameError as exc:
                log.write(json.dumps({"state_before": before, "command": fields,
                    "submitted_evidence": submitted, "status": "error", "error_kind": exc.kind,
                    "metadata": exc.metadata, "raw_response": exc.raw_response}, ensure_ascii=False) + "\n")
                log.flush()
                print(f"Provider/format failure ({exc.kind}); session stopped, no fallback.")
                break
            state = turn.output.new_state
            log.write(json.dumps({"state_before": before, "command": fields,
                "submitted_evidence": submitted, "status": "ok",
                "output": turn.output.model_dump(mode="json"), "metadata": turn.metadata,
                "raw_response": turn.raw_response}, ensure_ascii=False) + "\n")
            log.flush()
            print(turn.output.message)
            print("Visible:", turn.output.visible_objects, "People:", turn.output.visible_people)
            if state.ending_id:
                print("Ending:", state.ending_id)
                break


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("symbolic", "neural"), default="symbolic")
    parser.add_argument("--model", help="Provider model ID; select identical IDs across repetitions")
    parser.add_argument("--suite", choices=("all", "one-step", "rollout"), default="all")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--case", help="Run IDs containing this string (rollout IDs for rollouts)")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "logs/research/comparison.json")
    parser.add_argument("--play", action="store_true", help="Interactive structured JSON commands; logs JSONL")
    parser.add_argument("--allow-source-drift", action="store_true", help="Exploratory run only; record source mismatch")
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    bundle = load_game_bundle()
    adjudicator = NeuralGameMaster(bundle=bundle, model=args.model) if args.mode == "neural" else SymbolicAdjudicator()
    if args.play:
        play(adjudicator, bundle, args.output)
        return 0
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    source_hashes = {key: digest(bundle[key]) for key in ("world", "rules", "mechanics", "documents")}
    # Missing hashes are drift too: an unfrozen corpus must not look equivalent
    # to a reviewed one merely because an empty mapping passes an all-check.
    expected_hashes = corpus.get("source_hashes", {})
    drift = {key: {"expected": expected_hashes.get(key), "actual": value}
             for key, value in source_hashes.items() if expected_hashes.get(key) != value}
    if drift and not args.allow_source_drift:
        parser.error("Corpus source hashes differ. Review expectations and freeze a new version, or label exploratory with --allow-source-drift.")
    rows = []
    for repetition in range(args.repetitions):
        run_rows = run_corpus(adjudicator, corpus, args.suite, args.case)
        for row in run_rows:
            row["repetition"] = repetition
        rows.extend(run_rows)
    if not rows:
        parser.error("No cases matched")
    result = {"format_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": args.mode, "boundary": "parsed-command-adjudication",
              "model": args.model or getattr(adjudicator, "model", None),
              "corpus_id": corpus["id"], "corpus_status": corpus["status"],
              "corpus_sha256": digest(corpus), "bundle_sha256": digest(bundle),
              "source_hashes": source_hashes, "source_drift": drift,
              "code_hashes": {p: digest((ROOT / p).read_text(encoding="utf-8")) for p in
                  ("app/schemas.py", "app/neural/game_master.py", "app/symbolic/engine.py", "scripts/evaluate_modes.py")},
              "summary": summarize(rows),
              "summary_by_suite": {suite: summarize([r for r in rows if r["suite"] == suite])
                                   for suite in sorted({r["suite"] for r in rows})},
              "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"Saved {args.mode} only: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
