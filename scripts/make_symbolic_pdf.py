# -*- coding: utf-8 -*-
"""สร้าง docs/symbolic_layer_explained.pdf — เอกสารอธิบายโค้ดชั้น symbolic

เนื้อหาทั้งหมดอยู่ในไฟล์นี้ ถ้าจะแก้เอกสาร ให้แก้ที่นี่แล้วรันใหม่

    pip install pymupdf
    python docs/make_symbolic_pdf.py

ใช้ PyMuPDF ไม่ใช้ reportlab เพราะ reportlab ไม่ทำ text shaping
วรรณยุกต์ที่ซ้อนบนสระบน เช่นคำว่า สิ่ง ที่ นี้ จะหายไปทั้งหมด
ฟอนต์ดึงจากโฟลเดอร์ฟอนต์ของ Windows จึงรันได้บน Windows เท่านั้น
Leelawadee ใช้กับเนื้อความ และ Consolas ใช้กับโค้ด เพื่อให้ผังแบบ ASCII เรียงตรงกัน
ส่วนภาษาไทยในบล็อกโค้ด PyMuPDF จะ fallback ไปฟอนต์อื่นให้เอง
"""

import json
import os
import shutil
import tempfile
from html import escape
from pathlib import Path

import sys

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas import ActionType, GameState, ParsedCommand   # noqa: E402
from app.symbolic.engine import SymbolicEngine, apply_changes  # noqa: E402
OUT = ROOT / "docs" / "symbolic_layer_explained.pdf"

# ฟอนต์ต้องอยู่ในโฟลเดอร์เดียวกับที่ PyMuPDF ใช้เป็น archive จึงวางไว้นอก repo
HERE = Path(tempfile.gettempdir()) / "nesy_doc_fonts"
HERE.mkdir(exist_ok=True)

for src, dst in [("leelawad.ttf", "th.ttf"), ("leelawdb.ttf", "thb.ttf"),
                 ("consola.ttf", "mono.ttf"), ("consolab.ttf", "monob.ttf")]:
    if not (HERE / dst).exists():
        shutil.copy(Path(os.environ["WINDIR"]) / "Fonts" / src, HERE / dst)

rules = json.loads((ROOT / "data/rules.json").read_text(encoding="utf-8"))["rules"]
world = json.loads((ROOT / "data/story.json").read_text(encoding="utf-8"))

N_RULES = len(rules)
N_LOC = len(world["locations"])
N_OBJ = len(world["objects"])
N_SUS = len(world["suspects"])
N_END = sum(1 for e in world["endings"] if e.get("canon", True))
N_END_ALL = len(world["endings"])
N_STEPS = len(json.loads((ROOT / "data/walkthrough.json").read_text(encoding="utf-8"))["steps"])
N_ENGINE_TESTS = sum(1 for l in (ROOT / "tests/test_engine.py").read_text(encoding="utf-8").splitlines()
                     if l.startswith("def test_"))
N_EV = sum(1 for v in world["objects"].values() if v["type"] == "evidence")
MINUTES = world["time_limit_seconds"] // 60
FIRST_RULE, LAST_RULE = rules[0]["id"][:4], max(r["id"][:4] for r in rules)


_ENGINE = SymbolicEngine()


def trace(action, target, state, note=""):
    """รันคำสั่งจริงแล้วถอดผลออกมาเป็นข้อความ

    ตัวอย่างในเอกสารจึงเป็นผลลัพธ์จากโค้ดชุดที่สร้างเอกสารนี้เสมอ
    ไม่ใช่ผลที่ก๊อปมาแปะแล้วค้างอยู่จนไม่ตรงกับของจริง
    """
    cmd = ParsedCommand(action=ActionType(action), target=target, raw_text="", confidence=1.0)
    d = _ENGINE.decide(cmd, state)
    out = [f"cmd   = ParsedCommand(action={action!r}, target={target!r})",
           f"state = current_location={state.current_location!r}, inventory={state.inventory}",
           "",
           f"reasoning_chain ที่ได้ {len(d.reasoning_chain)} ขั้น"]
    for st in d.reasoning_chain:
        mark = "[ผ่าน]   " if st.passed else "[ไม่ผ่าน]"
        out.append(f"  {mark} {st.rule_id}")
        out.append(f"            {st.description}")
    out += ["", f"allowed       = {d.allowed}"]
    if d.violated_rule_id:
        out.append(f"violated      = {d.violated_rule_id}")
    out.append(f"state_changes = {d.state_changes}")
    if note:
        after = apply_changes(state, d.state_changes)
        out += ["", note,
                f"  inventory     {state.inventory}  ->  {after.inventory}",
                f"  interrogated  {state.interrogated_suspects}  ->  {after.interrogated_suspects}",
                f"  turn_count    {state.turn_count}   ->  {after.turn_count}",
                f"  elapsed       {state.elapsed_seconds}   ->  {after.elapsed_seconds} วินาที"]
    return "\n".join(out)


def _ending_condition(e):
    """แปลงเงื่อนไขของฉากจบเป็นภาษาคน อ่านจากฟิลด์จริง ไม่ได้เขียนบรรยายซ้ำ"""
    if e.get("on_timeout"):
        return "หมดเวลาโดยไม่ได้กล่าวหาใคร"
    who = e.get("accuse", "*")
    parts = ["กล่าวหา " + (world["suspects"][who]["name_th"] if who in world["suspects"] else "ใครก็ตาม")]
    if e.get("requires_pillars"):
        parts.append("หลักฐานครบสี่ด้าน")
    if e.get("requires_case_against_culprit"):
        parts.append("ทั้งที่คดีต่อคนร้ายตัวจริงครบแล้ว")
    if e.get("requires_evidence"):
        parts.append(f"มีหลักฐานเจาะจงอีก {len(e['requires_evidence'])} ชิ้น")
    if e.get("requires_inventory"):
        parts.append("ถือของสำคัญติดตัวไว้")
    return " + ".join(parts)


def field_rows(group, rows):
    """เติมคอลัมน์ 'มีกี่รายการ' จากข้อมูลฉากจริง แทนการพิมพ์ตัวเลขเอง"""
    items = world[group].values()
    out = []
    for field, reader, effect in rows:
        n = sum(1 for v in items if v.get(field.split(",")[0].strip()))
        out.append([field, f"{n}/{len(world[group])}", reader, effect])
    return out


def code(text):
    return "<pre>" + escape(text.strip("\n")) + "</pre>"


def tbl(rows, widths, header=True, mono=()):
    out = ['<table>']
    for r_i, row in enumerate(rows):
        out.append("<tr>")
        tag = "th" if (header and r_i == 0) else "td"
        for c_i, cell in enumerate(row):
            cls = ' class="m"' if (c_i in mono and not (header and r_i == 0)) else ""
            w = f' width="{widths[c_i]}%"' if r_i == 0 else ""
            body = escape(str(cell)).replace("\n", "<br/>")
            out.append(f"<{tag}{cls}{w}>{body}</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def H1(t):
    return f'<h1>{t}</h1>'


def H2(t):
    return f'<h2>{t}</h2>'


def P(t, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f"<p{c}>{t}</p>"


def NEW():
    return '<div class="pb"></div>'


B = []
A = B.append

# ------------------------------------------------------------ ปก
A('<div class="cover">')
A('<div class="ct">ชั้น Symbolic ของ NeSy-Escape</div>')
A('<div class="cs">คำอธิบายโค้ดทั้งหมด — แต่ละไฟล์ทำอะไร แต่ละส่วนใช้อย่างไร '
  'และดึงข้อมูลมาจากไหน</div>')
A('</div>')
A(tbl([
    ["สาขา", "draft1"],
    ["ขอบเขต", "app/symbolic/engine.py, app/schemas.py, data/rules.json, "
                "data/story.json, app/walkthrough.py และจุดที่ app/main.py เรียกใช้"],
    ["ฉากของเกม", f"นอกเทิร์นเอกซ์เพรส ตู้รถ {N_LOC} ของ {N_OBJ} ชิ้น คน {N_SUS} "
                   f"ฉากจบ {N_END} แบบตามเนื้อเรื่อง กรอบเวลา {MINUTES} นาที"],
    ["กฎในระบบ", f"{N_RULES} ข้อ ({FIRST_RULE}–{LAST_RULE})"],
    ["การทดสอบ", "70 ข้อ รันได้โดยไม่ต้องมี API key ยกเว้นกลุ่มที่เรียก LLM จริง"],
], [22, 78], header=False))
A(P("เอกสารนี้อธิบายเฉพาะชั้น symbolic ส่วนชั้น neural (การเรียก Gemini) "
    "ถูกกล่าวถึงเพียงเท่าที่จำเป็นเพื่อให้เห็นว่าสองชั้นต่อกันตรงไหน", "note"))

# ------------------------------------------------------------ 1
A(H1("1. ภาพรวม แนวคิดของระบบสองชั้น"))
A(P("NeSy-Escape แบ่งการทำงานเป็นสองชั้นที่มีหน้าที่ต่างกันชัดเจน และห้ามก้าวก่ายกัน"))
A(tbl([
    ["ชั้น", "หน้าที่", "ใช้ LLM"],
    ["Neural\napp/neural/", "แปลข้อความภาษาไทยของผู้เล่นให้เป็นโครงสร้าง ParsedCommand\n"
     "ตอบคำถามว่า ผู้เล่นอยากทำอะไร กับสิ่งไหน", "ใช้"],
    ["Symbolic\napp/symbolic/", "รับ ParsedCommand แล้วตัดสินว่าทำได้หรือไม่ ตามกฎใน rules.json\n"
     "ตอบคำถามว่า กติกาของเกมอนุญาตให้ทำหรือเปล่า", "ไม่ใช้"],
], [22, 66, 12]))

A(H2("หลักการสี่ข้อที่เขียนไว้บนหัวไฟล์ engine.py"))
A(code("""
engine.py - Symbolic Rule Engine

หน้าที่: รับ ParsedCommand + GameState -> คืน Decision
หลักการที่ห้ามละเมิด:
  1) การตัดสินใจเกิดที่นี่ 100% ไม่มีการเรียก LLM ในไฟล์นี้
  2) reasoning_chain สร้างจากกฎที่ถูกตรวจจริงเท่านั้น (faithful by construction)
  3) กฎอยู่ใน rules.json ไม่ hard-code เงื่อนไขลงในโค้ด
  4) ไม่นำ confidence จาก LLM มาใช้ในการตัดสิน
"""))
A(P("ข้อ 2 สำคัญที่สุดสำหรับงานวิจัย คำว่า <b>faithful by construction</b> หมายความว่า "
    "คำอธิบายเหตุผลที่ระบบแสดงให้ผู้เล่นเห็น ไม่ได้ถูกเขียนขึ้นทีหลังเพื่อให้ดูสมเหตุสมผล "
    "แต่ทุกบรรทัดเกิดจากกฎที่โค้ดวิ่งผ่านจริง ถ้าอยากได้คำอธิบายเพิ่ม ต้องเพิ่มกฎ ไม่ใช่เพิ่มข้อความ"))
A(P("ข้อ 4 หมายความว่าต่อให้ LLM ตอบมาว่ามั่นใจ 0.99 หรือ 0.10 ชั้น symbolic ก็ตัดสินเหมือนเดิม "
    "ค่านี้ถูกเก็บไว้เพื่อการวิเคราะห์เท่านั้น ไม่มีบรรทัดไหนใน engine.py อ่านมันเลย"))

# ------------------------------------------------------------ 2
A(H1("2. แผนที่ไฟล์ ใครดึงอะไรมาจากไหน"))
A(code("""
                  ผู้เล่นพิมพ์ภาษาไทย
                          |
                          v
                     app/main.py            <-- ท่อเชื่อม (FastAPI)
                      |          |
                      v          v
  app/neural/gemini_client.py    app/symbolic/engine.py
            |                          |            |
            v                          v            v
    data/story.json            data/rules.json   data/story.json
"""))
A(P(f"ฝั่งซ้ายอ่าน story.json ไปใช้สร้าง prompt ส่วนฝั่งขวาอ่าน rules.json ซึ่งเก็บกฎ {N_RULES} ข้อ "
    "และ story.json ซึ่งเก็บโลกของเกม ทั้งสองฝั่งคุยกันด้วยโครงสร้างใน app/schemas.py เท่านั้น"))
A(tbl([
    ["ไฟล์", "หน้าที่", "ดึงอะไรมา"],
    ["app/schemas.py", "นิยามโครงสร้างข้อมูลกลาง 5 แบบ ที่สองชั้นใช้คุยกัน", "pydantic"],
    ["app/symbolic/engine.py", f"หัวใจของงาน ตัวตรวจกฎ {N_RULES} ตัว คลาส SymbolicEngine\nและฟังก์ชัน apply_changes",
     "schemas.py\nrules.json\nstory.json"],
    ["data/rules.json", f"กฎทั้ง {N_RULES} ข้อ เก็บเป็นข้อมูล ไม่ใช่โค้ด", "—"],
    ["data/story.json", f"โลกของเกม ตู้รถ {N_LOC} ของ {N_OBJ} คน {N_SUS} "
                        f"พร้อมคำบรรยาย เงื่อนไข และฉากจบ {N_END_ALL} รายการ", "—"],
    ["app/walkthrough.py", f"อ่านเส้นทางเฉลย {N_STEPS} ขั้นจาก walkthrough.json ให้เทสใช้", "walkthrough.json"],
    ["app/main.py", "รับคำสั่งจากเว็บ เรียก neural แล้วส่งต่อให้ symbolic", "ทั้งสองชั้น"],
], [26, 52, 22], mono=(0,)))
A(P("จุดที่ควรสังเกต engine.py <b>ไม่ import อะไรจาก app/neural เลย</b> "
    f"จึงรันได้โดยไม่ต้องมี GEMINI_API_KEY และเทส {N_ENGINE_TESTS} ข้อของมันรันได้แม้อินเทอร์เน็ตหลุด "
    "นี่คือการบังคับด้วยโครงสร้างว่าชั้นตัดสินไม่แตะ LLM จริง ไม่ใช่แค่ข้อตกลงกันปากเปล่า"))

# ------------------------------------------------------------ 3
A(H1("3. app/schemas.py สัญญากลางระหว่างสองชั้น"))
A(P("ไฟล์นี้ไม่มีตรรกะใด ๆ มีแต่คำนิยามโครงสร้างข้อมูล (Pydantic) "
    "หน้าที่คือทำให้สองชั้นต่อกันผิดไม่ได้ ถ้าฝั่งหนึ่งส่งฟิลด์ผิดชื่อหรือผิดชนิด จะพังตั้งแต่ตอนตรวจ "
    "ไม่ใช่ไปพังกลางเกม"))

A(H2("3.1 ActionType คำกริยาที่ระบบรู้จัก"))
A(code("""
class ActionType(str, Enum):
    EXAMINE     = "examine"      # ตรวจสอบวัตถุ/สถานที่/หลักฐาน
    TAKE        = "take"         # หยิบ/เก็บวัตถุเข้ากระเป๋า
    USE         = "use"          # ใช้ไอเทมกับเป้าหมาย
    UNLOCK      = "unlock"       # ปลดล็อกวัตถุ/สถานที่
    MOVE        = "move"         # เคลื่อนที่ไปยังตู้รถอื่น
    INTERROGATE = "interrogate"  # สอบปากคำผู้ต้องสงสัย
    ACCUSE      = "accuse"       # กล่าวหาฆาตกร (จบเกม)

    AMBIGUOUS   = "ambiguous"    # คำสั่งกำกวม ตีความได้หลายทาง
    UNKNOWN     = "unknown"      # นอกขอบเขต หรือตีความไม่ได้
"""))
A(P("สองค่าล่างสำคัญกว่าที่คิด มันคือช่องทางให้ชั้น neural บอกว่า ฉันไม่รู้ "
    "แทนที่จะเดาแล้วส่งคำสั่งมั่ว ๆ มาให้ชั้น symbolic ทำ"))

A(H2("3.2 ParsedCommand ผลลัพธ์จากชั้น neural"))
A(tbl([
    ["ฟิลด์", "ชนิด", "ความหมาย"],
    ["action", "ActionType", "กริยาที่สกัดได้"],
    ["target", "str หรือ None", "id ภาษาอังกฤษของเป้าหมาย เช่น service_pantry"],
    ["instrument", "str หรือ None", "id ของไอเทมที่ใช้ ใช้กับ action use เท่านั้น"],
    ["raw_text", "str", "ข้อความไทยดิบที่ผู้เล่นพิมพ์ เก็บไว้ตรวจย้อนหลัง"],
    ["confidence", "float 0 ถึง 1", "ความมั่นใจของ LLM เก็บเพื่อวิเคราะห์ ไม่ใช้ตัดสิน"],
    ["alternatives", "list ของ str", "ตัวเลือก เมื่อ action เป็น ambiguous"],
], [18, 20, 62], mono=(0, 1)))
A(P("มีเทสข้อหนึ่งคอยล็อกไว้ว่าโครงสร้างนี้ <b>ต้องไม่มีฟิลด์ชื่อ allowed, permitted, valid "
    "หรือ decision</b> เพราะถ้ามีเมื่อไหร่ แปลว่าชั้น neural เริ่มตัดสินแทน "
    "ซึ่งทำลายข้อสรุปของงานวิจัยทั้งหมด"))

A(H2("3.3 GameState สถานะเกม ณ ขณะนั้น"))
A(code("""
class GameState(BaseModel):
    current_location: str            = "passenger_car"    # ตู้ที่ยืนอยู่
    inventory: list[str]             = []                 # ของที่ถือติดตัว
    discovered_evidence: list[str]   = []                 # หลักฐานที่พบแล้ว
    unlocked_objects: list[str]      = []                 # สิ่งที่เปิด/ตรวจแล้ว
    visited_locations: list[str]     = ["passenger_car"]  # ตู้ที่เคยไป
    interrogated_suspects: list[str] = []                 # คนที่สอบปากคำแล้ว
    elapsed_seconds: int             = 0                  # เวลาที่ใช้ไป
    turn_count: int                  = 0                  # จำนวนตา
"""))
A(P("เซิร์ฟเวอร์ <b>ไม่เก็บสถานะไว้เอง</b> ทุกครั้งที่ผู้เล่นส่งคำสั่ง ฝั่งเว็บจะแนบ GameState "
    "ทั้งก้อนมาด้วย แล้วเซิร์ฟเวอร์ส่งก้อนใหม่กลับไป ข้อดีคือรันหลายเกมพร้อมกันได้โดยไม่ปนกัน "
    "และการทดลองสามารถยัดสถานะที่ต้องการเข้าไปตรงกลางได้เลย ไม่ต้องเล่นไล่มาตั้งแต่ต้น"))

A(H2("3.4 ReasoningStep และ Decision ผลลัพธ์จากชั้น symbolic"))
A(code("""
class ReasoningStep(BaseModel):
    rule_id: str        # รหัสกฎใน rules.json เช่น "R005_SAME_LOCATION"
    description: str    # คำอธิบายกฎภาษาไทย
    passed: bool        # ผ่านหรือไม่

class Decision(BaseModel):
    allowed: bool                         # อนุมัติหรือไม่
    message: str                          # ข้อความที่ผู้เล่นจะเห็น
    reasoning_chain: list[ReasoningStep]  # ลำดับกฎที่ถูกตรวจจริง
    violated_rule_id: str | None          # กฎที่ทำให้ถูกปฏิเสธ
    state_changes: dict                   # รายการเปลี่ยนแปลงสถานะ
"""))
A(P("<b>reasoning_chain คือผลผลิตหลักของงานวิจัยนี้</b> มันไม่ใช่คำอธิบายที่ LLM แต่งขึ้น "
    "แต่เป็นบันทึกว่าโค้ดวิ่งผ่านกฎข้อไหนบ้างและผลเป็นอย่างไร "
    "ตรวจสอบย้อนกลับไปที่ rules.json ได้ทุกบรรทัด"))

# ------------------------------------------------------------ 4
A(H1("4. data/story.json โลกของเกม"))
A(P("ไฟล์นี้คือฉากทั้งหมด ถ้าอยากเปลี่ยนคดีใหม่ แก้ไฟล์นี้ไฟล์เดียวโดยไม่ต้องแตะโค้ด"))
A(tbl([
    ["คีย์บนสุด", "ความหมาย"],
    ["title, briefing", "ชื่อคดีและบทเกริ่นที่ผู้เล่นเห็นตอนเปิดเกม"],
    ["time_limit_seconds", f"กรอบเวลาทั้งคดี ปัจจุบัน {MINUTES * 60} วินาที เท่ากับ {MINUTES} นาที\nตรงกับเวลาในเรื่อง พบศพ 23:42 ถึงปลายทาง 01:12"],
    ["seconds_per_turn", f"หนึ่งตากินเวลาเท่าไร ปัจจุบัน 60 วินาที ทำให้เล่นได้ {MINUTES} ตา"],
    ["locations", f"ตู้รถ {N_LOC} ตู้"],
    ["objects", f"สิ่งของและหลักฐาน {N_OBJ} ชิ้น ในนั้นเป็นหลักฐาน {N_EV} ชิ้น"],
    ["suspects", f"ผู้เกี่ยวข้อง {N_SUS} คน"],
    ["culprit, framed, coerced", "เฉลยของฉาก ใช้เขียนเทสและใช้เลือกฉากจบ ไม่ได้ส่งให้ผู้เล่น"],
    ["endings", f"ฉากจบ {N_END} แบบตามเอกสารเนื้อเรื่อง บวกทางออกสำรองอีก "
                f"{N_END_ALL - N_END} รายการ พร้อมเงื่อนไขของแต่ละอัน"],
], [28, 72], mono=(0,)))

A(H2("4.1 ฟิลด์ใน locations"))
A(tbl([["ฟิลด์", "มีกี่รายการ", "ใครอ่าน", "ผลที่เกิด"]] + field_rows("locations", [
    ("name_th", "หลายจุด", "ชื่อไทยที่ผู้เล่นเห็น"),
    ("description", "look_around", "คำบรรยายตู้"),
    ("locked", "R004", "ตู้นี้ล็อกอยู่หรือไม่ นับเฉพาะตู้ที่ล็อก"),
    ("requires", "R004", "ต้องมีของชิ้นไหนในกระเป๋าจึงจะเข้าได้"),
]), [20, 14, 20, 46], mono=(0,)))

A(H2("4.2 ฟิลด์ใน objects"))
A(tbl([["ฟิลด์", "มีกี่รายการ", "ใครอ่าน", "ผลที่เกิด"]] + field_rows("objects", [
    ("description", "_success_message", "ข้อความที่คืนเมื่อตรวจสำเร็จ"),
    ("type", "_state_changes", "ถ้าเป็น evidence การตรวจจะบันทึกเข้า discovered_evidence"),
    ("takeable", "R006", "หยิบติดตัวได้หรือไม่ นับเฉพาะที่หยิบได้"),
    ("burnable", "R017", "เผาทิ้งได้หรือไม่"),
    ("location", "R005, R016", "อยู่ตู้ไหน ชิ้นที่ไม่มีคือของที่ได้จากการคุยกับคน"),
    ("hidden_in", "R007", "ซ่อนอยู่ในอะไร ต้องตรวจสิ่งนั้นก่อน"),
    ("requires_evidence", "R008", "ต้องพบหลักฐานชิ้นไหนก่อนจึงจะเห็นชิ้นนี้"),
    ("requires_suspect", "R009", "ต้องสอบปากคำใครก่อน"),
    ("supports", "R013", "หลักฐานชิ้นนี้ค้ำเสาไหนของใคร"),
    ("exculpates", "R012", "หลักฐานชิ้นนี้พิสูจน์ว่าใครถูกบังคับ"),
]), [24, 13, 18, 45], mono=(0,)))
A(P("ฟิลด์ <span class=\"m\">supports</span> เป็นตัวที่ทำให้คดีนี้มีความหมาย รูปแบบคือ "
    "<span class=\"m\">{\"gideon_hart\": \"motive\"}</span> "
    "แปลว่าหลักฐานชิ้นนี้ค้ำแรงจูงใจของกิเดียน ฮาร์ต "
    "หลักฐานชิ้นเดียวกันอาจค้ำคนละคนคนละด้านก็ได้"))

A(H2("4.3 ฟิลด์ใน suspects"))
A(tbl([["ฟิลด์", "มีกี่รายการ", "ใครอ่าน", "ผลที่เกิด"]] + field_rows("suspects", [
    ("role", "look_around", "ตำแหน่งที่แสดงตอนดูรอบ ๆ"),
    ("location", "R005", "อยู่ตู้ไหน ต้องเดินไปหาถึงจะคุยได้"),
    ("testimony", "_success_message", "คำให้การที่คืนเมื่อสอบปากคำสำเร็จ"),
    ("requires_evidence", "R010", "ต้องมีหลักฐานอะไรจึงจะมีประเด็นตั้งคำถาม"),
    ("requires_suspect", "R010", "ต้องสอบใครก่อน"),
    ("grants_object", "_state_changes", "คุยแล้วได้ของ ในฉากนี้คือกุญแจพนักงาน"),
]), [24, 13, 20, 43], mono=(0,)))

# ------------------------------------------------------------ 5
A(H1(f"5. data/rules.json กฎทั้ง {N_RULES} ข้อ"))
A(P("กฎถูกเก็บเป็น <b>ข้อมูล ไม่ใช่โค้ด</b> เพิ่มหรือแก้กฎจึงทำได้โดยไม่ต้องแก้ engine.py "
    "ตราบใดที่ยังใช้ตัวตรวจเดิม แต่ละข้อมี 6 ฟิลด์ และมีฟิลด์ที่เจ็ดที่ใส่หรือไม่ใส่ก็ได้"))
A(code("""
{
  "id": "R005_SAME_LOCATION",
  "description": "ต้องอยู่ในตู้รถเดียวกับสิ่งหรือคนที่ต้องการเข้าถึง",
  "applies_to": ["examine", "take", "use", "interrogate"],
  "check": "in_same_location",
  "params": {},
  "message_fail": "สิ่งหรือคนที่ระบุไม่ได้อยู่ในตู้รถนี้ ต้องเดินไปหาก่อน"
}
"""))
A(tbl([
    ["ฟิลด์", "ใช้ทำอะไร"],
    ["id", "รหัสกฎ โผล่ใน reasoning_chain และ violated_rule_id ให้ตรวจย้อนได้"],
    ["description", "คำอธิบายภาษาไทย เอาไปแสดงในสายเหตุผลตรง ๆ"],
    ["applies_to", "กฎนี้ใช้กับ action ไหนบ้าง ใส่ดอกจันแปลว่าทุก action"],
    ["check", "ชื่อฟังก์ชันตรวจใน engine.py ผูกกันผ่านตาราง CHECKERS"],
    ["params", "ค่าที่ส่งให้ฟังก์ชันตรวจ ใช้ปรับพฤติกรรมโดยไม่แก้โค้ด"],
    ["message_fail", "ข้อความที่ผู้เล่นเห็นเมื่อกฎนี้ไม่ผ่าน"],
    ["blocking", "ใส่ false เพื่อบอกว่ากฎนี้ไม่ปฏิเสธคำสั่ง ใช้จำแนกอย่างเดียว "
                 "ไม่ใส่ถือว่า true คือบล็อกตามปกติ"],
], [20, 80], mono=(0,)))

A(H2("5.1 กฎทั้งหมด เรียงตามลำดับที่ถูกตรวจจริง"))
rows = [["ลำดับ", "รหัส", "ใช้กับ action", "ตรวจอะไร"]]
for i, r in enumerate(rules, 1):
    mark = "" if r.get("blocking", True) else "  [ไม่บล็อก]"
    rows.append([str(i), r["id"], ", ".join(r["applies_to"]), r["description"] + mark])
A(tbl(rows, [8, 26, 20, 46], mono=(1, 2)))
A(P("<b>ลำดับในไฟล์คือลำดับการตรวจ และมีผลจริง</b> R014 เรื่องหมดเวลาถูกย้ายมาไว้อันดับสอง "
    "เพราะตอนแรกวางไว้ท้ายสุด ทำให้ผู้เล่นที่หมดเวลาแล้วกดกล่าวหา จะได้ข้อความว่า "
    "หลักฐานไม่ครบสี่ด้าน แทนที่จะเป็น หมดเวลาแล้ว ซึ่งเป็นคำอธิบายที่ผิดความจริง "
    "ตอนนี้มีเทสล็อกลำดับนี้ไว้ไม่ให้ใครสลับกลับ"))

# ------------------------------------------------------------ 6
A(H1(f"6. engine.py ตอนที่ 1 ตัวตรวจกฎ {N_RULES} ตัว"))
A(P("โค้ดครึ่งบนของ engine.py คือฟังก์ชันตรวจกฎ ทุกตัวมีหน้าตาเหมือนกันหมด"))
A(code("""
def _ชื่อ(cmd, state, world, p):
    ...
    return ผ่านหรือไม่, "รายละเอียดที่จะแสดงในสายเหตุผล"
"""))
A(tbl([
    ["พารามิเตอร์", "คืออะไร"],
    ["cmd", "ParsedCommand ที่ชั้น neural ส่งมา"],
    ["state", "GameState ปัจจุบัน"],
    ["world", "ข้อมูลทั้งก้อนจาก story.json"],
    ["p", "ค่า params ของกฎข้อนั้นจาก rules.json"],
], [20, 80], mono=(0,)))
A(P("ทุกตัวเป็นฟังก์ชันบริสุทธิ์ คือไม่แก้ไขอะไรเลย แค่ตอบว่าผ่านหรือไม่ผ่าน "
    "การเปลี่ยนสถานะเป็นหน้าที่ของฟังก์ชันอื่นทั้งหมด"))

A(H2(f"6.1 ฟังก์ชันตรวจทั้ง {N_RULES} ตัว"))
A(tbl([
    ["ฟังก์ชัน", "กฎ", "ตรรกะโดยย่อ", "อ่านจาก"],
    ["_action_is_known", "R000", "ถ้า action เป็น unknown หรือ ambiguous ให้ตก", "cmd"],
    ["_target_exists", "R001", "target ต้องอยู่ใน objects หรือ locations\n"
     "รับชื่อตู้ด้วย เพราะ ดูรอบ ๆ คือ examine ตู้", "world"],
    ["_location_exists", "R002", "target ต้องอยู่ใน locations", "world"],
    ["_suspect_exists", "R003", "target ต้องอยู่ใน suspects", "world"],
    ["_location_unlocked", "R004", "ถ้าตู้ locked ต้องมี requires อยู่ใน inventory", "world, state"],
    ["_in_same_location", "R005", "เทียบ location ของเป้าหมายกับ current_location\n"
     "ค้นทั้ง objects และ suspects", "world, state"],
    ["_target_is_takeable", "R006", "ของต้องมี takeable เป็น true", "world"],
    ["_container_unlocked", "R007", "ถ้ามี hidden_in ตัวที่ซ่อนต้องอยู่ใน unlocked_objects", "world, state"],
    ["_evidence_prerequisites_met", "R008", "ทุก id ใน requires_evidence ต้องอยู่ใน discovered_evidence", "world, state"],
    ["_testimony_prerequisite_met", "R009", "requires_suspect ต้องอยู่ใน interrogated_suspects", "world, state"],
    ["_suspect_available", "R010", "คนนี้ต้องมีหลักฐานตั้งประเด็นครบ และสอบคนก่อนหน้าแล้ว", "world, state"],
    ["_instrument_in_inventory", "R011", "instrument ต้องอยู่ใน inventory", "state"],
    ["_not_exculpated", "R012", "ห้ามกล่าวหาคนที่มีหลักฐาน exculpates ชี้ว่าถูกบังคับ", "world, state"],
    ["_four_pillars", "R013", "เสาทั้งสี่ต้องมีหลักฐานอย่างน้อยด้านละหนึ่งชิ้น", "world, state"],
    ["_within_time_limit", "R014", "elapsed_seconds ต้องไม่เกิน time_limit_seconds", "world, state"],
    ["_game_not_over", "R015", "ถ้า state มี ending_id แล้ว แปลว่าคดีปิดไปแล้ว", "state"],
    ["_not_destroyed", "R016", "target ต้องไม่อยู่ใน burned_objects", "state"],
    ["_target_is_burnable", "R017", "ของต้องมี burnable เป็น true", "world"],
], [26, 8, 50, 16], mono=(0,)))

A(H2("6.2 ตัวอย่างโค้ดจริง _in_same_location"))
A(P("ตัวที่ซับซ้อนที่สุด เพราะรับได้ทั้งตู้ ของ และคน"))
A(code("""
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
"""))
A(P("บรรทัด <span class=\"m\">where is None</span> คือทางผ่านของ crew_key "
    "ซึ่งเป็นของชิ้นเดียวที่ไม่มีที่อยู่ เพราะได้จากการคุยกับคน ไม่ได้วางอยู่ที่ไหน", "note"))

A(H2("6.3 ตัวอย่างโค้ดจริง _four_pillars กฎที่ทำให้เกมจบได้"))
A(code("""
def _collect_pillars(target, state, world):
    found = {k: [] for k in PILLARS}
    for ev_id in state.discovered_evidence:
        ev = world["objects"].get(ev_id, {})
        pillar = ev.get("supports", {}).get(target)
        if pillar in found:
            found[pillar].append(ev_id)
    return found

def _four_pillars(cmd, state, world, p):
    required = p.get("required", list(PILLARS))
    found = _collect_pillars(cmd.target, state, world)
    missing = [k for k in required if not found[k]]
    if missing:
        return False, f"ขาดหลักฐานด้าน: {', '.join(missing)}"
    summary = "; ".join(f"{k}={len(found[k])}" for k in required)
    return True, summary
"""))
A(P("สังเกตว่ามันไล่จาก <span class=\"m\">state.discovered_evidence</span> "
    "คือของที่ <b>ผู้เล่นหาเจอจริง</b> ไม่ใช่ของที่มีอยู่ในฉาก ผู้เล่นจึงต้องออกไปหาเอง "
    "และคำว่าครบสี่ด้านหมายถึงมีอย่างน้อยด้านละหนึ่งชิ้น ไม่ได้ต้องครบทุกชิ้น "
    "ทำให้มีหลายเส้นทางที่ชนะได้"))
A(P("รายชื่อเสาถูกส่งมาจาก params ใน rules.json ไม่ได้เขียนตายไว้ในโค้ด "
    "ถ้าอยากทดลองว่าใช้แค่สามเสาจะต่างกันไหม แก้ไฟล์ JSON ได้เลย", "note"))

# ------------------------------------------------------------ 7
A(H1("7. engine.py ตอนที่ 2 หัวใจของการตัดสิน"))
A(P("ตาราง CHECKERS คือจุดที่ผูกกฎในไฟล์ JSON เข้ากับฟังก์ชันในโค้ด "
    "ฟิลด์ check ของกฎต้องตรงกับคีย์ในตารางนี้ ถ้าสะกดผิดระบบจะโยน error ทันทีที่เจอกฎนั้น "
    "ไม่ใช่เงียบ ๆ ข้ามไป"))
A(code("""
CHECKERS: Dict[str, Callable] = {
    "action_is_known": _action_is_known,
    "target_exists": _target_exists,
    ...
    "within_time_limit": _within_time_limit,
}
"""))

A(H2("7.1 __init__ และ _applicable"))
A(code("""
class SymbolicEngine:
    def __init__(self, rules_path=None, story_path=None):
        self.rules = json.loads(rules_path.read_text(...))["rules"]
        self.world = json.loads(story_path.read_text(...))

    def _applicable(self, action):
        return [r for r in self.rules
                if "*" in r.get("applies_to", []) or action.value in r.get("applies_to", [])]
"""))
A(P("โหลดไฟล์ทั้งสองครั้งเดียวตอนสร้างวัตถุ แล้วเก็บไว้ในหน่วยความจำ "
    "การรับ path เข้ามาได้ทำให้เทสสร้างโลกจำลองของตัวเองได้โดยไม่แตะไฟล์จริง "
    "ส่วน _applicable คือตัวกรองว่า action นี้ต้องผ่านกฎข้อไหนบ้าง "
    "เช่น move ผ่าน 4 ข้อ ส่วน accuse ผ่าน 5 ข้อ"))

A(H2("7.2 decide() วงจรหลัก"))
A(code("""
def decide(self, cmd, state) -> Decision:
    chain = []
    for rule in self._applicable(cmd.action):
        checker = CHECKERS.get(rule["check"])
        if checker is None:
            raise ValueError(f"ไม่พบ checker '{rule['check']}' ของกฎ {rule['id']}")

        passed, detail = checker(cmd, state, self.world, rule.get("params", {}))
        desc = f"{rule['description']} ({detail})" if detail else rule["description"]
        chain.append(ReasoningStep(rule_id=rule["id"], description=desc, passed=passed))

        # หยุดที่กฎแรกที่ไม่ผ่าน เพราะกฎถัดไปอาจสมมติว่ากฎก่อนหน้าผ่านแล้ว
        if not passed:
            ...
            return Decision(allowed=False, message=message, reasoning_chain=chain,
                            violated_rule_id=rule["id"], state_changes={})

    return Decision(allowed=True, message=self._success_message(cmd, state),
                    reasoning_chain=chain, violated_rule_id=None,
                    state_changes=self._state_changes(cmd))
"""))
A(P("ทั้งฟังก์ชันมีแค่ 20 บรรทัด และนี่คือจุดที่ <b>reasoning_chain ถูกสร้างขึ้นระหว่างทาง</b> "
    "ไม่ได้เขียนทีหลัง ทุก ReasoningStep ถูกเพิ่มเข้าลิสต์ทันทีหลังเรียกตัวตรวจเสร็จ "
    "จึงเป็นไปไม่ได้เลยที่สายเหตุผลจะไม่ตรงกับสิ่งที่ระบบทำจริง"))
A(P("การหยุดที่กฎแรกที่ไม่ผ่านเป็นเรื่องจำเป็น ไม่ใช่แค่เรื่องความเร็ว "
    "เพราะกฎข้อหลังสมมติว่าข้อหน้าผ่านแล้ว เช่น R005 จะไปอ่าน location ของเป้าหมาย "
    "ซึ่งจะพังถ้า R001 ยังไม่ได้ยืนยันว่าเป้าหมายมีอยู่จริง"))

A(H2("7.3 กฎที่ไม่บล็อก ตัวจำแนกไม่ใช่ประตูปิด"))
A(P("กฎส่วนใหญ่ทำหน้าที่ปิดประตู ไม่ผ่านก็คือทำไม่ได้ แต่มีสองข้อที่ทำหน้าที่ต่างออกไป"))
A(tbl([["กฎ", "ทำไมต้องไม่บล็อก"]] + [
    [r["id"], r["description"]] for r in rules if r.get("blocking") is False
], [30, 70], mono=(0,)))
A(P("เดิมสองข้อนี้บล็อก ผลคือกล่าวหาผิดคนไม่ได้เลย ระบบปฏิเสธทิ้งทุกกรณี "
    "ซึ่งทำให้ฉากจบที่เป็นแก่นของเรื่อง คือฉากที่ผู้เล่นเลือกทางที่สะดวก ไปไม่ถึงสักอันเดียว"))
A(code("""
            # กฎที่ blocking=false ใช้ "จำแนก" ไม่ใช่ "ปิดประตู"
            # ผลของมันยังถูกบันทึกลงสายเหตุผลตามจริง แต่ไม่ทำให้คำสั่งถูกปฏิเสธ
            if not passed and not rule.get("blocking", True):
                continue
"""))
A(P("<b>จุดสำคัญคือคำอธิบายไม่ได้อ่อนลงเพราะปล่อยให้ทำได้</b> "
    "เมื่อผู้เล่นกล่าวหาคนที่หลักฐานไม่ครบ สายเหตุผลยังบันทึกตรง ๆ ว่า R013 ไม่ผ่าน "
    "และขาดหลักฐานด้านไหนบ้าง เพียงแต่ผลลัพธ์เปลี่ยนจากถูกปฏิเสธ เป็นได้ฉากจบที่แย่ลง"))

A(H2("7.4 การปรับข้อความให้ผู้เล่นไม่ตัน"))
A(P("ในกิ่งที่กฎไม่ผ่าน มีการปรับข้อความสามกรณี ทั้งหมดมาจากการให้คนอื่นลองเล่นจริง "
    "แล้วพบว่าอ่านแล้วไม่รู้ว่าต้องทำอะไรต่อ"))
A(tbl([
    ["กรณี", "ปัญหาเดิม", "แก้เป็น"],
    ["action = ambiguous", "ได้ข้อความว่า ระบบไม่เข้าใจคำสั่งนี้ เหมือนกรณี unknown",
     "บอกว่าคำสั่งกว้างไป ให้ระบุให้เจาะจง หรือพิมพ์ ดูรอบๆ"],
    ["action = unknown", "บอกแค่ว่าไม่เข้าใจ ไม่บอกว่าทำอะไรได้บ้าง",
     "ต่อท้ายด้วยรายการสิ่งที่ทำได้ทั้งหมด"],
    ["R005 ไม่ผ่าน", "บอกว่าต้องเดินไปหาก่อน แต่ไม่บอกว่าตู้ไหน ทั้งที่เอนจินรู้อยู่แล้ว",
     "ต่อท้ายชื่อไทยของตู้ปลายทาง เช่น มารา วอสส์ อยู่ที่ตู้โดยสาร"],
], [20, 40, 40], mono=(0,)))
A(P("จุดสำคัญคือการแก้เหล่านี้แตะแค่ฟิลด์ message ซึ่งเป็นข้อความสำหรับมนุษย์ "
    "<b>ไม่แตะ reasoning_chain</b> สายเหตุผลจึงยังเป็นบันทึกทางเทคนิคที่ซื่อตรงเหมือนเดิม"))

# ------------------------------------------------------------ 8
A(H1("8. engine.py ตอนที่ 3 การเปลี่ยนสถานะ"))
A(P("การตัดสินกับการเปลี่ยนสถานะถูกแยกออกจากกันโดยตั้งใจ decide() แค่บอกว่า "
    "<b>ควรเปลี่ยนอะไร</b> ส่วนการเปลี่ยนจริงเกิดที่ apply_changes() ซึ่งอยู่นอกคลาส"))

A(H2("8.1 _state_changes() แปลง action เป็นใบสั่งเปลี่ยนสถานะ"))
A(tbl([
    ["action", "state_changes ที่คืน", "หมายเหตุ"],
    ["move", "{\"move_to\": target}", "—"],
    ["take", "{\"inventory_add\": target}\nบวก discovered_evidence_add ถ้า type เป็น evidence", "—"],
    ["examine", "{} ถ้าเป้าหมายเป็นตู้ เพราะดูรอบ ๆ ไม่เปลี่ยนอะไร\n"
     "{\"unlocked_add\": target} ถ้าเป็นของ\n"
     "บวก discovered_evidence_add ถ้า type เป็น evidence",
     "ตรวจของเท่ากับเปิดของนั้น ทำให้ของที่ hidden_in มันโผล่ตามมา"],
    ["unlock", "{\"unlocked_add\": target}", "—"],
    ["interrogate", "{\"interrogated_add\": target}\nบวก inventory_add ถ้าคนนั้นมี grants_object",
     "ทางเดียวที่จะได้ crew_key"],
    ["accuse, use", "{}", "จบเกม หรือยังไม่มีผลต่อสถานะ"],
], [14, 52, 34], mono=(0, 1)))

A(H2("8.2 apply_changes() ผู้เปลี่ยนสถานะตัวจริง"))
A(code("""
def apply_changes(state: GameState, changes: dict) -> GameState:
    s = state.model_copy(deep=True)
    mapping = {
        "inventory_add": s.inventory,
        "discovered_evidence_add": s.discovered_evidence,
        "unlocked_add": s.unlocked_objects,
        "interrogated_add": s.interrogated_suspects,
    }
    for key, lst in mapping.items():
        v = changes.get(key)
        if v and v not in lst:
            lst.append(v)
    dest = changes.get("move_to")
    if dest:
        s.current_location = dest
        if dest not in s.visited_locations:
            s.visited_locations.append(dest)
    s.turn_count += 1
    s.elapsed_seconds += SECONDS_PER_TURN
    return s
"""))
A(P("<b>คืน state ก้อนใหม่เสมอ ไม่แก้ของเดิม</b> ทำให้ยิงคำสั่งชุดเดิมซ้ำกี่รอบก็ได้ผลเหมือนกัน "
    "ซึ่งจำเป็นมากสำหรับการทดลองที่ต้องรันซ้ำได้"))
A(P("สองบรรทัดสุดท้ายคือจุดที่ต้องอธิบายเป็นพิเศษ เวลาเดินที่นี่ "
    "<b>ไม่ได้เดินผ่าน state_changes</b> ทั้งที่ดูเหมือนควรจะเป็นแบบนั้น "
    "เหตุผลอยู่ในคอมเมนต์ของโค้ดเอง"))
A(code("""
เวลาเดินทุกตาโดยไม่ขึ้นกับว่าใครเป็นผู้ตัดสิน จงใจให้อยู่ตรงนี้ไม่ใช่ใน state_changes
เพราะถ้าปล่อยให้คำตัดสินเป็นตัวกำหนด โหมด A (LLM ตัดสินเอง) จะคุมเวลาของตัวเองได้
แล้วสองโหมดจะเดินด้วยนาฬิกาคนละเรือน เทียบกันไม่ได้
"""))
A(P("นี่เป็นการตัดสินใจเชิงการทดลอง ไม่ใช่เชิงเกม การเปรียบเทียบสองโหมดจำเป็นต้องให้ "
    "ทุกอย่างเหมือนกันหมดยกเว้นตัวแปรเดียวคือใครเป็นคนตัดสิน "
    "ถ้าเวลาเดินไม่เท่ากัน ผลที่ได้ก็เทียบกันไม่ได้"))
A(P("ค่า SECONDS_PER_TURN อ่านมาจาก story.json ตอนโหลดโมดูล ไม่ได้เขียนตัวเลขไว้ในโค้ด", "note"))

# ------------------------------------------------------------ 9
A(H1("9. engine.py ตอนที่ 4 ข้อความที่ผู้เล่นได้เห็น"))
A(P("เกมนี้เล่นด้วยการพิมพ์ล้วน ไม่มีปุ่มให้กด ผู้เล่นจึงรู้จักโลกได้จากข้อความที่ระบบตอบกลับเท่านั้น "
    "ส่วนนี้จึงสำคัญพอ ๆ กับตัวกฎ"))

A(H2("9.1 _success_message() เลือกข้อความตอบกลับ"))
A(tbl([
    ["action", "คืนอะไร"],
    ["examine ตู้", "เรียก look_around() ของตู้นั้น"],
    ["examine ของ", "ฟิลด์ description ของ object นั้นจาก story.json"],
    ["interrogate", "ฟิลด์ testimony ของ suspect นั้น"],
    ["move", "look_around() ของตู้ปลายทาง โดยใช้สำเนา state ที่ย้ายแล้ว"],
    ["accuse", "เรียก closing_argument()"],
    ["take, unlock, use", "ข้อความสำเร็จรูปสั้น ๆ เช่น เก็บ...ไว้เป็นหลักฐาน"],
], [22, 78], mono=(0,)))
A(P("ข้อสังเกต ข้อความส่วนใหญ่คืน <b>เนื้อความจริงจาก story.json</b> ไม่ใช่ประโยคยืนยันลอย ๆ "
    "เพราะถ้าตอบแค่ว่าตรวจสอบเรียบร้อย ผู้เล่นจะไม่ได้ข้อมูลอะไรเลยและเล่นต่อไม่ได้"))

A(H2("9.2 look_around() รายการสิ่งที่มองเห็นได้ตอนนี้"))
A(code("""
here = [oid for oid, o in self.world["objects"].items()
        if o.get("location") == loc_id and oid not in state.inventory]
visible = [oid for oid in here if self.decide(
    ParsedCommand(action=ActionType.EXAMINE, target=oid, raw_text="", confidence=0.0),
    state,
).allowed]
"""))
A(P("นี่คือเทคนิคสำคัญของไฟล์นี้ <b>look_around ไม่ได้มีรายการที่เขียนมือไว้ต่างหาก "
    "แต่ถามจากกฎชุดเดียวกับที่ใช้ตัดสินจริง</b> โดยลองเรียก decide() ด้วยคำสั่ง examine สมมติ "
    "ของที่ยังซ่อนอยู่หรือยังไม่มีหลักฐานนำทาง จะตกกฎ R007 หรือ R008 แล้วไม่ถูกแสดง"))
A(P("ผลคือ <b>สิ่งที่ผู้เล่นเห็น กับสิ่งที่ผู้เล่นทำได้ ตรงกันเสมอโดยอัตโนมัติ</b> "
    "ถ้าเขียนรายการแยกไว้ วันหนึ่งกฎเปลี่ยนแล้วลืมแก้รายการ "
    "ผู้เล่นจะเห็นของที่ตรวจไม่ได้ หรือตรวจได้แต่มองไม่เห็น"))
A(P("ส่วนรายชื่อคนที่อยู่ในตู้นี้จะแสดง <b>ทุกคน</b> ที่อยู่ ไม่ว่าจะสอบปากคำได้แล้วหรือยัง "
    "เพราะถ้าไม่บอกว่ามีใครอยู่ ผู้เล่นจะไม่มีทางรู้ว่าสอบใครได้ "
    "ส่วนคนที่ยังคุยไม่ได้ กฎ R010 จะเป็นคนบอกเองว่าต้องหาหลักฐานอะไรก่อน"))

A(H2("9.3 offerable() กันไม่ให้เกมเฉลยตัวเอง"))
A(P("ฟังก์ชันนี้ตอบคำถามว่า เอ่ยชื่อสิ่งนี้ให้ผู้เล่นเห็นได้ไหม โดยไม่เฉลยของที่เขายังหาไม่เจอ "
    "app/main.py เรียกมันมากรอง alternatives ก่อนส่งกลับ"))
A(code("""
def offerable(self, target, state) -> bool:
    obj = self.world["objects"].get(target)
    if obj is None:
        return True                      # ตู้รถหรือคน เอ่ยได้เสมอ
    if target in state.inventory or target in state.discovered_evidence:
        return True                      # ถือหรือเจอแล้ว
    return obj.get("location") == state.current_location and self.decide(
        ParsedCommand(action=ActionType.EXAMINE, target=target, ...), state,
    ).allowed                            # อยู่ตรงหน้าและมองเห็นได้
"""))
A(P("ที่มาของฟังก์ชันนี้ ผู้เล่นพิมพ์ว่า ปลดทุกอย่าง ตั้งแต่ตาแรก แล้วชั้น neural "
    "ซึ่งเห็นตารางทั้งโลกใน prompt แต่ไม่รู้ว่าผู้เล่นเดินไปถึงไหน "
    "ตอบกลับมาเป็นรายชื่อของ 4 ชิ้นในตู้ที่ยังไม่เคยไป รวมถึง crew_key ที่ต้องคุยกับคนถึงจะได้ "
    "เท่ากับเกมเฉลยตัวเอง"))
A(P("แก้ที่ backend ไม่ใช่ที่ prompt เพราะกันได้แน่นอนกว่า ทดสอบได้โดยไม่ต้องเรียก LLM "
    "และคุมทุกหน้าเว็บที่จะมาต่อทีหลัง สังเกตว่ามันใช้ decide() ถามกฎเหมือนที่ look_around ทำ "
    "ของที่ซ่อนอยู่จึงไม่หลุด", "note"))

A(H2("9.4 closing_argument() ฉากจบที่ประกอบจากหลักฐานจริง"))
A(code("""
sus = self.world["suspects"].get(suspect_id, {})
found = _collect_pillars(suspect_id, state, self.world)

lines = [f"คุณเรียกทุกคนมารวมกันที่ตู้เสบียง แล้วชี้ไปที่{sus.get('name_th', suspect_id)}", ""]
for pillar in PILLARS:
    names = [self.world["objects"][e].get("name_th", e) for e in found[pillar]]
    lines.append(f"  {label[pillar]}")
    for n in names:
        lines.append(f"    - {n}")
"""))
A(P("คำแถลงปิดคดี <b>ไม่ใช่ข้อความสำเร็จรูป</b> ทุกบรรทัดอ้างชิ้นหลักฐานที่อยู่ใน "
    "discovered_evidence จริง ๆ ถ้าผู้เล่นสองคนเก็บหลักฐานคนละชุด ฉากจบจะออกมาคนละแบบ "
    "แม้จะกล่าวหาคนเดียวกันก็ตาม"))
A(P("นี่คือหลักการเดียวกับ reasoning_chain คือ <b>คำอธิบายต้องมาจากสิ่งที่เกิดขึ้นจริง "
    "ไม่ใช่ข้อความที่เขียนรอไว้</b> ต่างกันแค่ reasoning_chain อธิบายว่าทำไมระบบตัดสินแบบนั้น "
    "ส่วน closing_argument อธิบายว่าทำไมผู้ต้องสงสัยคนนี้ผิด"))

A(H2("9.5 pillar_status() สำหรับ UI และการวิเคราะห์"))
A(P("คืนความคืบหน้าสี่เสาของผู้ต้องสงสัยที่ระบุ มีคอมเมนต์กำกับไว้ว่าใช้สำหรับ UI "
    "และการวิเคราะห์ผล ไม่ใช่ส่วนของการตัดสิน เพื่อกันไม่ให้ใครเผลอเอาไปใช้ในเส้นทางตัดสินภายหลัง "
    "ในสาขา draft1 ตัว HUD ที่เคยแสดงข้อมูลนี้ถูกถอดออกแล้ว "
    "เพราะมันแอบบอกรายชื่อผู้ต้องสงสัยที่ผู้เล่นยังไม่ควรรู้"))

# ------------------------------------------------------------ 10
A(H1(f"10. ฉากจบ {N_END} แบบ เลือกจากหลักฐานที่ผู้เล่นหามาได้จริง"))
A(P("เกมนี้ไม่ได้มีแค่ชนะกับแพ้ การกล่าวหาทำได้เสมอ แต่จะได้ฉากจบแบบไหน "
    "ขึ้นกับว่าชี้ตัวใคร และตอนนั้นมีหลักฐานอะไรอยู่ในมือ"))
A(tbl([["ฉากจบ", "เงื่อนไข", "ปิดคดี"]] + [
    [e["title"], _ending_condition(e), "ใช่" if e["solved"] else "ไม่"]
    for e in world["endings"] if e.get("canon", True)
], [30, 55, 15]))
A(P(f"เอกสารเนื้อเรื่องกำหนดฉากจบไว้ {N_END} แบบ แต่ไม่ได้ระบุว่าถ้าผู้เล่นกล่าวหาคนที่ไม่มี "
    "เส้นเรื่องรองรับจะเกิดอะไรขึ้น ซึ่งเอนจินต้องมีคำตอบให้ทุกกรณี "
    f"จึงมีทางออกสำรองอีก {N_END_ALL - N_END} รายการในไฟล์ ทำเครื่องหมาย canon เป็น false ไว้ "
    "เพื่อไม่ให้ถูกนับปนกับฉากจบตามเนื้อเรื่อง", "note"))
A(P("ฉากจบทั้งหมดอยู่ใน story.json ไม่ได้เขียนตายในโค้ด "
    "<font face='MONO' size='8'>engine.ending_for()</font> ไล่เงื่อนไขจากบนลงล่างแล้วหยิบอันแรกที่เข้า "
    "ทุกเงื่อนไขอ่านจาก GameState กับ story.json เท่านั้น "
    "<b>ไม่มี LLM เกี่ยวข้อง</b> ฉากจบจึงตรวจย้อนกลับได้เหมือน reasoning_chain"))
A(P("จุดที่ออกแบบไว้ตั้งใจที่สุดคือความต่างระหว่างฉากจบที่ 1 กับที่ 8 "
    "ทั้งคู่คือการกล่าวหาผู้โดยสารคนที่แปดเหมือนกัน ต่างกันแค่ว่าตอนนั้น "
    "คดีต่อคนร้ายตัวจริงครบสี่เสาแล้วหรือยัง "
    "<b>ความผิดจึงไม่ได้อยู่ที่ชี้ผิดคน แต่อยู่ที่ชี้ผิดทั้งที่รู้</b> "
    "ซึ่งเป็นแก่นของเรื่องพอดี และเป็นเงื่อนไขที่เช็คได้จากสถานะล้วน ๆ"))

A(H2("10.1 ปิดคดีแล้วจบจริง"))
A(P("เมื่อ accuse ผ่าน ฉากจบถูกเลือกครั้งเดียวแล้วบันทึกลง "
    "<font face='MONO' size='8'>GameState.ending_id</font> "
    "จากนั้นกฎ R015 ซึ่งครอบทุก action จะปฏิเสธทุกคำสั่งต่อจากนั้น "
    "การปิดฉากจึงเป็นกฎที่โผล่ในสายเหตุผล ไม่ใช่เงื่อนไขที่ซ่อนอยู่ในโค้ด"))
A(code("""
        if cmd.action == ActionType.ACCUSE:
            # ฉากจบถูกเลือกที่นี่ครั้งเดียว แล้วบันทึกลง state เพื่อปิดคดี
            return {"ending": self.ending_for(cmd.target, state).get("id")}
"""))
A(P("ส่วนกรณีหมดเวลา ไม่มี ending_id เพราะผู้เล่นไม่ได้ชี้ตัวใคร "
    "R014 จึงเป็นตัวปิดเกมเอง และใช้ข้อความของฉากจบที่ 4 เป็นข้อความปฏิเสธ", "note"))

A(H2("10.2 คำสั่งเผา ทางเลือกที่ย้อนกลับไม่ได้"))
A(P("เนื้อเรื่องให้ผู้เล่นเลือกว่าจะเก็บ ทิ้งไว้ หรือเผารายงานเก่าของตัวเองทิ้ง "
    "จึงมี action burn เพิ่มเข้ามา เผาได้เฉพาะของที่มี burnable ในฉาก ตอนนี้มีชิ้นเดียว"))
A(tbl([
    ["ทางเลือก", "ทำยังไงในเกม", "ผลต่อฉากจบ"],
    ["เก็บไว้", "take", "เปิดทางไปฉากจบแท้"],
    ["ทิ้งไว้", "ไม่ต้องทำอะไร", "ได้ฉากจบที่หกแทน"],
    ["เผาทิ้ง", "burn", "ปิดทางฉากจบแท้ถาวร ของหลุดจากมือและตรวจอีกไม่ได้"],
], [18, 30, 52], mono=(1,)))
A(P("การไม่ทำอะไรไม่ใช่คำสั่ง จึงไม่มี action สำหรับมัน "
    "ผู้เล่นที่พิมพ์ว่าทิ้งมันไว้ตรงนั้นจะได้ unknown ซึ่งถูกแล้ว", "note"))

A(H1("11. app/main.py จุดที่สองชั้นมาต่อกัน"))
A(code("""
@app.post("/command", response_model=CommandResponse)
def handle_command(req: CommandRequest):
    # ขั้นที่ 1: NEURAL LAYER
    try:
        parsed = interpret(req.text, req.state)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neural Layer ตีความล้มเหลว: {e}")

    # ขั้นที่ 2: SYMBOLIC LAYER
    decision = engine.decide(parsed, req.state)

    # ขั้นที่ 3: STATE UPDATE
    new_state = apply_changes(req.state, decision.state_changes) if decision.allowed else req.state

    # กรองตัวเลือกไม่ให้เฉลยของที่ผู้เล่นยังหาไม่เจอ
    parsed.alternatives = [a for a in parsed.alternatives
                           if engine.offerable((a.split() or [""])[-1], req.state)]

    return CommandResponse(parsed=parsed, decision=decision, new_state=new_state)
"""))
A(P("ทั้งเกมมีทางเข้าทางเดียวคือฟังก์ชันนี้ และมันสั้นแค่นี้ "
    "ลำดับสามขั้นบังคับว่า neural ต้องทำงานเสร็จก่อนเสมอ "
    "และ symbolic ไม่เคยเห็นข้อความดิบของผู้เล่นเลย เห็นแค่ ParsedCommand ที่ถูกแปลงแล้ว"))
A(P("บรรทัด <span class=\"m\">if decision.allowed</span> คือจุดบังคับว่า "
    "<b>คำสั่งที่ถูกปฏิเสธจะไม่เปลี่ยนสถานะใด ๆ เลย</b> รวมถึงไม่กินเวลาด้วย "
    "ผู้เล่นพิมพ์ผิดจึงไม่เสียตาฟรี"))
A(H2("อีกสองปลายทางที่ใช้ engine โดยตรง"))
A(tbl([
    ["ปลายทาง", "ใช้อะไรจาก engine"],
    ["GET /health", "len(engine.rules) และจำนวน objects เพื่อยืนยันว่าโหลดไฟล์ข้อมูลสำเร็จ"],
    ["GET /scene", "engine.world ทั้งก้อน แต่คืนเฉพาะ id กับชื่อไทย "
                   "ไม่ส่ง description หรือเงื่อนไขออกไป"],
], [20, 80], mono=(0,)))

# ------------------------------------------------------------ 11
A(H1("12. ตัวอย่างการทำงานจริง"))
A(P("ทั้งสองตัวอย่างนี้เป็นผลลัพธ์ที่รันออกมาจริงจากโค้ดชุดปัจจุบัน ไม่ได้เขียนขึ้นเอง", "note"))

A(H2("12.1 คำสั่งที่ถูกปฏิเสธ"))
A(code(trace("move", "electrical_compartment", GameState())))
A(P("สังเกตว่าสายเหตุผลหยุดที่กฎแรกที่ไม่ผ่านทันที กฎที่เหลือไม่ถูกตรวจเลย "
    "และข้อความในวงเล็บคือค่า detail ที่ตัวตรวจคืนกลับมา ไม่ใช่ข้อความที่เขียนไว้ล่วงหน้า"))

A(H2("12.2 คำสั่งที่ผ่าน และผลต่อสถานะ"))
A(code(trace("interrogate", "mara_voss", GameState(), note="หลังส่งเข้า apply_changes()")))
A(P("ของที่ได้มาคือกุญแจพนักงาน มาจากฟิลด์ grants_object ของเธอใน story.json "
    "และมันคือกุญแจที่ปลดล็อกตู้ในตัวอย่างแรก ทั้งสองตัวอย่างจึงต่อกันเป็นเส้นทางเดียว", "note"))

A(H2("12.3 กล่าวหาทั้งที่หลักฐานไม่ครบ"))
A(code(trace("accuse", "elias_venn",
             GameState(discovered_evidence=["elias_button", "elias_ticket"]))))
A(P("<b>นี่คือจุดที่กฎแบบไม่บล็อกทำงาน</b> คำสั่งผ่าน แต่ R013 ถูกบันทึกว่าไม่ผ่าน "
    "พร้อมบอกว่าขาดหลักฐานด้านไหน แล้วฉากจบที่ได้ก็เป็นฉากจบที่ไม่นับว่าคลี่คลาย"))

A(H1("13. การทดสอบ ยืนยันว่าชั้นนี้ทำงานถูกจริง"))
A(P(f"ชั้น symbolic มีเทส {N_ENGINE_TESTS} ข้อใน tests/test_engine.py ทั้งหมด "
    "<b>รันได้โดยไม่ต้องมี API key</b> เพราะไฟล์นี้ไม่แตะ LLM เลย แบ่งได้เป็นสี่กลุ่ม"))
A(tbl([
    ["กลุ่ม", "ตรวจอะไร", "ตัวอย่าง"],
    ["กฎรายข้อ", "แต่ละกฎปฏิเสธในสถานการณ์ที่ควรปฏิเสธ และอนุญาตในสถานการณ์ที่ควรอนุญาต",
     "สอบปากคำคนที่อยู่คนละตู้ ต้องตกด้วย R005 และยืนตู้เดียวกันต้องผ่าน"],
    ["ความสอดคล้องของโครงสร้าง", "กฎทุกข้อต้องมีตัวตรวจจริง ลำดับกฎต้องไม่ถูกสลับ",
     "R014 ต้องอยู่ก่อนกฎของ accuse ไม่งั้นข้อความบอกสาเหตุผิด"],
    ["เกมเดินได้จนจบ", f"เดินตามเส้นทางเฉลย {N_STEPS} ขั้นใน walkthrough.json ต้องผ่านทุกขั้นและปิดคดีได้ในเวลา",
     "กันกฎที่ขัดกันเองจนเกมตัน ซึ่งเคยเกิดขึ้นจริงตอนเพิ่ม R005"],
    ["คุณภาพของฉาก", "ไล่ความสัมพันธ์ใน story.json เอง แล้วฟ้องถ้าฉากมีทางตัน",
     "หลักฐานที่ปลดล็อกของในตู้อื่น คำบรรยายต้องเอ่ยชื่อตู้นั้นด้วย"],
    ["ฉากจบทุกแบบไปถึงได้", "สร้างสถานะของแต่ละฉากจบแล้วยืนยันว่าได้ฉากนั้นจริง",
     "กันฉากจบที่เงื่อนไขขัดกันเองจนไม่มีวันเกิด ซึ่งมองด้วยตาไม่เห็น"],
], [20, 40, 40]))
A(P("กลุ่มที่สามคุ้มค่าที่สุด ตอนเพิ่มกฎ R005 ให้คุมการสอบปากคำ เทสกลุ่มนี้ล้มทันที 11 ข้อ "
    "เพราะเส้นทางเฉลยเดิมแอบอาศัยช่องโหว่ที่สอบปากคำข้ามตู้ได้อยู่ "
    "ถ้าไม่มีเทสชุดนี้ เกมจะเล่นไม่จบโดยไม่มีใครรู้ จนกว่าจะมีคนเล่นถึงจุดนั้น"))
A(P("กลุ่มที่สี่ก็จับบั๊กได้จริง มันไล่ทุกความสัมพันธ์ requires_evidence เองแล้วพบว่า "
    "มีหลักฐานสองชิ้นที่ปลดล็อกของในตู้อื่นโดยไม่บอกว่าตู้ไหน "
    "ซึ่งเป็นทางตันที่มองด้วยตาไม่เห็น"))

A(H1("14. สรุปสิ่งที่ควรจำ"))
A(tbl([
    ["ประเด็น", "รายละเอียด"],
    ["ไม่มี LLM ในชั้นนี้", "engine.py ไม่ import อะไรจาก app/neural บังคับด้วยโครงสร้าง ไม่ใช่แค่ข้อตกลง"],
    ["กฎเป็นข้อมูล", f"กฎ {N_RULES} ข้ออยู่ใน rules.json แก้ลำดับ เงื่อนไข หรือข้อความได้โดยไม่แตะโค้ด"],
    ["ฉากเป็นข้อมูล", "โลกทั้งใบอยู่ใน story.json เปลี่ยนคดีใหม่ได้โดยไม่แตะโค้ด"],
    ["สายเหตุผลซื่อตรง", "reasoning_chain ถูกสร้างระหว่างวนลูปตรวจกฎ จึงตรงกับสิ่งที่ทำจริงเสมอ"],
    ["ตัดสินแยกจากเปลี่ยนสถานะ", "decide() บอกว่าควรเปลี่ยนอะไร apply_changes() เป็นคนเปลี่ยนจริง "
                                  "และคืนก้อนใหม่เสมอ"],
    ["สิ่งที่เห็นเท่ากับสิ่งที่ทำได้", "look_around และ offerable ถามจากกฎชุดเดียวกับที่ใช้ตัดสิน "
                                        "ไม่มีรายการเขียนมือแยก"],
    ["เวลาเดินนอกคำตัดสิน", "เพื่อให้เปรียบเทียบสองโหมดของการทดลองได้อย่างเป็นธรรม"],
], [26, 74]))

CSS = """
@font-face { font-family: TH;   src: url(th.ttf); }
@font-face { font-family: TH;   src: url(thb.ttf); font-weight: bold; }
@font-face { font-family: MONO; src: url(mono.ttf); }
@font-face { font-family: MONO; src: url(monob.ttf); font-weight: bold; }

body { font-family: TH; font-size: 10pt; line-height: 165%; color: #1a1a1a; }
p { margin: 0 0 7pt 0; text-align: left; }
b { font-weight: bold; }

h1 { font-family: TH; font-weight: bold; font-size: 16pt; color: #1f4e79;
     margin: 0 0 9pt 0; line-height: 140%; }
h2 { font-family: TH; font-weight: bold; font-size: 11.5pt; color: #1a1a1a;
     margin: 13pt 0 5pt 0; line-height: 145%; }

.cover { margin: 90pt 0 26pt 0; }
.ct { font-family: TH; font-weight: bold; font-size: 26pt; color: #1f4e79; line-height: 140%; }
.cs { font-family: TH; font-size: 12pt; color: #5b6470; line-height: 165%; margin-top: 10pt; }

.note { font-size: 8.8pt; color: #5b6470; line-height: 155%; }

pre { font-family: MONO; font-size: 8pt; line-height: 145%;
      background-color: #f5f6f8; border: 0.6pt solid #d5d9de;
      padding: 7pt; margin: 4pt 0 9pt 0; color: #1a1a1a; }

.m { font-family: MONO; font-size: 8.6pt; }

table { width: 100%; margin: 3pt 0 9pt 0; }
th { font-family: TH; font-weight: bold; font-size: 8.8pt; background-color: #eef1f4;
     border: 0.6pt solid #c9cfd6; padding: 4pt 5pt; text-align: left; line-height: 150%; }
td { font-family: TH; font-size: 8.8pt; border: 0.6pt solid #d5d9de;
     padding: 4pt 5pt; text-align: left; line-height: 155%; }
td.m, th.m { font-family: MONO; font-size: 8pt; }

.pb { }
"""

def wrap(inner):
    return f"<html><head><style>{CSS}</style></head><body>{inner}</body></html>"


# แบ่งเป็นหัวข้อ แล้วสั่งขึ้นหน้าใหม่เองทีละหัวข้อ
# ไม่ใช้ page-break-before ของ CSS เพราะ PyMuPDF วนไม่จบถ้าเจอมันตั้งแต่ต้นหน้า
sections, cur = [], []
for chunk in B:
    if chunk.startswith("<h1>") and cur:
        sections.append(cur)
        cur = []
    cur.append(chunk)
sections.append(cur)

(HERE / "doc.html").write_text(wrap("".join(B)), encoding="utf-8")

os.chdir(HERE)
archive = pymupdf.Archive(".")
writer = pymupdf.DocumentWriter(str(OUT))
page_rect = pymupdf.paper_rect("a4")
area = page_rect + (57, 51, -57, -57)   # ขอบ 20 มม. บน 18 มม.
pages = 0
for sec in sections:
    story = pymupdf.Story(html=wrap("".join(sec)), archive=archive)
    more = 1
    while more and pages < 60:
        dev = writer.begin_page(page_rect)
        more, _ = story.place(area)
        story.draw(dev)
        writer.end_page()
        pages += 1
writer.close()

# เลขหน้า
doc = pymupdf.open(OUT)
for i, page in enumerate(doc):
    if i == 0:
        continue
    page.insert_text((page.rect.width - 60, page.rect.height - 36), str(i + 1),
                     fontname="helv", fontsize=8.5, color=(0.36, 0.39, 0.44))
    page.draw_line((57, page.rect.height - 44), (page.rect.width - 57, page.rect.height - 44),
                   color=(0.84, 0.86, 0.88), width=0.5)
doc.saveIncr()
print(f"สร้างแล้ว {OUT}  {pages} หน้า ({len(sections)} หัวข้อ)  {OUT.stat().st_size} bytes")
