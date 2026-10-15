"""
app.profiler.schemas — Pydantic Schemas สำหรับระบบวิเคราะห์พฤติกรรมผู้เล่น
และตัวแปรเชิงสถิติเพื่องานวิจัย (Research Statistical Variables)
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class PlayerArchetype(str, Enum):
    """กลุ่มบุคลิกภาพและรูปแบบการสืบสวนของผู้เล่น (Player Archetypes)"""
    FORENSIC_ANALYST = "forensic_analyst"          # นักวิเคราะห์พิสูจน์หลักฐาน (เน้นวัตถุ/ละเอียดรอบคอบ)
    PSYCHOLOGICAL_INTERROGATOR = "psychological_interrogator"  # นักจิตวิทยาเจาะลึกบุคคล (เน้นสอบถาม/มนุษยสัมพันธ์)
    MAVERICK_TRAILBLAZER = "maverick_trailblazer"  # นักสืบนอกกรอบ/ชอบลองของ (ละเมิดกฎบ่อย/สั่งแหวกแนว)
    INTUITIVE_RUSHER = "intuitive_rusher"          # นักสืบสายสัญชาตญาณ/ใจร้อน (เร่งรีบ/กล่าวหาเร็ว)
    BALANCED_INVESTIGATOR = "balanced_investigator" # นักสืบสายสมดุลรอบด้าน


ARCHETYPE_METADATA: Dict[PlayerArchetype, Dict[str, str]] = {
    PlayerArchetype.FORENSIC_ANALYST: {
        "name_th": "นักวิเคราะห์พิสูจน์หลักฐาน (The Forensic Analyst)",
        "badge": "🔬",
        "description_th": "สืบสวนด้วยหลักตรรกะและความรอบคอบสูง เก็บและตรวจสอบวัตถุพยานอย่างถี่ถ้วน ไม่ด่วนสรุปจนกว่าพยานหลักฐานจะแน่นหนา 100%",
    },
    PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR: {
        "name_th": "นักจิตวิทยาเจาะลึกบุคคล (The Psychological Interrogator)",
        "badge": "🗣️",
        "description_th": "มุ่งเน้นการปฏิสัมพันธ์กับมนุษย์ สนทนาและเจาะลึกคำให้การของผู้ต้องสงสัยเพื่อค้นหาพิรุธและแรงจูงใจเบื้องหลัง",
    },
    PlayerArchetype.MAVERICK_TRAILBLAZER: {
        "name_th": "นักสืบนอกกรอบ (The Maverick Trailblazer)",
        "badge": "⚡",
        "description_th": "กล้าได้กล้าเสีย ชอบทดสอบขีดจำกัดของสถานการณ์ สั่งการนอกแผน ลองผิดลองถูก และไม่เกรงกลัวต่อกฎระเบียบ",
    },
    PlayerArchetype.INTUITIVE_RUSHER: {
        "name_th": "นักสืบสายสัญชาตญาณ (The Intuitive Rusher)",
        "badge": "⏱️",
        "description_th": "ตัดสินใจฉับไว พึ่งพาการคาดเดาและสัญชาตญาณแรก เคลื่อนที่รวดเร็ว แต่อาจมองข้ามรายละเอียดและหลักฐานสำคัญไปบางจุด",
    },
    PlayerArchetype.BALANCED_INVESTIGATOR: {
        "name_th": "นักสืบสายสมดุลรอบด้าน (The Balanced Investigator)",
        "badge": "⚖️",
        "description_th": "ผสมผสานการค้นหาวัตถุพยานและการสอบปากคำอย่างลงตัว ดำเนินคดีอย่างมีแบบแผนและยืดหยุ่นตามสถานการณ์",
    },
}


class PlaystyleDimensions(BaseModel):
    """คะแนน 5 มิติของรูปแบบการสืบสวน (Normalized 0.0 - 1.0) สำหรับการทำวิจัยและเรดาร์ชาร์ต"""
    methodical_score: float = Field(0.0, ge=0.0, le=1.0, description="ความละเอียดรอบคอบ (สัดส่วน examine และการตรวจวัตถุ)")
    social_score: float = Field(0.0, ge=0.0, le=1.0, description="การมุ่งเน้นบุคคล (สัดส่วน interrogate)")
    caution_score: float = Field(1.0, ge=0.0, le=1.0, description="ความเคารพกฎและสุขุม (1 - อัตราละเมิดกฎ)")
    curiosity_score: float = Field(0.0, ge=0.0, le=1.0, description="ความครอบคลุมการสำรวจ (สถานที่และวัตถุที่เข้าถึงจริง)")
    decisiveness_score: float = Field(0.0, ge=0.0, le=1.0, description="ความเด็ดขาด/ความเร็วในการคลี่คลายประเด็น")


class ArchetypeScores(BaseModel):
    """คะแนนความสอดคล้องกับแต่ละ Archetype (Normalized 0.0 - 1.0)"""
    forensic: float = 0.0
    interrogator: float = 0.0
    maverick: float = 0.0
    rusher: float = 0.0
    balanced: float = 0.0


class TurnTelemetry(BaseModel):
    """บันทึกข้อมูลสถิติรายเทิร์น (Per-Turn Research Log)"""
    turn_id: int
    timestamp: float
    elapsed_seconds: int
    raw_input: str
    action: str
    target: Optional[str] = None
    allowed: bool
    violated_rule_id: Optional[str] = None
    location: str
    evidence_count: int
    inventory_count: int
    pillars_count: int
    is_looping: bool = False
    adaptive_note: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    parser_mode: str = "typed"


class PlayerProfile(BaseModel):
    """โปรไฟล์พฤติกรรมผู้เล่นและสถิติสะสมสำหรับแสดงผลและวิจัย"""
    session_id: str
    primary_archetype: PlayerArchetype = PlayerArchetype.BALANCED_INVESTIGATOR
    archetype_name_th: str = ""
    archetype_badge: str = "⚖️"
    archetype_description_th: str = ""
    scores: ArchetypeScores = Field(default_factory=ArchetypeScores)
    dimensions: PlaystyleDimensions = Field(default_factory=PlaystyleDimensions)

    # ตัวแปรเชิงสถิติหลักเพื่องานวิจัย
    total_turns: int = 0
    allowed_turns: int = 0
    denied_turns: int = 0
    rule_violation_rate: float = 0.0
    clue_efficiency: float = 0.0
    looping_count: int = 0
    consecutive_looping_count: int = 0
    scaffolding_trigger_count: int = 0
    pillars_fulfilled: Dict[str, bool] = Field(default_factory=dict)
    ending_id: Optional[str] = None


class SessionSummary(BaseModel):
    """รายงานสรุปผลรอบการเล่นเพื่อส่งออกข้อมูลงานวิจัย (Research Dataset Record)"""
    session_id: str
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    total_duration_seconds: int = 0
    total_turns: int = 0
    allowed_turns: int = 0
    denied_turns: int = 0
    rule_violation_rate: float = 0.0
    clue_discovery_efficiency: float = 0.0
    evidence_discovered_count: int = 0
    primary_archetype: str
    dimensions: Dict[str, float]
    archetype_scores: Dict[str, float]
    scaffolding_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    avg_neural_latency_ms: float = 0.0
    final_ending_id: Optional[str] = None
    case_solved_successfully: bool = False
    turn_history: List[TurnTelemetry] = Field(default_factory=list)
