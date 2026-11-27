"""ภาพประกอบหลักฐาน: ทุกชื่อภาพที่ frontend/js/art.js อ้างถึงต้องมีไฟล์จริงและอยู่ใน catalog"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "assets" / "nocturne-stylized-v2"
ART_JS = (ROOT / "frontend" / "js" / "art.js").read_text(encoding="utf-8")


def referenced_assets():
    return set(re.findall(r"'((?:detail|scene|ending|medical)-[\w-]+)'", ART_JS))


def test_every_referenced_image_exists_and_is_catalogued():
    catalog = {a["id"] for a in json.loads((ART_DIR / "catalog.json").read_text(encoding="utf-8"))["assets"]}
    names = referenced_assets()
    assert "detail-dossier-file-c-present" in names
    missing_files = sorted(n for n in names if not (ART_DIR / f"{n}.png").exists())
    assert not missing_files
    # medical-key-v2 predates the catalog; everything else should be described there
    uncatalogued = sorted(n for n in names - {"medical-key-v2"} if n not in catalog)
    assert not uncatalogued


def test_open_dossier_image_depends_on_the_case():
    """คดี A แฟ้ม C หาย คดี B และ C แฟ้ม C ยังครบ ภาพกระเป๋าเปิดจึงต้องเลือกตามคดี"""
    assert "caseId === 'case_01_gideon' ? 'detail-dossier' : 'detail-dossier-file-c-present'" in ART_JS
    assert "if (evidence[target] === 'detail-dossier') return openDossierAsset(state);" in ART_JS


def test_story_specific_evidence_uses_a_fitting_image():
    groups = {asset: re.findall(r"'(\w+)'", ids) for asset, ids in re.findall(r"'([\w-]+)':\[([^\]]*)\]", ART_JS)}
    assert "mara_job_note" in groups["detail-vincent"]          # the note is in Vincent's coat pocket
    assert "mara_job_note" not in groups["detail-dossier"]
    assert "poison_vial" in groups["scene-04-medical"]           # the L-7 vial sits in the medical cabinet
