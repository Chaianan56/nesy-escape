"""
tests/test_resilience.py — ทดสอบความทนทานต่อสภาวะผิดปกติ (Resilience & Outage Recovery)

ครอบคลุม:
- การทดสอบการเล่นเกมแบบแทรกแซง (Adversarial Playthrough): การปฏิเสธคำสั่งนอกเส้นทาง การตรวจเบาะแสซ้ำ และการเดินย้อนกลับ
- การคงอยู่ของความคืบหน้าและสถานะหลักฐานเมื่อเกิดความล้มเหลวของ Neural Provider หรือโควตาเต็ม
- การจัดการคำสั่งที่หมดเวลาของเซิร์ฟเวอร์ขณะรอการประมวลผลของโมเดลภายนอก โดยต้องไม่เปลี่ยนสถานะโลกของเกม
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import main
from app.neural import gemini_client
from app.neural.gemini_client import NeuralQuotaExceeded, NeuralUnavailable
from app.schemas import ActionType, ParsedCommand

CASES = [('case_01_gideon','data/walkthrough.json'),
         ('case_02_vincent','data/walkthrough_case_02.json'),
         ('case_03_liora','data/walkthrough_case_03.json')]
PROGRESS = ('current_location','inventory','discovered_evidence','examined_objects',
            'unlocked_objects','dialogue_history','validated_claims','ending_id')

@pytest.fixture
def client(monkeypatch):
    """ฟิกซ์เจอร์จำลอง TestClient ในสภาวะออฟไลน์โดยตัดการเชื่อมต่อภายนอกทั้งหมด"""
    def offline(*args, **kwargs):
        raise NeuralUnavailable('Simulated provider outage')
    monkeypatch.setattr(gemini_client,'interpret',offline)
    monkeypatch.setattr(main,'interpret_remote',offline)
    monkeypatch.setattr(main,'llm_online',lambda: False)
    with TestClient(main.app) as c:
        yield c

def command(client,text,**extra):
    """ส่งคำสั่งไปยังเอนด์พอยต์ /command และส่งคืนข้อมูล JSON ผลลัพธ์"""
    response=client.post('/command',json={'text':text,**extra})
    assert response.status_code == 200
    return response.json()

def snapshot(client):
    """ดึงภาพรวมสถานะเริ่มต้น (Snapshot) ของฉากปัจจุบันจากเซิร์ฟเวอร์"""
    return client.get('/scene').json()['initial_state']

@pytest.mark.parametrize('case_id,filename',CASES)
def test_off_route_denials_repeated_clues_and_backtracking_still_solve(client,case_id,filename):
    """ทดสอบว่าการปฏิเสธคำสั่งนอกเส้นทาง การตรวจเบาะแสซ้ำ และการเดินย้อนกลับ
    ไม่ทำลายสถานะหลักฐานที่ได้รับแล้ว และยังคงสามารถคลี่คลายคดีจนจบได้สำเร็จ
    """
    client.get('/scene',params={'case_id':case_id})
    client.post('/start')
    # วัตถุที่อยู่ห่างไกล วัตถุที่ล็อกอยู่ หรือการกล่าวหาล่วงหน้า ต้องไม่เปิดเผยพยานหลักฐานก่อนกำหนด
    for text in ['examine secret_file','examine pocket_watch','accuse vincent_gray']:
        before=snapshot(client)
        reply=command(client,text)
        assert not reply['decision']['allowed'],text
        for field in PROGRESS:
            assert reply['new_state'][field] == before[field],(text,field)
    assert command(client,'move first_class_car')['decision']['allowed']
    for text in ['unlock dossier_bag 0000','examine dossier_missing_file_c','examine secret_file']:
        before=snapshot(client)
        reply=command(client,text)
        assert not reply['decision']['allowed'],text
        for field in PROGRESS:
            assert reply['new_state'][field] == before[field],(text,field)
    assert command(client,'move lounge_car')['decision']['allowed']
    walk=json.loads(Path(filename).read_text(encoding='utf-8'))
    for step in walk['steps']:
        extra={'submitted_evidence':walk['inference_evidence']} if step[0]=='infer' else {}
        reply=command(client,' '.join(step),**extra)
        assert reply['decision']['allowed'],(step,reply['decision'])
        if step[0] in ('examine','interrogate'):
            repeated=command(client,' '.join(step))
            assert repeated['decision']['allowed'],step
            for field in PROGRESS:
                assert repeated['new_state'][field] == reply['new_state'][field],(step,field)
    assert snapshot(client)['ending_id']=='true_ending'

@pytest.mark.parametrize('case_id,filename',CASES)
@pytest.mark.parametrize('failure',[NeuralUnavailable,NeuralQuotaExceeded])
def test_provider_failure_preserves_progress_and_recovers(client,monkeypatch,case_id,filename,failure):
    """ทดสอบว่าเมื่อระบบ Neural ขัดข้องหรือโควตาหมด สถานะความคืบหน้าจะคงเดิม และสามารถกลับมาทำงานต่อได้เมื่อระบบฟื้นตัว"""
    client.get('/scene',params={'case_id':case_id})
    client.post('/start')
    command(client,'move first_class_car')
    command(client,'examine cassian_reed')
    command(client,'examine pocket_watch')
    before=snapshot(client)
    tracker = main.get_tracker(before['session_id'])
    turns_before = len(tracker.turns)
    def unavailable(*args,**kwargs):
        raise failure('Simulated API timeout or exhausted quota')
    monkeypatch.setattr(gemini_client,'interpret',unavailable)
    reply=command(client,'อยากสำรวจรายละเอียดของห้องที่ยืนอยู่ช่วยหน่อย')
    assert not reply['decision']['allowed']
    assert reply['parsed']['parser_mode']=='fallback'
    assert reply['service_error'] == ('quota_exceeded' if failure is NeuralQuotaExceeded else 'unavailable')
    assert 'ไม่เข้าใจคำสั่ง' not in reply['decision']['message']
    assert 'รอสักครู่' in reply['decision']['message']
    assert reply['decision']['reasoning_chain'] == []
    assert reply['decision']['violated_rule_id'] is None
    assert len(tracker.turns) == turns_before
    for field in PROGRESS:
        assert reply['new_state'][field] == before[field],field
    assert command(client,'examine wall_clock')['decision']['allowed']
    def restored(text,state,**kwargs):
        return ParsedCommand(action=ActionType.EXAMINE,target='first_class_car',raw_text=text,parser_mode='gemini_knn')
    monkeypatch.setattr(gemini_client,'interpret',restored)
    assert command(client,'อยากสำรวจรายละเอียดของห้องที่ยืนอยู่ช่วยหน่อย')['decision']['allowed']
    assert 'pocket_watch' in snapshot(client)['discovered_evidence']

@pytest.mark.parametrize('case_id,filename',CASES)
def test_time_expiring_during_provider_wait_does_not_apply_command(client,monkeypatch,case_id,filename):
    """ทดสอบว่าหากเวลาของเกมหมดลงระหว่างรอการตอบกลับของ Provider คำสั่งนั้นต้องไม่ถูกนำไปแก้ไขสถานะของเกม"""
    now=[1000.0]
    monkeypatch.setattr(main.time,'time',lambda: now[0])
    client.get('/scene',params={'case_id':case_id})
    client.post('/start')
    before=snapshot(client)
    def delayed(text,state,**kwargs):
        now[0]+=5401
        return ParsedCommand(action=ActionType.MOVE,target='first_class_car',raw_text=text,parser_mode='gemini_knn')
    monkeypatch.setattr(gemini_client,'interpret',delayed)
    reply=command(client,'ช่วยพาไปดูสถานที่เกิดเหตุอย่างละเอียดหน่อย')
    assert not reply['decision']['allowed']
    assert reply['new_state']['ending_id'] is not None
    assert reply['new_state']['current_location']==before['current_location']
    assert reply['new_state']['discovered_evidence']==before['discovered_evidence']


@pytest.mark.parametrize('case_id,filename', CASES)
def test_current_case_guidance_uses_evidence_and_has_no_manual_inference(client, case_id, filename):
    client.get('/scene', params={'case_id': case_id})
    client.post('/start')
    result = command(client, 'accuse gideon_hart')
    message = result['decision']['message']
    assert 'แฟ้มสืบสวน' in message
    assert 'กระดานคดีทางด้านซ้าย' not in message
    assert '4 เสา:' not in message
    assert 'รายการเงื่อนไขที่ยังขาดของคดีนี้' in message
    # Exercise the actual engine with an infer intent even when the target is unknown.
    from app.cases import get_engine
    from app.schemas import GameState
    engine = get_engine(case_id)
    decision = engine.decide(ParsedCommand(action=ActionType.INFER, target='claim_two_times', raw_text='เสนอข้อสรุป'), GameState(case_id=case_id))
    assert not decision.allowed
    assert 'คดีนี้ไม่ต้องส่งข้อสรุป' in decision.message
    assert decision.state_changes == {}
