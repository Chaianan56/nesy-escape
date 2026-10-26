"""
app.symbolic — Symbolic Layer (เครื่องมือตัดสินตรรกะและกฎของเกม NeSy-Escape)

สถาปัตยกรรมระดับสัญลักษณ์ (Symbolic Tier):
1. engine.py (SymbolicEngine):
   - ทำหน้าที่ตัดสินว่าคำสั่ง (ParsedCommand) อนุมัติ (ALLOWED) หรือปฏิเสธ (DENIED) ตาม rules.json
   - สร้าง Explainable Reasoning Chain (XAI) รายเทิร์นจากกฎที่ถูกตรวจจริง (Faithful by Construction)
   - ประเมินสถานะ 4 เสาหลักคดี (Pillars) ได้แก่ Timeline, Motive, Opportunity, Corroboration
   - ปรับปรุงสถานะเกม (apply_changes) แบบ Functional State Transition

2. validation.py (validate_world):
   - ตรวจสอบความถูกต้องและความสอดคล้องของกราฟข้อมูลโลก (story.json) และกฎ (rules.json)
   - ป้องกันวงรอบวัฏจักร (Cycle Detection) ในลำดับการอนุมาน (Deduction DAG) ตั้งแต่ตอนเริ่มระบบ
"""

from app.symbolic.engine import SymbolicEngine, apply_changes, accusation_submission
from app.symbolic.validation import validate_world

__all__ = [
    "SymbolicEngine",
    "apply_changes",
    "accusation_submission",
    "validate_world",
]
