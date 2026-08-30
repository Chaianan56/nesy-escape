"""
schemas.py — สัญญากลาง (Data Contracts & Schemas) ระหว่าง Neural Layer และ Symbolic Layer

หน้าที่:
- กำหนดโครงสร้างข้อมูลมาตรฐาน (Pydantic Models) ที่ใช้แลกเปลี่ยนข้อมูลระหว่างเลเยอร์
- ป้องกันความผิดพลาดของชนิดข้อมูลและชื่อฟิลด์ในการเชื่อมต่อระบบ
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================
# 1) ACTION TYPE — ประเภทการกระทำทั้งหมดในเกม
# ============================================================
class ActionType(str, Enum):
    """รายการ Action ทั้งหมดที่ระบบรองรับ"""
    EXAMINE = "examine"          # ตรวจสอบวัตถุ/สถานที่/หลักฐาน
    TAKE = "take"                # หยิบ/เก็บวัตถุเข้ากระเป๋า
    USE = "use"                  # ใช้ไอเทมกับเป้าหมาย (ต้องระบุ instrument)
    UNLOCK = "unlock"            # ปลดล็อกวัตถุ/สถานที่
    MOVE = "move"                # เคลื่อนที่ไปยังตู้รถอื่น
    INTERROGATE = "interrogate"  # สอบปากคำผู้ต้องสงสัย
    ACCUSE = "accuse"            # กล่าวหาฆาตกร (จบเกม)

    AMBIGUOUS = "ambiguous"      # คำสั่งกำกวม ตีความได้หลายทาง
    UNKNOWN = "unknown"          # คำสั่งอยู่นอกขอบเขตหรือไม่สามารถตีความได้


# ============================================================
# 2) NEURAL LAYER OUTPUT — ผลลัพธ์จากการตีความของ LLM
# ============================================================
class ParsedCommand(BaseModel):
    """ผลลัพธ์ที่ Gemini สกัดจากข้อความภาษาไทยของผู้เล่น

    หมายเหตุ: โมเดลนี้ไม่มีฟิลด์ 'allowed' โดยเจตนา 
    เพราะหน้าที่ตัดสินใจเป็นของ Symbolic Layer 100%
    """
    action: ActionType = Field(..., description="ประเภทการกระทำที่สกัดได้")
    target: Optional[str] = Field(None, description="ID ภาษาอังกฤษของเป้าหมาย (เช่น 'service_pantry')")
    instrument: Optional[str] = Field(None, description="ID ภาษาอังกฤษของไอเทมที่ใช้ (เช่น 'crew_key')")
    raw_text: str = Field(..., description="ข้อความภาษาไทยดิบดั้งเดิมจากผู้เล่น")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="ความมั่นใจในการสกัดข้อมูลของ LLM")
    alternatives: List[str] = Field(default_factory=list, description="ตัวเลือกเพิ่มเติมหากคำสั่งกำกวม")


# ============================================================
# 3) GAME STATE — สถานะของเกม ณ ปัจจุบัน
# ============================================================
class GameState(BaseModel):
    """สถานะรวมของเกมในขณะนั้น (ตำแหน่ง, ไอเทม, หลักฐาน)"""
    current_location: str = Field("passenger_car", description="ID ของตู้รถที่ผู้เล่นยืนอยู่ปัจจุบัน")
    inventory: List[str] = Field(default_factory=list, description="รายการ ID วัตถุที่ถือติดตัว")
    discovered_evidence: List[str] = Field(default_factory=list, description="รายการ ID หลักฐานที่ค้นพบแล้ว")
    unlocked_objects: List[str] = Field(default_factory=list, description="รายการ ID สิ่งที่ถูกปลดล็อกแล้ว")
    visited_locations: List[str] = Field(default_factory=lambda: ["passenger_car"], description="ตู้รถที่เคยไปแล้ว")
    interrogated_suspects: List[str] = Field(default_factory=list, description="ผู้ต้องสงสัยที่เคยสอบปากคำแล้ว")
    elapsed_seconds: int = Field(0, description="เวลาที่ผ่านไปในเกม (วินาที)")
    turn_count: int = Field(0, description="จำนวนตาที่เล่นไปแล้ว")


# ============================================================
# 4) REASONING CHAIN & DECISION — คำตัดสินจาก Symbolic Engine
# ============================================================
class ReasoningStep(BaseModel):
    """ขั้นตอนการตรวจสอบกฎเกณฑ์ 1 ขั้น"""
    rule_id: str = Field(..., description="รหัสกฎใน rules.json (เช่น 'R005_SAME_LOCATION')")
    description: str = Field(..., description="คำอธิบายกฎภาษาไทย")
    passed: bool = Field(..., description="ผลการตรวจสอบกฎ (ผ่าน / ไม่ผ่าน)")


class Decision(BaseModel):
    """คำตัดสินสุดท้ายจาก Symbolic Engine"""
    allowed: bool = Field(..., description="อนุมัติให้ดำเนินการหรือไม่ (True / False)")
    message: str = Field(..., description="ข้อความบรรยายผลลัพธ์ที่จะแสดงแก่ผู้เล่น")
    reasoning_chain: List[ReasoningStep] = Field(default_factory=list, description="ลำดับการตรวจกฎทั้งหมด (Reasoning Chain)")
    violated_rule_id: Optional[str] = Field(None, description="รหัสกฎที่ละเมิด (หากถูกปฏิเสธ)")
    state_changes: Dict[str, Any] = Field(default_factory=dict, description="รายการเปลี่ยนแปลงสถานะเกม")


# ============================================================
# 5) API REQUEST & RESPONSE — โครงสร้างรับส่ง API
# ============================================================
class CommandRequest(BaseModel):
    """Payload รับเข้าจาก Frontend

    ไม่มีฟิลด์ mode เพราะ draft1 มีเส้นทางเดียวคือ Neural ตีความ -> Symbolic ตัดสิน
    ถ้ามีฟิลด์นี้แต่ไม่มีใครอ่าน หน้าเว็บจะทำปุ่มสลับโหมดขึ้นมาแล้วผู้ใช้เห็นสองโหมด
    ตอบเหมือนกันหมด ซึ่งเข้าใจผิดได้ว่าสองสถาปัตยกรรมไม่ต่างกัน
    โหมด baseline ที่ให้ LLM ตัดสินเองอยู่ในสาขาที่ทำการทดลอง
    """
    text: str = Field(..., description="ข้อความคำสั่งภาษาไทยจากผู้เล่น")
    state: GameState = Field(..., description="สถานะเกมปัจจุบัน")


class CommandResponse(BaseModel):
    """Payload ตอบกลับไปยัง Frontend"""
    parsed: ParsedCommand = Field(..., description="ผลการตีความจาก Neural Layer")
    decision: Decision = Field(..., description="คำตัดสินและ Reasoning Chain จาก Symbolic Layer")
    new_state: GameState = Field(..., description="สถานะเกมใหม่หลังประมวลผล")
