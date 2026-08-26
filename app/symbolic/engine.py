"""
engine.py — Symbolic Rule Engine

หน้าที่: รับ ParsedCommand + GameState -> คืน Decision
หลักการที่ห้ามละเมิด:
  1) การตัดสินใจเกิดที่นี่ 100% ไม่มีการเรียก LLM ในไฟล์นี้
  2) reasoning_chain สร้างจากกฎที่ถูกตรวจจริงเท่านั้น (faithful by construction)
  3) กฎอยู่ใน rules.json ไม่ hard-code เงื่อนไขลงในโค้ด
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from app.schemas import (
    ActionType,
    ParsedCommand,
    GameState,
    Decision,
    ReasoningStep,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ============================================================
# CHECKERS — หนึ่งฟังก์ชันต่อหนึ่งชนิดของกฎ
# แต่ละตัวคืน (ผ่านหรือไม่, เหตุผลเพิ่มเติม)
# เพิ่มกฎชนิดใหม่ = เขียนฟังก์ชันใหม่ + ลงทะเบียนใน CHECKERS
# ============================================================

def _action_is_known(cmd: ParsedCommand, state: GameState, world: dict, p: dict):
    if cmd.action in (ActionType.UNKNOWN, ActionType.AMBIGUOUS):
        return False, f"action={cmd.action.value}"
    return True, ""


def _target_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุเป้าหมาย"
    if cmd.target not in world["objects"]:
        return False, f"ไม่รู้จัก object id '{cmd.target}'"
    return True, ""


def _suspect_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุบุคคล"
    if cmd.target not in world["suspects"]:
        return False, f"ไม่รู้จัก suspect id '{cmd.target}'"
    return True, ""


def _target_is_takeable(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    if not obj.get("takeable", False):
        return False, f"'{cmd.target}' ไม่มีคุณสมบัติ takeable"
    return True, ""


def _container_unlocked(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    container = obj.get("hidden_in")
    if container and container not in state.unlocked_objects:
        return False, f"ถูกซ่อนอยู่ใน '{container}' ซึ่งยังไม่ถูกเปิด"
    return True, ""


def _has_required_key(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    required = obj.get("requires")
    if required is None:
        return True, "ไม่ต้องใช้อุปกรณ์"
    if required not in state.inventory:
        return False, f"ต้องมี '{required}' ในครอบครอง"
    return True, ""


def _instrument_in_inventory(cmd, state, world, p):
    if cmd.instrument is None:
        return False, "ไม่ได้ระบุสิ่งที่จะใช้"
    if cmd.instrument not in state.inventory:
        return False, f"'{cmd.instrument}' ไม่อยู่ในครอบครอง"
    return True, ""


def _min_evidence(cmd, state, world, p):
    need = p.get("minimum", 3)
    have = len(state.discovered_evidence)
    if have < need:
        return False, f"มีหลักฐาน {have} ชิ้น ต้องการอย่างน้อย {need} ชิ้น"
    return True, f"มีหลักฐาน {have} ชิ้น"


def _within_time_limit(cmd, state, world, p):
    limit = p.get("limit_seconds", 3600)
    if state.elapsed_seconds > limit:
        return False, f"ใช้เวลาไปแล้ว {state.elapsed_seconds} วินาที"
    return True, ""


CHECKERS: Dict[str, Callable] = {
    "action_is_known": _action_is_known,
    "target_exists": _target_exists,
    "suspect_exists": _suspect_exists,
    "target_is_takeable": _target_is_takeable,
    "container_unlocked": _container_unlocked,
    "has_required_key": _has_required_key,
    "instrument_in_inventory": _instrument_in_inventory,
    "min_evidence": _min_evidence,
    "within_time_limit": _within_time_limit,
}


# ============================================================
# ENGINE
# ============================================================
class SymbolicEngine:
    def __init__(self, rules_path: Path = None, story_path: Path = None):
        rules_path = rules_path or DATA_DIR / "rules.json"
        story_path = story_path or DATA_DIR / "story.json"
        self.rules: List[dict] = json.loads(rules_path.read_text(encoding="utf-8"))["rules"]
        self.world: dict = json.loads(story_path.read_text(encoding="utf-8"))

    def _applicable(self, action: ActionType) -> List[dict]:
        out = []
        for r in self.rules:
            scope = r.get("applies_to", [])
            if "*" in scope or action.value in scope:
                out.append(r)
        return out

    def decide(self, cmd: ParsedCommand, state: GameState) -> Decision:
        chain: List[ReasoningStep] = []

        for rule in self._applicable(cmd.action):
            checker = CHECKERS.get(rule["check"])
            if checker is None:
                raise ValueError(f"ไม่พบ checker '{rule['check']}' ของกฎ {rule['id']}")

            passed, detail = checker(cmd, state, self.world, rule.get("params", {}))
            desc = rule["description"]
            if detail:
                desc = f"{desc} ({detail})"
            chain.append(ReasoningStep(rule_id=rule["id"], description=desc, passed=passed))

            # หยุดที่กฎแรกที่ไม่ผ่าน เพราะกฎถัดไปอาจสมมติว่ากฎก่อนหน้าผ่านแล้ว
            if not passed:
                return Decision(
                    allowed=False,
                    message=rule["message_fail"],
                    reasoning_chain=chain,
                    violated_rule_id=rule["id"],
                    state_changes={},
                )

        return Decision(
            allowed=True,
            message=self._success_message(cmd),
            reasoning_chain=chain,
            violated_rule_id=None,
            state_changes=self._state_changes(cmd),
        )

    # --- ผลที่เกิดเมื่อคำสั่งผ่าน ---
    def _state_changes(self, cmd: ParsedCommand) -> dict:
        obj = self.world["objects"].get(cmd.target, {})
        if cmd.action == ActionType.TAKE:
            changes = {"inventory_add": cmd.target}
            if obj.get("type") == "evidence":
                changes["discovered_evidence_add"] = cmd.target
            return changes
        if cmd.action == ActionType.EXAMINE and obj.get("type") == "evidence":
            return {"discovered_evidence_add": cmd.target}
        if cmd.action == ActionType.UNLOCK:
            return {"unlocked_add": cmd.target}
        if cmd.action == ActionType.INTERROGATE:
            return {"interrogated_add": cmd.target}
        return {}

    def _success_message(self, cmd: ParsedCommand) -> str:
        name = (
            self.world["objects"].get(cmd.target, {}).get("name_th")
            or self.world["suspects"].get(cmd.target, {}).get("name_th")
            or cmd.target
        )
        templates = {
            ActionType.EXAMINE: f"ตรวจสอบ{name}เรียบร้อย",
            ActionType.TAKE: f"เก็บ{name}ไว้แล้ว",
            ActionType.UNLOCK: f"ปลดล็อก{name}สำเร็จ",
            ActionType.USE: f"ใช้งานกับ{name}สำเร็จ",
            ActionType.MOVE: f"เคลื่อนย้ายไปยัง{name}",
            ActionType.INTERROGATE: f"สอบปากคำ{name}เรียบร้อย",
            ActionType.ACCUSE: f"ยื่นข้อกล่าวหาต่อ{name}",
        }
        return templates.get(cmd.action, "ดำเนินการเรียบร้อย")


def apply_changes(state: GameState, changes: dict) -> GameState:
    """คืน state ใหม่ ไม่แก้ของเดิม เพื่อให้ทดลองซ้ำได้"""
    s = state.model_copy(deep=True)
    mapping = {
        "inventory_add": s.inventory,
        "discovered_evidence_add": s.discovered_evidence,
        "unlocked_add": s.unlocked_objects,
        "interrogated_add": s.interrogated_suspects,
    }
    for key, lst in mapping.items():
        v = changes.get(key)
        if v and v not in lst:
            lst.append(v)
    s.turn_count += 1
    return s
