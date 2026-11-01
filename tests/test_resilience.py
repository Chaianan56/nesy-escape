"""Adversarial API playthroughs and provider outage recovery; no external calls."""
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
    def offline(*args, **kwargs):
        raise NeuralUnavailable('Simulated provider outage')
    monkeypatch.setattr(gemini_client,'interpret',offline)
    monkeypatch.setattr(main,'interpret_remote',offline)
    monkeypatch.setattr(main,'llm_online',lambda: False)
    with TestClient(main.app) as c:
        yield c

def command(client,text,**extra):
    response=client.post('/command',json={'text':text,**extra})
    assert response.status_code == 200
    return response.json()

def snapshot(client):
    return client.get('/scene').json()['initial_state']

@pytest.mark.parametrize('case_id,filename',CASES)
def test_off_route_denials_repeated_clues_and_backtracking_still_solve(client,case_id,filename):
    client.get('/scene',params={'case_id':case_id})
    client.post('/start')
    # Remote/locked content and premature accusations cannot reveal evidence.
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
    client.get('/scene',params={'case_id':case_id})
    client.post('/start')
    command(client,'move first_class_car')
    command(client,'examine pocket_watch')
    before=snapshot(client)
    def unavailable(*args,**kwargs):
        raise failure('Simulated API timeout or exhausted quota')
    monkeypatch.setattr(gemini_client,'interpret',unavailable)
    reply=command(client,'อยากสำรวจรายละเอียดของห้องที่ยืนอยู่ช่วยหน่อย')
    assert not reply['decision']['allowed']
    assert reply['parsed']['parser_mode']=='fallback'
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
