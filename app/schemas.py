"""
schemas.py — สัญญากลาง (Contract) ระหว่าง Neural Layer และ Symbolic Layer

ไฟล์นี้คือจุดเดียวที่ทั้งทีมต้องเห็นตรงกัน
- Neural Layer  : รับข้อความดิบ  -> ต้องคืน ParsedCommand
- Symbolic Layer: รับ ParsedCommand -> ต้องคืน Decision

ห้ามแก้ไฟล์นี้คนเดียว ต้องตกลงกันทั้งทีมก่อนเสมอ
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================
# 1) ACTION — รายการสิ่งที่ผู้เล่นทำได้ทั้งหมด
#    ⚠️ TODO ทีม: เคาะให้ครบก่อนเริ่มเขียนโค้ด
#    ถ้า LLM ตีความออกมาเป็น action นอกลิสต์นี้ = ถือว่าไม่ผ่าน
# ============================================================
class ActionType(str, Enum):
    EXAMINE = "examine"        # ตรวจสอบวัตถุ/หลักฐาน
    TAKE = "take"              # หยิบ/เก็บ
    USE = "use"                # ใช้ของกับเป้าหมาย (ต้องมี instrument)
    UNLOCK = "unlock"          # ปลดล็อก
    MOVE = "move"              # เคลื่อนย้ายตัวเอง/วัตถุ
    INTERROGATE = "interrogate"  # สอบปากคำผู้ต้องสงสัย
    ACCUSE = "accuse"          # กล่าวหา (จบเกม)

    # --- สอง action นี้สำคัญมากต่อการทดลอง ห้ามตัดออก ---
    AMBIGUOUS = "ambiguous"    # ตีความได้หลายทาง -> กลุ่ม D (30 คำสั่ง)
    UNKNOWN = "unknown"        # ตีความไม่ได้เลย / อยู่นอกขอบเขตเกม


# ============================================================
# 2) NEURAL OUTPUT — สิ่งที่เพื่อนต้องส่งมาให้คุณ
# ============================================================
class ParsedCommand(BaseModel):
    """ผลลัพธ์จาก LLM หลังตีความภาษาธรรมชาติ

    หมายเหตุสำคัญเชิงวิจัย:
    โมเดลนี้ไม่มีฟิลด์ใดที่บอกว่า 'อนุญาตหรือไม่' โดยเจตนา
    เพราะการตัดสินใจเป็นหน้าที่ของ Symbolic Layer 100%
    """
    action: ActionType
    target: Optional[str] = Field(
        None, description="id ของเป้าหมาย เช่น 'cabinet_03' ไม่ใช่ 'ตู้ใบที่สาม'"
    )
    instrument: Optional[str] = Field(
        None, description="id ของสิ่งที่ใช้ เช่น 'keycard_A'"
    )
    raw_text: str = Field(..., description="ข้อความดิบของผู้เล่น เก็บไว้เพื่อ log และตรวจย้อนหลัง")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    alternatives: List[str] = Field(
        default_factory=list,
        description="ถ้า action=AMBIGUOUS ให้ใส่ตัวเลือกที่เป็นไปได้ไว้ที่นี่",
    )


# ============================================================
# 3) GAME STATE — สถานะเกมที่ Symbolic ต้องใช้ตรวจกฎ
# ============================================================
class GameState(BaseModel):
    current_location: str = Field("passenger_car", description="id ของตู้รถที่ผู้เล่นอยู่")
    inventory: List[str] = Field(default_factory=list)
    discovered_evidence: List[str] = Field(default_factory=list)
    unlocked_objects: List[str] = Field(default_factory=list)
    visited_locations: List[str] = Field(default_factory=lambda: ["passenger_car"])
    interrogated_suspects: List[str] = Field(default_factory=list)
    elapsed_seconds: int = 0
    turn_count: int = 0


# ============================================================
# 4) REASONING CHAIN — หัวใจของ Explainability
# ============================================================
class ReasoningStep(BaseModel):
    """หนึ่งขั้นของการตรวจกฎ

    ต้องสร้างจากกฎที่ถูกตรวจ 'จริง' เท่านั้น
    ห้ามให้ LLM เขียนคำอธิบายย้อนหลัง (post-hoc rationalization)
    ไม่งั้นจะเสีย faithfulness ซึ่งเป็นข้ออ้างหลักของงาน
    """
    rule_id: str = Field(..., description="ต้องตรงกับ id ใน rules.json")
    description: str
    passed: bool


class Decision(BaseModel):
    """ผลลัพธ์จาก Symbolic Layer — คำตัดสินสุดท้าย"""
    allowed: bool
    message: str = Field(..., description="ข้อความที่แสดงให้ผู้เล่นเห็น")
    reasoning_chain: List[ReasoningStep] = Field(
        default_factory=list,
        description="ต้องมีทั้งกรณีอนุมัติและปฏิเสธ (Explanation Coverage)",
    )
    violated_rule_id: Optional[str] = None
    state_changes: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 5) API + LOGGING — สำหรับการทดลอง
# ============================================================
class SystemMode(str, Enum):
    """ตัวแปรเดียวที่ต่างกันระหว่างสองระบบในการทดลอง"""
    A_BASELINE = "A"    # LLM ตีความ + ตัดสินเอง
    B_SYMBOLIC = "B"    # LLM ตีความ -> Symbolic ตัดสิน


class CommandRequest(BaseModel):
    text: str
    mode: SystemMode = SystemMode.B_SYMBOLIC
    state: GameState


class CommandResponse(BaseModel):
    parsed: ParsedCommand
    decision: Decision
    new_state: GameState


class ExperimentLog(BaseModel):
    """หนึ่งบรรทัดใน .jsonl — ออกแบบให้อ่านเข้า pandas ได้ตรง"""
    command_id: str
    group: str = Field(..., description="A=ถูกกฎ, B=ผิดกฎ, C=หลอกระบบ, D=กำกวม")
    mode: SystemMode
    raw_text: str
    parsed: ParsedCommand
    decision: Decision
    expected_allowed: bool = Field(..., description="ground truth ที่ label ไว้ล่วงหน้า")
    latency_ms: int
