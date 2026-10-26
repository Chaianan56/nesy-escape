"""
app/walkthrough.py — ตัวถอดรหัสขั้นตอนการเล่นอัตโนมัติ (Walkthrough Step Decoder)

ใช้แปลงขั้นตอนใน walkthrough.json ให้เป็น ParsedCommand
เพื่อใช้ทดสอบการเล่นซ้ำแบบ Offline Regression Test โดยไม่ต้องพึ่งพา LLM
"""
from app.schemas import ParsedCommand


def parse_step(step, walkthrough: dict) -> ParsedCommand:
    """แปลงข้อมูลขั้นตอนใน walkthrough เป็น ParsedCommand พร้อมฟิลด์ครบถ้วน"""
    if isinstance(step, dict):
        fields = dict(step)
    else:
        fields = {"action": step[0], "target": step[1]}
        if len(step) > 2:
            key = (
                "topic"
                if step[0] == "interrogate"
                else ("code" if str(step[2]).isdigit() else "instrument")
            )
            fields[key] = str(step[2])
    if fields["action"] == "infer":
        fields.setdefault("evidence", walkthrough.get("inference_evidence", []))
    fields.setdefault("raw_text", "walkthrough")
    return ParsedCommand(**fields)
