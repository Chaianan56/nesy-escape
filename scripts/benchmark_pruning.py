"""
scripts/benchmark_pruning.py — Benchmark Script เปรียบเทียบ Latency และ Token Savings
ระหว่าง Full Original Prompt (Unpruned) กับ Dynamic Semantic Pruning

วิธีรัน:
    python scripts/benchmark_pruning.py
"""

import sys
import time
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.schemas import GameState, ParsedCommand
from app.neural.prompts import build_interpret_system_prompt
from app.neural.gemini_client import (
    STORY_DATA,
    DEFAULT_MODEL,
    llm_online,
    _clients,
)

try:
    from google.genai import types
except ImportError:
    types = None


TEST_CASES: List[Tuple[str, GameState]] = [
    (
        "ดูรอบๆ",
        GameState(current_location="lounge_car"),
    ),
    (
        "เดินไปตู้โดยสารชั้นหนึ่ง",
        GameState(current_location="lounge_car"),
    ),
    (
        "ตรวจดูนาฬิกาพกกลไก",
        GameState(current_location="first_class_car"),
    ),
    (
        "ขอสอบปากคำกิเดียน ฮาร์ตหน่อย",
        GameState(current_location="lounge_car"),
    ),
    (
        "ตรวจดูเศษเอกสารไหม้ไฟ",
        GameState(current_location="first_class_car"),
    ),
    (
        "เดินไปที่ตู้โดยสารชั้นสอง",
        GameState(current_location="dining_car_staff"),
    ),
]


def measure_prompt_length():
    """วัดความยาวอักขระและประมาณการ Token ของ System Prompt"""
    print("\n" + "=" * 78)
    print("📊 1. การเปรียบเทียบขนาด System Prompt และประมาณการ Token")
    print("=" * 78)

    full_prompt = build_interpret_system_prompt(STORY_DATA, prune=False)
    full_len = len(full_prompt)
    full_tokens_est = int(full_len / 3.5)

    print(f"🔹 Full Prompt (Unpruned): {full_len:,} Chars (~{full_tokens_est:,} Tokens)")
    print("-" * 78)
    print(f"{'#':<3} | {'User Command':<30} | {'Pruned Chars':<14} | {'Token Savings (%)':<18}")
    print("-" * 78)

    for i, (text, state) in enumerate(TEST_CASES, 1):
        pruned_prompt = build_interpret_system_prompt(STORY_DATA, state=state, user_text=text, prune=True)
        pruned_len = len(pruned_prompt)
        savings_pct = ((full_len - pruned_len) / full_len) * 100
        print(f"{i:<3} | {text:<30} | {pruned_len:<14,} | {savings_pct:>16.1f}%")

    print("-" * 78)


def run_latency_benchmark():
    """จับเวลา Latency การเรียก Gemini API จริง (ถ้ามี GEMINI_API_KEY)"""
    if not llm_online():
        print("\n⚠️ ไม่พบ GEMINI_API_KEY หรือ GenAI SDK จึงแสดงเฉพาะผลการเปรียบเทียบ Prompt Size")
        print("💡 หากต้องการวัด Latency API จริง ให้ตั้งค่า GEMINI_API_KEY ในไฟล์ .env แล้วรันใหม่")
        return

    clients = _clients()
    client = clients[0]

    print("\n" + "=" * 80)
    print(f"🚀 2. การวัด Latency API จริงด้วย Gemini Model: '{DEFAULT_MODEL}'")
    print("=" * 80)
    print(f"{'#':<2} | {'User Command':<26} | {'Unpruned (ms)':<14} | {'Pruned (ms)':<13} | {'Speedup (%)':<12}")
    print("-" * 80)

    unpruned_system_prompt = build_interpret_system_prompt(STORY_DATA, prune=False)

    speedup_list = []
    for i, (text, state) in enumerate(TEST_CASES, 1):
        prompt_content = (
            f"ข้อความผู้เล่น (Raw Input): '{text}'\n"
            f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
            f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
            f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
        )

        # 1. วัด Latency แบบ Unpruned
        t0 = time.perf_counter()
        try:
            _ = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=unpruned_system_prompt,
                    response_mime_type="application/json",
                    response_schema=ParsedCommand,
                    temperature=0.0,
                ),
            )
            t_unpruned = (time.perf_counter() - t0) * 1000
        except Exception as e:
            print(f"ข้ามข้อ {i} (Unpruned Error): {str(e)[:50]}")
            continue

        # 2. วัด Latency แบบ Pruned
        pruned_system_prompt = build_interpret_system_prompt(STORY_DATA, state=state, user_text=text, prune=True)
        t0 = time.perf_counter()
        try:
            _ = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=pruned_system_prompt,
                    response_mime_type="application/json",
                    response_schema=ParsedCommand,
                    temperature=0.0,
                ),
            )
            t_pruned = (time.perf_counter() - t0) * 1000
        except Exception as e:
            print(f"ข้ามข้อ {i} (Pruned Error): {str(e)[:50]}")
            continue

        speedup = ((t_unpruned - t_pruned) / t_unpruned) * 100 if t_unpruned > 0 else 0.0
        speedup_list.append(speedup)
        print(f"{i:<2} | {text:<26} | {t_unpruned:>12.1f} ms | {t_pruned:>11.1f} ms | {speedup:>10.1f}%")

    print("-" * 80)
    if speedup_list:
        avg_speedup = sum(speedup_list) / len(speedup_list)
        print(f"💡 เฉลี่ย Speedup โดยรวม: {avg_speedup:.1f}%")
    print("-" * 80)


def main():
    print("🔎 เริ่มต้นการรัน Benchmark เปรียบเทียบ Prompt Engineering Latency & Pruning...")
    measure_prompt_length()
    run_latency_benchmark()
    print("\n✅ เสร็จสิ้นการรัน Benchmark")


if __name__ == "__main__":
    main()
