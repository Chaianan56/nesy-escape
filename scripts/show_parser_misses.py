"""สรุปประโยคที่ตัวแปลคำสั่งพลาด จาก data/telemetry/parser_misses.jsonl (บันทึกตอนคนอื่นลองเล่น)

    python scripts/show_parser_misses.py            # สรุปทั้งหมด
    python scripts/show_parser_misses.py --since 2026-12-01
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.parser_log import LOG_PATH  # noqa: E402

REASONS = {
    "unknown": "ไม่เข้าใจ",
    "ambiguous": "กำกวม",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="เฉพาะบรรทัดตั้งแต่วันที่นี้ (YYYY-MM-DD)")
    args = parser.parse_args()
    if not LOG_PATH.exists():
        print("ยังไม่มีบันทึก (ยังไม่มีประโยคที่พลาด หรือยังไม่ได้เปิดเกมเล่น)")
        return
    rows = [json.loads(line) for line in LOG_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.since:
        rows = [r for r in rows if r["time"] >= args.since]
    quota = [r for r in rows if r.get("service_error")]
    misread = [r for r in rows if not r.get("service_error")]
    print(f"ทั้งหมด {len(rows)} บรรทัด: AI ใช้งานไม่ได้ {len(quota)} · ตีความไม่ได้หรือถูกปฏิเสธ {len(misread)}")
    kinds = Counter(REASONS.get(r["parsed"]["action"], f"ถูกปฏิเสธ ({r.get('rule') or '-'})") for r in misread)
    for kind, n in kinds.most_common():
        print(f"  {n:>3}  {kind}")
    print()
    for r in misread:
        p = r["parsed"]
        target = f" {p['target']}" if p.get("target") else ""
        print(f"[{r['time']}] {r.get('case_id')} @ {r.get('location')}")
        print(f"    พิมพ์: {r['text']}")
        print(f"    ได้:   {p['action']}{target}  {'(ผ่าน)' if r['allowed'] else '(ไม่ผ่าน ' + str(r.get('rule')) + ')'}")


if __name__ == "__main__":
    main()
