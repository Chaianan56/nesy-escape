"""
run_episode.py — การทดลองที่สอง วัดสถานะที่แตกสะสมเมื่อเล่นยาว

ต่างจาก run_experiment.py อย่างไร
    run_experiment  ยิงทีละคำสั่งจาก checkpoint ที่ล็อกไว้ สองโหมดเห็นสถานะเดียวกันเสมอ
                    วัดได้ว่า "ตัดสินถูกไหม" แต่วัดไม่ได้ว่าความผิดพลาดสะสมยังไง
    run_episode     ปล่อยให้แต่ละโหมดถือสถานะของตัวเองแล้วเล่นยาว
                    วัดว่าสถานะของใครหลุดจากความถูกต้องตามกฎก่อนกัน และหลุดแค่ไหน

ตัววัดหลัก
    สถานะที่เป็นไปไม่ได้   นับด้วย app/invariants.py ทุกตา
                          โหมด B เป็นศูนย์เสมอโดยโครงสร้าง เพราะทุกการเปลี่ยนสถานะผ่านกฎมาแล้ว
    ตาที่สถานะเริ่มแตก     ตาแรกที่สถานะสองโหมดไม่ตรงกัน
    ปิดคดีโดยไม่มีหลักฐาน  โหมดไหนยอมให้ accuse สำเร็จทั้งที่หลักฐานไม่ครบสี่เสา

ข้อจำกัดที่ต้องเขียนไว้ในเล่ม
    พอสถานะสองโหมดแตกกันแล้ว prompt ที่ส่งเข้า interpret ก็ต่างกัน
    จึงแชร์ ParsedCommand ระหว่างสองโหมดไม่ได้อีก ความแปรปรวนจากการสุ่มของ LLM
    จึงกลับเข้ามาเป็นตัวแปรที่สอง ข้ออ้างของการทดลองนี้จึงเป็น
    "ระบบทั้งระบบ B รักษาความถูกต้องของสถานะได้ดีกว่า"
    ไม่ใช่ "ใครเป็นผู้ตัดสินคือสาเหตุเดียว" อย่างการทดลองที่หนึ่ง
    สคริปต์นี้ยังแชร์ผลตีความให้ตราบใดที่สองสถานะยังเหมือนกันเป๊ะ เพื่อลดตัวแปรนั้นให้น้อยที่สุด

รันด้วย
    python run_episode.py                    รันทุกบท
    python run_episode.py --episode EP2      เลือกบท
    python run_episode.py --dry-run          ตรวจกลไกโดยไม่เรียก LLM (ใช้ตัวสำรอง)
    python run_episode.py --report-only      สรุปจาก cache เดิม
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("NEURAL_STRICT", "1")

from app.invariants import violations
from app.neural.gemini_client import NeuralUnavailable, decide_autonomously, interpret, llm_online
from app.schemas import Decision, GameState, ParsedCommand, SystemMode
from app.symbolic.engine import SymbolicEngine, apply_changes
from run_experiment import Cache, RateLimiter, decide_key, interpret_key, with_retry

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG_DIR = ROOT / "logs"
CACHE_PATH = LOG_DIR / "llm_cache.json"


def snapshot(state: GameState) -> tuple:
    """ส่วนของสถานะที่ใช้เทียบว่าสองโหมดยังเดินด้วยกันอยู่ไหม

    ไม่รวม turn_count กับ elapsed_seconds เพราะสองค่านั้นเดินเท่ากันเสมอ
    ไม่ว่าคำสั่งจะผ่านหรือไม่ผ่าน จึงไม่ได้บอกอะไรเรื่องการแตกของสถานะ
    """
    return (
        state.current_location,
        tuple(sorted(state.inventory)),
        tuple(sorted(state.discovered_evidence)),
        tuple(sorted(state.unlocked_objects)),
        tuple(sorted(state.interrogated_suspects)),
    )


def run_episode(ep: dict, engine, cache, limiter, args) -> dict:
    world = engine.world
    state_a = GameState()
    state_b = GameState()
    diverged_at = None
    turns = []

    print(f"\n{'='*74}\n{ep['id']} · {ep['name']}\n{ep['purpose']}\n{'='*74}", flush=True)

    for turn, text in enumerate(ep["commands"], 1):
        shared = snapshot(state_a) == snapshot(state_b)

        # ตราบใดที่สองสถานะยังเหมือนกันเป๊ะ ใช้ผลตีความร่วมกันได้ ลดตัวแปรและประหยัดโควตา
        parsed_b = _interpret(text, state_b, cache, limiter, args)
        parsed_a = parsed_b if shared else _interpret(text, state_a, cache, limiter, args)

        decision_b = engine.decide(parsed_b, state_b)
        decision_a = _decide_a(text, state_a, parsed_a, cache, limiter, args)

        if decision_b.allowed:
            state_b = apply_changes(state_b, decision_b.state_changes)
        if decision_a.allowed:
            state_a = apply_changes(state_a, decision_a.state_changes)

        bad_a = violations(state_a, world)
        bad_b = violations(state_b, world)
        if diverged_at is None and snapshot(state_a) != snapshot(state_b):
            diverged_at = turn

        turns.append({
            "turn": turn, "text": text,
            "parsed_a": f"{parsed_a.action.value}/{parsed_a.target}",
            "parsed_b": f"{parsed_b.action.value}/{parsed_b.target}",
            "shared_parse": shared,
            "a_allowed": decision_a.allowed, "b_allowed": decision_b.allowed,
            "b_rule": decision_b.violated_rule_id,
            "a_violations": bad_a, "b_violations": bad_b,
            "a_evidence": len(state_a.discovered_evidence),
            "b_evidence": len(state_b.discovered_evidence),
        })

        flag = "  ⚠ สถานะเป็นไปไม่ได้" if bad_a else ""
        print(f"  [{turn:2}] {text[:34]:36} A={'ผ่าน ' if decision_a.allowed else 'ปฏิเสธ'} "
              f"B={'ผ่าน ' if decision_b.allowed else 'ปฏิเสธ'}{flag}", flush=True)

    return {
        "episode": ep["id"], "name": ep["name"], "turns": turns,
        "diverged_at": diverged_at,
        "final_a_violations": violations(state_a, world),
        "final_b_violations": violations(state_b, world),
        "final_a_evidence": len(state_a.discovered_evidence),
        "final_b_evidence": len(state_b.discovered_evidence),
    }


def _interpret(text, state, cache, limiter, args) -> ParsedCommand:
    key = interpret_key(text, state)
    hit = cache.get(key)
    if hit is not None:
        return ParsedCommand.model_validate(hit["parsed"])
    if args.report_only:
        raise SystemExit(f"ยังไม่มีใน cache: {text!r} — สั่ง --report-only ไว้จึงเรียก LLM ไม่ได้")
    parsed, ms = with_retry(interpret, text, state, limiter=limiter)
    cache.put(key, {"parsed": parsed.model_dump(), "latency_ms": ms})
    return parsed


def _decide_a(text, state, parsed, cache, limiter, args) -> Decision:
    key = decide_key(text, state, parsed)
    hit = cache.get(key)
    if hit is not None:
        return Decision.model_validate(hit["decision"])
    if args.report_only:
        raise SystemExit(f"ยังไม่มีใน cache: {text!r}")
    decision, ms = with_retry(decide_autonomously, text, state, parsed, limiter=limiter)
    cache.put(key, {"decision": decision.model_dump(), "latency_ms": ms})
    return decision


def report(results):
    print(f"\n{'='*74}\nสรุปการทดลองที่สอง\n{'='*74}")
    print(f"\n{'บท':<6}{'ตา':>4}{'A พังตาแรก':>13}{'A อยู่ในสถานะพัง':>19}"
          f"{'B พัง':>9}{'สถานะแตกที่ตา':>16}")
    print("-" * 78)
    for r in results:
        a_turns = [t["turn"] for t in r["turns"] if t["a_violations"]]
        b_turns = [t["turn"] for t in r["turns"] if t["b_violations"]]
        first = a_turns[0] if a_turns else "ไม่พัง"
        div = r["diverged_at"] if r["diverged_at"] else "ไม่แตก"
        print(f"{r['episode']:<6}{len(r['turns']):>4}{str(first):>13}"
              f"{len(a_turns):>15} ตา{len(b_turns):>7} ตา{str(div):>16}")

    total_turns = sum(len(r["turns"]) for r in results)
    a_bad = sum(1 for r in results for t in r["turns"] if t["a_violations"])
    b_bad = sum(1 for r in results for t in r["turns"] if t["b_violations"])
    broke = sum(1 for r in results if any(t["a_violations"] for t in r["turns"]))
    print("-" * 78)
    print(f"{'รวม':<6}{total_turns:>4}{'':>13}{a_bad:>15} ตา{b_bad:>7} ตา")
    print(f"\nโหมด A พาไปสู่สถานะที่เป็นไปไม่ได้ใน {broke}/{len(results)} บท "
          f"คิดเป็น {a_bad}/{total_turns} ตา ({a_bad/total_turns:.0%})")
    print(f"โหมด B เป็นศูนย์ทุกบทโดยโครงสร้าง เพราะทุกการเปลี่ยนสถานะผ่านการตรวจกฎมาแล้ว")

    print("\nรายละเอียดสถานะที่เป็นไปไม่ได้ของโหมด A")
    seen = set()
    for r in results:
        for t in r["turns"]:
            for v in t["a_violations"]:
                if v not in seen:
                    seen.add(v)
                    print(f"  {r['episode']} ตาที่ {t['turn']}: {v}")
    if not seen:
        print("  ไม่พบเลย")

    print("\nหลักฐานที่เก็บได้เมื่อจบบท (ตัวชี้ว่าสถานะเดินไปคนละทางแค่ไหน)")
    for r in results:
        print(f"  {r['episode']}: โหมด A {r['final_a_evidence']} ชิ้น | "
              f"โหมด B {r['final_b_evidence']} ชิ้น")

    print("\nปิดคดีโดยหลักฐานไม่ครบ (accuse ที่โหมด A อนุมัติแต่โหมด B ปฏิเสธ)")
    found = False
    for r in results:
        for t in r["turns"]:
            if t["a_allowed"] and not t["b_allowed"] and t["parsed_b"].startswith("accuse"):
                print(f"  {r['episode']} ตาที่ {t['turn']}: \"{t['text']}\" "
                      f"-> โหมด B ปฏิเสธที่ {t['b_rule']}")
                found = True
    if not found:
        print("  ไม่พบ")


def main():
    ap = argparse.ArgumentParser(description="การทดลองที่สอง วัดสถานะที่แตกสะสม")
    ap.add_argument("--episode", nargs="+", help="เลือกบท เช่น EP1 EP2")
    ap.add_argument("--rpm", type=int, default=12)
    ap.add_argument("--report-only", action="store_true", help="ใช้เฉพาะผลใน cache")
    ap.add_argument("--dry-run", action="store_true",
                    help="ตรวจกลไกโดยไม่เรียก LLM ใช้ตัวสำรองแทน ห้ามใช้ผลนี้ในการทดลอง")
    args = ap.parse_args()

    if args.dry_run:
        # ต้องตัดทางไม่ให้เรียก LLM จริง ไม่ใช่แค่ปิด strict mode
        # เดิมปิดแค่ strict แล้วยังมี API key อยู่ สคริปต์จึงยังยิง LLM และกินโควตา
        os.environ["NEURAL_STRICT"] = ""
        os.environ["GEMINI_API_KEY"] = ""
        import app.neural.gemini_client as gc
        gc._client_instance = None
        assert not llm_online(), "--dry-run ต้องไม่เรียก LLM"
        print("โหมดตรวจกลไก ใช้ตัวสำรองแทน LLM — ห้ามนำผลนี้ไปใช้ในการทดลอง\n")
    elif not args.report_only and not llm_online():
        raise SystemExit("ไม่มี GEMINI_API_KEY — การทดลองต้องใช้ LLM จริง")

    eps = json.loads((DATA / "episodes.json").read_text(encoding="utf-8"))["episodes"]
    if args.episode:
        eps = [e for e in eps if e["id"] in args.episode]

    engine = SymbolicEngine()
    cache = Cache(CACHE_PATH)
    limiter = RateLimiter(args.rpm)
    LOG_DIR.mkdir(exist_ok=True)

    results = []
    try:
        for ep in eps:
            results.append(run_episode(ep, engine, cache, limiter, args))
    except NeuralUnavailable as e:
        print(f"\nหยุดกลางคัน เรียก LLM ไม่สำเร็จ: {str(e)[:160]}")
        print("ผลที่ได้มาแล้วถูก cache ไว้ รันซ้ำจะเริ่มต่อจากจุดที่ค้าง")

    if results:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = LOG_DIR / f"{stamp}_episodes.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        report(results)
        print(f"\nไฟล์ผล: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
