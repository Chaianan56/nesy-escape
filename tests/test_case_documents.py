"""เอกสารในเกมและบันทึกเบื้องหลังต้องมาจากคดีที่กำลังเล่น และไม่ขัดกับเนื้อเรื่องของคดีนั้น"""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.cases import get_engine

ROOT = Path(__file__).resolve().parents[1]
CASES = ["case_01_gideon", "case_02_vincent", "case_03_liora"]
WALKTHROUGHS = {"case_01_gideon": "walkthrough.json", "case_02_vincent": "walkthrough_case_02.json",
                "case_03_liora": "walkthrough_case_03.json"}
DOC_FIELDS = {"id", "unlocked_by", "image_evidence_id", "title", "date", "classification", "summary", "content"}


def world(case_id):
    return get_engine(case_id).world


def story_text(w):
    """ทุกข้อความของคดี ยกเว้นเอกสารและบันทึกเบื้องหลังเอง"""
    rest = {k: v for k, v in w.items() if k not in ("documents", "case_background")}
    return json.dumps(rest, ensure_ascii=False)


@pytest.mark.parametrize("case_id", CASES)
def test_documents_are_well_formed_and_point_at_real_evidence(case_id):
    w = world(case_id)
    docs, background = w["documents"], w["case_background"]
    assert docs and background
    for doc in docs:
        assert set(doc) == DOC_FIELDS, doc["id"]
        assert doc["unlocked_by"] and all(e in w["objects"] for e in doc["unlocked_by"]), doc["id"]
        assert doc["image_evidence_id"] in w["objects"], doc["id"]
    for entry in background:
        assert entry["title"] and entry["text"]
        assert all(e in w["objects"] for e in entry["requires_evidence"])


@pytest.mark.parametrize("case_id", CASES)
def test_documents_add_no_numbers_the_case_does_not_have(case_id):
    """วันที่ เวลา ปี และเลขเอกสารในเอกสารต้องมีอยู่ในเนื้อเรื่องของคดีนั้นแล้ว"""
    w = world(case_id)
    known = set(re.findall(r"\d+", story_text(w)))
    for item in w["documents"] + w["case_background"]:
        text = " ".join(str(v) for k, v in item.items() if k not in ("id", "unlocked_by", "image_evidence_id",
                                                                       "requires_evidence"))
        assert set(re.findall(r"\d+", text)) <= known, (case_id, item.get("id") or item["title"])


@pytest.mark.parametrize("case_id", CASES)
def test_no_leftovers_from_older_story_versions(case_id):
    w = world(case_id)
    text = json.dumps(w["documents"] + w["case_background"], ensure_ascii=False)
    for stale in ("Project Nocturne", "PROJECT NOCTURNE", "ฮีตเตอร์", "ถาดเขี่ยบุหรี่"):
        assert stale not in text, (case_id, stale)


def test_file_c_is_missing_only_in_case_a():
    """คดี A แฟ้ม C หายไป คดี B และ C แฟ้ม C ยังครบ บันทึกเบื้องหลังต้องพูดตรงกับคดีของตัวเอง"""
    def dossier_note(case_id):
        return next(e["text"] for e in world(case_id)["case_background"]
                    if e["requires_evidence"] == ["dossier_missing_file_c"])
    assert "ช่อง C ว่าง" in dossier_note("case_01_gideon")
    for case_id in ("case_02_vincent", "case_03_liora"):
        assert "ช่อง C ว่าง" not in dossier_note(case_id)
        assert "แฟ้ม C ยังอยู่ครบ" in dossier_note(case_id)


def test_elias_file_follows_each_case():
    def secret(case_id):
        return next(d for d in world(case_id)["documents"] if d["id"] == "secret_file")["content"]
    assert "สำเนารับเงิน" in secret("case_03_liora")
    assert "สำเนารับเงิน" not in secret("case_01_gideon")
    assert "คำเตือนก่อนออกขบวน" in secret("case_02_vincent")


def test_case_a_data_files_agree():
    """คดี A รันจาก story.json ส่วน case_01_gideon.json เป็นสำเนา เอกสารต้องตรงกัน"""
    story = json.loads((ROOT / "data" / "story.json").read_text(encoding="utf-8"))
    copy = json.loads((ROOT / "data" / "cases" / "case_01_gideon.json").read_text(encoding="utf-8"))
    for key in ("documents", "case_background"):
        assert story[key] == copy[key]


def play_until(client, case_id, target):
    for step in json.loads((ROOT / "data" / WALKTHROUGHS[case_id]).read_text(encoding="utf-8"))["steps"]:
        reply = client.post("/command", json={"text": " ".join(step)}).json()
        assert reply["decision"]["allowed"], step
        if step[1] == target:
            return


@pytest.mark.parametrize("case_id", CASES)
def test_journal_sends_only_found_documents_of_the_current_case(case_id):
    client = TestClient(main.app)
    client.cookies.clear()
    client.get(f"/scene?case_id={case_id}")
    client.post("/new-game", json={"case_id": case_id})
    client.post("/start")
    before = client.post("/journal").json()
    assert before["documents"] == [] and before["background"] == []

    play_until(client, case_id, "burnt_folder_c")
    after = client.post("/journal").json()
    expected = next(d for d in world(case_id)["documents"] if d["id"] == "burnt_folder_c")
    sent = {d["id"]: d for d in after["documents"]}
    assert sent["burnt_folder_c"] == expected
    assert "secret_file" not in sent  # not found yet, so its text must not reach the page
