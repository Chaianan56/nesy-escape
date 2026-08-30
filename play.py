"""
play.py — สคริปต์ทดสอบเล่นผ่าน Terminal (NeSy-Escape CLI)

หน้าที่:
- ใช้ทดสอบและพิมพ์คำสั่งภาษาไทยเล่นผ่าน Terminal ได้ทันที
- แสดงผลการตีความของ Neuro Layer (ParsedCommand)
- แสดงผลคำตัดสินและ Reasoning Chain ของ Symbolic Layer (Decision)
"""

import sys
from app.schemas import GameState
from app.neural import interpret
from app.symbolic.engine import SymbolicEngine, apply_changes

# ตั้งค่าให้ Terminal รองรับภาษาไทย UTF-8
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    engine = SymbolicEngine()
    state = GameState()
    world = engine.world

    print("==================================================================")
    print(f"🚂 {world.get('title', 'NeSy-Escape')}")
    print("==================================================================")
    print(world.get("briefing", ""))
    print("\nพิมพ์คำสั่งสืบสวนเป็นภาษาไทย (พิมพ์ 'exit' หรือ 'q' เพื่อให้ออก)\n")

    while True:
        try:
            raw_text = input("\nผู้สืบสวน > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nออกจากระบบสืบสวน")
            break

        if not raw_text:
            continue
        if raw_text.lower() in ("exit", "quit", "q", "ออก"):
            print("จบการทำงาน")
            break

        # ------------------------------------------------------------
        # 1. NEURAL LAYER — ตีความภาษาไทยเป็น ParsedCommand
        # ------------------------------------------------------------
        try:
            parsed = interpret(raw_text, state)
        except Exception as e:
            print(f"\n❌ Neural Layer Error: {e}")
            continue

        print(f"\n⚡ Parsed: action='{parsed.action.value}' | target='{parsed.target or 'none'}' | confidence={parsed.confidence:.2f}")

        # ------------------------------------------------------------
        # 2. SYMBOLIC LAYER — ตรวจสอบกฎของเกมและตัดสินใจ
        # ------------------------------------------------------------
        decision = engine.decide(parsed, state)

        # ------------------------------------------------------------
        # 3. STATE UPDATE & OUTPUT DISPLAY
        # ------------------------------------------------------------
        if decision.allowed:
            state = apply_changes(state, decision.state_changes)
            print("Status : ✓ อนุมัติ (ALLOWED)")
        else:
            print(f"Status : ✗ ปฏิเสธ (DENIED - ละเมิดกฎ {decision.violated_rule_id})")

        print(f"Story  : {decision.message}")

        # แสดง Reasoning Chain
        if decision.reasoning_chain:
            print("Reasoning Chain:")
            for step in decision.reasoning_chain:
                symbol = "✓ ผ่าน" if step.passed else "✗ ไม่ผ่าน"
                print(f"  - [{symbol}] {step.rule_id}: {step.description}")

        print(f"Location: {state.current_location} | Inventory: {state.inventory or 'ไม่มี'}")


if __name__ == "__main__":
    main()
