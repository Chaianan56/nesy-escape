"""
tests/test_neural_language.py — ชุดทดสอบตัวอย่างการตีความภาษาธรรมชาติแบบ Live (Opt-in Language Sample)

หน้าที่:
- ทดสอบการตีความข้อความภาษาไทยของผู้เล่นด้วยโมเดล Gemini จริง (Live LLM) เมื่อเปิด Flag
- ตรวจสอบความถูกต้องของการแปลงข้อความสืบสวนอิสระเป็น ParsedCommand และการส่งต่อให้ Symbolic Engine
- ทดสอบทั้งคำสั่งที่ชัดเจน (Exact Action) และคำสั่งที่คลุมเครือ (Ambiguous)
"""
import json
from pathlib import Path
import pytest
from app.cases import get_engine
from app.game_setup import new_game_state
from app.walkthrough import parse_step
from app.symbolic.engine import apply_changes
from app.neural.gemini_client import interpret, NeuralNotConfigured, NeuralQuotaExceeded

SAMPLES=[
 ('case_01_gideon','ขอเดนไปตู้เสบียงหน่อย','move','dining_car_staff',None),
 ('case_01_gideon','อยากคุยกับคุณกิเดียนหน่อย','interrogate','gideon_hart',None),
 ('case_02_vincent','ช่วยดูคราบเลืดบนเสื้อโค้ตวินเซนต์หน่อย','examine','vincent_blood','vincent_blood'),
 ('case_02_vincent','อยากตรวจดูของสักชิ้น แต่ยังเลือกไม่ถูกว่าจะดูอันไหน',None,None,None),
 ('case_03_liora','ช่วยสำรวจขวดยาแอลเจ็ดในห้องแพทย์หน่อย','examine','poison_vial','poison_vial'),
 ('case_03_liora','ขอเดนไปตู้โดยสารชั้นหนึ่งหน่อย','move','first_class_car',None),
]

@pytest.mark.llm
@pytest.mark.parametrize('case_id,text,action,target,checkpoint',SAMPLES)
def test_live_freeform_language(case_id,text,action,target,checkpoint):
    """ทดสอบการตีความภาษาธรรมชาติภาษาไทยแบบ Live ด้วย Gemini API สำหรับกรณีคำสั่งปกติและคำสั่งคลุมเครือ"""
    engine=get_engine(case_id)
    state=new_game_state(engine.world,case_id)
    if checkpoint:
        # หากมีการกำหนด Checkpoint ให้รัน Walkthrough จนถึงจุดที่พบหลักฐานเป้าหมายก่อน
        suffix='02' if case_id=='case_02_vincent' else '03'
        walk=json.loads(Path(f'data/walkthrough_case_{suffix}.json').read_text(encoding='utf-8'))
        for step in walk['steps']:
            if step[:2]==['examine',checkpoint]: break
            decision=engine.decide(parse_step(step,walk),state)
            assert decision.allowed
            state=apply_changes(state,decision.state_changes)
        else: raise AssertionError('Missing checkpoint')
    try:
        # เรียกใช้โมเดลเพื่อตีความข้อความภาษาไทยของผู้เล่น
        parsed=interpret(text,state)
    except (NeuralNotConfigured,NeuralQuotaExceeded) as error:
        pytest.skip(type(error).__name__)
    print(json.dumps({'case':case_id,'text':text,'action':parsed.action.value,'target':parsed.target,'latency_ms':parsed.latency_ms},ensure_ascii=False))
    if action is None:
        # กรณีคำสั่งคลุมเครือ ต้องตีความเป็น ambiguous หรือ unknown และถูกปฏิเสธโดย Symbolic Engine
        assert parsed.action.value in ('ambiguous','unknown')
        assert not engine.decide(parsed,state).allowed
    else:
        # กรณีคำสั่งระบุเจาะจง ต้องสอดคล้องกับ Action และ Target ที่คาดหวัง และผ่านการอนุญาตของ Engine
        assert parsed.action.value==action
        assert parsed.target==target
        assert engine.decide(parsed,state).allowed
