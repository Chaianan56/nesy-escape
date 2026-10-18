"""
app.profiler.adaptation — ระบบปรับเปลี่ยนการตอบสนองเชิงพลวัต (Dynamic Adaptation Engine)
ปรับเปลี่ยนน้ำเสียงและปฏิกิริยาของ NPC และส่งคำแนะนำช่วยเหลือ (Scaffolding) ตามพฤติกรรมผู้เล่น
โดยไม่ทำลายความถูกต้องของ Symbolic Rules (Sound Logic)
"""

from typing import Optional, Tuple
from app.schemas import ActionType, Decision, GameState, ParsedCommand
from app.profiler.schemas import PlayerArchetype, PlayerProfile


class DynamicAdaptationEngine:
    """ประเมินและแต่งเติมการตอบสนองของระบบให้ตอบรับกับพฤติกรรมผู้เล่นแบบ Real-time"""

    def adapt(
        self,
        decision: Decision,
        parsed: ParsedCommand,
        state: GameState,
        profile: PlayerProfile,
        is_looping: bool = False,
        recent_violation_count: int = 0,
        consecutive_looping_count: Optional[int] = None,
    ) -> Tuple[Decision, Optional[str]]:
        """
        ปรับปรุงข้อความใน Decision ให้มีน้ำเสียงและปฏิกิริยาของตัวละครที่เหมาะสม
        และเพิ่มคำแนะนำ (Scaffolding) หากผู้เล่นพบปัญหาติดขัด
        คืนค่า: (Updated Decision, Adaptive Note หรือ None)
        """
        adapted_message = decision.message
        adaptive_note = None

        # ----------------------------------------------------------------------
        # 1. Dynamic Suspect Dialogue Adaptation (ปรับน้ำเสียงของพยาน/ผู้ต้องสงสัย)
        # ----------------------------------------------------------------------
        if parsed.action == ActionType.INTERROGATE and decision.allowed and parsed.target:
            reaction = self._get_suspect_reaction(parsed.target, profile, state)
            if reaction:
                adapted_message = f"{reaction}\n\n{adapted_message}"
                adaptive_note = f"NPC reaction adapted for {profile.primary_archetype.value}"

        # ----------------------------------------------------------------------
        # 2. Adaptive Scaffolding (ระบบให้คำแนะนำเมื่อติดหล่ม หรือทำผิดกฎซ้ำๆ)
        # ----------------------------------------------------------------------
        scaffold = self._get_scaffolding_nudge(
            decision, parsed, state, profile, is_looping, recent_violation_count, consecutive_looping_count
        )
        if scaffold:
            adapted_message = f"{adapted_message}\n\n{scaffold}"
            adaptive_note = (adaptive_note + " | " if adaptive_note else "") + "Scaffolding nudge triggered"

        # สร้าง Decision ใหม่ที่มีข้อความผ่านการ Adapt
        new_decision = Decision(
            allowed=decision.allowed,
            message=adapted_message,
            reasoning_chain=decision.reasoning_chain,
            violated_rule_id=decision.violated_rule_id,
            state_changes=decision.state_changes,
        )
        return new_decision, adaptive_note

    def _get_suspect_reaction(
        self, target: str, profile: PlayerProfile, state: GameState
    ) -> Optional[str]:
        """สร้างคำบรรยายท่าทีและน้ำเสียงตอบรับเฉพาะตัวละครตาม Archetype ของผู้เล่น"""
        archetype = profile.primary_archetype

        # ======================================================================
        # กิเดียน ฮาร์ต (Gideon Hart) — ทายาทตระกูลอิทธิพล สุขุม เย่อหยิ่ง กุมความลับ
        # ======================================================================
        if target == "gideon_hart":
            # หากผู้เล่นถือหลักฐานมัดตัว (เช่น กระดุม หรือ เศษแฟ้ม C) กิเดียนจะระแวงขึ้นทันที
            has_incriminating = any(
                c in state.discovered_evidence
                for c in ["obsidian_cufflink", "burnt_folder_c", "wax_seal_imprint"]
            )
            if has_incriminating or archetype == PlayerArchetype.FORENSIC_ANALYST:
                return (
                    "*(กิเดียนชะงักไปเล็กน้อย สายตาของเขาจ้องมองคุณอย่างระแวดระวัง "
                    "มือขวากุมแหวนตราประจำตระกูลแน่นขึ้นเมื่อสังเกตเห็นความคมกริบของพยานหลักฐานที่คุณถือ)*"
                )
            if archetype == PlayerArchetype.MAVERICK_TRAILBLAZER:
                return (
                    "*(กิเดียนยิ้มมุมปากอย่างเยือกเย็นและปรายตามองคุณด้วยความเหยียดหยาม)* "
                    "\"คุณดูใจร้อนและไร้ระเบียบนะคุณผู้สืบสวน... บนรถไฟขบวนนี้ ความผลีผลามมักมีราคาที่ต้องจ่ายแพงเสมอ\""
                )
            if archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                return (
                    "*(กิเดียนยกแก้วเครื่องดื่มขึ้นจิบช้าๆ พลางประเมินคำถามของคุณ)* "
                    "\"พยายามเจาะลึกจิตใจคนอื่นดีนี่... แต่ระวังไว้หน่อย ความจริงบางเรื่องบนขบวนนี้ ยิ่งรู้มากก็ยิ่งอันตราย\""
                )
            if archetype == PlayerArchetype.INTUITIVE_RUSHER:
                return (
                    "*(กิเดียนพ่นควันซิการ์ออกมาอย่างไม่ยี่หระ)* "
                    "\"ด่วนสรุปเกินไปแล้วคุณเจ้าหน้าที่ คิดจะฟันธงคดีโดยไม่ดูบริบทให้รอบคอบก่อนหรือไง?\""
                )
            if archetype == PlayerArchetype.BALANCED_INVESTIGATOR:
                return (
                    "*(กิเดียนสบตาคุณด้วยท่าทีสุขุมระมัดระวังถ้อยคำตามแบบฉบับเจ้าหน้าที่ส่วนกลาง)* "
                    "\"มีเรื่องอะไรจะถามผมหรือครับคุณเจ้าหน้าที่?\""
                )

        # ======================================================================
        # ดร. ลิโอรา เวนน์ (Dr. Liora Venn) — นักวิจัย หวาดระแวง กลัวภัยมืด
        # ======================================================================
        elif target == "dr_liora_venn":
            if archetype == PlayerArchetype.FORENSIC_ANALYST:
                return (
                    "*(ดร.ลิโอราถอนหายใจด้วยความโล่งอกเล็กน้อยเมื่อเห็นว่าคุณทำงานอย่างเป็นระบบและยึดถือพยานหลักฐาน)* "
                    "\"ถ้าคุณเป็นคนที่เชื่อในหลักฐานและข้อเท็จจริงทางการแพทย์... ฉันก็พร้อมจะให้ความร่วมมือค่ะ\""
                )
            if archetype == PlayerArchetype.MAVERICK_TRAILBLAZER:
                return (
                    "*(ดร.ลิโอราผงะถอยหลังด้วยความหวาดระแวง มือทั้งสองกุมกระเป๋าเอกสารไว้แน่น)* "
                    "\"อย่า... อย่าเข้ามาใกล้ฉันมากไปกว่านี้เลยค่ะ! ท่าทางและการกระทำของคุณดูคาดเดาไม่ได้และน่ากลัวเกินไป...\""
                )
            if archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                return (
                    "*(ดร.ลิโอราสบตาคุณด้วยแววตาที่สับสนและกังวลใจ น้ำเสียงสั่นเทาเล็กน้อย)* "
                    "\"คุณดูพยายามเข้าใจสิ่งที่ฉันแบกรับอยู่... แต่ได้โปรดระวังตัวด้วยนะคะ เงามืดบนรถไฟขบวนนี้จับตาดูพวกเราอยู่ตลอดเวลา\""
                )
            if archetype == PlayerArchetype.INTUITIVE_RUSHER:
                return (
                    "*(ดร.ลิโอรากะพริบตาถี่ๆ เมื่อเห็นคุณรีบร้อนซักถาม)* "
                    "\"ใจเย็นๆ ก่อนนะคะคุณเจ้าหน้าที่... คดีแบบนี้การด่วนสรุปอาจทำให้มองข้ามความจริงสำคัญไปได้ค่ะ\""
                )
            if archetype == PlayerArchetype.BALANCED_INVESTIGATOR:
                return (
                    "*(ดร.ลิโอราพยักหน้ารับอย่างสุภาพ แววตายังคงมีความกังวลฉายอยู่)* "
                    "\"ฉันพร้อมตอบสิ่งที่เป็นประโยชน์ต่อการตรวจคดีค่ะ\""
                )

        # ======================================================================
        # วินเซนต์ เกรย์ (Vincent Gray) — โจรรับจ้าง กระด้าง แต่เปิดเผยตามข้อเท็จจริง
        # ======================================================================
        elif target == "vincent_gray":
            if archetype == PlayerArchetype.FORENSIC_ANALYST:
                return (
                    "*(วินเซนต์เหลือบมองสายตาของคุณแล้วสะบัดหน้าหนีอย่างรำคาญ)* "
                    "\"คุณมองผมเหมือนกำลังใช้แว่นขยายส่องหาความผิดเลยนะ... ผมบอกสิ่งที่รู้ไปหมดแล้ว อย่ามาจับผิดกันเลยน่า!\""
                )
            if archetype == PlayerArchetype.MAVERICK_TRAILBLAZER:
                return (
                    "*(วินเซนต์หัวเราะหึๆ ในลำคออย่างไม่เกรงกลัว)* "
                    "\"ชอบเล่นนอกกรอบเหมือนกันนี่หว่า... แต่ระวังตัวไว้เถอะ คนกล้าแบบคุณ ถ้าล้ำเส้นเกินไปมักอยู่ไม่ถึงปลายทางหรอก\""
                )
            if archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                return (
                    "*(วินเซนต์ถูรอยแผลที่แขนเบาๆ สีหน้าดูอ่อนลงเล็กน้อย)* "
                    "\"คุณพูดจาดูเป็นมิตรดีนี่เจ้าหน้าที่... เอาเป็นว่าผมให้ความร่วมมือเท่าที่จำเป็น แต่ขอร้องว่าอย่าเอาผมไปเอี่ยวกับแผนการฆาตกรรมเลย\""
                )
            if archetype == PlayerArchetype.INTUITIVE_RUSHER:
                return (
                    "*(วินเซนต์ยกมือห้ามอย่างเหนื่อยหน่าย)* "
                    "\"เฮ้ยๆ ถามเร็วจังวะคุณ... ใจเย็นก่อน ผมไม่ใช่เครื่องจักรนะ คิดจะรวบรัดคดีหรือไง?\""
                )
            if archetype == PlayerArchetype.BALANCED_INVESTIGATOR:
                return (
                    "*(วินเซนต์เหลือบมองคุณอย่างหยั่งเชิง ก่อนจะตอบอย่างระวังตัว)* "
                    "\"จะถามอะไรก็รีบถามเถอะครับ รถไฟใกล้ถึงสถานีแล้ว\""
                )

        # ======================================================================
        # พนักงานตรวจตู้ (Car Attendant) — ซื่อตรง ใส่ใจผู้โดยสาร ยึดถือกฎระเบียบ
        # ======================================================================
        elif target == "car_attendant":
            if archetype == PlayerArchetype.FORENSIC_ANALYST:
                return (
                    "*(พนักงานตรวจตู้หยิบสมุดบันทึกขึ้นมาเปิดเทียบ)* "
                    "\"ยินดีให้ความร่วมมือครับคุณเจ้าหน้าที่ ผมจดรอบบริการและเวลาไว้อย่างละเอียดครับ\""
                )
            if archetype == PlayerArchetype.MAVERICK_TRAILBLAZER:
                return (
                    "*(พนักงานตรวจตู้มองคุณด้วยความระแวงเล็กน้อย)* "
                    "\"เอ่อ... มีอะไรในตู้เสบียงที่ทำให้คุณไม่พอใจหรือเปล่าครับ? กรุณาอย่าทำลายทรัพย์สินของรถไฟนะครับ\""
                )
            if archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                return (
                    "*(พนักงานตรวจตู้ถอนหายใจยาวก่อนจะเล่า)* "
                    "\"คืนนี้วุ่นวายจริงๆ ครับคุณผู้สืบสวน ขอบคุณที่เข้าใจความกดดันของพนักงานอย่างพวกผมนะ\""
                )
            if archetype == PlayerArchetype.INTUITIVE_RUSHER:
                return (
                    "*(พนักงานตรวจตู้สะดุ้งเล็กน้อยกับคำถามที่โพล่งออกมา)* "
                    "\"ใจเย็นๆ ครับท่าน! เดี๋ยวผมจะสรุปข้อมูลสำคัญให้ฟังเดี๋ยวนี้ครับ\""
                )
            if archetype == PlayerArchetype.BALANCED_INVESTIGATOR:
                return (
                    "*(พนักงานตรวจตู้ยืนตัวตรงและตอบคำถามด้วยความเคารพ)* "
                    "\"สอบถามเรื่องรอบบริการหรือเหตุการณ์บนรถไฟได้เลยครับ\""
                )

        # ======================================================================
        # ผู้ป่วยที่ลิโอราดูแล (Patient Witness) — อ่อนแรง ต้องการการพักผ่อน
        # ======================================================================
        elif target == "patient_witness":
            if archetype == PlayerArchetype.FORENSIC_ANALYST:
                return (
                    "*(ผู้ป่วยขยับตัวช้าๆ สีหน้ายังซีดเซียว)* "
                    "\"คุณหมอลิโอราดูแลผมตั้งแต่ก่อนไฟดับ... ผมจำเวลาที่หมอเข้ามาได้แม่นยำครับ\""
                )
            if archetype == PlayerArchetype.MAVERICK_TRAILBLAZER:
                return (
                    "*(ผู้ป่วยสะดุ้งตัวโยนและไอเบาๆ)* "
                    "\"โอ๊ย... อย่าเสียงดังเลยครับคุณ ผมยังเวียนหัวอยู่เลย...\""
                )
            if archetype == PlayerArchetype.PSYCHOLOGICAL_INTERROGATOR:
                return (
                    "*(ผู้ป่วยสบตาคุณด้วยความรู้สึกขอบคุณ)* "
                    "\"คุณดูเป็นห่วงอาการผมมากกว่าจะมาเค้นเอาเรื่อง... ขอบคุณนะครับ เดี๋ยวผมจะบอกสิ่งที่ผมเห็น\""
                )
            if archetype == PlayerArchetype.INTUITIVE_RUSHER:
                return (
                    "*(ผู้ป่วยกุมขมับแน่น)* "
                    "\"อย่าเพิ่งรัวคำถามใส่ผมเลยครับ... หัวผมยังตื้อๆ อยู่เลย\""
                )
            if archetype == PlayerArchetype.BALANCED_INVESTIGATOR:
                return (
                    "*(ผู้ป่วยพยุงตัวขึ้นนั่งเล็กน้อย)* "
                    "\"ผมยังพักอยู่ตรงนี้ มีอะไรที่ผมพอจะช่วยได้บ้างครับ?\""
                )

        return None

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
        if not decision.allowed and decision.violated_rule_id == "R005_SAME_LOCATION":
            if recent_violation_count >= 2:
                return (
                    "💡 *[ข้อสังเกตของผู้สืบสวน]*: ขบวนรถไฟแบ่งพื้นที่ออกเป็นตู้โดยสารหลายตู้ "
                    "หากต้องการตรวจสิ่งของหรือคุยกับบุคคล ควรใช้คำสั่ง 'เดินไปที่...' ก่อน"
                )

        # 2. ผู้เล่นพยายามใช้คำสั่งที่ไม่รองรับ (เช่น take, use, burn ใส่ของที่ห้ามหยิบ)
        if not decision.allowed and decision.violated_rule_id == "R007_ACTION_SUPPORTED":
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
        if not decision.allowed and decision.violated_rule_id == "R012_ACCUSE_ENDING_REQUIREMENTS":
            return (
                "💡 *[ข้อสังเกตของผู้สืบสวน]*: การชี้ตัวคนร้ายต้องการเสาหลักฐาน (4 เสา: เวลาตาย, แรงจูงใจ, โอกาส, หลักฐานมัดตัว) "
                "ตรวจสอบกระดานคดีทางด้านซ้ายเพื่อดูว่ายังมีเงื่อนงำข้อใดที่ยังไม่คลี่คลาย"
            )

        return None
