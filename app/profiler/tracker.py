"""
app.profiler.tracker — คำนวณและประมวลผลพฤติกรรมผู้เล่น (Behavior Tracker)
รวบรวม Telemetry รายเทิร์น และจัดหมวดหมู่ Archetype แบบ Real-time
"""

import math
import time
import uuid
from typing import Dict, List, Optional, Any

from app.schemas import ActionType, Decision, GameState, ParsedCommand
from app.profiler.schemas import (
    ARCHETYPE_METADATA,
    ArchetypeScores,
    PlayerArchetype,
    PlayerProfile,
    PlaystyleDimensions,
    SessionSummary,
    TurnTelemetry,
)


class BehaviorTracker:
    """ตัวติดตามและคำนวณพฤติกรรมผู้เล่นแบบ Real-time"""

    def __init__(self, session_id: Optional[str] = None, total_locations: int = 6, total_evidence: int = 34):
        self.session_id: str = session_id or str(uuid.uuid4())[:8]
        self.started_at: float = time.time()
        self.total_locations: int = total_locations
        self.total_evidence: int = total_evidence

        self.turns: List[TurnTelemetry] = []
        self.action_counts: Dict[str, int] = {}
        self.violated_rules_counts: Dict[str, int] = {}
        self.recent_actions: List[Dict[str, Any]] = []  # เก็บ 5 ตาล่าสุดเพื่อจับลูป
        self.scaffolding_triggers: int = 0

    def record_turn(
        self,
        raw_input: str,
        parsed: ParsedCommand,
        decision: Decision,
        state: GameState,
        pillars_status: Optional[Dict[str, Any]] = None,
        adaptive_note: Optional[str] = None,
    ) -> PlayerProfile:
        """บันทึกข้อมูลคำสั่งและอัปเดตสถิติพฤติกรรมผู้เล่นทันทีในแต่ละเทิร์น"""
        turn_id = len(self.turns) + 1
        now = time.time()
        action_name = parsed.action.value if hasattr(parsed.action, "value") else str(parsed.action)

        # 1. ตรวจจับการวนลูป (Looping Detection)
        # ผู้เล่นสั่งสิ่งเดิมซ้ำๆ หรือเดินสลับไปมาระหว่างสองตู้เดิมโดยไม่เกิดความคืบหน้า
        current_sig = {
            "action": action_name,
            "target": parsed.target,
            "topic": getattr(parsed, "topic", None),
            "code": getattr(parsed, "code", None),
            "location": state.current_location,
            "allowed": decision.allowed,
        }
        is_looping = self._check_is_looping(current_sig)
        self.recent_actions.append(current_sig)
        if len(self.recent_actions) > 6:
            self.recent_actions.pop(0)

        # 2. บันทึกสถิตินับจำนวน
        self.action_counts[action_name] = self.action_counts.get(action_name, 0) + 1
        if not decision.allowed and decision.violated_rule_id:
            self.violated_rules_counts[decision.violated_rule_id] = (
                self.violated_rules_counts.get(decision.violated_rule_id, 0) + 1
            )

        if adaptive_note:
            self.scaffolding_triggers += 1

        # 3. คำนวณจำนวนเสาที่ปลดล็อกแล้ว (ถ้ามีข้อมูล)
        pillars_count = 0
        pillars_fulfilled_map = {}
        if pillars_status:
            for suspect_id, p_dict in pillars_status.items():
                if isinstance(p_dict, dict):
                    for pillar_name, deductions in p_dict.items():
                        is_ok = bool(deductions)
                        key = f"{suspect_id}_{pillar_name}"
                        pillars_fulfilled_map[key] = is_ok
                        if is_ok:
                            pillars_count += 1

        prompt_tokens = getattr(parsed, "prompt_tokens", 0) or 0
        completion_tokens = getattr(parsed, "completion_tokens", 0) or 0
        latency_ms = getattr(parsed, "latency_ms", 0.0) or 0.0
        parser_mode = getattr(parsed, "parser_mode", "typed") or "typed"

        # 4. บันทึก Telemetry
        telemetry = TurnTelemetry(
            turn_id=turn_id,
            timestamp=now,
            elapsed_seconds=state.elapsed_seconds,
            raw_input=raw_input,
            action=action_name,
            target=parsed.target,
            allowed=decision.allowed,
            violated_rule_id=decision.violated_rule_id,
            location=state.current_location,
            evidence_count=len(state.discovered_evidence),
            inventory_count=len(state.inventory),
            pillars_count=pillars_count,
            is_looping=is_looping,
            adaptive_note=adaptive_note,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            parser_mode=parser_mode,
        )
        self.turns.append(telemetry)

        # 5. คำนวณ Dimensions และ Archetype Scores
        return self.get_profile(state, pillars_status=pillars_status)

    def get_profile(
        self,
        state: GameState,
        pillars_status: Optional[Dict[str, Any]] = None,
    ) -> PlayerProfile:
        pillars_fulfilled_map: Dict[str, bool] = {}
        if pillars_status:
            for suspect_id, p_info in pillars_status.items():
                if isinstance(p_info, dict):
                    for pillar_name, deductions in p_info.items():
                        key = f"{suspect_id}_{pillar_name}"
                        pillars_fulfilled_map[key] = bool(deductions)

        dimensions = self._calculate_dimensions(state)
        scores, primary = self._classify_archetype(dimensions, state)

        meta = ARCHETYPE_METADATA.get(primary, ARCHETYPE_METADATA[PlayerArchetype.BALANCED_INVESTIGATOR])

        total_t = len(self.turns)
        allowed_t = sum(1 for t in self.turns if t.allowed)
        denied_t = total_t - allowed_t
        violation_rate = (denied_t / total_t) if total_t > 0 else 0.0

        examine_count = self.action_counts.get(ActionType.EXAMINE.value, 0)
        clue_eff = (len(state.discovered_evidence) / examine_count) if examine_count > 0 else 0.0

        consec_looping = 0
        for t in reversed(self.turns):
            if t.is_looping:
                consec_looping += 1
            else:
                break

        return PlayerProfile(
            session_id=self.session_id,
            primary_archetype=primary,
            archetype_name_th=meta["name_th"],
            archetype_badge=meta["badge"],
            archetype_description_th=meta["description_th"],
            scores=scores,
            dimensions=dimensions,
            total_turns=total_t,
            allowed_turns=allowed_t,
            denied_turns=denied_t,
            rule_violation_rate=round(violation_rate, 4),
            clue_efficiency=round(clue_eff, 4),
            looping_count=sum(1 for t in self.turns if t.is_looping),
            consecutive_looping_count=consec_looping,
            scaffolding_trigger_count=self.scaffolding_triggers,
            pillars_fulfilled=pillars_fulfilled_map,
            ending_id=state.ending_id,
        )

    update_profile = get_profile

    def _check_is_looping(self, current: Dict[str, Any]) -> bool:
        """ตรวจหาพฤติกรรมวนซ้ำ เช่น สั่งเดิมติดต่อกัน 2 ครั้งขึ้นไป หรือสลับที่เดิม"""
        if not self.recent_actions:
            return False

        # ซ้ำคำสั่งเดิมเป๊ะ (action, target, topic, code ตรงกัน)
        prev = self.recent_actions[-1]
        if (
            prev["action"] == current["action"]
            and prev["target"] == current["target"]
            and prev.get("topic") == current.get("topic")
            and prev.get("code") == current.get("code")
        ):
            return True

        # วนสลับสถานที่แบบไปกลับ A -> B -> A -> B (เดินสลับตู้ซ้ำๆ 4 ตาติดต่อกันโดยไม่ทำอะไร)
        if len(self.recent_actions) >= 3 and current["action"] == ActionType.MOVE.value:
            r1 = self.recent_actions[-1]
            r2 = self.recent_actions[-2]
            r3 = self.recent_actions[-3]
            if (
                r1.get("action") == ActionType.MOVE.value
                and r2.get("action") == ActionType.MOVE.value
                and r3.get("action") == ActionType.MOVE.value
                and r3.get("target") == r1.get("target")
                and r2.get("target") == current.get("target")
                and r1.get("target") != current.get("target")
            ):
                return True

        return False

    def _calculate_dimensions(self, state: GameState) -> PlaystyleDimensions:
        """คำนวณคะแนน 5 มิติ (0.0 - 1.0) สำหรับการวิเคราะห์พฤติกรรม"""
        total = len(self.turns)
        if total == 0:
            return PlaystyleDimensions()

        examine_c = self.action_counts.get(ActionType.EXAMINE.value, 0)
        interrogate_c = self.action_counts.get(ActionType.INTERROGATE.value, 0)
        denied_c = sum(1 for t in self.turns if not t.allowed)

        # 1. Methodical: สัดส่วนการ examine และการเจอหลักฐาน
        methodical = min(1.0, (examine_c / total) * 1.5)

        # 2. Social: สัดส่วนการ interrogate และความหลากหลายของผู้ต้องสงสัยที่คุย
        unique_suspects = len(set(state.interrogated_suspects))
        social = min(1.0, ((interrogate_c / total) * 1.5) + (unique_suspects * 0.15))

        # 3. Caution: ความเคารพกฎและสุขุมรอบคอบ (ยิ่งทำผิดกฎบ่อย ยิ่งคะแนนต่ำ)
        violation_rate = (denied_c / total)
        caution = max(0.0, min(1.0, 1.0 - (violation_rate * 1.5)))

        # 4. Curiosity: ความครอบคลุมในการสำรวจ (สถานที่ที่ไป + สัดส่วนหลักฐานที่พบ)
        loc_ratio = len(state.visited_locations) / max(1, self.total_locations)
        evi_ratio = len(state.discovered_evidence) / max(1, self.total_evidence)
        curiosity = min(1.0, (loc_ratio * 0.4) + (evi_ratio * 0.6))

        # 5. Decisiveness: ความต่อเนื่องและความรวดเร็วในการก้าวหน้า
        # คำนวณจากการบรรลุหลักฐานต่อจำนวนเทิร์น (ความแม่นยำ ไม่เสียเทิร์นเปล่า)
        efficiency = len(state.discovered_evidence) / max(1, total)
        decisiveness = min(1.0, efficiency * 2.0)

        return PlaystyleDimensions(
            methodical_score=round(methodical, 3),
            social_score=round(social, 3),
            caution_score=round(caution, 3),
            curiosity_score=round(curiosity, 3),
            decisiveness_score=round(decisiveness, 3),
        )

    def _classify_archetype(
        self, d: PlaystyleDimensions, state: GameState
    ) -> tuple[ArchetypeScores, PlayerArchetype]:
        """ประเมินและจัดกลุ่มผู้เล่นเข้าสู่ Archetype ด้วยสถาปัตยกรรม Vector Space Centroid Classifier & Softmax Probability

        หลักการ Machine Learning:
        1. แมปค่ามิติพฤติกรรม 5 มิติลงในพื้นที่เวกเตอร์ x = [m, s, c, u, d] in R^5
        2. คำนวณ Cosine Similarity เทียบกับพิกัดอุดมคติของแต่ละ Archetype (Ideal Archetype Centroids)
        3. ปรับปรุงคะแนนด้วย Dynamic Behavioral Priors (เช่น การเผาทำลายหลักฐาน, การด่วนกล่าวหา)
        4. แปลงเวกเตอร์ความคล้ายคลึงให้อยู่ในรูปการกระจายความน่าจะเป็น (Probability Distribution) ด้วย Softmax Temperature Scaling
        """
        # พิกัด Ideal Centroids ใน 5 มิติ [Methodical, Social, Caution, Curiosity, Decisiveness]
        centroids: Dict[PlayerArchetype, List[float]] = {
            PlayerArchetype.FORENSIC_ANALYST:          [0.85, 0.15, 0.90, 0.50, 0.50],
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:[0.20, 0.90, 0.70, 0.60, 0.35],
            PlayerArchetype.MAVERICK_TRAILBLAZER:      [0.25, 0.25, 0.10, 0.70, 0.50],
            PlayerArchetype.INTUITIVE_RUSHER:          [0.10, 0.15, 0.30, 0.20, 0.95],
            PlayerArchetype.BALANCED_INVESTIGATOR:     [0.50, 0.50, 0.50, 0.50, 0.50],
        }

        x = [d.methodical_score, d.social_score, d.caution_score, d.curiosity_score, d.decisiveness_score]
        norm_x = math.sqrt(sum(v * v for v in x))

        if norm_x < 1e-5:
            scores = ArchetypeScores(forensic=0.2, interrogator=0.2, maverick=0.2, rusher=0.2, balanced=0.2)
            return scores, PlayerArchetype.BALANCED_INVESTIGATOR

        # คำนวณ Cosine Similarity เทียบกับทุกลักษณะ
        sims: Dict[PlayerArchetype, float] = {}
        for arch, centroid in centroids.items():
            norm_c = math.sqrt(sum(v * v for v in centroid))
            cosine_sim = sum(a * b for a, b in zip(x, centroid)) / (norm_x * norm_c)
            sims[arch] = cosine_sim

        # ปรับคะแนนด้วย Dynamic Context Priors (พฤติกรรมเฉพาะที่ชัดเจน)
        if len(state.burned_objects) > 0 or d.caution_score < 0.25:
            sims[PlayerArchetype.MAVERICK_TRAILBLAZER] += 0.40

        is_early_accuse = (self.action_counts.get(ActionType.ACCUSE.value, 0) > 0 and len(state.discovered_evidence) < 5)
        if is_early_accuse or (d.decisiveness_score > 0.85 and d.methodical_score < 0.4):
            sims[PlayerArchetype.INTUITIVE_RUSHER] += 0.35

        # ปรับความสมดุล (Balanced Indicator)
        diff = max(
            abs(d.methodical_score - d.social_score),
            abs(d.methodical_score - d.caution_score),
        )
        if diff < 0.20:
            sims[PlayerArchetype.BALANCED_INVESTIGATOR] += 0.25

        # Softmax Normalization (Temperature tau = 0.15 สำหรับแยกแยะคลาสอย่างเด่นชัด)
        tau = 0.15
        max_z = max(v / tau for v in sims.values())
        exp_z = {k: math.exp((v / tau) - max_z) for k, v in sims.items()}
        sum_exp = sum(exp_z.values())
        probs = {k: round(v / sum_exp, 3) for k, v in exp_z.items()}

        scores = ArchetypeScores(
            forensic=probs[PlayerArchetype.FORENSIC_ANALYST],
            interrogator=probs[PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR],
            maverick=probs[PlayerArchetype.MAVERICK_TRAILBLAZER],
            rusher=probs[PlayerArchetype.INTUITIVE_RUSHER],
            balanced=probs[PlayerArchetype.BALANCED_INVESTIGATOR],
        )

        best_archetype, best_prob = max(probs.items(), key=lambda item: item[1])
        if best_prob < 0.28:
            best_archetype = PlayerArchetype.BALANCED_INVESTIGATOR

        return scores, best_archetype

    def get_summary(self, state: GameState) -> SessionSummary:
        """สร้างข้อมูลสรุปการเล่นทั้ง Session สำหรับบันทึกงานวิจัย"""
        now = time.time()
        dims = self._calculate_dimensions(state)
        scores, primary = self._classify_archetype(dims, state)

        total_t = len(self.turns)
        allowed_t = sum(1 for t in self.turns if t.allowed)
        denied_t = total_t - allowed_t
        violation_rate = (denied_t / total_t) if total_t > 0 else 0.0

        examine_c = self.action_counts.get(ActionType.EXAMINE.value, 0)
        clue_eff = (len(state.discovered_evidence) / examine_c) if examine_c > 0 else 0.0

        is_solved = (state.ending_id in ("true_ending", "ending_true_justice"))

        total_p_tokens = sum(t.prompt_tokens for t in self.turns)
        total_c_tokens = sum(t.completion_tokens for t in self.turns)
        neural_latencies = [t.latency_ms for t in self.turns if t.parser_mode != "typed" and t.latency_ms > 0]
        avg_neural_lat = round(sum(neural_latencies) / len(neural_latencies), 2) if neural_latencies else 0.0

        return SessionSummary(
            session_id=self.session_id,
            started_at=self.started_at,
            ended_at=now,
            total_duration_seconds=int(now - self.started_at),
            total_turns=total_t,
            allowed_turns=allowed_t,
            denied_turns=denied_t,
            rule_violation_rate=round(violation_rate, 4),
            clue_discovery_efficiency=round(clue_eff, 4),
            evidence_discovered_count=len(state.discovered_evidence),
            primary_archetype=primary.value,
            dimensions=dims.model_dump(),
            archetype_scores=scores.model_dump(),
            scaffolding_count=self.scaffolding_triggers,
            total_prompt_tokens=total_p_tokens,
            total_completion_tokens=total_c_tokens,
            avg_neural_latency_ms=avg_neural_lat,
            final_ending_id=state.ending_id,
            case_solved_successfully=is_solved,
            turn_history=self.turns,
        )
