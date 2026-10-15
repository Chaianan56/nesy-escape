"""
scripts/evaluate_neural_parser.py — สคริปต์วัดผลและวิเคราะห์ Ablation Study ของ Neural Parser

เปรียบเทียบ 3 โหมดการทำงาน:
1. Zero-Shot Parser: ส่งแค่ Schema + Entity Grounding Table (ไม่มีตัวอย่างสอน)
2. Static Few-Shot: ส่ง Prompt พร้อมตัวอย่างตายตัว 25 ข้อใน prompts.py (ระบบเดิม)
3. Dynamic kNN + Semantic Pruning: ดึงตัวอย่างจาก Memory Bank + Semantic N-gram Pruning + Repair Loop (ระบบใหม่)

ตัวชี้วัด (Metrics):
- Action Accuracy (%)
- Target ID Accuracy (%)
- Strict Match Accuracy (%)
- Prompt Length & Estimated Token Usage
- Latency (Mean & P95 ms)

การรัน:
  python scripts/evaluate_neural_parser.py
  python scripts/evaluate_neural_parser.py --live
  python scripts/evaluate_neural_parser.py --mode dynamic-knn
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas import ActionType, GameState, ParsedCommand
from app.neural.prompts import build_interpret_system_prompt
from app.neural.repair import repair_parsed_command
from app.neural.retriever import get_retriever, score_entity_candidate
from app.neural.typed_commands import parse_typed_command

DEFAULT_DATASET = ROOT / "data/neural_eval_dataset.json"
DEFAULT_STORY = ROOT / "data/story.json"
LOGS_DIR = ROOT / "logs/research"


def estimate_tokens(text: str) -> int:
    """ประมาณการ Token สำหรับข้อความผสมไทย-อังกฤษ (~3.2 ตัวอักษรต่อ 1 token)"""
    return max(1, int(len(text) / 3.2))


def evaluate_single_mode(
    mode_name: str,
    dataset: List[Dict[str, Any]],
    story_data: Dict[str, Any],
    live: bool = False,
    k_examples: int = 5,
    client: Any = None,
    model_name: str = "gemini-3.5-flash-lite",
) -> Dict[str, Any]:
    """ประเมินผลโหมดที่ระบุกับชุดข้อมูลทดสอบ"""
    state = GameState(current_location="first_class_car")
    total_samples = len(dataset)
    action_correct = 0
    target_correct = 0
    strict_correct = 0

    latencies_ms = []
    prompt_tokens = []
    case_results = []

    for item in dataset:
        query = item["query"]
        exp_action = item.get("expected_action")
        exp_target = item.get("expected_target")
        exp_topic = item.get("expected_topic")
        exp_code = item.get("expected_code")

        t0 = time.perf_counter()

        # สร้าง System Prompt ตามโหมด
        if mode_name == "zero-shot":
            prompt = build_interpret_system_prompt(
                story_data, state=state, user_text=query, prune=False, zero_shot=True
            )
        elif mode_name == "static-few-shot":
            prompt = build_interpret_system_prompt(
                story_data, state=state, user_text=query, prune=False, use_knn=False
            )
        elif mode_name == "dynamic-knn":
            prompt = build_interpret_system_prompt(
                story_data, state=state, user_text=query, prune=True, use_knn=True, k_examples=k_examples
            )
        else:
            raise ValueError(f"Unknown mode: {mode_name}")

        prompt_len = len(prompt)
        tokens = estimate_tokens(prompt + query)
        prompt_tokens.append(tokens)

        parsed_cmd: Optional[ParsedCommand] = None
        repair_applied = None

        if live and client is not None:
            # รันโมเดลจริงผ่าน Gemini API
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
            except Exception as e:
                parsed_cmd = ParsedCommand(action=ActionType.UNKNOWN, raw_text=query, confidence=0.0)
        else:
            # รันจำลองเชิงสัญลักษณ์สำหรับการทดสอบ Offline / CI
            parsed_cmd = parse_typed_command(query, state, story_data)
            if not parsed_cmd:
                # จำลองการ Match ผ่าน Grounding / kNN Memory Bank
                if mode_name == "dynamic-knn":
                    retriever = get_retriever()
                    nearest = retriever.retrieve(query, k=1)
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
                elif mode_name == "static-few-shot":
                    # Static mode: match เฉพาะคำมาตรฐาน
                    clean = query.lower()
                    if "นาฬิกา" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.EXAMINE, target="pocket_watch", raw_text=query)
                    elif "แฟ้ม" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.EXAMINE, target="burnt_folder_c", raw_text=query)
                    elif "กิเดียน" in clean:
                        parsed_cmd = ParsedCommand(action=ActionType.INTERROGATE, target="gideon_hart", raw_text=query)
                
            if not parsed_cmd:
                parsed_cmd = ParsedCommand(action=ActionType.UNKNOWN, raw_text=query, confidence=0.0)

        # ในโหมด Dynamic kNN: ทำการส่งเข้า Symbolic Repair Loop
        if mode_name == "dynamic-knn":
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
        "mode": mode_name,
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
    parser = argparse.ArgumentParser(description="Evaluate Neural Parser Ablation Study")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Evaluation dataset JSON")
    parser.add_argument("--story", type=Path, default=DEFAULT_STORY, help="story.json path")
    parser.add_argument("--mode", choices=["all", "zero-shot", "static-few-shot", "dynamic-knn"], default="all")
    parser.add_argument("--live", action="store_true", help="Query live Gemini API")
    parser.add_argument("--output", type=Path, default=LOGS_DIR / "neural-ablation-results.json")
    parser.add_argument("-k", type=int, default=5, help="Number of retrieved few-shot examples for kNN")
    args = parser.parse_args()

    if not args.dataset.exists():
        print(f"Error: Dataset not found: {args.dataset}")
        sys.exit(1)

    dataset: List[Dict[str, Any]] = json.loads(args.dataset.read_text(encoding="utf-8"))
    story_data: Dict[str, Any] = json.loads(args.story.read_text(encoding="utf-8"))

    client = None
    if args.live:
        from app.neural.gemini_client import get_genai_client, DEFAULT_MODEL
        client = get_genai_client()
        if not client:
            print("Warning: Live API requested but credentials missing. Falling back to offline simulation.")
            args.live = False

    modes_to_run = (
        ["zero-shot", "static-few-shot", "dynamic-knn"]
        if args.mode == "all"
        else [args.mode]
    )

    print("=" * 80)
    print("NEURAL PARSER ABLATION STUDY BENCHMARK")
    print(f"Dataset: {args.dataset.name} ({len(dataset)} samples) | Live Mode: {args.live}")
    print("=" * 80)

    results = []
    for mode in modes_to_run:
        print(f"Evaluating mode: {mode} ...")
        res = evaluate_single_mode(
            mode, dataset, story_data, live=args.live, k_examples=args.k, client=client
        )
        results.append(res)

    print("\n" + "=" * 80)
    print("ABLATION STUDY SUMMARY COMPARISON TABLE")
    print("=" * 80)
    header = f"{'Mode (Ablation)':<26} | {'Action Acc':<11} | {'Target Acc':<11} | {'Strict Acc':<11} | {'Avg Tokens':<11} | {'Mean Latency':<12}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['mode']:<26} | {r['action_accuracy']:>9.1f}% | {r['target_accuracy']:>9.1f}% | "
            f"{r['strict_accuracy']:>9.1f}% | {r['avg_prompt_tokens']:>11} | {r['mean_latency_ms']:>9.2f} ms"
        )
    print("=" * 80)

    # บันทึกไฟล์ผลลัพธ์
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetailed evaluation results saved to: {args.output}")


if __name__ == "__main__":
    main()
