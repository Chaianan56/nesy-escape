"""
engine.py — Symbolic Rule Engine

หน้าที่: รับ ParsedCommand + GameState -> คืน Decision
หลักการที่ห้ามละเมิด:
  1) การตัดสินใจเกิดที่นี่ 100% ไม่มีการเรียก LLM ในไฟล์นี้
  2) reasoning_chain สร้างจากกฎที่ถูกตรวจจริงเท่านั้น (faithful by construction)
  3) เงื่อนไขฉากอยู่ใน JSON ส่วน checker และผลของ action อยู่ใน Python
  4) ไม่นำ confidence จาก LLM มาใช้ในการตัดสิน
"""

import json
from pathlib import Path
from typing import Callable, Dict, List
from app.symbolic.validation import validate_world

from app.schemas import (
    ActionType,
    ParsedCommand,
    GameState,
    Decision,
    ReasoningStep,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# เสาหลักของคดีไม่ได้ตายตัวในโค้ด อ่านจาก story.json
# คดีนี้ใช้ TIMELINE แทน MEANS เพราะแก่นของคดีคือการลวงเวลาตาย
DEFAULT_PILLARS = ("timeline", "motive", "opportunity", "corroboration")


# ค่าเริ่มต้นสำหรับฉากเก่า ฉากใหม่กำหนดเพดานจากเส้นทางหลักฐานที่ตรวจแล้ว
MAX_SUBMITTED_EVIDENCE = 15
# กล่าวหาพลาดได้สองครั้งพร้อมคำบอกเสาที่ขาด ครั้งที่สามคดีปิดแบบพิสูจน์ไม่ได้
MAX_FAILED_ACCUSATIONS = 3
ACCUSATION_RULE = "R012_ACCUSE_ENDING_REQUIREMENTS"


def accusation_submission(engine, cmd, state, submitted=None):
    """Judge an accusation against the complete evidence record the player found.

    ``submitted`` remains accepted for older callers, but is deliberately ignored:
    selecting a subset must not hide relevant or exculpatory evidence.
    """
    decision = engine.decide(cmd, state)
    if decision.violated_rule_id != ACCUSATION_RULE:
        return decision
    return failed_accusation(engine, cmd.target, state, decision, state.failed_accusations + 1)


def failed_accusation(engine, suspect_id, offered, decision, attempt):
    """บอกว่าเสาไหนพิสูจน์ได้แล้ว โดยไม่บอกว่าขาดหลักฐานชิ้นไหน และปิดคดีเมื่อพลาดครบ"""
    checklist = engine.pillar_checklist(suspect_id, offered)
    chain = list(decision.reasoning_chain)
    if attempt >= MAX_FAILED_ACCUSATIONS:
        step = f"กล่าวหาไม่ผ่านครบ {MAX_FAILED_ACCUSATIONS} ครั้ง คดีปิดแบบพิสูจน์ไม่ได้"
        chain.append(ReasoningStep(rule_id="R_ACCUSATION_LIMIT", description=step, passed=False))
        ending = engine.world["endings"]["unproven"]
        message = engine._render_ending(ending, [step, ""] + checklist)
        return Decision(allowed=False, message=message, violated_rule_id=ACCUSATION_RULE,
                        reasoning_chain=chain, state_changes={"ending": "unproven", "failed_accusations": attempt})
    left = MAX_FAILED_ACCUSATIONS - attempt
    # "เหลือโอกาส" นับเฉพาะครั้งที่หลักฐานที่พบยังไม่เข้าเงื่อนไขฉากจบใด
    # แม้เป็นฉากจบผิด คดีปิดทันที ข้อความต้องบอกทั้งสองกรณี ไม่ให้ผู้เล่นคิดว่าลองได้ฟรี
    message = "\n".join(["หลักฐานที่พบยังไม่พอจะสรุปคดี", ""] + checklist + [
        "", f"กล่าวหาใหม่ได้อีก {left} ครั้ง ถ้าครั้งสุดท้ายยังไม่พอ คดีจะปิดแบบพิสูจน์ไม่ได้",
        "ถ้าหลักฐานที่พบพอจะสรุปคดีได้ คดีจะปิดทันทีตามข้อสรุปนั้น แม้ข้อสรุปจะผิดและยังเหลือโอกาสอยู่"])
    return Decision(allowed=False, message=message, violated_rule_id=ACCUSATION_RULE,
                    reasoning_chain=chain, state_changes={"failed_accusations": attempt})


# ============================================================
# CHECKERS — หนึ่งฟังก์ชันต่อหนึ่งชนิดของกฎ
# คืน (ผ่านหรือไม่, รายละเอียดที่จะแสดงใน reasoning chain)
# ============================================================

def _action_is_known(cmd, state, world, p):
    if cmd.action in (ActionType.UNKNOWN, ActionType.AMBIGUOUS, ActionType.SEQUENCE):
        return False, f"action={cmd.action.value}"
    return True, ""


def _target_exists(cmd, state, world, p):
    if cmd.target is None:
        return False, "ไม่ได้ระบุเป้าหมาย"
    # ระบบนี้เล่นด้วยการพิมพ์ล้วน ไม่มีปุ่มให้กด "ดูรอบๆ ห้องนี้" จึงเป็นคำสั่งพื้นฐาน
    if cmd.target not in world["objects"] and cmd.target not in world["locations"] and cmd.target not in world["suspects"]:
        return False, f"ไม่รู้จัก id '{cmd.target}'"
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


def _evidence_source_available(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    owner = obj.get("from_testimony")
    if owner and (owner not in state.interrogated_suspects or cmd.target not in state.discovered_evidence):
        return False, "หลักฐานนี้ต้องได้รับจากการสอบปากคำก่อน"
    return True, ""


def _condition_met(cond: dict, evidence: set, held: set) -> bool:
    """เงื่อนไขหนึ่งข้อเป็นจริงหรือยัง

    รองรับสามแบบที่สเปกใช้จริง
        requires_evidence    ต้องมีหลักฐานครบทุกชิ้นที่ระบุ
        requires_deductions  ต้องสรุปข้อก่อนหน้าได้ครบทุกข้อ
        at_least / of        ต้องได้อย่างน้อย n ข้อจากรายการที่ให้มา
    ทั้งสามอย่างต้องผ่านพร้อมกัน ถ้าไม่ได้ระบุข้อไหนถือว่าข้อนั้นผ่าน
    """
    if any(e not in evidence for e in cond.get("requires_evidence", [])):
        return False
    if any(d not in held for d in cond.get("requires_deductions", [])):
        return False
    need = cond.get("at_least")
    if need is not None:
        pool = cond.get("of", [])
        got = sum(1 for x in pool if x in held or x in evidence)
        if got < need:
            return False
    return True


def deductions_held(state: GameState, world: dict) -> set:
    """ข้อสรุปทั้งหมดที่ผู้เล่นมีสิทธิ์สรุปได้จากหลักฐานที่หามาได้จริง

    ข้อสรุปไม่ได้ถูกเก็บใน GameState แต่คำนวณสดจาก discovered_evidence ทุกครั้ง
    เพื่อไม่ให้มีสองแหล่งความจริงที่หลุดจากกันได้ ถ้าเก็บไว้ในสถานะ
    จะมีทางที่ใครสักคนเซ็ตข้อสรุปโดยไม่มีหลักฐานรองรับ ซึ่งเป็นสิ่งที่งานนี้ห้าม

    ข้อสรุปอ้างข้อสรุปอื่นได้ จึงต้องวนจนกว่าจะไม่มีอะไรเพิ่ม
    """
    evidence = set(state.discovered_evidence)
    rules = world.get("deductions", {})
    held: set = set()
    changed = True
    while changed:
        changed = False
        for did, cond in rules.items():
            if did not in held and _condition_met(cond, evidence, held):
                held.add(did)
                changed = True
    return held


def _collect_pillars(target: str, state: GameState, world: dict) -> Dict[str, List[str]]:
    """เสาหลักของผู้ถูกกล่าวหา คืนเป็น เสา -> รายการข้อสรุปที่ค้ำเสานั้น

    เสาไหนไม่มีข้อสรุปค้ำเลย ถือว่ายังไม่ครบ
    ผู้ต้องสงสัยที่ฉากไม่ได้กำหนดเสาไว้ให้ จะได้เสาว่างทั้งหมด
    การกล่าวหายังต้องผ่านเงื่อนไขฉากจบของบุคคลนั้นใน R012
    """
    spec = world.get("pillars", {}).get(target, {})
    held = deductions_held(state, world)
    found = {}
    for pillar in pillar_names(world):
        condition = spec.get(pillar, {})
        need = condition.get("requires_deductions", [])
        claims_ok = all(_claim_held(cid, state, world) or _claim_supported(cid, state.discovered_evidence, state, world)
                        for cid in condition.get("requires_claims", []))
        found[pillar] = list(need) if need and all(d in held for d in need) and claims_ok else []
    return found


def pillar_names(world: dict) -> tuple:
    """ชื่อเสาหลักของฉากนี้ อ่านจากฉากก่อน ถ้าไม่ได้กำหนดค่อยใช้ค่าเริ่มต้น"""
    order = world.get("pillar_order")
    return tuple(order) if order else DEFAULT_PILLARS


def _ending_matches(ending, suspect_id, state, world):
    if ending.get("on_timeout") or ending.get("accuse", "*") not in ("*", suspect_id):
        return False
    pillars = _collect_pillars(suspect_id, state, world)
    held = deductions_held(state, world)
    return (
        all(pillars.get(p) for p in ending.get("requires_pillars", []))
        and not any(pillars.get(p) for p in ending.get("denies_pillars", []))
        and all(d in held for d in ending.get("requires_deductions", []))
        and not any(d in held for d in ending.get("denies_deductions", []))
        and all(e in state.discovered_evidence for e in ending.get("requires_evidence", []))
        and not any(e in state.discovered_evidence for e in ending.get("denies_evidence", []))
        and all(_claim_held(cid, state, world) or _claim_supported(cid, state.discovered_evidence, state, world)
                for cid in ending.get("requires_claims", []))
    )


def _accusation_ready(cmd, state, world, p):
    # Only an actual ending for this suspect can authorize an accusation.
    # The wildcard fallback must never make an unsupported accusation playable.
    candidates = [e for e in world.get("endings", {}).values()
                  if e.get("accuse") == cmd.target]
    if any(_ending_matches(e, cmd.target, state, world) for e in candidates):
        return True, "หลักฐานและข้อสรุปเข้าเงื่อนไขฉากจบของผู้ต้องสงสัยแล้ว"
    return False, "หลักฐานหรือข้อสรุปยังไม่เข้าเงื่อนไข ต้องสืบสวนต่อก่อนกล่าวหา"


def _four_pillars(cmd, state, world, p):
    """กฎสี่เสา ตรวจว่าคำกล่าวหามีหลักฐานครบทุกด้านหรือยัง"""
    found = _collect_pillars(cmd.target, state, world)
    names = pillar_names(world)
    missing = [k for k in names if not found[k]]
    if missing:
        return False, f"ขาดเสา: {', '.join(missing)}"
    return True, "; ".join(f"{k}={len(found[k])}" for k in names)


def _location_accessible(cmd, state, world, p):
    """บางพื้นที่บนขบวนผู้เล่นเข้าไม่ได้ และไม่มีวันเข้าได้

    ต่างจากประตูล็อกตรงที่ไม่มีกุญแจให้หา มันคือขอบของโลกเกม
    ยังแสดงบนแผนที่เพราะรถไฟจริงก็มีหัวรถจักร แต่ไม่ใช่พื้นที่เล่น
    """
    loc = world["locations"].get(cmd.target, {})
    if loc.get("restricted"):
        return False, loc.get("restricted_reason", "เป็นพื้นที่หวงห้าม")
    return True, ""


def _object_supports_action(cmd, state, world, p):
    """สิทธิ์ทำกับวัตถุอ่านจาก supports; รหัส กุญแจ และการเข้าถึงตรวจอีกกฎหนึ่ง"""
    obj = world["objects"].get(cmd.target, {})
    if cmd.action.value in obj.get("supports", []):
        return True, ""
    return False, f"'{obj.get('name_th', cmd.target)}' ไม่ได้ประกาศว่ารองรับ {cmd.action.value}"


def _requirements_met(requirements, state, world):
    return (_condition_met(requirements, set(state.discovered_evidence), deductions_held(state, world))
            and set(requirements.get("requires_unlocked", [])) <= set(state.unlocked_objects)
            and set(requirements.get("requires_inventory", [])) <= set(state.inventory)
            and all(_claim_held(cid, state, world) for cid in requirements.get("requires_claims", [])))


def _visible(cmd, state, world, p):
    entity = world["objects"].get(cmd.target, {})
    if cmd.target in state.burned_objects:
        return False, "สิ่งนี้ถูกทำลายแล้ว"
    return _requirements_met(entity.get("visible_requirements", {}), state, world), ""


def _unlock_ready(cmd, state, world, p):
    obj = world["objects"].get(cmd.target, {})
    requirement = obj.get("unlock_requirements")
    if not requirement:
        return False, "เป้าหมายไม่มีวิธีปลดล็อกที่กำหนดไว้"
    if cmd.target in state.unlocked_objects:
        return True, "ปลดล็อกแล้ว"
    if not _requirements_met(requirement, state, world):
        return False, "ยังไม่มีหลักฐานหรือสิ่งของที่ต้องใช้"
    if "code" in requirement and cmd.code != str(requirement["code"]):
        return False, "รหัสไม่ถูกต้อง"
    key = requirement.get("key")
    if key and (key not in state.inventory or (cmd.instrument and cmd.instrument != key)):
        return False, "ต้องใช้กุญแจที่ถูกต้องและมีอยู่ในครอบครอง"
    return True, ""


def _eligible_dialogue(person, state, world):
    return [node for node in person.get("dialogue_nodes", []) if _requirements_met(node, state, world)]


def _dialogue_node(sid, topic, state, world):
    nodes = _eligible_dialogue(world["suspects"].get(sid, {}), state, world)
    if topic:
        matching = [node for node in nodes if node.get("topic") == topic]
        return matching[-1] if matching else None
    unseen = [node for node in nodes if f"{sid}:{node['id']}" not in state.dialogue_history]
    return unseen[0] if unseen else (nodes[-1] if nodes else None)


def _dialogue_available(cmd, state, world, p):
    person = world["suspects"].get(cmd.target, {})
    if "dialogue_nodes" not in person:
        return not cmd.topic, "ยังไม่มีบทสำหรับประเด็นนี้" if cmd.topic else ""
    return _dialogue_node(cmd.target, cmd.topic, state, world) is not None, ""


def _accusable(cmd, state, world, p):
    person = world["suspects"].get(cmd.target, {})
    if person.get("accusable", True) is False:
        return False, "บุคคลนี้เป็นพยาน ไม่ใช่ผู้ต้องสงสัย"
    held = deductions_held(state, world)
    if (set(person.get("exculpatory_deductions", [])) & held
            or set(person.get("exculpatory_evidence", [])) & set(state.discovered_evidence)):
        return False, "หลักฐานที่คุณทราบแล้วหักล้างข้อกล่าวหานี้"
    return True, ""


def _available_questions(state, world):
    return [q for q in world.get("inference_questions", []) if _requirements_met(q, state, world)]


def _claim_supported(cid, evidence, state, world):
    claim = world.get("claims", {}).get(cid, {})
    offered = state.model_copy(update={"discovered_evidence": list(evidence)})
    return bool(claim.get("supported")) and _condition_met(
        claim, set(evidence), deductions_held(offered, world))


def _claim_held(cid, state, world):
    # Keep the player's earned reasoning, but do not turn optional supporting
    # observations into mandatory evidence in every later accusation.
    known = set(state.discovered_evidence)
    evidence = [eid for eid in state.claim_evidence.get(cid, []) if eid in known]
    return (cid in state.validated_claims and bool(evidence)
            and _claim_supported(cid, evidence, state, world))


def _inference_ready(cmd, state, world, p):
    available = {choice["target"] for q in _available_questions(state, world) for choice in q.get("choices", [])}
    if cmd.target not in available:
        return False, "ยังไม่มีประเด็นนี้ในสมุดคดี"
    if not cmd.evidence or len(cmd.evidence) != len(set(cmd.evidence)) or not set(cmd.evidence) <= set(state.discovered_evidence):
        return False, "เลือกหลักฐานที่ค้นพบแล้ว โดยแต่ละชิ้นใช้ได้ครั้งเดียว"
    if not _claim_supported(cmd.target, cmd.evidence, state, world):
        return False, world.get("claims", {}).get(cmd.target, {}).get("feedback", "หลักฐานที่เลือกยังไม่รองรับข้อสรุปนี้")
    return True, "ข้อสรุปได้รับการรองรับจากหลักฐานที่เลือก"


def _game_not_over(cmd, state, world, p):
    """คดีปิดแล้วก็จบ ไม่ให้สั่งอะไรต่อ

    เดิมไม่ต้องมีกฎข้อนี้ เพราะจบเกมได้ทางเดียวคือกล่าวหาถูกตอนหลักฐานครบ
    เมื่อกล่าวหาผ่านเงื่อนไขฉากจบแล้ว คดีต้องปิดและไม่รับคำสั่งเพิ่มเติม
    """
    if state.ending_id:
        return False, f"คดีปิดไปแล้วด้วยฉากจบ '{state.ending_id}'"
    return True, ""


def _within_time_limit(cmd, state, world, p):
    # กรอบเวลาเป็นสมบัติของฉาก จึงอยู่ใน story.json ที่เดียว
    # params ใน rules.json ใช้ override ได้ถ้าอยากทดลองค่าอื่นโดยไม่แตะฉาก
    limit = p.get("limit_seconds", world.get("time_limit_seconds", 3600))
    # ใช้เวลาครบพอดีก็คือหมดแล้ว ไม่ใช่ยังเหลืออีกหนึ่งตา
    # เดิมเป็น > ทำให้ตอนนาฬิกาบนหน้าเว็บขึ้น 00:00 กฎยังรับคำสั่งได้อีกหนึ่งครั้ง
    # สองฝั่งจึงบอกผู้เล่นคนละเรื่อง
    if state.elapsed_seconds >= limit:
        return False, f"ใช้เวลาไปแล้ว {state.elapsed_seconds} วินาที จากที่มี {limit} วินาที"
    return True, ""


CHECKERS: Dict[str, Callable] = {
    "visible": _visible,
    "unlock_ready": _unlock_ready,
    "dialogue_available": _dialogue_available,
    "accusable": _accusable,
    "inference_ready": _inference_ready,
    "evidence_source_available": _evidence_source_available,
    "accusation_ready": _accusation_ready,
    "action_is_known": _action_is_known,
    "target_exists": _target_exists,
    "location_exists": _location_exists,
    "suspect_exists": _suspect_exists,
    "in_same_location": _in_same_location,
    "within_time_limit": _within_time_limit,
    "object_supports_action": _object_supports_action,
    "location_accessible": _location_accessible,
    "four_pillars": _four_pillars,
    "game_not_over": _game_not_over,
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
        validate_world(self.rules, self.world, CHECKERS, {a.value for a in ActionType})

    @property
    def max_submitted_evidence(self):
        return self.world.get("max_submitted_evidence", MAX_SUBMITTED_EVIDENCE)

    @property
    def time_limit_seconds(self):
        rule = next((r for r in self.rules if r["check"] == "within_time_limit"), {})
        return rule.get("params", {}).get("limit_seconds", self.world.get("time_limit_seconds", 3600))

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
                if rule["check"] in {"inference_ready", "accusable", "unlock_ready"} and detail:
                    message = detail
                closes = {}
                if rule["id"] == "R000_KNOWN_ACTION" and cmd.action is ActionType.AMBIGUOUS:
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
                    # หมดเวลาไม่ใช่แค่คำสั่งถูกปฏิเสธ แต่คือคดีปิด
                    # เดิมคืนแค่ข้อความฉากจบ ส่วนสถานะไม่ถูกปิด ผู้เล่นจึงยิงคำสั่งต่อได้เรื่อยๆ
                    # แล้วได้ข้อความฉากจบซ้ำทุกครั้ง จึงต้องส่ง ending กลับไปให้บันทึกลงสถานะด้วย
                    timeout = self.ending_for(on_timeout=True)
                    if timeout:
                        message = self._render_ending(timeout, [])
                        closes = {"ending": timeout["id"]}
                elif rule["id"] == "R000_KNOWN_ACTION" and cmd.action is ActionType.UNKNOWN:
                    message += (" สิ่งที่ทำได้คือ ดูรอบๆ เดินไปตู้อื่น "
                                "ตรวจดูของ สอบปากคำคน และกล่าวหาเมื่อมีหลักฐานพอ")
                return Decision(
                    allowed=False,
                    message=message,
                    reasoning_chain=chain,
                    violated_rule_id=rule["id"],
                    state_changes=closes,
                )

        changes = self._state_changes(cmd, state)
        message = self._success_message(cmd, state)
        return Decision(
            allowed=True,
            message=message,
            reasoning_chain=chain,
            violated_rule_id=None,
            state_changes=changes,
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
            # ตรวจคือดู ไม่ใช่เปิด สถานะปลดล็อกได้มาจาก UNLOCK เท่านั้น
            # ไม่งั้นแค่ "ดูกระเป๋า" ก็เปิดกระเป๋าที่ล็อกรหัสได้
            if obj.get("type") == "evidence":
                return {"discovered_evidence_add": cmd.target, "examined_add": cmd.target}
            return {"examined_add": cmd.target}
        if cmd.action in (ActionType.UNLOCK, ActionType.USE):
            return {"unlocked_add": cmd.target}
        if cmd.action == ActionType.INFER:
            return {"validated_claims_add": cmd.target, "claim_evidence": {cmd.target: list(cmd.evidence)}}
        if cmd.action == ActionType.BURN:
            return {"burned_add": cmd.target}
        if cmd.action == ActionType.ACCUSE:
            # ส่ง ID ฉากจบให้ interaction layer บันทึกเพื่อปิดคดี
            return {"ending": self.ending_for(cmd.target, state).get("id")}
        if cmd.action == ActionType.INTERROGATE:
            sus = self.world["suspects"].get(cmd.target, {})
            changes = {"interrogated_add": cmd.target}
            if "dialogue_nodes" in sus:
                node = _dialogue_node(cmd.target, cmd.topic, state, self.world)
                changes["dialogue_history_add"] = f"{cmd.target}:{node['id']}"
                changes["discovered_evidence_add"] = node.get("grants_evidence", [])
                changes["inventory_add"] = node.get("grants_inventory", [])
                return changes
            granted = sus.get("grants_object")
            if granted:
                changes["inventory_add"] = granted
            # คำให้การบางอย่างมีค่าเป็นหลักฐาน เช่นคำประเมินเวลาตายของแพทย์
            # หลักฐานพวกนี้ไม่มีที่อยู่ในโลก ผู้เล่นจึงหาเจอได้ทางเดียวคือถามเจ้าตัว
            if sus.get("grants_evidence"):
                changes["discovered_evidence_add"] = list(sus["grants_evidence"])
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
            lines.append('ตรวจของได้โดยพิมพ์ “ตรวจดู<ชื่อสิ่งของ>” หรือกดปุ่มสำรวจตรงหน้า')
        else:
            lines.append("ตอนนี้ยังไม่มีอะไรในตู้นี้ที่น่าตรวจสอบเพิ่ม")

        # คนที่อยู่ในตู้นี้ — แสดงทุกคนที่อยู่ ไม่ว่าจะสอบปากคำได้แล้วหรือยัง
        # เกมนี้พิมพ์ล้วนไม่มีปุ่ม ถ้าไม่บอกว่ามีใครอยู่ ผู้เล่นจะไม่มีทางรู้ว่าสอบปากคำใครได้
        # ส่วนคนที่ยังสอบไม่ได้ กฎจะเป็นคนบอกเองว่าต้องหาหลักฐานอะไรก่อน
        people = [(sid, s) for sid, s in self.world["suspects"].items()
                  if s.get("location") == loc_id]
        if people:
            entries = []
            for sid, person in people:
                name = person.get("name_th", sid)
                role = f" ({person['role']})" if person.get("role") else ""
                topics = self.dialogue_options(sid, state)
                topic_labels = ", ".join(topic["label"] for topic in topics)
                entry = f"  - {name}{role}"
                if topic_labels:
                    entry += f" — ถามได้: {topic_labels}"
                entries.append(entry)
            who = "\n".join(entries)
            lines.append(f"คนที่อยู่ในตู้นี้:\n{who}")
            lines.append('ถามได้โดยพิมพ์ “สอบปากคำ <ชื่อคน> เรื่อง <หัวข้อ>” หรือสอบปากคำตามชื่อ')
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
            return target in self.world["locations"] or target in self.world["suspects"]
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
            doc_map = {
                "burnt_folder_c": "burnt_memo_fragment.md",
                "secret_file": "liora_project_nocturne.md"
            }
            if cmd.target in doc_map:
                from app.document_loader import load_in_game_document
                return load_in_game_document(doc_map[cmd.target])
            return obj.get("description") or sus.get("description") or f"ตรวจสอบ{name}อย่างละเอียด แต่ไม่พบอะไรเพิ่มเติม"

        if cmd.action == ActionType.INTERROGATE:
            if "dialogue_nodes" in sus:
                return _dialogue_node(cmd.target, cmd.topic, state, self.world)["text"]
            return sus.get("testimony") or f"สอบปากคำ {name} แต่ไม่ได้ข้อมูลเพิ่ม"
        if cmd.action == ActionType.INFER:
            return self.world["claims"][cmd.target].get("feedback_success") or (
                "บันทึกข้อสรุปที่คุณเสนอ: " + self.world["claims"][cmd.target].get("name_th", cmd.target))
        if cmd.action == ActionType.MOVE:
            return self.look_around(cmd.target, state.model_copy(update={"current_location": cmd.target}))
        if cmd.action == ActionType.ACCUSE:
            return self.closing_argument(cmd.target, state)

        templates = {
            ActionType.TAKE: f"เก็บ{name}ไว้เป็นหลักฐาน",
            ActionType.UNLOCK: f"เปิด{name}ได้แล้ว",
            ActionType.USE: f"เปิด{name}ด้วยกุญแจได้แล้ว",
            ActionType.BURN: f"คุณเผา{name}ทิ้ง เถ้าที่เหลือเรียกอะไรกลับมาไม่ได้อีก",
        }
        return templates.get(cmd.action, "ดำเนินการเรียบร้อย")

    def pillars_complete(self, suspect_id: str, state: GameState) -> bool:
        """ผู้ถูกกล่าวหาคนนี้มีหลักฐานครบทุกเสาแล้วหรือยัง"""
        found = _collect_pillars(suspect_id, state, self.world)
        return all(found[p] for p in pillar_names(self.world))

    def dialogue_options(self, suspect_id: str, state: GameState) -> List[dict]:
        person = self.world["suspects"].get(suspect_id, {})
        if person.get("location") != state.current_location or state.ending_id or self.is_out_of_time(state):
            return []
        topics = {}
        for node in _eligible_dialogue(person, state, self.world):
            topic = node.get("topic")
            if topic:
                topics[topic] = {"topic": topic, "label": node.get("label") or node.get("name_th") or topic}
        return list(topics.values())

    def narrative_scene(self, scene_id: str, state: GameState, evidence_scope=None):
        """Return authored pages supported by this knowledge scope, never their gates.

        The interaction layer owns when a scene may be opened (introduction,
        an approved dialogue, or a resolved case). A recap's evidence_scope is
        the submitted case; supplying IDs cannot create knowledge the player lacks.
        """
        scene = self.world.get("narrative_scenes", {}).get(scene_id)
        if scene is None:
            return None
        known = set(state.discovered_evidence)
        if evidence_scope is not None:
            known.intersection_update(evidence_scope)
        scoped = state.model_copy(update={"discovered_evidence": [eid for eid in state.discovered_evidence if eid in known]})
        pages = []
        for page in scene.get("pages", []):
            evidence = page.get("evidence_ids", [])
            if not _requirements_met(page, scoped, self.world) or not set(evidence) <= known:
                continue
            pages.append({field: page[field] for field in ("id", "speaker", "time_label", "text", "art")})
            pages[-1]["evidence"] = [{"id": eid, "name": self.world["objects"][eid]["name_th"]} for eid in evidence]
        return {"id": scene_id, "title": scene["title"], "pages": pages} if pages else None

    def dialogue_scene(self, cmd: ParsedCommand, before_state: GameState):
        """Use the same pre-action node as the spoken text and its exact grants."""
        if cmd.action != ActionType.INTERROGATE or not self.decide(cmd, before_state).allowed:
            return None
        node = _dialogue_node(cmd.target, cmd.topic, before_state, self.world)
        if not node or not node.get("scene_id"):
            return None
        return self.narrative_scene(node["scene_id"], before_state)

    def narrative_followups(self, state: GameState) -> List[dict]:
        """Earned, unread scene topics, including people in another train car."""
        if state.ending_id or self.is_out_of_time(state):
            return []
        followups = []
        for sid, person in self.world["suspects"].items():
            latest = {node["topic"]: node for node in _eligible_dialogue(person, state, self.world)}
            for topic, node in latest.items():
                if not node.get("scene_id") or f"{sid}:{node['id']}" in state.dialogue_history:
                    continue
                if self.narrative_scene(node["scene_id"], state) is None:
                    continue
                followups.append({"person_id": sid, "person_name": person.get("name_th", sid),
                                  "location": person.get("location"), "topic": topic,
                                  "label": node.get("label") or node.get("name_th") or topic})
        return followups

    def inference_questions(self, state: GameState) -> List[dict]:
        if state.ending_id or self.is_out_of_time(state):
            return []
        return [{"id": q["id"], "prompt": q.get("prompt", q.get("question", "")),
                 "choices": [{"id": c["id"], "label": c["label"], "target": c["target"]}
                             for c in q.get("choices", [])]}
                for q in _available_questions(state, self.world)]

    def deductions(self, state: GameState) -> set:
        """ข้อสรุปที่ผู้เล่นมีสิทธิ์สรุปได้ ณ ตอนนี้ ใช้กับ UI และการอธิบาย"""
        return deductions_held(state, self.world)

    def ending_for(self, suspect_id: str = None, state: GameState = None,
                   on_timeout: bool = False) -> dict:
        """เลือกฉากจบจากเงื่อนไขที่เขียนไว้ใน story.json

        ไล่จากบนลงล่างแล้วหยิบอันแรกที่เข้าเงื่อนไข จึงต้องเรียงจากเฉพาะไปกว้าง
        ทุกเงื่อนไขอ่านจาก GameState กับ story.json เท่านั้น ไม่มี LLM เกี่ยวข้อง
        และไม่มีเงื่อนไขไหนเขียนตายในโค้ด เพิ่มฉากจบใหม่จึงไม่ต้องแก้ไฟล์นี้
        """
        endings = self.world.get("endings", {})
        order = self.world.get("ending_order") or list(endings)

        for eid in order:
            e = endings.get(eid)
            if not e:
                continue
            if bool(e.get("on_timeout")) != on_timeout:
                continue
            if on_timeout:
                return {**e, "id": eid}
            if not _ending_matches(e, suspect_id, state, self.world):
                continue
            return {**e, "id": eid}
        return {}

    def _render_ending(self, ending: dict, body: List[str]) -> str:
        head = [f"=== {ending.get('title', 'จบเกม')} ({ending.get('rank', '')}) ===", ""]
        return "\n".join(head + body + ["", ending.get("text", "")])

    def closing_argument(self, suspect_id: str, state: GameState) -> str:
        """คำแถลงปิดคดี ประกอบขึ้นจากหลักฐานที่ผู้เล่นหามาได้จริง

        ส่วนข้อสรุปอ้างหลักฐานใน discovered_evidence ส่วนฉากจบเป็นข้อความจาก world
        แสดงทั้งข้อสรุปที่มีหลักฐานรองรับและรายการที่ยังขาด
        ฉากจบถูกเลือกจากสถานะเดียวกัน แต่ข้อความฉากจบเป็นเนื้อหาที่กำหนดไว้
        """
        sus = self.world["suspects"].get(suspect_id, {})
        found = _collect_pillars(suspect_id, state, self.world)
        names = pillar_names(self.world)
        spec = self.world.get("pillars", {}).get(suspect_id, {})
        rules = self.world.get("deductions", {})

        body = [f"คุณเรียกทุกคนมารวมกัน แล้วชี้ไปที่{sus.get('name_th', suspect_id)}", ""]
        for pillar in names:
            label = self.world.get("pillar_labels", {}).get(pillar, pillar)
            body.append(f"  {label}")
            if found[pillar]:
                for d in found[pillar]:
                    body.append(f"    - {rules.get(d, {}).get('name_th', d)}")
            else:
                need = spec.get(pillar, {}).get("requires_deductions", [])
                if need:
                    miss = [rules.get(d, {}).get("name_th", d) for d in need]
                    body.append(f"    - ยังสรุปไม่ได้ ต้องมี {', '.join(miss)}")
                else:
                    body.append("    - ไม่มีหลักฐานด้านนี้")
        body.append("")
        body.append(f"หลักฐานที่หามาได้ {len(state.discovered_evidence)} ชิ้น "
                    f"สรุปได้ {len(self.deductions(state))} ข้อ "
                    f"เสาครบ {sum(1 for p in names if found[p])} จาก {len(names)} "
                    f"ใช้เวลาไป {state.elapsed_seconds // 60} นาที จาก "
                    f"{self.time_limit_seconds // 60} นาที")
        return self._render_ending(self.ending_for(suspect_id, state), body)

    def seconds_left(self, state: GameState) -> int:
        """เวลาที่เหลือ ติดลบได้ถ้าเลยกำหนดไปแล้ว

        กรอบเวลามีอยู่ในกฎตั้งแต่แรก แต่ไม่มีใครเห็น ผู้เล่นจึงไม่รู้สึกถึงมันเลย
        จนกระทั่งถูกปฏิเสธทุกคำสั่งแบบไม่มีปี่มีขลุ่ย
        """
        return self.time_limit_seconds - state.elapsed_seconds

    def is_out_of_time(self, state: GameState) -> bool:
        """หมดเวลาแล้วหรือยัง ใช้ตัดสินว่าเกมจบ ไม่ใช่ตัดสินว่าคำสั่งผ่านไหม

        เงื่อนไขตรงกับ _within_time_limit เพื่อไม่ให้ UI กับกฎบอกคนละอย่าง
        เหลือศูนย์คือหมดแล้ว เท่ากับที่นาฬิกาบนหน้าเว็บขึ้น 00:00 พอดี
        """
        return self.seconds_left(state) <= 0

    def ending_message(self, state: GameState) -> str:
        """ข้อความปิดเกมกรณีหมดเวลา ดึงจากฉากจบที่ทำเครื่องหมาย on_timeout ไว้

        เดิมเขียนข้อความไว้ในโค้ด ตอนนี้ฉากจบทั้งหมดอยู่ใน story.json แล้ว
        จึงต้องอ่านจากที่เดียวกัน ไม่งั้น UI บนเว็บกับ UI บนเทอร์มินัลจะเล่าตอนจบคนละแบบ
        """
        return self._render_ending(self.ending_for(on_timeout=True), [])

    def pillar_checklist(self, suspect_id: str, state: GameState) -> List[str]:
        """สี่เสาแบบ ✓/✗ บอกเฉพาะข้อสรุปที่ผู้เล่นได้แล้ว ไม่บอกว่าขาดอะไร จึงไม่เฉลย"""
        found = _collect_pillars(suspect_id, state, self.world)
        labels = self.world.get("pillar_labels", {})
        rules = self.world.get("deductions", {})
        return [f"  ✓ {labels.get(p, p)} — {', '.join(rules.get(d, {}).get('name_th', d) for d in found[p])}"
                if found[p] else f"  ✗ {labels.get(p, p)} — หลักฐานที่พบยังพิสูจน์ด้านนี้ไม่ได้"
                for p in pillar_names(self.world)]

    # ใช้สำหรับ UI และการวิเคราะห์ผล ไม่ใช่ส่วนของการตัดสิน
    def pillar_status(self, target: str, state: GameState) -> Dict[str, List[str]]:
        """ความคืบหน้าสี่เสาหลัก — สำหรับ UI และการวิเคราะห์ ไม่ใช่ส่วนของการตัดสิน"""
        return _collect_pillars(target, state, self.world)


def apply_changes(state: GameState, changes: dict) -> GameState:
    """คืน state ใหม่ ไม่แก้ของเดิม เพื่อให้ยิงคำสั่งชุดเดิมซ้ำได้ผลเหมือนกัน

    เวลาเล่นจริงถูกอัปเดตโดย interaction layer การทำคำสั่งไม่เพิ่มเวลาเอง
    """
    s = state.model_copy(deep=True)
    mapping = {
        "inventory_add": s.inventory,
        "discovered_evidence_add": s.discovered_evidence,
        "unlocked_add": s.unlocked_objects,
        "interrogated_add": s.interrogated_suspects,
        "dialogue_history_add": s.dialogue_history,
        "examined_add": s.examined_objects,
        "validated_claims_add": s.validated_claims,
    }
    for key, lst in mapping.items():
        v = changes.get(key)
        if not v:
            continue
        for item in (v if isinstance(v, list) else [v]):
            if item not in lst:
                lst.append(item)
    burned = changes.get("burned_add")
    if burned:
        if burned not in s.burned_objects:
            s.burned_objects.append(burned)
        # ของที่ถูกเผาต้องหลุดจากมือด้วย ไม่งั้นเงื่อนไขฉากจบที่ดูจากของในมือจะเพี้ยน
        if burned in s.inventory:
            s.inventory.remove(burned)
    if changes.get("ending"):
        s.ending_id = changes["ending"]
    if "failed_accusations" in changes:
        s.failed_accusations = changes["failed_accusations"]
    for cid, evidence in changes.get("claim_evidence", {}).items():
        s.claim_evidence[cid] = list(evidence)
    dest = changes.get("move_to")
    if dest:
        s.current_location = dest
        if dest not in s.visited_locations:
            s.visited_locations.append(dest)
    s.turn_count += 1
    return s
