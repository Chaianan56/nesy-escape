"""
schemas.py — สัญญากลาง (Contract) ระหว่าง Neural Layer และ Symbolic Layer
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================
# 1) ACTION — รายการสิ่งที่ผู้เล่นทำได้ทั้งหมด
# ============================================================
class ActionType(str, Enum):
    EXAMINE = "examine"        # ตรวจสอบวัตถุ/หลักฐาน
    TAKE = "take"              # หยิบ/เก็บ
    USE = "use"                # ใช้ของกับเป้าหมาย
    UNLOCK = "unlock"          # ปลดล็อก
    MOVE = "move"              # เคลื่อนย้ายตัวเอง/วัตถุ
    INTERROGATE = "interrogate"  # สอบปากคำผู้ต้องสงสัย
    ACCUSE = "accuse"          # กล่าวหา (จบเกม)

    AMBIGUOUS = "ambiguous"    # ตีความได้หลายทาง
    UNKNOWN = "unknown"        # ตีความไม่ได้เลย / อยู่นอกขอบเขตเกม


# ============================================================
# 2) NEURAL OUTPUT
# ============================================================
class ParsedCommand(BaseModel):
    """ผลลัพธ์จาก LLM หลังตีความภาษาธรรมชาติ"""
    action: ActionType
    target: Optional[str] = Field(None, description="id ของเป้าหมาย")
    instrument: Optional[str] = Field(None, description="id ของสิ่งที่ใช้")
    raw_text: str = Field(..., description="ข้อความดิบของผู้เล่น")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    alternatives: List[str] = Field(default_factory=list)


# ============================================================
# 3) GAME STATE
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
# 4) REASONING CHAIN & DECISION
# ============================================================
class ReasoningStep(BaseModel):
    rule_id: str
    description: str
    passed: bool


class Decision(BaseModel):
    allowed: bool
    message: str
    reasoning_chain: List[ReasoningStep] = Field(default_factory=list)
    violated_rule_id: Optional[str] = None
    state_changes: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 5) API REQUEST & RESPONSE
# ============================================================
class CommandRequest(BaseModel):
    """คำขอหนึ่งครั้งจากผู้เล่น

    ไม่มีฟิลด์ mode เพราะ draft1 มีเส้นทางเดียวคือ Neural ตีความ -> Symbolic ตัดสิน
    โหมด baseline ที่ให้ LLM ตัดสินเองอยู่ในสาขาที่ทำการทดลอง
    """
    text: str
    state: GameState


class CommandResponse(BaseModel):
    parsed: ParsedCommand
    decision: Decision
    new_state: GameState
