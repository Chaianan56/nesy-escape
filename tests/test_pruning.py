import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.schemas import GameState, ParsedCommand
from app.neural.prompts import build_interpret_system_prompt, prune_world_entities

__test__ = False

load_dotenv()

# โหลดข้อมูลฉากจำลอง
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "story.json"
STORY_DATA: Dict[str, Any] = json.loads(DATA_PATH.read_text(encoding="utf-8"))

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
client = None  # The manual benchmark creates its client only when invoked.


def build_full_prompt(world_data: Dict[str, Any]) -> str:
    """สร้าง Prompt แบบดั้งเดิมที่ยัด Object ทั้งหมด 26 ชิ้นลงไป"""
    # จำลอง State หลอกๆ เพื่อหลอกฟังก์ชันเดิมให้คืน Object ครบทุกตัว
    fake_state = GameState(
        current_location="*",
        inventory=list(world_data.get("objects", {}).keys()),
    )
    # หรือใช้วิธีดึงตรงๆ จาก world_data ทั้งหมด
    objects_text = "\n".join(
        f"  - ID: '{k}' | ชื่อไทย: '{v.get('name_th', '')}' | ประเภท: {v.get('type', '')}"
        for k, v in world_data.get("objects", {}).items()
    )
    locations_text = "\n".join(
        f"  - ID: '{k}' | ชื่อไทย: '{v.get('name_th', '')}'"
        for k, v in world_data.get("locations", {}).items()
    )
    suspects_text = "\n".join(
        f"  - ID: '{k}' | ชื่อไทย: '{v.get('name_th', '')}' | บทบาท: {v.get('role', '')}"
        for k, v in world_data.get("suspects", {}).items()
    )

    return f"""
คุณคือส่วนตีความภาษาธรรมชาติ (Natural Language Perception Layer) ของเกม NeSy-Escape

หน้าที่: สกัดเจตนาคำสั่งผู้เล่นลงใน ParsedCommand JSON

[สถานที่ / ตู้รถ]
{locations_text}

[วัตถุและหลักฐานทั้งหมดบนขบวน]
{objects_text}

[ผู้ต้องสงสัย]
{suspects_text}
"""


def execute_call(system_instruction: str, user_text: str, state: GameState):
    """เรียก API และจับเวลาอย่างแม่นยำ พร้อมนับ Token ขาเข้า"""
    prompt_content = (
        f"ข้อความผู้เล่น (Raw Input): '{user_text}'\n"
        f"ตู้รถที่ผู้เล่นอยู่ตอนนี้: {state.current_location}\n"
        f"ของที่ถือติดตัว: {state.inventory or 'ไม่มี'}\n"
        f"หลักฐานที่พบแล้ว: {state.discovered_evidence or 'ยังไม่พบ'}"
    )

    global client
    if client is None:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    start_time = time.perf_counter()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt_content,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=ParsedCommand,
            temperature=0.0,
        ),
    )
    latency_ms = (time.perf_counter() - start_time) * 1000

    # ดึงค่า Input Tokens จาก Metadata ที่ส่งกลับมา
    input_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count

    parsed = ParsedCommand.model_validate_json(response.text)
    return latency_ms, input_tokens, parsed


def run_benchmark():
    # ชุดเคสทดสอบกระจายตามตู้รถและสถานะต่างกัน
    test_cases = [
        {
            "text": "ตรวจดูนาฬิกาพกในอกเสื้อ",
            "state": GameState(current_location="first_class_car"),
        },
        {
            "text": "เดินไปที่ตู้สัมภาระ",
            "state": GameState(current_location="lounge_car"),
        },
        {
            "text": "สอบปากคำวินเซนต์เรื่องไฟดับ",
            "state": GameState(current_location="second_class_car"),
        },
        {
            "text": "ตรวจดูแผงควบคุมไฟหลัก",
            "state": GameState(current_location="luggage_van_electrical"),
        },
    ]

    print(f"================================================================================")
    print(f"🚀 เริ่มต้นการทดสอบ Benchmark (Model: {MODEL_NAME})")
    print(f"================================================================================\n")

    results = []

    for idx, case in enumerate(test_cases, 1):
        text = case["text"]
        state = case["state"]

        print(f"[{idx}/{len(test_cases)}] ทดสอบคำสั่ง: \"{text}\" (ตำแหน่ง: {state.current_location})")

        # 1. ทดสอบแบบ Full Prompt (เดิม)
        full_sys_prompt = build_full_prompt(STORY_DATA)
        time.sleep(1)  # พักยิงเพื่อเลี่ยง Rate Limit สั้นๆ
        t_full, tok_full, parsed_full = execute_call(full_sys_prompt, text, state)

        # 2. ทดสอบแบบ Dynamic Pruning (ใหม่)
        pruned_sys_prompt = build_interpret_system_prompt(STORY_DATA, state)
        time.sleep(1)
        t_pruned, tok_pruned, parsed_pruned = execute_call(pruned_sys_prompt, text, state)

        token_reduction = ((tok_full - tok_pruned) / tok_full) * 100 if tok_full else 0
        speedup = ((t_full - t_pruned) / t_full) * 100 if t_full else 0

        results.append({
            "cmd": text,
            "tok_full": tok_full,
            "tok_pruned": tok_pruned,
            "tok_red": token_reduction,
            "lat_full": t_full,
            "lat_pruned": t_pruned,
            "speedup": speedup,
            "match": (parsed_full.action == parsed_pruned.action and parsed_full.target == parsed_pruned.target),
        })

    # สรุปผลตาราง
    print("\n" + "=" * 90)
    print(f"{'คำสั่งทดสอบ':<28} | {'Tokens (เดิม -> ใหม่)':<22} | {'Latency (เดิม -> ใหม่)':<24} | {'ความแม่นยำ'}")
    print("=" * 90)

    avg_tok_red = sum(r["tok_red"] for r in results) / len(results)
    avg_speedup = sum(r["speedup"] for r in results) / len(results)

    for r in results:
        tok_str = f"{r['tok_full']} -> {r['tok_pruned']} (-{r['tok_red']:.1f}%)"
        lat_str = f"{r['lat_full']:.0f}ms -> {r['lat_pruned']:.0f}ms ({r['speedup']:+.1f}%)"
        acc_str = "✅ ตรงกัน" if r["match"] else "❌ ไม่ตรง"
        print(f"{r['cmd']:<28} | {tok_str:<22} | {lat_str:<24} | {acc_str}")

    print("=" * 90)
    print(f"📊 สรุปภาพรวม: ลด Tokens เฉลี่ย {avg_tok_red:.2f}% | Latency เร็วขึ้นเฉลี่ย {avg_speedup:.2f}%\n")


if __name__ == "__main__":
    run_benchmark()
