"""
tests/test_session_isolation.py — ทดสอบการแยกเซสชันของผู้เล่น (Session Isolation & Concurrency)

หน้าที่:
- ตรวจสอบว่าผู้เล่นต่างเซสชันกันไม่แชร์สถานะความคืบหน้า และการเริ่มเกมใหม่ไม่กระทบอีกฝ่าย
- ตรวจสอบว่าแท็บเบราว์เซอร์ที่ใช้ Cookie เดียวกันจะจัดลำดับคำสั่งแบบเรียงลำดับ (Serialized)
- ตรวจสอบการปฏิเสธคำสั่งเมื่อ Cookie หมดอายุหรือไม่ถูกต้อง และการสร้างเซสชันใหม่เมื่อโหลดหน้าจอ
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from app import main
from app.sessions import COOKIE
from app.game_setup import new_game_state
from app.cases import get_engine
from app.neural import gemini_client
from app.neural.gemini_client import NeuralUnavailable

CASES=['case_01_gideon','case_02_vincent','case_03_liora']

def initial_evidence(case_id):
    """ดึงรายการพยานหลักฐานเริ่มต้นที่เปิดเผยในแต่ละคดี"""
    return new_game_state(get_engine(case_id).world,case_id).discovered_evidence

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """ฟิกซ์เจอร์ตั้งค่าให้ระบบทำงานแบบออฟไลน์โดยปฏิเสธการเรียกใช้โมเดลภายนอก"""
    def unavailable(*args,**kwargs):
        raise NeuralUnavailable('Offline session test')
    monkeypatch.setattr(gemini_client,'interpret',unavailable)
    monkeypatch.setattr(main,'interpret_remote',unavailable)
    monkeypatch.setattr(main,'llm_online',lambda:False)

def scene(c):
    """ดึงสถานะเริ่มต้นของฉากผ่านเอนด์พอยต์ /scene"""
    return c.get('/scene').json()['initial_state']

def send(c,text):
    """ส่งคำสั่งไปยัง /command และตรวจสอบสถานะ HTTP 200"""
    r=c.post('/command',json={'text':text})
    assert r.status_code==200
    return r.json()

@pytest.mark.parametrize('case_id',CASES)
def test_independent_players_do_not_share_progress_or_restart(case_id):
    """ทดสอบว่าผู้เล่นต่างเซสชันมีสถานะแยกขาดจากกัน ไม่แชร์พยานหลักฐาน และการรีเซ็ตเกมของคนหนึ่งไม่กระทบอีกคน"""
    with TestClient(main.app) as a, TestClient(main.app) as b:
        a.get('/scene',params={'case_id':case_id})
        b.get('/scene',params={'case_id':'case_03_liora'})
        assert a.cookies[COOKIE]!=b.cookies[COOKIE]
        a.post('/start')
        send(a,'move first_class_car')
        send(a,'examine pocket_watch')
        untouched=scene(b)
        assert untouched['current_location']=='lounge_car'
        assert untouched['discovered_evidence']==initial_evidence('case_03_liora')
        assert untouched['started_at'] is None
        b.post('/new-game',json={'case_id':'case_02_vincent'})
        assert scene(a)['case_id']==case_id
        assert 'pocket_watch' in scene(a)['discovered_evidence']
        assert scene(b)['discovered_evidence']==initial_evidence('case_02_vincent')

@pytest.mark.parametrize('case_id',CASES)
def test_shared_cookie_tabs_serialize_commands_and_keep_journal_responsive(monkeypatch,case_id):
    """ทดสอบว่าคำสั่งจากหลายแท็บที่ใช้ Cookie เดียวกันจะถูกจัดคิวทำงานตามลำดับ และสมุดบันทึกยังตอบสนองได้โดยไม่ติดบล็อก"""
    with TestClient(main.app) as a, TestClient(main.app) as b:
        a.get('/scene',params={'case_id':case_id})
        b.cookies.update(a.cookies)
        a.post('/start')
        entered,release=Event(),Event()
        original=main.interpret
        def delayed(text,state):
            if text=='move first_class_car':
                entered.set()
                assert release.wait(5)
            return original(text,state)
        monkeypatch.setattr(main,'interpret',delayed)
        with ThreadPoolExecutor(max_workers=3) as pool:
            move=pool.submit(send,a,'move first_class_car')
            try:
                assert entered.wait(3)
                journal=pool.submit(b.post,'/journal',json={}).result(timeout=2)
                assert journal.status_code==200
                assert {e['id'] for e in journal.json()['evidence']}==set(initial_evidence(case_id))
                examine=pool.submit(send,b,'examine pocket_watch')
            finally:
                release.set()
            assert move.result(timeout=5)['decision']['allowed']
            assert examine.result(timeout=5)['decision']['allowed']
        assert scene(a)['discovered_evidence']==scene(b)['discovered_evidence']
        assert scene(a)['discovered_evidence'].count('pocket_watch')==1
        b.post('/new-game',json={'case_id':case_id})
        assert scene(a)['discovered_evidence']==initial_evidence(case_id)
        assert scene(a)['started_at'] is None

def test_unknown_cookie_cannot_send_commands_and_reload_creates_fresh_session():
    """ทดสอบว่า Cookie ที่ไม่ถูกต้องหรือไม่รู้จักจะถูกปฏิเสธ (401) และการเรียก /scene จะออก Cookie ใหม่ที่สะอาดเสมอ"""
    with TestClient(main.app) as c:
        c.cookies.set(COOKIE,'expired-test-session')
        assert c.post('/command',json={'text':'move first_class_car'}).status_code==401
        fresh=scene(c)
        assert fresh['discovered_evidence']==initial_evidence(fresh['case_id'])
        assert fresh['started_at'] is None
        assert c.cookies.get(COOKIE,domain='testserver.local')!='expired-test-session'
