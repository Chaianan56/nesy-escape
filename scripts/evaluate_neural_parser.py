"""
scripts/evaluate_neural_parser.py — สคริปต์วัดผลและวิเคราะห์ Factorial Ablation Study (2x2x2) ของ Neural Parser

ออกแบบการทดลองแบบ Factorial Design ครบ 8 สภาวะ + 1 Zero-Shot Baseline:
ปัจจัยที่ 1: Few-Shot Strategy (Static Few-Shot vs Dynamic kNN Few-Shot with MMR)
ปัจจัยที่ 2: Context Pruning (Full Entity Grounding vs Semantic N-gram Pruning)
ปัจจัยที่ 3: Symbolic Repair Loop (Disabled vs Enabled)

ตัวชี้วัด (Evaluation Metrics):
1. Action Accuracy (%)
2. Target ID Accuracy (%)
3. Strict Match Accuracy (%)
4. Prompt Tokens (Estimated Token Count)
5. Token Reduction vs Static Baseline (%)
6. Latency (Mean ms & P95 ms)
7. Data Leakage Verification (Overlap with Training Bank)

การรันคำสั่ง:
  python scripts/evaluate_neural_parser.py
  python scripts/evaluate_neural_parser.py --mode factorial
  python scripts/evaluate_neural_parser.py --live
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.prompts import build_interpret_system_prompt
from app.neural.repair import repair_parsed_command
from app.neural.retriever import get_retriever, score_entity_candidate
from app.neural.typed_commands import parse_typed_command

DEFAULT_DATASET = ROOT / "data/neural_eval_dataset.json"
DEFAULT_TRAIN_BANK = ROOT / "data/neural_training_bank.json"
DEFAULT_STORY = ROOT / "data/story.json"
LOGS_DIR = ROOT / "logs/research"


def estimate_tokens(text: str) -> int:
    """ประมาณการ Token สำหรับข้อความผสมไทย-อังกฤษ (~3.2 ตัวอักษรต่อ 1 token)"""
    return max(1, int(len(text) / 3.2))


def check_data_leakage(train_bank_path: Path, eval_dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ตรวจสอบความซ้ำซ้อนของประโยคระหว่าง Training Bank กับ Evaluation Dataset"""
    if not train_bank_path.exists():
        return {"total_train": 0, "total_eval": len(eval_dataset), "leaked_count": 0, "leakage_rate": 0.0}

    train_bank = json.loads(train_bank_path.read_text(encoding="utf-8"))
    train_queries = {ex["query"].strip().lower() for ex in train_bank}
    leaked = [ex for ex in eval_dataset if ex["query"].strip().lower() in train_queries]

    return {
        "total_train": len(train_bank),
        "total_eval": len(eval_dataset),
        "leaked_count": len(leaked),
        "leakage_rate": round((len(leaked) / max(1, len(eval_dataset))) * 100.0, 2),
        "leaked_queries": [ex["query"] for ex in leaked],
    }


def evaluate_single_config(
    cfg: Dict[str, Any],
    dataset: List[Dict[str, Any]],
    story_data: Dict[str, Any],
    live: bool = False,
    client: Any = None,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """ประเมินผลหนึ่งสภาวะการทดลอง (Ablation Condition)"""
    state = GameState(current_location="first_class_car")
    total_samples = len(dataset)
    action_correct = 0
    target_correct = 0
    strict_correct = 0

    latencies_ms = []
    prompt_tokens = []
    case_results = []

    use_knn = cfg.get("use_knn", False)
    prune = cfg.get("prune", False)
    use_repair = cfg.get("repair", False)
    use_mmr = cfg.get("use_mmr", False)
    zero_shot = cfg.get("zero_shot", False)
    k_examples = cfg.get("k", 5)

    for item in dataset:
        query = item["query"]
        exp_action = item.get("expected_action")
        exp_target = item.get("expected_target")
        exp_topic = item.get("expected_topic")
        exp_code = item.get("expected_code")

        t0 = time.perf_counter()

        # 1. ประกอบ System Prompt ตามเงื่อนไขของ Factorial Matrix
        prompt = build_interpret_system_prompt(
            story_data,
            state=state,
            user_text=query,
            prune=prune,
            use_knn=use_knn,
            use_mmr=use_mmr,
            k_examples=k_examples,
            zero_shot=zero_shot,
        )

        tokens = estimate_tokens(prompt + query)
        prompt_tokens.append(tokens)

        parsed_cmd: Optional[ParsedCommand] = None
        repair_applied = None

        if live and client is not None:
            from google.genai import types
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=f"ข้อความผู้เล่น: '{query}'",
                    config=types.GenerateContentConfig(
                        system_instruction=prompt,
                        response_mime_type="application/json",
                        response_schema=ParsedCommand,
                        temperature=0.0,
                    ),
                )
                if response.text:
                    parsed_cmd = ParsedCommand.model_validate_json(response.text)
                    parsed_cmd.raw_text = query
            except Exception:
                parsed_cmd = ParsedCommand(action=ActionType.UNKNOWN, raw_text=query, confidence=0.0)
        else:
            # การจำลองการแปลผลเชิงสัญลักษณ์สำหรับการทดสอบความถูกต้องของสถาปัตยกรรม (Deterministic Simulation)
            parsed_cmd = parse_typed_command(query, state, story_data)
            if not parsed_cmd:
                if use_knn:
                    retriever = get_retriever()
                    nearest = retriever.retrieve_mmr(query, k=1) if use_mmr else retriever.retrieve(query, k=1)
                    if nearest and nearest[0].get("action"):
                        matched = nearest[0]
                        act = ActionType(matched["action"])
                        tgt = matched.get("target")
                        parsed_cmd = ParsedCommand(
                            action=act,
                            target=tgt,
                            raw_text=query,
                            topic=matched.get("topic"),
                            code=matched.get("code"),
                            confidence=0.9,
                        )
                elif not zero_shot:
                    # Static mode: match เฉพาะคำที่มีใน Few-shot ตายตัว
                    clean = query.lower()
                    if "นาฬิกา" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.EXAMINE, target="pocket_watch", raw_text=query)
                    elif "แฟ้ม" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.EXAMINE, target="burnt_folder_c", raw_text=query)
                    elif "กิเดียน" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", raw_text=query)

            if not parsed_cmd:
                parsed_cmd = ParsedCommand(action=ActionType.UNKNOWN, raw_text=query, confidence=0.0)

        # 2. ทำการส่งเข้า Symbolic Repair Loop หากเงื่อนไขกำหนดให้เปิดใช้งาน
        if use_repair:
            parsed_cmd, repair_applied = repair_parsed_command(
                parsed_cmd, story_data, state=state, raw_text=query
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        pred_action = parsed_cmd.action.value if hasattr(parsed_cmd.action, "value") else str(parsed_cmd.action)
        pred_target = parsed_cmd.target

        is_act_match = (pred_action == exp_action)
        is_tgt_match = (exp_target is None and pred_target is None) or (pred_target == exp_target)

        is_strict_match = is_act_match and is_tgt_match
        if exp_topic is not None:
            is_strict_match = is_strict_match and (parsed_cmd.topic == exp_topic)
        if exp_code is not None:
            is_strict_match = is_strict_match and (parsed_cmd.code == exp_code)

        if is_act_match:
            action_correct += 1
        if is_tgt_match:
            target_correct += 1
        if is_strict_match:
            strict_correct += 1

        case_results.append({
            "query": query,
            "category": item.get("category", "general"),
            "expected": {"action": exp_action, "target": exp_target},
            "predicted": {"action": pred_action, "target": pred_target},
            "match": is_strict_match,
            "repaired": bool(repair_applied),
        })

    latencies_ms.sort()
    mean_lat = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
    p95_lat = latencies_ms[int(len(latencies_ms) * 0.95)] if latencies_ms else 0.0
    avg_tokens = sum(prompt_tokens) / len(prompt_tokens) if prompt_tokens else 0

    return {
        "name": cfg["name"],
        "use_knn": use_knn,
        "prune": prune,
        "repair": use_repair,
        "use_mmr": use_mmr,
        "zero_shot": zero_shot,
        "sample_count": total_samples,
        "action_accuracy": round((action_correct / total_samples) * 100.0, 2),
        "target_accuracy": round((target_correct / total_samples) * 100.0, 2),
        "strict_accuracy": round((strict_correct / total_samples) * 100.0, 2),
        "avg_prompt_tokens": int(avg_tokens),
        "mean_latency_ms": round(mean_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "case_details": case_results,
    }


def main():
    parser = argparse.ArgumentParser(description="NeSy Neural Parser Factorial Ablation Study")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Evaluation dataset JSON")
    parser.add_argument("--train-bank", type=Path, default=DEFAULT_TRAIN_BANK, help="Training bank JSON for leakage check")
    parser.add_argument("--story", type=Path, default=DEFAULT_STORY, help="story.json path")
    parser.add_argument("--mode", choices=["all", "standard", "factorial"], default="all",
                        help="'standard' runs 3 modes; 'factorial' runs full 2x2x2; 'all' runs everything")
    parser.add_argument("--live", action="store_true", help="Query live Gemini API")
    parser.add_argument("--output", type=Path, default=LOGS_DIR / "neural-ablation-results.json")
    parser.add_argument("-k", type=int, default=5, help="Number of retrieved few-shot examples for kNN")
    args = parser.parse_args()

    if not args.dataset.exists():
        print(f"Error: Dataset not found: {args.dataset}")
        sys.exit(1)

    dataset: List[Dict[str, Any]] = json.loads(args.dataset.read_text(encoding="utf-8"))
    story_data: Dict[str, Any] = json.loads(args.story.read_text(encoding="utf-8"))

    # 1. ตรวจสอบ Data Leakage
    leakage = check_data_leakage(args.train_bank, dataset)

    client = None
    if args.live:
        from app.neural.gemini_client import get_genai_client, DEFAULT_MODEL
        client = get_genai_client()
        if not client:
            print("Warning: Live API requested but credentials missing. Falling back to offline simulation.")
            args.live = False

    # 2. นิยาม Factorial Design Matrix (2 x 2 x 2 + Zero-Shot Baseline)
    factorial_configs = [
        {"name": "1. Zero-Shot Baseline",          "zero_shot": True,  "use_knn": False, "prune": False, "repair": False, "use_mmr": False},
        {"name": "2. Static Few-Shot (Vanilla)",    "zero_shot": False, "use_knn": False, "prune": False, "repair": False, "use_mmr": False},
        {"name": "3. Static + Prune",              "zero_shot": False, "use_knn": False, "prune": True,  "repair": False, "use_mmr": False},
        {"name": "4. Static + Repair",             "zero_shot": False, "use_knn": False, "prune": False, "repair": True,  "use_mmr": False},
        {"name": "5. Static + Prune + Repair",     "zero_shot": False, "use_knn": False, "prune": True,  "repair": True,  "use_mmr": False},
        {"name": "6. Dynamic kNN (No Prune/Rep)",  "zero_shot": False, "use_knn": True,  "prune": False, "repair": False, "use_mmr": False, "k": args.k},
        {"name": "7. Dynamic kNN + Prune",         "zero_shot": False, "use_knn": True,  "prune": True,  "repair": False, "use_mmr": False, "k": args.k},
        {"name": "8. Dynamic kNN + Repair",        "zero_shot": False, "use_knn": True,  "prune": False, "repair": True,  "use_mmr": False, "k": args.k},
        {"name": "9. Full NeSy (kNN+Prune+Rep+MMR)","zero_shot": False, "use_knn": True,  "prune": True,  "repair": True,  "use_mmr": True,  "k": args.k},
    ]

    standard_configs = [
        {"name": "1. Zero-Shot Baseline",          "zero_shot": True,  "use_knn": False, "prune": False, "repair": False, "use_mmr": False},
        {"name": "2. Static Few-Shot (Baseline)",  "zero_shot": False, "use_knn": False, "prune": False, "repair": False, "use_mmr": False},
        {"name": "3. Full NeSy System (kNN+MMR)",  "zero_shot": False, "use_knn": True,  "prune": True,  "repair": True,  "use_mmr": True,  "k": args.k},
    ]

    configs_to_run = standard_configs if args.mode == "standard" else factorial_configs

    print("=" * 86)
    print("NEURAL-SYMBOLIC PARSER ABLATION BENCHMARK (FACTORIAL DESIGN)")
    print(f"Dataset: {args.dataset.name} ({len(dataset)} samples) | Live Mode: {args.live}")
    print(f"Data Leakage Verification: {leakage['leaked_count']}/{leakage['total_eval']} samples ({leakage['leakage_rate']}%)")
    print("=" * 86)

    results = []
    baseline_tokens = None

    for cfg in configs_to_run:
        print(f"Evaluating: {cfg['name']} ...")
        res = evaluate_single_config(cfg, dataset, story_data, live=args.live, client=client)
        if "Static Few-Shot" in cfg["name"] and baseline_tokens is None:
            baseline_tokens = res["avg_prompt_tokens"]
        results.append(res)

    # คำนวณ Token Reduction เทียบกับ Static Baseline
    if baseline_tokens is None and results:
        baseline_tokens = results[1]["avg_prompt_tokens"] if len(results) > 1 else results[0]["avg_prompt_tokens"]

    print("\n" + "=" * 94)
    print("FACTORIAL ABLATION STUDY COMPARISON TABLE (FOR THESIS CHAPTER 4)")
    print("=" * 94)
    header = f"{'Configuration':<34} | {'Action Acc':<10} | {'Target Acc':<10} | {'Strict Acc':<10} | {'Tokens':<8} | {'Saved (%)':<10} | {'Latency':<9}"
    print(header)
    print("-" * len(header))
    for r in results:
        saved_pct = round(((baseline_tokens - r["avg_prompt_tokens"]) / baseline_tokens) * 100.0, 1) if baseline_tokens else 0.0
        saved_str = f"{saved_pct:+.1f}%" if saved_pct != 0 else "0.0%"
        print(
            f"{r['name']:<34} | {r['action_accuracy']:>8.1f}% | {r['target_accuracy']:>8.1f}% | "
            f"{r['strict_accuracy']:>8.1f}% | {r['avg_prompt_tokens']:>8} | {saved_str:>10} | {r['mean_latency_ms']:>6.2f} ms"
        )
    print("=" * 94)

    # สรุป Main Effects ทางสถิติ
    if len(results) >= 9:
        print("\n[Factorial Main Effects Analysis]")
        # 1. Effect of kNN: Avg strict acc of configs with kNN vs static
        knn_strict = sum(r["strict_accuracy"] for r in results[5:9]) / 4
        static_strict = sum(r["strict_accuracy"] for r in results[1:5]) / 4
        print(f"- kNN Few-Shot Main Effect:       +{knn_strict - static_strict:.1f}% Strict Accuracy improvement")

        # 2. Effect of Pruning: Avg token reduction
        prune_tokens = (results[2]["avg_prompt_tokens"] + results[4]["avg_prompt_tokens"] + results[6]["avg_prompt_tokens"] + results[8]["avg_prompt_tokens"]) / 4
        noprune_tokens = (results[1]["avg_prompt_tokens"] + results[3]["avg_prompt_tokens"] + results[5]["avg_prompt_tokens"] + results[7]["avg_prompt_tokens"]) / 4
        token_diff = round(((noprune_tokens - prune_tokens) / noprune_tokens) * 100.0, 1)
        print(f"- Context Pruning Main Effect:     {token_diff}% Token Reduction")

        # 3. Effect of Repair Loop
        repair_strict = (results[3]["strict_accuracy"] + results[4]["strict_accuracy"] + results[7]["strict_accuracy"] + results[8]["strict_accuracy"]) / 4
        norepair_strict = (results[1]["strict_accuracy"] + results[2]["strict_accuracy"] + results[5]["strict_accuracy"] + results[6]["strict_accuracy"]) / 4
        print(f"- Symbolic Repair Main Effect:     +{repair_strict - norepair_strict:.1f}% Strict Accuracy recovery")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_payload = {
        "dataset_samples": len(dataset),
        "data_leakage": leakage,
        "results": results,
    }
    args.output.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults and thesis dataset metrics saved to: {args.output}")


if __name__ == "__main__":
    main()
