"""
app.profiler.adaptation — ระบบปรับเปลี่ยนการตอบสนองเชิงพลวัต (Dynamic Adaptation Engine)
ปรับเปลี่ยนน้ำเสียงและปฏิกิริยาของ NPC และส่งคำแนะนำช่วยเหลือ (Scaffolding) ตามพฤติกรรมผู้เล่น
โดยไม่ทำลายความถูกต้องของ Symbolic Rules (Sound Logic)
"""

from typing import Any, Dict, Optional, Tuple
from app.schemas import ActionType, Decision, GameState, ParsedCommand
from app.profiler.schemas import PlayerArchetype, PlayerProfile


class DynamicAdaptationEngine:
    """ประเมินและแต่งเติมการตอบสนองของระบบให้ตอบรับกับพฤติกรรมผู้เล่นแบบ Real-time"""

    def adapt_turn(
        self,
        tracker: Any,
        result: Any,
        state: GameState,
        engine: Optional[Any] = None,
        profile: Optional[PlayerProfile] = None,
    ) -> PlayerProfile:
        """ปรับแต่งการตอบสนองและคำแนะนำช่วยเหลือสำหรับเทิร์นปัจจุบันแบบเบ็ดเสร็จ (Encapsulated 100%)

        ซ่อนตรรกะภายในทั้งหมด:
        - คำนวณ recent_violation_count จากประวัติ 3 เทิร์นล่าสุด
        - ตรวจสอบสถานะการวนลูป (is_looping) และ consecutive_looping_count
        - ปรับข้อความและคำแนะนำผ่าน adapt()
        - บันทึก adaptive_note ลงในประวัติเทิร์นล่าสุด
        - เพิ่มตัวนับ tracker.scaffolding_triggers เมื่อเกิด Scaffolding และซิงค์ลงใน profile
        - อัปเดต result.decision และ result.profile
        - คืนค่า PlayerProfile ที่ได้รับการปรับปรุงแล้ว
        """
        if profile is None:
            profile = tracker.get_profile(state)

        # 1. คำนวณจำนวนการละเมิดกฎใน 3 เทิร์นล่าสุด และตรวจสอบการวนลูป
        turns = getattr(tracker, "turns", [])
        recent_violation_count = sum(1 for turn in turns[-3:] if not turn.allowed)
        is_looping = turns[-1].is_looping if turns else False
        consecutive_looping_count = getattr(profile, "consecutive_looping_count", 0)

        # 2. เรียก adapt() เพื่อปรับปรุง Decision และสร้างข้อความคำแนะนำ
        # ท่าทีของ NPC แสดงครั้งเดียวต่อตัวละครต่อสไตล์ผู้เล่น ไม่ซ้ำทุกตาที่ถาม
        shown = getattr(tracker, "shown_reactions", None)
        if shown is None:
            shown = set()
            try:
                tracker.shown_reactions = shown
            except AttributeError:
                pass
        reaction_key = (getattr(result.parsed, "target", None), profile.primary_archetype)
        new_decision, adaptive_note = self.adapt(
            decision=result.decision,
            parsed=result.parsed,
            state=state,
            profile=profile,
            is_looping=is_looping,
            recent_violation_count=recent_violation_count,
            consecutive_looping_count=consecutive_looping_count,
            engine=engine,
            allow_reaction=reaction_key not in shown,
        )
        if adaptive_note and "NPC reaction" in adaptive_note:
            shown.add(reaction_key)
        result.decision = new_decision

        # 3. บันทึก telemetry และอัปเดตตัวนับ Scaffolding Triggers
        if adaptive_note and turns:
            turns[-1].adaptive_note = adaptive_note
        if adaptive_note and ("Scaffolding" in adaptive_note or "Assistance Chip" in adaptive_note):
            tracker.scaffolding_triggers += 1
            profile.scaffolding_trigger_count = tracker.scaffolding_triggers
        elif hasattr(tracker, "scaffolding_triggers"):
            profile.scaffolding_trigger_count = tracker.scaffolding_triggers

        # 4. ซิงค์โปรไฟล์ลงในผลลัพธ์ของคำสั่ง
        if hasattr(result, "profile") and profile is not None:
            result.profile = profile.model_dump() if hasattr(profile, "model_dump") else profile

        return profile

    def adapt(
        self,
        decision: Decision,
        parsed: ParsedCommand,
        state: GameState,
        profile: PlayerProfile,
        is_looping: bool = False,
        recent_violation_count: int = 0,
        consecutive_looping_count: Optional[int] = None,
        engine: Optional[Any] = None,
        allow_reaction: bool = True,
    ) -> Tuple[Decision, Optional[str]]:
        """
        ปรับปรุงข้อความใน Decision ให้มีน้ำเสียงและปฏิกิริยาของตัวละครที่เหมาะสม
        และเพิ่มคำแนะนำ (Scaffolding) หากผู้เล่นพบปัญหาติดขัด:
        - Level 1: Consecutive looping >= 2 หรือทำผิดกฎซ้ำ แสดงข้อความวิเคราะห์/คำแนะนำสืบสวนเชิงตรรกะในกล่องบทสนทนา
        - Level 2: Consecutive looping >= 3 หรือติดซ้ำหลังได้รับคำแนะนำ ส่งชิปคำสั่งช่วยเหลือเจาะจง (Profiler Assistance Chip)
        คืนค่า: (Updated Decision, Adaptive Note หรือ None)
        """
        adapted_message = decision.message
        adaptive_note = None

        # ----------------------------------------------------------------------
        # 1. Dynamic Suspect Dialogue Adaptation (ปรับน้ำเสียงของพยาน/ผู้ต้องสงสัย)
        # ----------------------------------------------------------------------
        if allow_reaction and parsed.action == ActionType.INTERROGATE and decision.allowed and parsed.target:
            reaction = self._get_suspect_reaction(parsed.target, profile, state)
            if reaction:
                adapted_message = f"{reaction}\n\n{adapted_message}"
                adaptive_note = f"NPC reaction adapted for {profile.primary_archetype.value}"

        # ----------------------------------------------------------------------
        # 2. Adaptive Scaffolding (ระดับ 1 & 2)
        # ----------------------------------------------------------------------
        consec_loops = (
            consecutive_looping_count
            if consecutive_looping_count is not None
            else getattr(profile, "consecutive_looping_count", 0)
        )

        scaffold = self._get_scaffolding_nudge(
            decision, parsed, state, profile, is_looping, recent_violation_count, consec_loops
        )
        if scaffold:
            adapted_message = f"{adapted_message}\n\n{scaffold}"
            adaptive_note = (adaptive_note + " | " if adaptive_note else "") + "Scaffolding nudge triggered"

        # Level 2 Scaffolding: เมื่อยังคงติดซ้ำหลังได้รับคำแนะนำ (consec_loops >= 3 หรือ recent_violations >= 3 หรือติดซ้ำหลังมี trigger)
        is_level_2 = (
            (is_looping and consec_loops >= 3)
            or recent_violation_count >= 3
            or (is_looping and consec_loops >= 2 and profile.scaffolding_trigger_count >= 1)
        )

        if is_level_2:
            chip = self.generate_assistance_chip(state, engine, profile)
            profile.assistance_chip = chip
            level2_msg = (
                f"💡 *[คำแนะนำสืบสวนเจาะจงของ Profiler]*: ตรวจพบว่าคุณยังคงวนซ้ำในจุดเดิม "
                f"Profiler ได้สร้างชิปคำสั่งนำทาง [{chip['label']}] บนแถบ Quick Action ให้แล้ว"
            )
            adapted_message = f"{adapted_message}\n\n{level2_msg}"
            adaptive_note = (adaptive_note + " | " if adaptive_note else "") + "Profiler Level 2 Scaffolding Assistance Chip generated"
        else:
            profile.assistance_chip = None

        # สร้าง Decision ใหม่ที่มีข้อความผ่านการ Adapt
        new_decision = Decision(
            allowed=decision.allowed,
            message=adapted_message,
            reasoning_chain=decision.reasoning_chain,
            violated_rule_id=decision.violated_rule_id,
            state_changes=decision.state_changes,
        )
        return new_decision, adaptive_note

    # ท่าทีของ NPC ตามสไตล์ผู้เล่น
    # ทุกคดีใช้ตัวละครชุดเดียวกันแต่คนร้ายต่างกัน ข้อความนี้จึงต้อง
    # - ใช้แค่สิ่งที่คำบรรยายตัวละครใน data บอกไว้ (เช่น กิเดียนถือแก้วน้ำร้อน ลิโอราถือสมุดเล่มเล็ก วินเซนต์มือสั่น)
    # - ไม่ให้ข้อเท็จจริงใหม่ ไม่ให้การแทนพยาน และไม่ขึ้นกับหลักฐานที่ผู้เล่นถือ (ไม่งั้นจะกลายเป็นคำใบ้ว่าใครผิด)
    # - ไม่ข่มขู่หรือพูดจาลึกลับชวนให้สงสัยตัวละครคนใดเป็นพิเศษ
    # ข้อความนี้ต่อหน้าข้อความของเอนจินหลังผู้เล่าเรื่องทำงานแล้ว จึงไม่ผ่านตัวตรวจของผู้เล่า
    SUSPECT_REACTIONS: Dict[str, Dict[PlayerArchetype, str]] = {
        "gideon_hart": {
            PlayerArchetype.FORENSIC_ANALYST:
                "*(กิเดียนวางแก้วน้ำร้อนลงแล้วหันมาหาคุณเต็มตัว)* "
                "\"คุณจดทุกอย่างละเอียดดีนะครับ ถามมาได้เลย\"",
            PlayerArchetype.MAVERICK_TRAILBLAZER:
                "*(กิเดียนเลิกคิ้วเล็กน้อย แล้วพูดช้าๆ ตามแบบของเขา)* "
                "\"ใจเย็นสักนิดครับ เราทำงานสายเดียวกัน ไล่ไปทีละเรื่องดีกว่า\"",
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                "*(กิเดียนยกแก้วน้ำร้อนขึ้นจิบช้าๆ ก่อนตอบ)* "
                "\"คุณอยากรู้ว่าผมคิดอะไรอยู่สินะครับ ถามตรงๆ ได้เลย\"",
            PlayerArchetype.INTUITIVE_RUSHER:
                "*(กิเดียนยกมือขึ้นเบาๆ ให้คุณชะลอ)* "
                "\"ทีละคำถามครับ คุณเจ้าหน้าที่\"",
            PlayerArchetype.BALANCED_INVESTIGATOR:
                "*(กิเดียนสบตาคุณด้วยท่าทีสุขุมระมัดระวังถ้อยคำตามแบบฉบับเจ้าหน้าที่ส่วนกลาง)* "
                "\"มีเรื่องอะไรจะถามผมหรือครับคุณเจ้าหน้าที่?\"",
        },
        "dr_liora_venn": {
            PlayerArchetype.FORENSIC_ANALYST:
                "*(ดร.ลิโอราเปิดสมุดบันทึกเล่มเล็กเตรียมไว้)* "
                "\"ถ้าคุณอยากได้ข้อเท็จจริงทางการแพทย์ ฉันพร้อมตอบค่ะ\"",
            PlayerArchetype.MAVERICK_TRAILBLAZER:
                "*(ดร.ลิโอราถอยไปครึ่งก้าว กำสมุดบันทึกเล่มเล็กไว้แน่น)* "
                "\"ค่อยๆ พูดได้ไหมคะ ฉันตอบให้ได้ค่ะ\"",
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                "*(ดร.ลิโอราสบตาคุณครู่หนึ่ง)* "
                "\"ขอบคุณที่ถามอย่างใจเย็นนะคะ\"",
            PlayerArchetype.INTUITIVE_RUSHER:
                "*(ดร.ลิโอรากะพริบตาถี่ๆ เมื่อเห็นคุณรีบร้อนซักถาม)* "
                "\"ใจเย็นๆ ก่อนนะคะคุณเจ้าหน้าที่ ถามทีละเรื่องดีกว่าค่ะ\"",
            PlayerArchetype.BALANCED_INVESTIGATOR:
                "*(ดร.ลิโอราพยักหน้ารับอย่างสุภาพ)* "
                "\"ฉันพร้อมตอบสิ่งที่เป็นประโยชน์ต่อการตรวจคดีค่ะ\"",
        },
        "vincent_gray": {
            PlayerArchetype.FORENSIC_ANALYST:
                "*(วินเซนต์เหลือบมองสายตาของคุณแล้วสะบัดหน้าหนีอย่างรำคาญ)* "
                "\"คุณมองผมเหมือนกำลังใช้แว่นขยายส่องเลยนะ... ถามมาเถอะ\"",
            PlayerArchetype.MAVERICK_TRAILBLAZER:
                "*(วินเซนต์ขยับไปพิงผนัง มือยังสั่นเล็กน้อย)* "
                "\"ถามมาเถอะ ไม่ต้องตะคอกก็ได้\"",
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                "*(วินเซนต์สอดมือที่สั่นเข้ากระเป๋าโค้ต สีหน้าอ่อนลงเล็กน้อย)* "
                "\"คุณพูดจาดีนี่เจ้าหน้าที่... ถามมาเถอะ\"",
            PlayerArchetype.INTUITIVE_RUSHER:
                "*(วินเซนต์ยกมือห้ามอย่างเหนื่อยหน่าย)* "
                "\"เฮ้ยๆ ถามเร็วจังวะคุณ... ใจเย็นก่อน ผมไม่ใช่เครื่องจักรนะ\"",
            PlayerArchetype.BALANCED_INVESTIGATOR:
                "*(วินเซนต์เหลือบมองคุณอย่างหยั่งเชิง ก่อนจะตอบอย่างระวังตัว)* "
                "\"จะถามอะไรก็ถามมาเถอะครับ\"",
        },
        "car_attendant": {
            PlayerArchetype.FORENSIC_ANALYST:
                "*(พนักงานตรวจตู้หยิบสมุดบันทึกขึ้นมาเปิดเทียบ)* "
                "\"ยินดีให้ความร่วมมือครับคุณเจ้าหน้าที่\"",
            PlayerArchetype.MAVERICK_TRAILBLAZER:
                "*(พนักงานตรวจตู้มองคุณด้วยความระแวงเล็กน้อย)* "
                "\"เอ่อ... ถามได้ครับ แต่กรุณาอย่าทำลายทรัพย์สินของรถไฟนะครับ\"",
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                "*(พนักงานตรวจตู้ถอนหายใจยาวก่อนจะเล่า)* "
                "\"คืนนี้วุ่นวายจริงๆ ครับคุณผู้สืบสวน\"",
            PlayerArchetype.INTUITIVE_RUSHER:
                "*(พนักงานตรวจตู้สะดุ้งเล็กน้อยกับคำถามที่โพล่งออกมา)* "
                "\"ใจเย็นๆ ครับท่าน!\"",
            PlayerArchetype.BALANCED_INVESTIGATOR:
                "*(พนักงานตรวจตู้ยืนตัวตรงและตอบคำถามด้วยความเคารพ)* "
                "\"สอบถามได้เลยครับ\"",
        },
        "patient_witness": {
            PlayerArchetype.FORENSIC_ANALYST:
                "*(ผู้ป่วยขยับตัวช้าๆ สีหน้ายังซีดเซียว)* "
                "\"ถามได้ครับ ผมจะตอบเท่าที่จำได้\"",
            PlayerArchetype.MAVERICK_TRAILBLAZER:
                "*(ผู้ป่วยสะดุ้งและไอเบาๆ)* "
                "\"อย่าเสียงดังเลยครับ ผมยังเวียนหัวอยู่...\"",
            PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                "*(ผู้ป่วยสบตาคุณด้วยความรู้สึกขอบคุณ)* "
                "\"ขอบคุณที่ถามอาการผมก่อนนะครับ\"",
            PlayerArchetype.INTUITIVE_RUSHER:
                "*(ผู้ป่วยกุมขมับ)* "
                "\"อย่าเพิ่งรัวคำถามใส่ผมเลยครับ... หัวผมยังตื้อๆ อยู่\"",
            PlayerArchetype.BALANCED_INVESTIGATOR:
                "*(ผู้ป่วยพยุงตัวขึ้นนั่งเล็กน้อย)* "
                "\"มีอะไรที่ผมพอจะช่วยได้บ้างครับ?\"",
        },
    }

    def _get_suspect_reaction(
        self, target: str, profile: PlayerProfile, state: GameState
    ) -> Optional[str]:
        """ท่าทีของตัวละครตามสไตล์ของผู้เล่น ไม่ขึ้นกับหลักฐานหรือคดี (ดู SUSPECT_REACTIONS)"""
        return self.SUSPECT_REACTIONS.get(target, {}).get(profile.primary_archetype)

    def _get_scaffolding_nudge(
        self,
        decision: Decision,
        parsed: ParsedCommand,
        state: GameState,
        profile: PlayerProfile,
        is_looping: bool,
        recent_violation_count: int,
        consecutive_looping_count: Optional[int] = None,
    ) -> Optional[str]:
        """ให้คำแนะนำเชิงบริบท (Contextual Scaffolding Nudge) เมื่อระบบตรวจพบว่าผู้เล่นเริ่มติดขัด"""

        # 1. ผู้เล่นทำผิดกฎเรื่องระยะทางติดต่อกัน (พยายามสั่งตรวจของข้ามตู้รถ)
        if not decision.allowed and decision.violated_rule_id == "R007_SAME_LOCATION":
            if recent_violation_count >= 2:
                return (
                    "💡 *[ข้อสังเกตของผู้สืบสวน]*: ขบวนรถไฟแบ่งพื้นที่ออกเป็นตู้โดยสารหลายตู้ "
                    "หากต้องการตรวจสิ่งของหรือคุยกับบุคคล ควรใช้คำสั่ง 'เดินไปที่...' ก่อน"
                )

        # 2. ผู้เล่นพยายามใช้คำสั่งที่ไม่รองรับ (เช่น take, use, burn ใส่ของที่ห้ามหยิบ)
        if not decision.allowed and decision.violated_rule_id == "R010_ACTION_SUPPORTED":
            return (
                "💡 *[ข้อสังเกตของผู้สืบสวน]*: วัตถุชิ้นนี้เป็นพยานหลักฐานที่ไม่ควรเคลื่อนย้ายหรือแตะต้อง "
                "การ 'ตรวจดู' รายละเอียด หรือสอบถามพยานที่เกี่ยวข้อง จะให้ข้อมูลที่เป็นประโยชน์มากกว่า"
            )

        # 3. ผู้เล่นเดินวนซ้ำในตู้เดิมๆ หรือตรวจสิ่งเดิมซ้ำติดต่อกัน (Consecutive Looping)
        consec_loops = (
            consecutive_looping_count
            if consecutive_looping_count is not None
            else getattr(profile, "consecutive_looping_count", 0)
        )
        if is_looping and consec_loops >= 2:
            return (
                "💡 *[ข้อสังเกตของผู้สืบสวน]*: คุณตรวจสอบบริเวณนี้อย่างถี่ถ้วนแล้ว "
                "ลองสำรวจตู้โดยสารอื่นๆ ที่ยังไม่เคยไป เช่น ตู้สัมภาระ ตู้เสบียง หรือตู้พักพนักงานเพื่อหาเบาะแสใหม่"
            )

        # 4. ผู้เล่นพยายามกล่าวหา (accuse) แต่หลักฐานยังห่างไกล
        if not decision.allowed and decision.violated_rule_id == "R015_ACCUSE_ENDING_REQUIREMENTS":
            return (
                "💡 *[ข้อสังเกตของผู้สืบสวน]*: ตรวจรายการเงื่อนไขที่ยังขาดของคดีนี้ในข้อความด้านบน "
                "เปิดแฟ้มสืบสวนเพื่อทบทวนหลักฐานและไทม์ไลน์ แล้วค้นข้อมูลหรือสอบถามพยานเพิ่มเติม"
            )

        return None

    def generate_assistance_chip(
        self,
        state: GameState,
        engine: Optional[Any] = None,
        profile: Optional[PlayerProfile] = None,
    ) -> Dict[str, str]:
        """สร้างชิปคำสั่งช่วยเหลือเจาะจง (Profiler Assistance Chip) ตามบริบทสถานการณ์ปัจจุบัน"""
        if engine is None:
            try:
                from app.cases import get_engine
                engine = get_engine(getattr(state, "case_id", None) or "case_01_gideon")
            except Exception:
                engine = None

        if engine and hasattr(engine, "world"):
            w = engine.world
            cur_loc = state.current_location

            # 1. หาสิ่งของที่ยังไม่ได้ตรวจในห้องปัจจุบัน
            unexamined_objs = [
                (oid, obj)
                for oid, obj in w.get("objects", {}).items()
                if obj.get("location") == cur_loc
                and oid not in state.discovered_evidence
                and oid not in state.examined_objects
                and (not hasattr(engine, "offerable") or engine.offerable(oid, state))
            ]
            if unexamined_objs:
                oid, obj = unexamined_objs[0]
                obj_name = obj.get("name_th", oid)
                return {
                    "command": f"ตรวจ{obj_name}",
                    "label": f"Profiler แนะนำ: ตรวจ{obj_name}",
                }

            # 2. หาบุคคลที่อยู่ในห้องปัจจุบัน
            suspects_here = [
                (sid, sus)
                for sid, sus in w.get("suspects", {}).items()
                if sus.get("location") == cur_loc
            ]
            if suspects_here:
                sid, sus = suspects_here[0]
                sus_name = sus.get("name_th", sid).split(" (")[0]
                # ถ้ายังไม่เคยสอบปากคำ
                if sid not in state.interrogated_suspects:
                    return {
                        "command": f"สอบปากคำ {sus_name}",
                        "label": f"Profiler แนะนำ: สอบปากคำ {sus_name}",
                    }
                # ถ้าเคยแล้วแต่ยังมีหัวข้อคุย
                if hasattr(engine, "dialogue_options"):
                    topics = engine.dialogue_options(sid, state)
                    if topics:
                        t = topics[0]
                        return {
                            "command": f"ถาม{sus_name} เรื่อง{t['label']}",
                            "label": f"Profiler แนะนำ: ถาม {sus_name} เรื่อง{t['label']}",
                        }

            # 3. แนะนำเดินไปตู้ที่ยังไม่เคยไป
            visited = set(state.visited_locations or [cur_loc])
            unvisited_locs = [
                (lid, loc)
                for lid, loc in w.get("locations", {}).items()
                if lid not in visited
            ]
            if unvisited_locs:
                lid, loc = unvisited_locs[0]
                loc_clean = loc.get("name_th", lid).split(" (")[0]
                return {
                    "command": f"ไปที่ {lid}",
                    "label": f"Profiler แนะนำ: เดินไป {loc_clean}",
                }

        return {
            "command": "ดูรอบๆ",
            "label": "Profiler แนะนำ: ดูรอบๆ",
        }
