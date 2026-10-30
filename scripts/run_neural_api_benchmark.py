"""
scripts/run_neural_api_benchmark.py — ชุดทดสอบวัดผลประสิทธิภาพ Neural API (Gemini LLM) เชิงประจักษ์

จุดประสงค์:
1. บายพาส Fast-Path Parser ทั้งหมด 100% เพื่อทดสอบความสามารถที่แท้จริงของ Gemini API
2. ทดสอบคำสั่งภาษาธรรมชาติที่ซับซ้อน ทั้งภาษาไทยและภาษาอังกฤษ (65 รูปแบบ)
3. ตรวจสอบการตีความ Action, Target, Code, Instrument และการทำงานของ Symbolic Repair Loop
4. ส่งผลลัพธ์ต่อไปยัง Symbolic Engine เพื่อตรวจสอบว่ากฎ (Rules) อนุญาต/ปฏิเสธ ได้ถูกต้องตามความคาดหมาย
5. เก็บข้อมูลสถิติเชิงลึก:
   - Action Accuracy & Target Accuracy
   - True Positive, True Negative, False Positive, False Negative
   - Latency & Token Usage Distribution
   - Breakdown แยกตามภาษา (TH vs EN) และหมวดหมู่คำสั่ง (Categories)
   - Detailed Error Diagnostics & System Recommendations
"""

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.neural.gemini_client import interpret
from app.symbolic.engine import SymbolicEngine
from app.schemas import ActionType, GameState, ParsedCommand

DATASET_PATH = ROOT / "data/neural_api_benchmark_suite.json"
RESULTS_PATH = ROOT / "logs/research/neural_api_benchmark_results.json"


def run_benchmark():
    if not DATASET_PATH.exists():
        print(f"Error: {DATASET_PATH} not found!")
        sys.exit(1)

    with open(DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    print(f"================================================================================")
    print(f"  NOCTURNE EXPRESS — NEURAL API STRESS-TEST BENCHMARK (LIVE GEMINI API)")
    print(f"================================================================================")
    print(f"Total Test Cases: {len(cases)}")
    print(f"Fast-Path Mode: BYPASSED (Every command goes directly to Gemini API)")
    print(f"Date & Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"================================================================================\n")

    engine = SymbolicEngine()
    results = []

    # Counters
    total = len(cases)
    action_correct = 0
    target_correct = 0
    decision_correct = 0
    strict_pass = 0

    false_negatives = []
    false_positives = []
    mismatches = []
    repaired_count = 0

    latencies = []
    prompt_tokens_list = []
    completion_tokens_list = []

    cat_stats = defaultdict(lambda: {"total": 0, "action_ok": 0, "target_ok": 0, "dec_ok": 0, "strict_ok": 0})
    lang_stats = defaultdict(lambda: {"total": 0, "action_ok": 0, "target_ok": 0, "dec_ok": 0, "strict_ok": 0})

    for i, case in enumerate(cases, 1):
        cid = case["id"]
        query = case["query"]
        lang = case["language"]
        cat = case["category"]
        exp_action = case["expected_action"]
        exp_target = case.get("expected_target")
        exp_allowed = case.get("expected_allowed", True)
        exp_rule = case.get("expected_rule")

        state = GameState(
            current_location=case["initial_location"],
            inventory=list(case.get("inventory", [])),
            discovered_evidence=list(case.get("discovered_evidence", []))
        )

        print(f"[{i:02d}/{total:02d}] ({lang.upper()}) \"{query}\" ... ", end="", flush=True)

        cmd: ParsedCommand = None
        max_attempts = 3
        for attempt in range(max_attempts):
            t_start = time.perf_counter()
            api_error = None
            try:
                # DIRECT CALL TO GEMINI API (Bypassing typed_commands Fast-Path)
                cmd = interpret(query, state)
                elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
                break
            except Exception as e:
                err_str = str(e)
                if ("RESOURCE_EXHAUSTED" in err_str or "429" in err_str) and attempt < max_attempts - 1:
                    print(f"⏳ Rate-limit (429), pausing 18s before retry (attempt {attempt+1})... ", end="", flush=True)
                    time.sleep(18)
                    continue
                elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
                api_error = err_str
                print(f"❌ API ERROR: {e}")
                break

        if cmd is None:
            results.append({
                "id": cid,
                "query": query,
                "language": lang,
                "category": cat,
                "status": "API_ERROR",
                "error": api_error,
                "latency_ms": elapsed_ms
            })
            continue

        # Throttling to respect Gemini Free Tier 15 RPM
        time.sleep(3.5)

        latencies.append(cmd.latency_ms or elapsed_ms)
        if cmd.prompt_tokens:
            prompt_tokens_list.append(cmd.prompt_tokens)
        if cmd.completion_tokens:
            completion_tokens_list.append(cmd.completion_tokens)
        if cmd.repair_note:
            repaired_count += 1

        # Check action & target match
        act_ok = (cmd.action.value == exp_action) if cmd.action else False
        tgt_ok = (cmd.target == exp_target)

        # In overview / ambiguous cases, target can be current location or None
        if exp_action == "examine" and exp_target in (state.current_location, None):
            if cmd.target in (state.current_location, None):
                tgt_ok = True

        # Pass through Symbolic Engine
        decision = engine.decide(cmd, state)
        dec_ok = (decision.allowed == exp_allowed)
        if not exp_allowed and exp_rule:
            dec_ok = dec_ok and (decision.violated_rule_id == exp_rule)

        # Strict pass = action OK, target OK, decision OK
        is_strict = act_ok and tgt_ok and dec_ok

        # Classification of errors
        status = "PASS"
        if not is_strict:
            if exp_allowed and not decision.allowed:
                status = "FALSE_NEGATIVE"
                false_negatives.append({
                    "id": cid,
                    "query": query,
                    "language": lang,
                    "category": cat,
                    "expected": f"action={exp_action}, target={exp_target}, allowed=True",
                    "actual": f"action={cmd.action.value}, target={cmd.target}, allowed={decision.allowed}, rule={decision.violated_rule_id}",
                    "reason": getattr(decision, "message", None) or "Rejected by rule",
                    "repair_note": cmd.repair_note
                })
            elif not exp_allowed and decision.allowed:
                status = "FALSE_POSITIVE"
                false_positives.append({
                    "id": cid,
                    "query": query,
                    "language": lang,
                    "category": cat,
                    "expected": f"allowed=False (rule: {exp_rule})",
                    "actual": f"allowed=True",
                    "cmd": f"action={cmd.action.value}, target={cmd.target}"
                })
            else:
                status = "PARSER_MISMATCH"
                mismatches.append({
                    "id": cid,
                    "query": query,
                    "language": lang,
                    "category": cat,
                    "expected": f"action={exp_action}, target={exp_target}",
                    "actual": f"action={cmd.action.value}, target={cmd.target}",
                    "repair_note": cmd.repair_note
                })

        # Aggregation
        if act_ok: action_correct += 1
        if tgt_ok: target_correct += 1
        if dec_ok: decision_correct += 1
        if is_strict: strict_pass += 1

        cat_stats[cat]["total"] += 1
        if act_ok: cat_stats[cat]["action_ok"] += 1
        if tgt_ok: cat_stats[cat]["target_ok"] += 1
        if dec_ok: cat_stats[cat]["dec_ok"] += 1
        if is_strict: cat_stats[cat]["strict_ok"] += 1

        lang_stats[lang]["total"] += 1
        if act_ok: lang_stats[lang]["action_ok"] += 1
        if tgt_ok: lang_stats[lang]["target_ok"] += 1
        if dec_ok: lang_stats[lang]["dec_ok"] += 1
        if is_strict: lang_stats[lang]["strict_ok"] += 1

        icon = "✅" if is_strict else ("⚠️" if status == "PARSER_MISMATCH" else "❌")
        rep_flag = f" [Repaired: {cmd.repair_note[:30]}...]" if cmd.repair_note else ""
        print(f"{icon} {status} ({cmd.latency_ms:.0f}ms) -> {cmd.action.value} {cmd.target}{rep_flag}")

        results.append({
            "id": cid,
            "query": query,
            "language": lang,
            "category": cat,
            "status": status,
            "expected": {
                "action": exp_action,
                "target": exp_target,
                "allowed": exp_allowed,
                "rule": exp_rule
            },
            "actual": {
                "action": cmd.action.value if cmd.action else None,
                "target": cmd.target,
                "allowed": decision.allowed,
                "violated_rule_id": decision.violated_rule_id,
                "code": cmd.code,
                "instrument": cmd.instrument
            },
            "repair_note": cmd.repair_note,
            "latency_ms": cmd.latency_ms,
            "prompt_tokens": cmd.prompt_tokens,
            "completion_tokens": cmd.completion_tokens
        })

    # Summary Statistics Calculation
    action_acc = round(action_correct / total * 100, 2)
    target_acc = round(target_correct / total * 100, 2)
    decision_acc = round(decision_correct / total * 100, 2)
    strict_acc = round(strict_pass / total * 100, 2)

    mean_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0
    p95_latency = round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if latencies else 0
    mean_prompt_tokens = round(sum(prompt_tokens_list) / len(prompt_tokens_list), 1) if prompt_tokens_list else 0
    mean_completion_tokens = round(sum(completion_tokens_list) / len(completion_tokens_list), 1) if completion_tokens_list else 0

    summary_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_test_cases": total,
        "metrics": {
            "strict_accuracy_percent": strict_acc,
            "action_accuracy_percent": action_acc,
            "target_accuracy_percent": target_acc,
            "symbolic_decision_accuracy_percent": decision_acc,
            "repaired_cases_count": repaired_count,
            "repaired_rate_percent": round(repaired_count / total * 100, 2),
            "false_negatives_count": len(false_negatives),
            "false_positives_count": len(false_positives),
            "parser_mismatches_count": len(mismatches),
            "mean_latency_ms": mean_latency,
            "p95_latency_ms": p95_latency,
            "mean_prompt_tokens": mean_prompt_tokens,
            "mean_completion_tokens": mean_completion_tokens
        },
        "language_breakdown": {
            l: {
                "total": s["total"],
                "strict_pass": s["strict_ok"],
                "strict_accuracy_percent": round(s["strict_ok"] / s["total"] * 100, 2) if s["total"] else 0,
                "action_accuracy_percent": round(s["action_ok"] / s["total"] * 100, 2) if s["total"] else 0,
                "target_accuracy_percent": round(s["target_ok"] / s["total"] * 100, 2) if s["total"] else 0
            }
            for l, s in lang_stats.items()
        },
        "category_breakdown": {
            c: {
                "total": s["total"],
                "strict_pass": s["strict_ok"],
                "strict_accuracy_percent": round(s["strict_ok"] / s["total"] * 100, 2) if s["total"] else 0,
                "action_accuracy_percent": round(s["action_ok"] / s["total"] * 100, 2) if s["total"] else 0,
                "target_accuracy_percent": round(s["target_ok"] / s["total"] * 100, 2) if s["total"] else 0
            }
            for c, s in cat_stats.items()
        },
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "mismatches": mismatches,
        "all_results": results
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print("  NEURAL API BENCHMARK REPORT SUMMARY")
    print("=" * 80)
    print(f"Total Cases Tested:            {total}")
    print(f"Strict Pass Accuracy:          {strict_acc}% ({strict_pass}/{total})")
    print(f"Action Extraction Accuracy:    {action_acc}% ({action_correct}/{total})")
    print(f"Target Entity Accuracy:        {target_acc}% ({target_correct}/{total})")
    print(f"Symbolic Decision Accuracy:    {decision_acc}% ({decision_correct}/{total})")
    print(f"Symbolic Repair Loop Triggered:{repaired_count} times ({round(repaired_count/total*100, 1)}%)")
    print(f"Mean Latency:                  {mean_latency} ms (P95: {p95_latency} ms)")
    print(f"Mean Prompt Tokens:            {mean_prompt_tokens} tokens")
    print(f"False Negatives (Rejected):    {len(false_negatives)}")
    print(f"False Positives (Leaked):      {len(false_positives)}")
    print(f"Parser Mismatches:             {len(mismatches)}")
    print("=" * 80)

    print("\n[Language Breakdown]:")
    for l, s in summary_data["language_breakdown"].items():
        print(f"  - {l.upper():3}: Strict={s['strict_accuracy_percent']:5.1f}% | Action={s['action_accuracy_percent']:5.1f}% | Target={s['target_accuracy_percent']:5.1f}% ({s['strict_pass']}/{s['total']})")

    print("\n[Category Breakdown]:")
    for c, s in summary_data["category_breakdown"].items():
        print(f"  - {c:22}: Strict={s['strict_accuracy_percent']:5.1f}% | Target={s['target_accuracy_percent']:5.1f}% ({s['strict_pass']}/{s['total']})")

    if false_negatives:
        print("\n[CRITICAL: False Negatives - Player commands rejected by system]:")
        for fn in false_negatives:
            print(f"  * [{fn['id']}] \"{fn['query']}\"")
            print(f"    Expected: {fn['expected']}")
            print(f"    Actual:   {fn['actual']}")
            print(f"    Feedback: {fn['reason']}")

    print(f"\nFull results saved to: {RESULTS_PATH}")
    return summary_data


if __name__ == "__main__":
    run_benchmark()
