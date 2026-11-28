"""
parser_log.py — บันทึกประโยคที่ตัวแปลคำสั่ง (AI) ตีความไม่ได้หรือถูกกฎปฏิเสธ

ใช้ตอนเปิดให้คนอื่นลองเล่น เพื่อเก็บประโยคจริงจากผู้เล่นมาแก้ตัวแปลคำสั่งภายหลัง
บันทึกเฉพาะคำสั่งที่ผ่าน AI (ไม่บันทึกคำสั่งพิมพ์ตรงหรือปุ่มกด) ลง data/telemetry/parser_misses.jsonl
ไฟล์นี้อยู่ใน .gitignore จึงไม่ถูกส่งขึ้น GitHub
อ่านสรุปได้ด้วย: python scripts/show_parser_misses.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "telemetry" / "parser_misses.jsonl"


def _enabled() -> bool:
    setting = os.getenv("PARSER_LOG", "").strip().lower()
    if setting in ("0", "off", "false", "no"):
        return False
    # ระหว่างรัน pytest ไม่เขียนไฟล์ลงโปรเจกต์ เว้นแต่ตั้ง PARSER_LOG=on
    return setting in ("1", "on", "true", "yes") or "pytest" not in sys.modules


def log_if_missed(text: str, result, case_id: str | None, location: str | None) -> bool:
    """บันทึกหนึ่งบรรทัดถ้าคำสั่งนี้ผ่าน AI แล้วตีความไม่ได้ ถูกปฏิเสธ หรือ AI ใช้งานไม่ได้ คืน True ถ้าบันทึก"""
    parsed = result.parsed
    if not _enabled() or (parsed.parser_mode or "typed") == "typed":
        return False
    decision = result.decision
    missed = (parsed.action.value in ("unknown", "ambiguous") or not decision.allowed or bool(result.service_error))
    if not missed:
        return False
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "case_id": case_id,
        "location": location,
        "text": text,
        "parsed": {"action": parsed.action.value, "target": parsed.target, "topic": parsed.topic,
                   "alternatives": list(parsed.alternatives or []), "mode": parsed.parser_mode,
                   "repair_note": parsed.repair_note},
        "allowed": decision.allowed,
        "rule": decision.violated_rule_id,
        "service_error": result.service_error,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return False   # บันทึกไม่ได้ก็ไม่เป็นไร เกมต้องเล่นต่อได้
    return True
