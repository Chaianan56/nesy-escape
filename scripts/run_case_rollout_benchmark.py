"""Paired full-case pilot at the parsed-command boundary, with auditable logs.

Offline by default. --live explicitly spends one Gemini request per neural turn.
The symbolic reference is a software oracle, NOT independent ground truth.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from pydantic import BaseModel, create_model

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cases import CASE_METADATA, get_engine
from app.game_setup import new_game_state
from app.neural.game_master import NeuralGameError, NeuralGameMaster, NeuralGameOutput, digest, load_game_bundle
from app.schemas import GameState
from app.walkthrough import parse_step
from scripts.evaluate_modes import SymbolicAdjudicator

CASES = {
    "A": ("case_01_gideon", "walkthrough.json"),
    "B": ("case_02_vincent", "walkthrough_case_02.json"),
    "C": ("case_03_liora", "walkthrough_case_03.json"),
}

# Pydantic defaults otherwise make fields optional in the provider's response schema.
# Preserve nullable types, but require the key to appear in every returned state.
RequiredGameState = create_model(
    "RequiredGameState", __base__=GameState,
    **{name: (field.annotation, ...) for name, field in GameState.model_fields.items()})
RequiredGameOutput = create_model(
    "RequiredGameOutput", __base__=NeuralGameOutput, new_state=(RequiredGameState, ...))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def semantic(value):
    """Ignore list ordering, retain duplicates and every state field."""
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted((semantic(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def compare(actual, reference):
    a, b = actual.new_state.model_dump(mode="json"), reference.new_state.model_dump(mode="json")
    differences = [k for k in b if semantic(a[k]) != semantic(b[k])]
    return {
        "allowed": actual.allowed == reference.allowed,
        "state": not differences,
        "state_differences": differences,
        "visible_objects": semantic(actual.visible_objects) == semantic(reference.visible_objects),
        "visible_people": semantic(actual.visible_people) == semantic(reference.visible_people),
        "deductions": semantic(actual.deductions) == semantic(reference.deductions),
        "pillar_status": semantic(actual.pillar_status) == semantic(reference.pillar_status),
    }


class ResilientGeminiProvider:
    """Gemini Provider with bounded retry for transient server/network errors and multi-key rotation."""
    def __init__(self, model=None, timeout_ms=60000, max_retries=2, retry_delay=4.0):
        from app.neural.gemini_client import DEFAULT_MODEL
        self.model = model or DEFAULT_MODEL
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def __call__(self, system: str, content: str, schema: type[BaseModel]):
        from app.neural.gemini_client import _clients, _is_quota_error, _is_transient, types, NeuralNotConfigured
        from app.neural.game_master import _pydantic_schema_for_gemini, ProviderReply

        clients = _clients()
        if not clients:
            raise NeuralNotConfigured("Configure Gemini before running the neural game master")

        sanitized_schema = _pydantic_schema_for_gemini(schema)
        queue = list(clients)
        last_error = None

        while queue:
            client = queue[0]
            for attempt in range(1, self.max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=content,
                        config=types.GenerateContentConfig(
                            system_instruction=system,
                            response_mime_type="application/json",
                            response_schema=sanitized_schema,
                            temperature=0,
                            http_options=types.HttpOptions(
                                timeout=self.timeout_ms,
                                retry_options=types.HttpRetryOptions(attempts=1),
                            ),
                        ),
                    )
                    usage = getattr(response, "usage_metadata", None)
                    return ProviderReply(
                        text=response.text or "",
                        usage=usage.model_dump(mode="json") if usage is not None else {},
                        model_version=getattr(response, "model_version", None),
                    )
                except Exception as exc:
                    last_error = exc
                    exc_name = type(exc).__name__
                    is_quota = _is_quota_error(exc)
                    is_trans = _is_transient(exc) or exc_name in {
                        "ServerError", "ReadTimeout", "ConnectTimeout", "ConnectError", "Timeout", "RemoteProtocolError"
                    }
                    if is_quota:
                        queue.pop(0)
                        if queue:
                            print(f"\n  [Provider: Quota hit on active key, switching to backup key...]", flush=True)
                            time.sleep(1.0)
                        break
                    elif is_trans and attempt < self.max_retries:
                        print(f"\n  [Provider: Transient {exc_name}, retrying in {self.retry_delay:.0f}s (attempt {attempt+1}/{self.max_retries})...]", flush=True)
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        raise exc

        if last_error:
            raise last_error


class CompleteStateGameMaster(NeuralGameMaster):
    """Reject missing state fields rather than accepting the legacy adapter's defaults."""
    def __init__(self, *args, **kwargs):
        if "provider" not in kwargs and (len(args) < 2 or args[1] is None):
            kwargs["provider"] = ResilientGeminiProvider(model=kwargs.get("model"))
        super().__init__(*args, **kwargs)
        provider = self.provider
        self.provider = lambda system, content, schema: provider(system, content, RequiredGameOutput)

    def adjudicate(self, command, state, submitted_evidence=None):
        turn = super().adjudicate(command, state, submitted_evidence)
        raw_state = json.loads(turn.raw_response)["new_state"]
        missing = sorted(set(GameState.model_fields) - set(raw_state))
        if missing:
            raise NeuralGameError("incomplete_state", {**turn.metadata, "missing_fields": missing},
                                  turn.raw_response)
        return turn


def prepare(letter):
    cid, filename = CASES[letter]
    walk = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
    engine = get_engine(cid)
    adjudicator = SymbolicAdjudicator(engine)
    initial = new_game_state(engine.world, cid)
    commands = []
    for step in walk["steps"]:
        command = parse_step(step, walk)
        # Identical, explicit commands; not a test of natural-language parsing.
        text = " ".join(str(v) for v in [command.action.value, command.target,
                                        command.topic, command.code, command.instrument] if v)
        commands.append(command.model_copy(update={"raw_text": text}))
    references, state = [], initial.model_copy(deep=True)
    for command in commands:
        turn = adjudicator.adjudicate(command, state.model_copy(deep=True))
        if not turn.output.allowed:
            raise ValueError(f"Walkthrough preflight failed: {letter} {command.raw_text}")
        references.append(turn.output)
        state = turn.output.new_state
    if state.ending_id != "true_ending" or commands[-1].target != CASE_METADATA[cid]["culprit"]:
        raise ValueError(f"Walkthrough does not solve case {letter}")
    bundle = load_game_bundle()
    bundle["world"] = engine.world
    bundle["mechanics"] = (ROOT / "docs/research-mechanics-v3.md").read_text(encoding="utf-8")
    return cid, initial, commands, references, adjudicator, bundle


def run_episode(mode, letter, repetition, initial, commands, references, actor, oracle,
                record, pause=0):
    state = initial.model_copy(deep=True)
    rows = []
    first_state_divergence = None
    stop_reason = "commands_exhausted"
    for index, command in enumerate(commands):
        before = state.model_dump(mode="json")
        row = {"case": letter, "mode": mode, "repetition": repetition, "step": index + 1,
               "command": command.model_dump(mode="json"), "state_before": before,
               "previous_state_divergence": first_state_divergence is not None}
        try:
            turn = actor.adjudicate(command.model_copy(deep=True), state.model_copy(deep=True))
        except NeuralGameError as exc:
            row.update(status="error", error_kind=exc.kind, metadata=exc.metadata,
                       raw_response=exc.raw_response)
            record(row)
            rows.append(row)
            stop_reason = "service_or_schema_error"
            break
        output = turn.output
        trajectory = compare(output, references[index])
        # Audit after generation. Nothing from the oracle is fed back to the actor.
        try:
            executed_command = getattr(turn, "executed_command", command)
            local_reference = oracle.adjudicate(executed_command.model_copy(deep=True),
                                                GameState.model_validate(before)).output
            local = compare(output, local_reference)
            audit_error = None
        except (KeyError, ValueError, TypeError) as exc:
            local = None
            audit_error = type(exc).__name__
        if not trajectory["state"] and first_state_divergence is None:
            first_state_divergence = index + 1
        row.update(status="ok", output=output.model_dump(mode="json"), metadata=turn.metadata,
                   executed_command=getattr(turn, "executed_command", command).model_dump(mode="json"),
                   raw_response=turn.raw_response, reference_trajectory=trajectory,
                   own_state_rule_audit=local, audit_error=audit_error)
        record(row)
        rows.append(row)
        # Preserve the actor's own result, including every semantic mistake.
        state = output.new_state.model_copy(deep=True)
        if state.ending_id is not None:
            stop_reason = "ending_reached"
            break
        if pause:
            time.sleep(pause)
    ok = [r for r in rows if r["status"] == "ok"]
    audits = [r["own_state_rule_audit"] for r in ok if r["own_state_rule_audit"] is not None]
    final_matches = semantic(state.model_dump(mode="json")) == semantic(
        references[-1].new_state.model_dump(mode="json"))
    return {
        "case": letter, "mode": mode, "repetition": repetition,
        "planned_turns": len(commands), "attempted_turns": len(rows), "valid_responses": len(ok),
        "unexecuted_turns": len(commands) - len(rows), "stop_reason": stop_reason,
        "errors": dict(Counter(r["error_kind"] for r in rows if r["status"] == "error")),
        "ending_id": state.ending_id, "claimed_true_ending": state.ending_id == "true_ending",
        "final_state_matches_reference": final_matches,
        "completed_reference_solution": len(ok) == len(commands) and final_matches,
        "first_state_divergence_step": first_state_divergence,
        "trajectory_state_matches": sum(r["reference_trajectory"]["state"] for r in ok),
        "trajectory_allowed_matches": sum(r["reference_trajectory"]["allowed"] for r in ok),
        "trajectory_visible_object_matches": sum(r["reference_trajectory"]["visible_objects"] for r in ok),
        "own_state_auditable_turns": len(audits),
        "own_state_permission_disagreements": sum(not a["allowed"] for a in audits),
        "own_state_transition_disagreements": sum(not a["state"] for a in audits),
        "total_latency_ms": round(sum(r["metadata"].get("latency_ms", 0) for r in rows), 3),
        "provider_attempts": sum(r["metadata"].get("attempts", 0) for r in rows),
        "usage": dict(sum((Counter({k: v for k, v in r["metadata"].get("usage", {}).items()
                                    if isinstance(v, (int, float)) and not isinstance(v, bool)})
                           for r in rows), Counter())),
        "final_state": state.model_dump(mode="json"),
    }


def report(summary):
    lines = ["# ผลนำร่องการเล่นต่อเนื่องจนจบคดี", "",
             "เปรียบเทียบคำสั่งที่ตีความแล้วชุดเดียวกัน โดยแต่ละระบบใช้สถานะของตัวเองในตาถัดไป",
             "NeSy ในตารางหมายถึงส่วนตัดสิน Symbolic เท่านั้น ไม่รวม Neural parser หรือหน้าเว็บ", "",
             "| คดี | ระบบ | คำตอบใช้ได้/แผน | ฉากจบ | สถานะตรงเส้นทางอ้างอิง | เริ่มต่างที่ตา | จบตรงเส้นทางอ้างอิง |",
             "|---|---|---:|---|---:|---:|---|"]
    for e in summary["episodes"]:
        name = "Neural-only" if e["mode"] == "neural" else "NeSy ส่วนตัดสิน"
        outcome = "ใช่" if e["completed_reference_solution"] else "ไม่"
        if e["errors"]:
            outcome = "ยังประเมินการจบไม่ได้: " + ", ".join(e["errors"])
        lines.append(f"| {e['case']} | {name} | {e['valid_responses']}/{e['planned_turns']} | "
                     f"{e['ending_id'] or 'ยังไม่จบ'} | {e['trajectory_state_matches']}/{e['valid_responses']} | "
                     f"{e['first_state_divergence_step'] or '-'} | {outcome} |")
    lines += ["", "## การตีความ", "",
              "- ผลนี้เป็น pilot บน walkthrough ที่ใช้พัฒนาเกม ไม่ใช่ held-out benchmark และไม่ใช่ผลเชิงนัยสำคัญทางสถิติ",
              "- เส้นทางอ้างอิงและตัวตรวจสร้างจาก Symbolic engine เดียวกับฝั่ง NeSy จึงวัดความสอดคล้องกับ implementation ไม่ใช่ความถูกต้องที่ผู้ตรวจอิสระรับรอง",
              "- สถานะต่างหลังตาแรกอาจเป็นผลสะสม ไม่ใช่ข้อผิดพลาดใหม่ทุกตา ดู own_state_rule_audit ใน turns.jsonl เพื่อแยกสองเรื่องนี้",
              "- ตัวเลขผ่านของ Symbolic เป็นการตรวจเส้นทางและความสม่ำเสมอ ไม่ใช่หลักฐานอิสระว่า NeSy เหนือกว่า",
              "- หยุดเมื่อมีฉากจบหรือ service/schema error ไม่ซ่อมคำตอบ ไม่ย้อนสถานะ ไม่ลองใหม่ และรายงานตาที่ไม่ได้รัน",
              "- ถ้า Neural ไม่ได้รันหรือหยุดเพราะบริการ ห้ามตีความว่าแพ้ด้านเหตุผล",
              "- นับการจบตรงเส้นทางเมื่อประมวลผลครบและสถานะสุดท้ายตรงอ้างอิง ไม่ถือว่าพิมพ์ true_ending อย่างเดียวคือสำเร็จ",
              "- ไม่ตรวจความถูกต้องของข้อความเล่าเรื่องอัตโนมัติ ไม่วัดความเข้าใจภาษา/ความสนุก/ประสบการณ์ผู้เล่น",
              "- เวลาในเกมตรึงไว้ที่ 0 เวลา API วัดแยก ไม่ใช่ latency ของ NeSy ครบระบบ", "",
              "## ไฟล์ตรวจสอบ", "",
              "- manifest.json: แผนทดลอง รุ่นโมเดล hash ของโค้ดและข้อมูล",
              "- inputs-*.json: คำสั่ง สถานะเริ่ม และ bundle ที่ส่งให้ Neural",
              "- reference-*.json: ผล replay ด้วย Symbolic ซึ่งไม่ส่งให้ Neural",
              "- turns.jsonl: ผลรายตา คำตอบดิบ สถานะก่อน/หลัง และผลตรวจ",
              "- summary.json: สรุปรายคดีและจำนวนเรียก API", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=["A", "B", "C"])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--max-provider-calls", type=int, default=None,
                        help="Maximum allowed provider calls (default: planned calls for selected cases + 10)")
    parser.add_argument("--pause-seconds", type=float, default=10,
                        help="Pause seconds between neural turns to prevent rate limits (default: 10)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.repetitions < 1 or not 0 <= args.pause_seconds <= 60:
        parser.error("positive repetitions and pause between 0 and 60 seconds required")
    if len(set(args.cases)) != len(args.cases):
        parser.error("duplicate cases are not allowed; use --repetitions")
    if args.output.exists():
        parser.error("use a new output directory; existing results are never overwritten")
    prepared = {letter: prepare(letter) for letter in args.cases}
    planned = sum(len(p[2]) for p in prepared.values()) * args.repetitions if args.live else 0
    max_provider_calls = args.max_provider_calls if args.max_provider_calls is not None else (planned + 10)
    if planned > max_provider_calls:
        parser.error(f"planned {planned} provider calls exceeds --max-provider-calls ({max_provider_calls})")
    args.output.mkdir(parents=True)
    from app.neural.gemini_client import DEFAULT_MODEL
    model = args.model or DEFAULT_MODEL
    sources = ["scripts/run_case_rollout_benchmark.py", "scripts/evaluate_modes.py",
               "app/neural/game_master.py", "app/symbolic/engine.py", "app/schemas.py",
               "docs/research-mechanics-v3.md"]
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "protocol_version": "case-rollout-1.1-required-state-schema",
                "boundary": "parsed-command-full-case-rollout", "status": "development-pilot-not-held-out",
                "reference_basis": "same-engine replay, not independently authored truth",
                "live": args.live, "model": model if args.live else None, "temperature": 0,
                "cases": args.cases, "repetitions": args.repetitions, "planned_provider_calls": planned,
                "max_provider_calls": max_provider_calls, "pause_seconds": args.pause_seconds,
                "retry": "none", "clock": "fixed elapsed_seconds=0, started_at=null",
                "schema_policy": "all state fields required; no semantic repair",
                "response_schema_sha256": digest(RequiredGameOutput.model_json_schema()),
                "list_comparison": "ignore order, retain duplicates", "prose_review": "not_performed",
                "code_hashes": {p: digest((ROOT / p).read_text(encoding="utf-8")) for p in sources},
                "input_hashes": {}}
    save(args.output / "response-schema.json", RequiredGameOutput.model_json_schema())
    for source in sources:
        snapshot = args.output / "code-snapshot" / source
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text((ROOT / source).read_text(encoding="utf-8"), encoding="utf-8")
    for letter, (cid, initial, commands, references, oracle, bundle) in prepared.items():
        inputs = {"case_id": cid, "initial_state": initial.model_dump(mode="json"),
                  "commands": [c.model_dump(mode="json") for c in commands], "bundle": bundle}
        save(args.output / f"inputs-{letter}.json", inputs)
        save(args.output / f"reference-{letter}.json", [r.model_dump(mode="json") for r in references])
        manifest["input_hashes"][letter] = digest(inputs)
    save(args.output / "manifest.json", manifest)
    summary = {"status": "running", "live": args.live, "episodes": []}
    with (args.output / "turns.jsonl").open("w", encoding="utf-8") as log:
        def record(row):
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
            print(f"{row['case']} {row['mode']} rep={row['repetition']} step={row['step']} {row['status']}", flush=True)
        for letter, (cid, initial, commands, references, oracle, bundle) in prepared.items():
            for rep in range(1, args.repetitions + 1):
                for mode in (["nesy_adjudicator", "neural"] if args.live else ["nesy_adjudicator"]):
                    actor = CompleteStateGameMaster(bundle=bundle, model=model) if mode == "neural" else oracle
                    if mode == "neural":
                        (args.output / f"system-prompt-{letter}.txt").write_text(actor.system, encoding="utf-8")
                    episode = run_episode(mode, letter, rep, initial, commands, references, actor, oracle,
                                          record, args.pause_seconds if mode == "neural" else 0)
                    summary["episodes"].append(episode)
                    save(args.output / "summary.json", summary)
                    (args.output / "report.md").write_text(report(summary), encoding="utf-8")
    summary["status"] = "finished"
    save(args.output / "summary.json", summary)
    (args.output / "report.md").write_text(report(summary), encoding="utf-8")
    print(f"Saved: {args.output.resolve()}")

    # บันทึกสรุปสถิติลงไฟล์ log รวมส่วนกลาง (Centralized Benchmark History)
    history_log_path = ROOT / "logs" / "research" / "rollout_benchmark_history.jsonl"
    history_log_path.parent.mkdir(parents=True, exist_ok=True)
    history_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(args.output.resolve()),
        "live": args.live,
        "model": model if args.live else None,
        "cases": args.cases,
        "repetitions": args.repetitions,
        "pause_seconds": args.pause_seconds,
        "planned_provider_calls": planned,
        "max_provider_calls": max_provider_calls,
        "status": summary["status"],
        "episodes": [
            {
                "case": ep.get("case"),
                "mode": ep.get("mode"),
                "repetition": ep.get("repetition"),
                "planned_turns": ep.get("planned_turns"),
                "attempted_turns": ep.get("attempted_turns"),
                "valid_responses": ep.get("valid_responses"),
                "unexecuted_turns": ep.get("unexecuted_turns"),
                "stop_reason": ep.get("stop_reason"),
                "ending_id": ep.get("ending_id"),
                "claimed_true_ending": ep.get("claimed_true_ending"),
                "final_state_matches_reference": ep.get("final_state_matches_reference"),
                "completed_reference_solution": ep.get("completed_reference_solution"),
                "first_state_divergence_step": ep.get("first_state_divergence_step"),
                "trajectory_state_matches": ep.get("trajectory_state_matches"),
                "trajectory_allowed_matches": ep.get("trajectory_allowed_matches"),
                "total_latency_ms": ep.get("total_latency_ms"),
                "provider_attempts": ep.get("provider_attempts"),
                "usage": ep.get("usage"),
                "errors": ep.get("errors"),
            }
            for ep in summary.get("episodes", [])
        ],
    }
    with history_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
    print(f"Appended history summary to: {history_log_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
