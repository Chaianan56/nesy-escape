"""
app.profiler.telemetry — ระบบจัดเก็บและส่งออกข้อมูลสถิติเพื่องานวิจัย (Research Telemetry)
รองรับการ Export ไฟล์ JSON รายละเอียดทั้งรอบ และไฟล์ CSV ตารางข้อมูลรวม
"""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.profiler.schemas import SessionSummary


TELEMETRY_DIR = Path(__file__).resolve().parents[2] / "data" / "telemetry"


def ensure_telemetry_dir() -> Path:
    """สร้างโฟลเดอร์สำหรับเก็บข้อมูลงานวิจัยหากยังไม่มีอยู่"""
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    return TELEMETRY_DIR


def save_session_telemetry(summary: SessionSummary) -> Path:
    """บันทึกข้อมูลรายละเอียดของ Session (JSON) เพื่อใช้ตรวจสอบและวิเคราะห์ย้อนหลัง"""
    out_dir = ensure_telemetry_dir()
    filepath = out_dir / f"session_{summary.session_id}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, ensure_ascii=False, indent=2)

    # อัปเดตไฟล์ CSV ตารางรวมด้วย
    append_to_research_csv(summary)
    return filepath


def append_to_research_csv(summary: SessionSummary) -> Path:
    """เพิ่มข้อมูล Session ลงในตาราง CSV รวมเพื่อง่ายต่อการเปิดใน Excel / SPSS / R"""
    out_dir = ensure_telemetry_dir()
    csv_path = out_dir / "research_dataset.csv"

    headers = [
        "session_id",
        "total_duration_seconds",
        "total_turns",
        "allowed_turns",
        "denied_turns",
        "rule_violation_rate",
        "clue_discovery_efficiency",
        "evidence_discovered_count",
        "primary_archetype",
        "methodical_score",
        "social_score",
        "caution_score",
        "curiosity_score",
        "decisiveness_score",
        "forensic_score",
        "interrogator_score",
        "maverick_score",
        "rusher_score",
        "scaffolding_count",
        "total_prompt_tokens",
        "total_completion_tokens",
        "avg_neural_latency_ms",
        "final_ending_id",
        "case_solved_successfully",
    ]

    row = {
        "session_id": summary.session_id,
        "total_duration_seconds": summary.total_duration_seconds,
        "total_turns": summary.total_turns,
        "allowed_turns": summary.allowed_turns,
        "denied_turns": summary.denied_turns,
        "rule_violation_rate": summary.rule_violation_rate,
        "clue_discovery_efficiency": summary.clue_discovery_efficiency,
        "evidence_discovered_count": summary.evidence_discovered_count,
        "primary_archetype": summary.primary_archetype,
        "methodical_score": summary.dimensions.get("methodical_score", 0.0),
        "social_score": summary.dimensions.get("social_score", 0.0),
        "caution_score": summary.dimensions.get("caution_score", 0.0),
        "curiosity_score": summary.dimensions.get("curiosity_score", 0.0),
        "decisiveness_score": summary.dimensions.get("decisiveness_score", 0.0),
        "forensic_score": summary.archetype_scores.get("forensic", 0.0),
        "interrogator_score": summary.archetype_scores.get("interrogator", 0.0),
        "maverick_score": summary.archetype_scores.get("maverick", 0.0),
        "rusher_score": summary.archetype_scores.get("rusher", 0.0),
        "scaffolding_count": summary.scaffolding_count,
        "total_prompt_tokens": summary.total_prompt_tokens,
        "total_completion_tokens": summary.total_completion_tokens,
        "avg_neural_latency_ms": summary.avg_neural_latency_ms,
        "final_ending_id": summary.final_ending_id or "",
        "case_solved_successfully": 1 if summary.case_solved_successfully else 0,
    }

    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return csv_path


def load_all_session_summaries() -> List[Dict[str, Any]]:
    """โหลดรายการสรุปทุกเซสชันที่มีบันทึกไว้"""
    out_dir = ensure_telemetry_dir()
    summaries = []
    for p in out_dir.glob("session_*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                summaries.append(json.load(f))
        except Exception:
            pass
    return summaries
