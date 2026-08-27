"""
run_experiment.py — รันชุดคำสั่งใน data/commands.json เข้าทั้งสองโหมด แล้วสรุปผล

    โหมด A (baseline) : LLM ตีความ + ตัดสินเอง
    โหมด B (proposed) : LLM ตีความ -> Symbolic ตัดสิน

การควบคุมตัวแปร (สำคัญที่สุดของไฟล์นี้)
    เรียก interpret() ครั้งเดียวต่อคำสั่ง แล้วใช้ ParsedCommand ตัวเดียวกันทั้งสองโหมด
    ถ้าเรียกแยกกัน ความแปรปรวนจากการสุ่มของ LLM จะปนเข้ามาเป็นตัวแปรที่สอง
    ทำให้ชี้ผลกลับไปที่ "ใครเป็นผู้ตัดสิน" ไม่ได้

กันข้อมูลปนเปื้อน
    บังคับ NEURAL_STRICT=1 เสมอ ถ้าเรียก LLM ไม่สำเร็จจะหยุดและบอก ไม่แอบใช้ fallback

โควตา
    free tier จำกัด request ต่อนาที สคริปต์จึงเดินตามจังหวะที่ตั้งไว้ตั้งแต่แรก
    และ cache ผลลงไฟล์ รันซ้ำเพื่อแก้การวิเคราะห์จึงไม่กินโควตาอีก

รันด้วย:
    python run_experiment.py                 # รันทั้งหมด (ใช้ cache ที่มีอยู่)
    python run_experiment.py --group A       # เฉพาะกลุ่ม A
    python run_experiment.py --limit 10      # ลองสิบข้อแรก
    python run_experiment.py --rpm 10        # ลดจังหวะลงถ้าชนโควตาบ่อย
    python run_experiment.py --report-only   # ไม่เรียก LLM สรุปจาก cache ที่มีอยู่
"""

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

os.environ.setdefault("NEURAL_STRICT", "1")   # ต้องตั้งก่อน import neural layer

from app.neural.gemini_client import (
    SYSTEM_BASELINE_DECISION_PROMPT,
    SYSTEM_INTERPRET_PROMPT,
    DEFAULT_MODEL,
    NeuralUnavailable,
    decide_autonomously,
    interpret,
    llm_online,
)
from app.scenario import checkpoint
from app.schemas import (
    ExperimentLog,
    GameState,
    ParsedCommand,
    SystemMode,
)
from app.symbolic.engine import SymbolicEngine

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG_DIR = ROOT / "logs"
CACHE_PATH = LOG_DIR / "llm_cache.json"


# ============================================================
# CACHE — key คือสิ่งที่กำหนดผลลัพธ์ทั้งหมด ถ้าเปลี่ยนอย่างใดอย่างหนึ่ง ผลต้องถูกเรียกใหม่
# ============================================================
class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        value = self.data.get(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def put(self, key: str, value: dict):
        self.data[key] = value
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


class RateLimiter:
    """เดินตามจังหวะตั้งแต่แรก ดีกว่ายิงรัวแล้วโดน 429 แล้วค่อยถอย"""

    def __init__(self, rpm: int):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self.last = 0.0

    def wait(self):
        gap = self.interval - (time.monotonic() - self.last)
        if gap > 0:
            time.sleep(gap)
        self.last = time.monotonic()


# ============================================================
# CACHE KEY — ต้องผูกกับ "ทุกอย่างที่กำหนดคำตอบ" และไม่ผูกกับอะไรที่ไม่เกี่ยว
#
# เดิมผูกกับ GameState ทั้งก้อน ทำให้เพิ่ม field เดียว (เช่น elapsed_seconds)
# ก็ทิ้ง cache ทั้งหมดทั้งที่คำตอบไม่เปลี่ยน
# ตอนนี้ผูกกับ hash ของ prompt + โมเดล + เฉพาะส่วนของ state ที่ prompt นั้นใช้จริง
# ถ้าใครแก้ prompt หรือเปลี่ยนโมเดล cache จะถูกทิ้งเองอัตโนมัติ — กันผลเก่าปนผลใหม่
# ============================================================
def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


INTERPRET_FP = _fingerprint(DEFAULT_MODEL + SYSTEM_INTERPRET_PROMPT)
DECIDE_FP = _fingerprint(DEFAULT_MODEL + SYSTEM_BASELINE_DECISION_PROMPT)


def interpret_key(text: str, state: GameState) -> str:
    """interpret() ส่งให้ LLM แค่ตำแหน่ง ของติดตัว และหลักฐานที่พบ — ต้องตรงกับ prompt ใน gemini_client"""
    seen = json.dumps([state.current_location, state.inventory, state.discovered_evidence],
                      ensure_ascii=False)
    return f"interpret|{INTERPRET_FP}|{text}|{seen}"


def decide_key(text: str, state: GameState, parsed: ParsedCommand) -> str:
    """decide_autonomously() ส่ง GameState ทั้งก้อนให้ LLM จึงต้องผูกกับทั้งก้อน"""
    return f"decide|{DECIDE_FP}|{text}|{state.model_dump_json()}|{parsed.model_dump_json()}"


def with_retry(fn, *args, limiter=None, tries=6):
    """เรียก LLM แล้วรอลองใหม่เมื่อชนโควตา

    การรอไม่ใช่การผ่อนความเข้มงวด — ผลที่ได้ยังมาจาก LLM จริงทุกครั้ง
    ต่างจากการตกไปใช้ fallback ซึ่งจะทำให้ log ปนผลของสองระบบ
    error ชนิดอื่นยังโยนออกทันทีเหมือนเดิม

    คืน (ผลลัพธ์, latency_ms) โดยนับเฉพาะครั้งที่สำเร็จ ไม่นับเวลาที่นั่งรอโควตา
    ไม่งั้นตัวเลข latency จะกลายเป็นการวัดโควตาแทนที่จะวัดความเร็วของระบบ
    """
    for attempt in range(tries):
        try:
            if limiter:
                limiter.wait()
            t0 = time.perf_counter()
            return fn(*args), int((time.perf_counter() - t0) * 1000)
        except NeuralUnavailable as e:
            if "RESOURCE_EXHAUSTED" not in str(e) or attempt == tries - 1:
                raise
            delay = 20 * (attempt + 1)
            print(f"      ชนโควตา รอ {delay} วินาทีแล้วลองใหม่ ({attempt + 1}/{tries - 1})",
                  flush=True)
            time.sleep(delay)


def _row(entry, parsed, decision_b, rule_desc, decision_a=None):
    """หนึ่งแถวสำหรับการสรุปผล โหมด A เป็น None ได้เมื่อสั่ง --interpret-only"""
    chain_a = decision_a.reasoning_chain if decision_a else []
    return {
        "id": entry["id"], "group": entry["group"], "expected": entry["expected_allowed"],
        "expected_rule": entry.get("expected_rule"),
        "expected_action": entry.get("expected_action"),
        "expected_target": entry.get("expected_target"),
        "parsed_action": parsed.action.value, "parsed_target": parsed.target,
        "a_allowed": decision_a.allowed if decision_a else None,
        "b_allowed": decision_b.allowed,
        "b_rule": decision_b.violated_rule_id,
        "a_chain": len(chain_a), "b_chain": len(decision_b.reasoning_chain),
        "a_fake_rules": sum(s.rule_id not in rule_desc for s in chain_a),
        "a_reworded": sum(s.rule_id in rule_desc
                          and not s.description.startswith(rule_desc[s.rule_id][:18])
                          for s in chain_a),
    }


def load_state(entry: dict) -> GameState:
    state = checkpoint(entry["checkpoint"])
    override = entry.get("state_override")
    return state.model_copy(update=override) if override else state


def run(args):
    commands = json.loads((DATA / "commands.json").read_text(encoding="utf-8"))["commands"]
    if args.group:
        commands = [c for c in commands if c["group"] in args.group]
    if args.limit:
        commands = commands[: args.limit]

    engine = SymbolicEngine()
    rule_desc = {r["id"]: r["description"] for r in engine.rules}
    cache = Cache(CACHE_PATH)
    limiter = RateLimiter(args.rpm)
    LOG_DIR.mkdir(exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_paths = {m: LOG_DIR / f"{stamp}_mode_{m.value}.jsonl" for m in SystemMode}
    handles = {m: p.open("w", encoding="utf-8") for m, p in out_paths.items()}

    rows = []
    try:
        for i, entry in enumerate(commands, 1):
            state = load_state(entry)

            # --- ตีความครั้งเดียว ใช้ร่วมกันทั้งสองโหมด ---
            key = interpret_key(entry["text"], state)
            cached = cache.get(key)
            if cached is None:
                if args.report_only:
                    print(f"  ข้าม {entry['id']} — ยังไม่มีใน cache และสั่ง --report-only ไว้")
                    continue
                parsed, latency = with_retry(interpret, entry["text"], state, limiter=limiter)
                cache.put(key, {"parsed": parsed.model_dump(), "latency_ms": latency})
            else:
                parsed = ParsedCommand.model_validate(cached["parsed"])
                latency = cached["latency_ms"]

            # --- โหมด B: symbolic ตัดสิน (ไม่เรียก LLM) ---
            t0 = time.perf_counter()
            decision_b = engine.decide(parsed, state)
            latency_b = latency + int((time.perf_counter() - t0) * 1000)

            # --- โหมด A: LLM ตัดสินเอง ---
            # ตอนจูน prompt ของ interpret ไม่ต้องเรียกโหมด A เลย ประหยัดโควตาครึ่งหนึ่ง
            if args.interpret_only:
                # ยังเขียน log ฝั่งโหมด B เพราะโหมด B ไม่ต้องใช้ LLM ตัดสิน
                # ถ้าไม่เขียน จะไล่ดูไม่ได้ว่าข้อไหนพลาดเพราะอะไร
                handles[SystemMode.B_SYMBOLIC].write(ExperimentLog(
                    command_id=entry["id"], group=entry["group"], mode=SystemMode.B_SYMBOLIC,
                    raw_text=entry["text"], parsed=parsed, decision=decision_b,
                    expected_allowed=entry["expected_allowed"], latency_ms=latency_b,
                ).model_dump_json() + "\n")
                rows.append(_row(entry, parsed, decision_b, rule_desc))
                print(f"[{i}/{len(commands)}] {entry['id']} {entry['text'][:34]:36} "
                      f"ตีความ {parsed.action.value}/{parsed.target}", flush=True)
                continue

            key_a = decide_key(entry["text"], state, parsed)
            cached_a = cache.get(key_a)
            if cached_a is None:
                if args.report_only:
                    continue
                decision_a, ms_a = with_retry(decide_autonomously, entry["text"], state, parsed,
                                              limiter=limiter)
                latency_a = latency + ms_a
                cache.put(key_a, {"decision": decision_a.model_dump(), "latency_ms": latency_a})
            else:
                from app.schemas import Decision
                decision_a = Decision.model_validate(cached_a["decision"])
                latency_a = cached_a["latency_ms"]

            for mode, decision, ms in ((SystemMode.A_BASELINE, decision_a, latency_a),
                                       (SystemMode.B_SYMBOLIC, decision_b, latency_b)):
                log = ExperimentLog(
                    command_id=entry["id"],
                    group=entry["group"],
                    mode=mode,
                    raw_text=entry["text"],
                    parsed=parsed,
                    decision=decision,
                    expected_allowed=entry["expected_allowed"],
                    latency_ms=ms,
                )
                handles[mode].write(log.model_dump_json() + "\n")

            rows.append(_row(entry, parsed, decision_b, rule_desc, decision_a))
            print(f"[{i}/{len(commands)}] {entry['id']} {entry['text'][:34]:36} "
                  f"A={'อนุมัติ' if decision_a.allowed else 'ปฏิเสธ ':7} "
                  f"B={'อนุมัติ' if decision_b.allowed else 'ปฏิเสธ ':7} "
                  f"(ควรเป็น {'อนุมัติ' if entry['expected_allowed'] else 'ปฏิเสธ'})",
                  flush=True)   # ไม่ flush จะดูความคืบหน้าไม่ได้เวลา redirect ลงไฟล์

    except NeuralUnavailable as e:
        print(f"\nหยุดกลางคัน: เรียก LLM ไม่สำเร็จ — {str(e)[:200]}")
        print("ผลที่ได้มาแล้วถูก cache ไว้ รันคำสั่งเดิมซ้ำได้ จะเริ่มต่อจากจุดที่ค้าง")
    except KeyboardInterrupt:
        print("\nหยุดโดยผู้ใช้ — ผลที่ได้มาแล้วถูก cache ไว้")
    finally:
        for h in handles.values():
            h.close()

    report(rows, cache, out_paths)


def report(rows, cache, out_paths):
    if not rows:
        print("\nไม่มีผลลัพธ์")
        return

    print(f"\n{'='*74}")
    print(f"ผลการทดลอง  {len(rows)} คำสั่ง   (cache ใช้ซ้ำ {cache.hits} / เรียกใหม่ {cache.misses})")
    print("=" * 74)

    has_a = any(r["a_allowed"] is not None for r in rows)

    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)

    label = {"A": "ถูกกฎ", "B": "ผิดกฎ", "C": "หลอกระบบ", "D": "กำกวม"}
    col_a = f"{'โหมด A ถูก':>14}" if has_a else ""
    print(f"\n{'กลุ่ม':<14}{'n':>4}{col_a}{'โหมด B ถูก':>14}")
    print("-" * 74)
    for g in sorted(by_group):
        rs = by_group[g]
        n = len(rs)
        b = sum(r["b_allowed"] == r["expected"] for r in rs)
        line = f"{g} {label.get(g, ''):<11}{n:>4}"
        if has_a:
            a = sum(r["a_allowed"] == r["expected"] for r in rs)
            line += f"{a:>8} ({a/n:>4.0%})"
        print(line + f"{b:>8} ({b/n:>4.0%})")
    total = len(rows)
    b_all = sum(r["b_allowed"] == r["expected"] for r in rows)
    line = f"{'รวม':<14}{total:>4}"
    if has_a:
        a_all = sum(r["a_allowed"] == r["expected"] for r in rows)
        line += f"{a_all:>8} ({a_all/total:>4.0%})"
    print("-" * 74)
    print(line + f"{b_all:>8} ({b_all/total:>4.0%})")

    # แยกสาเหตุของความผิดพลาด — เมตริกที่ชี้ขาดของงานนี้
    #
    # อัตราผิดรวมบอกอะไรไม่ได้ เพราะสองโหมดใช้ผลตีความตัวเดียวกัน
    # ถ้า neural ตีความพลาด ทั้งสองโหมดพลาดตามเหมือนกัน ไม่เกี่ยวกับว่าใครตัดสิน
    # สิ่งที่ต่างกันจริงคือ "ตีความถูกแล้วยังตัดสินผิด" = ละเมิดกฎที่ตัวเองถืออยู่
    def misparsed(r):
        return r["parsed_action"] != r["expected_action"] or r["parsed_target"] != r["expected_target"]

    checkable = [r for r in rows if r["group"] in ("A", "B")]
    if checkable and has_a:
        print(f"\nแยกสาเหตุของความผิดพลาด (กลุ่ม A+B, n={len(checkable)})")
        print(f"{'':<26}{'ตีความพลาด':>14}{'ละเมิดกฎ':>14}")
        print("-" * 74)
        for mode, k in (("A", "a_allowed"), ("B", "b_allowed")):
            wrong = [r for r in checkable if r[k] != r["expected"]]
            mis = sum(misparsed(r) for r in wrong)
            viol = len(wrong) - mis
            print(f"  โหมด {mode} ผิด {len(wrong):>3} ข้อ{'':<10}{mis:>10}{viol:>14}")
        print("\n  'ละเมิดกฎ' = ตีความถูกต้องแล้ว แต่ยังตัดสินขัดกับกฎที่มีอยู่ในมือ")
        print("  โหมด B เป็นศูนย์เสมอโดยโครงสร้าง เพราะ engine ตัดสินจากกฎโดยตรง")

    denied = [r for r in rows if not r["expected"]]
    if denied and has_a:
        unsafe = [r for r in denied if r["a_allowed"]]
        unsafe_b = [r for r in denied if r["b_allowed"]]
        print(f"\nอนุมัติทั้งที่ควรปฏิเสธ")
        print(f"  โหมด A : {len(unsafe)}/{len(denied)} ({len(unsafe)/len(denied):.0%})"
              f"   ในนั้นตีความถูกแต่ตัดสินผิด {sum(not misparsed(r) for r in unsafe)} ข้อ")
        print(f"  โหมด B : {len(unsafe_b)}/{len(denied)} ({len(unsafe_b)/len(denied):.0%})"
              f"   ในนั้นตีความถูกแต่ตัดสินผิด {sum(not misparsed(r) for r in unsafe_b)} ข้อ")

    # Explanation coverage + faithfulness — วัดได้ต่อเมื่อมีข้อมูลฝั่งโหมด A
    if not has_a:
        print("\n(ข้ามการวัดฝั่งโหมด A ทั้งหมด เพราะสั่ง --interpret-only ไว้)")
    else:
        print(f"\nExplanation coverage (คำตัดสินที่มี reasoning_chain)")
        for mode, k in (("A", "a_chain"), ("B", "b_chain")):
            cov = sum(1 for r in rows if r[k] > 0) / len(rows)
            avg = sum(r[k] for r in rows) / len(rows)
            print(f"  โหมด {mode} : {cov:.0%}   เฉลี่ย {avg:.1f} ขั้นต่อคำตัดสิน")
        shorter = sum(1 for r in rows if r["a_chain"] < r["b_chain"])
        print(f"  โหมด A ตรวจกฎน้อยกว่าที่ engine ตรวจ: {shorter}/{len(rows)} คำสั่ง "
              f"({shorter/len(rows):.0%}) — ข้ามการตรวจแล้วสรุปเลย")

    # faithfulness: คำอธิบายของโหมด A เป็นข้อความที่ LLM เขียนขึ้นเอง ไม่ใช่ผลของการตรวจ
    steps = sum(r["a_chain"] for r in rows)
    if steps:
        fake = sum(r["a_fake_rules"] for r in rows)
        reworded = sum(r["a_reworded"] for r in rows)
        print(f"\nFaithfulness ของคำอธิบาย (โหมด A, {steps} ขั้น)")
        print(f"  อ้าง rule_id ที่ไม่มีอยู่จริง  : {fake} ขั้น ({fake/steps:.0%})")
        print(f"  อ้าง id ถูกแต่เขียนถ้อยคำเอง : {reworded} ขั้น ({reworded/steps:.0%})")
        print(f"  โหมด B: ทุกขั้นถูกสร้างจากโค้ดที่ตรวจกฎจริง จึงตรงกับกฎ 100% โดยโครงสร้าง")

    # ความแม่นของการตีความ วัดเฉพาะกลุ่มที่ระบุ target ไว้แน่นอน
    grounded = [r for r in rows if r["group"] in ("A", "B")]
    if grounded:
        ok = sum(r["parsed_action"] == r["expected_action"]
                 and r["parsed_target"] == r["expected_target"] for r in grounded)
        print(f"\nความแม่นของการตีความ (Neural, กลุ่ม A+B): {ok}/{len(grounded)} ({ok/len(grounded):.0%})")

    cd = [r for r in rows if r["group"] in ("C", "D")]
    if cd:
        ok = sum(r["parsed_action"] == r["expected_action"] for r in cd)
        print(f"จับ unknown/ambiguous ได้ถูก (กลุ่ม C+D): {ok}/{len(cd)} ({ok/len(cd):.0%})")

    # กฎที่โหมด B อ้างถึงต้องตรงกับที่ label ไว้ — ตรวจความตรงของคำอธิบาย
    with_rule = [r for r in rows if r["expected_rule"] and r["group"] == "B"]
    if with_rule:
        ok = sum(r["b_rule"] == r["expected_rule"] for r in with_rule)
        print(f"โหมด B ชี้กฎที่ถูกละเมิดได้ตรง: {ok}/{len(with_rule)} ({ok/len(with_rule):.0%})")

    print(f"\nไฟล์ log:")
    for m, p in out_paths.items():
        print(f"  โหมด {m.value}: {p.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="รันการทดลองเปรียบเทียบโหมด A กับ B")
    ap.add_argument("--group", nargs="+", choices=list("ABCD"), help="เลือกเฉพาะบางกลุ่ม")
    ap.add_argument("--limit", type=int, help="จำกัดจำนวนคำสั่ง")
    ap.add_argument("--rpm", type=int, default=13, help="จังหวะเรียก LLM ต่อนาที (free tier = 15)")
    ap.add_argument("--report-only", action="store_true", help="ไม่เรียก LLM ใช้เฉพาะผลใน cache")
    ap.add_argument("--interpret-only", action="store_true",
                    help="วัดเฉพาะความแม่นของการตีความ ไม่เรียกโหมด A (ใช้โควตาครึ่งเดียว)")
    args = ap.parse_args()

    if not args.report_only and not llm_online():
        raise SystemExit("ไม่มี GEMINI_API_KEY — การทดลองต้องใช้ LLM จริง "
                         "(ผล fallback ใช้ไม่ได้) ตั้งคีย์ใน .env ก่อน")
    run(args)


if __name__ == "__main__":
    main()
