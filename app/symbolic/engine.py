"""
engine.py — Symbolic Rule Engine

หน้าที่: รับ ParsedCommand + GameState -> คืน Decision
หลักการที่ห้ามละเมิด:
  1) การตัดสินใจเกิดที่นี่ 100% ไม่มีการเรียก LLM ในไฟล์นี้
  2) reasoning_chain สร้างจากกฎที่ถูกตรวจจริงเท่านั้น (faithful by construction)
  3) กฎอยู่ใน rules.json ไม่ hard-code เงื่อนไขลงในโค้ด
  4) ไม่นำ confidence จาก LLM มาใช้ในการตัดสิน
"""

import json
from pathlib import Path
from typing import Callable, Dict, List

from app.schemas import (
    ActionType,
    ParsedCommand,
    GameState,
    Decision,
    ReasoningStep,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

PILLARS = ("motive", "means", "opportunity", "corroboration")


# ============================================================
# CHECKERS — หนึ่งฟังก์ชันต่อหนึ่งชนิดของกฎ
# คืน (ผ่านหรือไม่, รายละเอียดที่จะแสดงใน reasoning chain)
# ============================================================

def _action_is_known(cmd, state, world, p):
    if cmd.action in (ActionType.UNKNOWN, ActionType.AMBIGUOUS):
        return False, f"action={cmd.action.value}"
    return True, ""


def _target_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุเป้าหมาย"
    # ระบบนี้เล่นด้วยการพิมพ์ล้วน ไม่มีปุ่มให้กด "ดูรอบๆ ห้องนี้" จึงเป็นคำสั่งพื้นฐาน
    # ที่ต้องใช้ได้ ดังนั้น examine จึงรับชื่อตู้รถเป็นเป้าหมายได้ด้วย
    if cmd.target not in world["objects"] and cmd.target not in world["locations"]:
        return False, f"ไม่รู้จัก object id '{cmd.target}'"
    return True, ""


def _location_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุจุดหมาย"
    if cmd.target not in world["locations"]:
        return False, f"ไม่รู้จัก location id '{cmd.target}'"
    return True, ""


def _suspect_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุบุคคล"
    if cmd.target not in world["suspects"]:
        return False, f"ไม่รู้จัก suspect id '{cmd.target}'"
    return True, ""


def _location_unlocked(cmd, state, world, p):
    loc = world["locations"].get(cmd.target, {})
    if not loc.get("locked", False):
        return True, ""
    required = loc.get("requires")
    if required and required not in state.inventory:
        return False, f"ต้องมี '{required}' จึงจะเข้าได้"
    return True, f"ใช้ '{required}' เปิดทาง"


def _in_same_location(cmd, state, world, p):
    if cmd.target in world["locations"]:
        # มองรอบๆ ได้เฉพาะตู้ที่ยืนอยู่ ตู้อื่นต้องเดินไปก่อน
        if cmd.target != state.current_location:
            return False, f"ต้องเดินไปที่ '{cmd.target}' ก่อนจึงจะมองเห็นได้"
        return True, ""
    # ค้นทั้งของและคน คนก็ต้องอยู่ตู้เดียวกันถึงจะสอบปากคำได้ ตะโกนข้ามขบวนไม่ได้
    entity = world["objects"].get(cmd.target) or world["suspects"].get(cmd.target, {})
    where = entity.get("location")
    if where is None:
        return True, ""
    if cmd.target in state.inventory:
        return True, "อยู่ในครอบครองแล้ว"
    if where != state.current_location:
        return False, f"อยู่ที่ '{where}' แต่ผู้สืบสวนอยู่ที่ '{state.current_location}'"
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
        return False, f"ซ่อนอยู่ใน '{container}' ซึ่งยังไม่ได้ตรวจสอบ"
    return True, ""


def _evidence_prerequisites_met(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    missing = [e for e in obj.get("requires_evidence", [])
               if e not in state.discovered_evidence]
    if missing:
        return False, f"ยังขาดหลักฐานนำทาง: {', '.join(missing)}"
    return True, ""


def _testimony_prerequisite_met(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    who = obj.get("requires_suspect")
    if who and who not in state.interrogated_suspects:
        return False, f"ต้องสอบปากคำ '{who}' ก่อน"
    return True, ""


def _suspect_available(cmd, state, world, p):
    sus = world["suspects"].get(cmd.target, {})
    missing = [e for e in sus.get("requires_evidence", [])
               if e not in state.discovered_evidence]
    if missing:
        return False, f"ยังขาดหลักฐานตั้งประเด็น: {', '.join(missing)}"
    prior = sus.get("requires_suspect")
    if prior and prior not in state.interrogated_suspects:
        return False, f"ต้องสอบปากคำ '{prior}' ก่อน"
    return True, ""


def _instrument_in_inventory(cmd, state, world, p):
    if cmd.instrument is None:
        return False, "ไม่ได้ระบุสิ่งที่จะใช้"
    if cmd.instrument not in state.inventory:
        return False, f"'{cmd.instrument}' ไม่อยู่ในครอบครอง"
    return True, ""


def _not_exculpated(cmd, state, world, p):
    """ถ้าพบหลักฐานที่ยืนยันว่าบุคคลนี้ถูกบังคับ จะกล่าวหาไม่ได้"""
    for ev_id in state.discovered_evidence:
        ev = world["objects"].get(ev_id, {})
        if ev.get("exculpates") == cmd.target:
            return False, f"หลักฐาน '{ev_id}' ยืนยันว่าถูกบังคับ"
    return True, ""


def _collect_pillars(target: str, state: GameState, world: dict) -> Dict[str, List[str]]:
    found = {k: [] for k in PILLARS}
    for ev_id in state.discovered_evidence:
        ev = world["objects"].get(ev_id, {})
        pillar = ev.get("supports", {}).get(target)
        if pillar in found:
            found[pillar].append(ev_id)
    return found


def _four_pillars(cmd, state, world, p):
    required = p.get("required", list(PILLARS))
    found = _collect_pillars(cmd.target, state, world)
    missing = [k for k in required if not found[k]]
    if missing:
        return False, f"ขาดหลักฐานด้าน: {', '.join(missing)}"
    summary = "; ".join(f"{k}={len(found[k])}" for k in required)
    return True, summary


def _game_not_over(cmd, state, world, p):
    """คดีปิดแล้วก็จบ ไม่ให้สั่งอะไรต่อ

    เดิมไม่ต้องมีกฎข้อนี้ เพราะจบเกมได้ทางเดียวคือกล่าวหาถูกตอนหลักฐานครบ
    พอมีฉากจบหลายแบบ ผู้เล่นกล่าวหาใครก็จบได้ตั้งแต่ตาแรก จึงต้องมีตัวปิดฉากจริงๆ
    """
    if state.ending_id:
        return False, f"คดีปิดไปแล้วด้วยฉากจบ '{state.ending_id}'"
    return True, ""


def _not_destroyed(cmd, state, world, p):
    if cmd.target in state.burned_objects:
        return False, f"'{cmd.target}' ถูกทำลายไปแล้ว"
    return True, ""


def _target_is_burnable(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    if not obj.get("burnable", False):
        return False, f"'{cmd.target}' ไม่มีคุณสมบัติ burnable"
    return True, ""


def _within_time_limit(cmd, state, world, p):
    # กรอบเวลาเป็นสมบัติของฉาก จึงอยู่ใน story.json ที่เดียว
    # params ใน rules.json ใช้ override ได้ถ้าอยากทดลองค่าอื่นโดยไม่แตะฉาก
    limit = p.get("limit_seconds") or world.get("time_limit_seconds", 3600)
    if state.elapsed_seconds > limit:
        return False, f"ใช้เวลาไปแล้ว {state.elapsed_seconds} วินาที"
    return True, ""


CHECKERS: Dict[str, Callable] = {
    "action_is_known": _action_is_known,
    "target_exists": _target_exists,
    "location_exists": _location_exists,
    "suspect_exists": _suspect_exists,
    "location_unlocked": _location_unlocked,
    "in_same_location": _in_same_location,
    "target_is_takeable": _target_is_takeable,
    "container_unlocked": _container_unlocked,
    "evidence_prerequisites_met": _evidence_prerequisites_met,
    "testimony_prerequisite_met": _testimony_prerequisite_met,
    "suspect_available": _suspect_available,
    "instrument_in_inventory": _instrument_in_inventory,
    "not_exculpated": _not_exculpated,
    "four_pillars": _four_pillars,
    "within_time_limit": _within_time_limit,
    "game_not_over": _game_not_over,
    "not_destroyed": _not_destroyed,
    "target_is_burnable": _target_is_burnable,
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
        return [r for r in self.rules
                if "*" in r.get("applies_to", []) or action.value in r.get("applies_to", [])]

    def decide(self, cmd: ParsedCommand, state: GameState) -> Decision:
        chain: List[ReasoningStep] = []

        for rule in self._applicable(cmd.action):
            checker = CHECKERS.get(rule["check"])
            if checker is None:
                raise ValueError(f"ไม่พบ checker '{rule['check']}' ของกฎ {rule['id']}")

            passed, detail = checker(cmd, state, self.world, rule.get("params", {}))
            desc = f"{rule['description']} ({detail})" if detail else rule["description"]
            chain.append(ReasoningStep(rule_id=rule["id"], description=desc, passed=passed))

            # กฎที่ blocking=false ใช้ "จำแนก" ไม่ใช่ "ปิดประตู"
            # ผลของมันยังถูกบันทึกลงสายเหตุผลตามจริง แต่ไม่ทำให้คำสั่งถูกปฏิเสธ
            # เกมนี้ต้องกล่าวหาผิดคนได้ ไม่งั้นฉากจบที่เป็นแก่นของเรื่องจะไปไม่ถึง
            # ส่วนการเลือกว่าได้ฉากจบไหน ยังเป็นงานของ symbolic ทั้งหมด ไม่มี LLM เกี่ยว
            if not passed and not rule.get("blocking", True):
                continue

            # หยุดที่กฎแรกที่ไม่ผ่าน เพราะกฎถัดไปอาจสมมติว่ากฎก่อนหน้าผ่านแล้ว
            if not passed:
                # กฎข้อแรกครอบทั้ง unknown และ ambiguous ด้วยข้อความเดียว แต่ผู้เล่นต้องการ
                # คำแนะนำคนละแบบ เกมนี้พิมพ์ล้วนไม่มีปุ่ม ถ้าบอกแค่ว่าไม่เข้าใจ ผู้เล่นจะตันทันที
                message = rule["message_fail"]
                if cmd.action is ActionType.AMBIGUOUS:
                    message = ("คำสั่งนี้กว้างเกินไป ระบบจะไม่เดาแทนผู้เล่น "
                               "ลองบอกให้เจาะจงว่าจะทำกับสิ่งไหน "
                               "หรือพิมพ์ 'ดูรอบๆ' เพื่อดูว่าตอนนี้มีอะไรอยู่ตรงหน้าบ้าง")
                elif rule["id"] == "R005_SAME_LOCATION":
                    # เอนจินรู้อยู่แล้วว่าเป้าหมายอยู่ตู้ไหน แต่เดิมข้อความทิ้งข้อมูลนั้นไป
                    # บอกแค่ว่าต้องเดินไปหาก่อน ผู้เล่นเลยตันเพราะไม่รู้ว่าตู้ไหน
                    # ไม่ถือว่าเฉลย เพราะผู้เล่นเอ่ยชื่อสิ่งนั้นออกมาเองแล้ว
                    entity = (self.world["objects"].get(cmd.target)
                              or self.world["suspects"].get(cmd.target) or {})
                    where = entity.get("location")
                    if where:
                        message += (f" {entity.get('name_th', cmd.target)} อยู่ที่"
                                    f"{self.world['locations'].get(where, {}).get('name_th', where)}")
                elif rule["id"] == "R014_TIME_LIMIT":
                    timeout = self.ending_for(on_timeout=True)
                    if timeout:
                        message = self._render_ending(timeout, [])
                elif cmd.action is ActionType.UNKNOWN:
                    message += (" สิ่งที่ทำได้คือ ดูรอบๆ เดินไปตู้อื่น "
                                "ตรวจดูของ สอบปากคำคน และกล่าวหาเมื่อมีหลักฐานพอ")
                return Decision(
                    allowed=False,
                    message=message,
                    reasoning_chain=chain,
                    violated_rule_id=rule["id"],
                    state_changes={},
                )

        return Decision(
            allowed=True,
            message=self._success_message(cmd, state),
            reasoning_chain=chain,
            violated_rule_id=None,
            state_changes=self._state_changes(cmd, state),
        )

    def _state_changes(self, cmd: ParsedCommand, state: GameState) -> dict:
        obj = self.world["objects"].get(cmd.target, {})
        if cmd.action == ActionType.MOVE:
            return {"move_to": cmd.target}
        if cmd.action == ActionType.TAKE:
            changes = {"inventory_add": cmd.target}
            if obj.get("type") == "evidence":
                changes["discovered_evidence_add"] = cmd.target
            return changes
        if cmd.action == ActionType.EXAMINE:
            if cmd.target in self.world["locations"]:
                return {}          # มองรอบๆ ไม่เปลี่ยนสถานะอะไร
            changes = {"unlocked_add": cmd.target}
            if obj.get("type") == "evidence":
                changes["discovered_evidence_add"] = cmd.target
            return changes
        if cmd.action == ActionType.UNLOCK:
            return {"unlocked_add": cmd.target}
        if cmd.action == ActionType.BURN:
            return {"burned_add": cmd.target}
        if cmd.action == ActionType.ACCUSE:
            # ฉากจบถูกเลือกที่นี่ครั้งเดียว แล้วบันทึกลง state เพื่อปิดคดี
            return {"ending": self.ending_for(cmd.target, state).get("id")}
        if cmd.action == ActionType.INTERROGATE:
            changes = {"interrogated_add": cmd.target}
            granted = self.world["suspects"].get(cmd.target, {}).get("grants_object")
            if granted:
                changes["inventory_add"] = granted
            return changes
        return {}

    def look_around(self, loc_id: str, state: GameState) -> str:
        """คำบรรยายตู้รถ พร้อมรายการสิ่งที่ 'มองเห็นได้ตอนนี้'

        สิ่งที่ยังไม่ผ่านเงื่อนไข (ซ่อนอยู่ หรือยังไม่มีหลักฐานนำทาง) จะไม่ถูกแสดง
        โดยถามจากกฎชุดเดียวกับที่ใช้ตัดสินจริง ไม่ใช่รายการที่เขียนมือแยกไว้
        ไม่งั้นสิ่งที่เห็นกับสิ่งที่ทำได้จะไม่ตรงกัน
        """
        loc = self.world["locations"].get(loc_id, {})
        lines = [loc.get("description", loc.get("name_th", loc_id))]

        here = [oid for oid, o in self.world["objects"].items()
                if o.get("location") == loc_id and oid not in state.inventory]
        visible = [oid for oid in here if self.decide(
            ParsedCommand(action=ActionType.EXAMINE, target=oid, raw_text="", confidence=0.0),
            state,
        ).allowed]

        if visible:
            names = "\n".join(f"  - {self.world['objects'][oid].get('name_th', oid)}"
                              for oid in visible)
            lines.append(f"สิ่งที่สังเกตเห็นได้ตอนนี้:\n{names}")
        else:
            lines.append("ตอนนี้ยังไม่มีอะไรในตู้นี้ที่น่าตรวจสอบเพิ่ม")

        # คนที่อยู่ในตู้นี้ — แสดงทุกคนที่อยู่ ไม่ว่าจะสอบปากคำได้แล้วหรือยัง
        # เกมนี้พิมพ์ล้วนไม่มีปุ่ม ถ้าไม่บอกว่ามีใครอยู่ ผู้เล่นจะไม่มีทางรู้ว่าสอบปากคำใครได้
        # ส่วนคนที่ยังสอบไม่ได้ กฎจะเป็นคนบอกเองว่าต้องหาหลักฐานอะไรก่อน
        people = [(sid, s) for sid, s in self.world["suspects"].items()
                  if s.get("location") == loc_id]
        if people:
            who = "\n".join(f"  - {s.get('name_th', sid)} ({s.get('role', '')})"
                            for sid, s in people)
            lines.append(f"คนที่อยู่ในตู้นี้:\n{who}")
        return "\n".join(lines)

    def offerable(self, target: str, state: GameState) -> bool:
        """ตัวเลือกนี้เอ่ยชื่อให้ผู้เล่นเห็นได้ไหม โดยไม่เฉลยของที่เขายังหาไม่เจอ

        ตู้รถกับผู้คนบอกได้หมด ตู้ทุกตู้ถูกเอ่ยชื่ออยู่ในคำบรรยายตู้แรกแล้ว
        ส่วนคนก็เดินไปเจอเองได้ และคำสั่งพ่วงอย่าง "ไปที่ ก แล้วคุยกับ ข"
        ต้องยังแตกขั้นได้ตามปกติ
        แต่ 'ของ' คือสิ่งที่ผู้เล่นต้องออกไปหา ถ้าลิสต์ชื่อให้ก็เท่ากับเกมเฉลยตัวเอง
        จึงเสนอได้เฉพาะของที่ถืออยู่ เจอแล้ว หรือมองเห็นได้ในตู้ที่ยืนอยู่ตอนนี้
        โดยถามจากกฎชุดเดียวกับที่ look_around ใช้ ของที่ยังซ่อนอยู่จึงไม่หลุด
        """
        obj = self.world["objects"].get(target)
        if obj is None:
            return True
        if target in state.inventory or target in state.discovered_evidence:
            return True
        return obj.get("location") == state.current_location and self.decide(
            ParsedCommand(action=ActionType.EXAMINE, target=target, raw_text="", confidence=0.0),
            state,
        ).allowed

    def _success_message(self, cmd: ParsedCommand, state: GameState) -> str:
        obj = self.world["objects"].get(cmd.target, {})
        sus = self.world["suspects"].get(cmd.target, {})
        loc = self.world["locations"].get(cmd.target, {})
        name = obj.get("name_th") or sus.get("name_th") or loc.get("name_th") or cmd.target

        # ระบบพิมพ์ล้วน ผู้เล่นรู้จักโลกได้จากข้อความที่ตอบกลับเท่านั้น
        # จึงต้องคืนเนื้อความจริงจาก story.json ไม่ใช่ประโยคยืนยันลอยๆ
        if cmd.action == ActionType.EXAMINE:
            if cmd.target in self.world["locations"]:
                return self.look_around(cmd.target, state)
            return obj.get("description") or f"ตรวจสอบ{name}อย่างละเอียด แต่ไม่พบอะไรเพิ่มเติม"
        if cmd.action == ActionType.INTERROGATE:
            return sus.get("testimony") or f"สอบปากคำ {name} แต่ไม่ได้ข้อมูลเพิ่ม"
        if cmd.action == ActionType.MOVE:
            return self.look_around(cmd.target, state.model_copy(update={"current_location": cmd.target}))
        if cmd.action == ActionType.ACCUSE:
            return self.closing_argument(cmd.target, state)

        templates = {
            ActionType.TAKE: f"เก็บ{name}ไว้เป็นหลักฐาน",
            ActionType.UNLOCK: f"เปิด{name}ได้แล้ว",
            ActionType.USE: f"ใช้งานกับ{name}",
            ActionType.BURN: f"คุณเผา{name}ทิ้ง เถ้าที่เหลือเรียกอะไรกลับมาไม่ได้อีก",
        }
        return templates.get(cmd.action, "ดำเนินการเรียบร้อย")

    def pillars_complete(self, suspect_id: str, state: GameState) -> bool:
        """ผู้ถูกกล่าวหาคนนี้มีหลักฐานครบทั้งสี่ด้านแล้วหรือยัง"""
        found = _collect_pillars(suspect_id, state, self.world)
        return all(found[p] for p in PILLARS)

    def ending_for(self, suspect_id: str = None, state: GameState = None,
                on_timeout: bool = False) -> dict:
        """เลือกฉากจบจากสถานะจริงของผู้เล่น ตามเงื่อนไขที่เขียนไว้ใน story.json

        เรียงจากเงื่อนไขเฉพาะที่สุดไปกว้างที่สุด หยิบอันแรกที่เข้าเงื่อนไข
        ทุกเงื่อนไขอ่านจาก GameState และ story.json เท่านั้น ไม่มี LLM เกี่ยวข้อง
        ฉากจบจึงตรวจย้อนกลับได้เหมือน reasoning_chain
        """
        culprit = self.world.get("culprit")
        for ending in self.world.get("endings", []):
            if bool(ending.get("on_timeout")) != on_timeout:
                continue
            if on_timeout:
                return ending
            who = ending.get("accuse", "*")
            if who != "*" and who != suspect_id:
                continue
            if ending.get("requires_pillars") and not self.pillars_complete(suspect_id, state):
                continue
            if ending.get("requires_case_against_culprit") and not self.pillars_complete(culprit, state):
                continue
            if any(e not in state.discovered_evidence for e in ending.get("requires_evidence", [])):
                continue
            if any(i not in state.inventory for i in ending.get("requires_inventory", [])):
                continue
            return ending
        return {}

    def _render_ending(self, ending: dict, body: List[str]) -> str:
        head = [f"=== {ending.get('title', 'จบเกม')} ({ending.get('rank', '')}) ===", ""]
        return "\n".join(head + body + ["", ending.get("text", "")])

    def closing_argument(self, suspect_id: str, state: GameState) -> str:
        """คำแถลงปิดคดี ประกอบขึ้นจากหลักฐานที่ผู้เล่นหามาได้จริง

        ไม่ใช่ข้อความสำเร็จรูป ทุกบรรทัดอ้างชิ้นหลักฐานที่อยู่ใน discovered_evidence
        จริงๆ ถ้าผู้เล่นเก็บหลักฐานคนละชุด คำแถลงก็ออกมาคนละแบบ
        หลักการเดียวกับ reasoning_chain คือคำอธิบายต้องมาจากสิ่งที่เกิดขึ้นจริง
        ไม่ใช่ข้อความที่เขียนรอไว้ ส่วนฉากจบก็ถูกเลือกจากสถานะเดียวกันนี้
        """
        sus = self.world["suspects"].get(suspect_id, {})
        found = _collect_pillars(suspect_id, state, self.world)
        label = {
            "motive": "แรงจูงใจ",
            "means": "วิธีการ",
            "opportunity": "โอกาส",
            "corroboration": "หลักฐานสนับสนุน",
        }

        body = [f"คุณเรียกทุกคนมารวมกันที่ตู้เสบียง แล้วชี้ไปที่{sus.get('name_th', suspect_id)}", ""]
        for pillar in PILLARS:
            names = [self.world["objects"][e].get("name_th", e) for e in found[pillar]]
            body.append(f"  {label[pillar]}")
            for n in names:
                body.append(f"    - {n}")
            if not names:
                body.append("    - ไม่มีหลักฐานด้านนี้")
        body.append("")
        body.append(f"รวมหลักฐาน {sum(len(v) for v in found.values())} ชิ้น "
                    f"ครบ {sum(1 for p in PILLARS if found[p])} จาก 4 ด้าน "
                    f"ใช้เวลาไป {state.elapsed_seconds // 60} นาที จาก "
                    f"{self.world.get('time_limit_seconds', 3600) // 60} นาที")
        return self._render_ending(self.ending_for(suspect_id, state), body)

    def seconds_left(self, state: GameState) -> int:
        """เวลาที่เหลือ ติดลบได้ถ้าเลยกำหนดไปแล้ว

        กรอบเวลามีอยู่ในกฎตั้งแต่แรก แต่ไม่มีใครเห็น ผู้เล่นจึงไม่รู้สึกถึงมันเลย
        จนกระทั่งถูกปฏิเสธทุกคำสั่งแบบไม่มีปี่มีขลุ่ย
        """
        return self.world.get("time_limit_seconds", 3600) - state.elapsed_seconds

    def is_out_of_time(self, state: GameState) -> bool:
        """หมดเวลาแล้วหรือยัง ใช้ตัดสินว่าเกมจบ ไม่ใช่ตัดสินว่าคำสั่งผ่านไหม

        เงื่อนไขตรงกับ _within_time_limit เพื่อไม่ให้ UI กับกฎบอกคนละอย่าง
        """
        return self.seconds_left(state) < 0

    def ending_message(self, state: GameState) -> str:
        """ข้อความปิดเกมกรณีหมดเวลา ดึงจากฉากจบที่ทำเครื่องหมาย on_timeout ไว้

        เดิมเขียนข้อความไว้ในโค้ด ตอนนี้ฉากจบทั้งหมดอยู่ใน story.json แล้ว
        จึงต้องอ่านจากที่เดียวกัน ไม่งั้น UI บนเว็บกับ UI บนเทอร์มินัลจะเล่าตอนจบคนละแบบ
        """
        return self._render_ending(self.ending_for(on_timeout=True), [])

    # ใช้สำหรับ UI และการวิเคราะห์ผล ไม่ใช่ส่วนของการตัดสิน
    def pillar_status(self, target: str, state: GameState) -> Dict[str, List[str]]:
        """ความคืบหน้าสี่เสาหลัก — สำหรับ UI และการวิเคราะห์ ไม่ใช่ส่วนของการตัดสิน"""
        return _collect_pillars(target, state, self.world)


_STORY = json.loads((DATA_DIR / "story.json").read_text(encoding="utf-8"))

# เวลาที่หมดไปต่อหนึ่งตา — ปรับที่ story.json ไม่ปรับในโค้ด
# ponytail: คิดเท่ากันทุก action ถ้าอยากให้เดินข้ามตู้แพงกว่าตรวจของ ค่อยทำเป็น dict ต่อ action
SECONDS_PER_TURN: int = _STORY.get("seconds_per_turn", 60)


def apply_changes(state: GameState, changes: dict) -> GameState:
    """คืน state ใหม่ ไม่แก้ของเดิม เพื่อให้ยิงคำสั่งชุดเดิมซ้ำได้ผลเหมือนกัน

    เวลาเดินทุกตาโดยไม่ขึ้นกับว่าใครเป็นผู้ตัดสิน จงใจให้อยู่ตรงนี้ไม่ใช่ใน state_changes
    เพราะถ้าปล่อยให้คำตัดสินเป็นตัวกำหนด โหมด A (LLM ตัดสินเอง) จะคุมเวลาของตัวเองได้
    แล้วสองโหมดจะเดินด้วยนาฬิกาคนละเรือน เทียบกันไม่ได้
    """
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
    burned = changes.get("burned_add")
    if burned:
        if burned not in s.burned_objects:
            s.burned_objects.append(burned)
        # ของที่ถูกเผาต้องหลุดจากมือด้วย ไม่งั้นเงื่อนไขฉากจบที่ดูจากของในมือจะเพี้ยน
        if burned in s.inventory:
            s.inventory.remove(burned)
    if changes.get("ending"):
        s.ending_id = changes["ending"]
    dest = changes.get("move_to")
    if dest:
        s.current_location = dest
        if dest not in s.visited_locations:
            s.visited_locations.append(dest)
    s.turn_count += 1
    s.elapsed_seconds += SECONDS_PER_TURN
    return s
