# Final Demo Payload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ชุดคำสั่งเดโม 12–15 คำสั่งตามเส้นเรื่อง 9 จังหวะ ที่ตรวจแล้วว่าวิ่งผ่านทางที่ตั้งใจ (Gemini หรือตัวแปลในเครื่อง) และให้ผลตามที่คาดในเกมจริง

**Architecture:** เก็บชุดคำสั่งเป็นข้อมูลไฟล์เดียวที่ทั้งเทสและสคริปต์ตรวจก่อนเดโมอ่านร่วมกัน เทสออฟไลน์ตรึงเส้นทางของแต่ละคำสั่งโดยไม่เรียก Gemini สคริปต์ `--live` เล่นทั้งชุดผ่าน `/command` ด้วย Gemini จริงเพื่อยืนยันผลและใช้เป็นการซ้อมก่อนขึ้นเวที เอกสารสคริปต์สำหรับผู้นำเสนอเขียนจากผลรันจริง

**Tech Stack:** Python 3, FastAPI `TestClient`, pytest, `app/neural/typed_commands.py`, Gemini ผ่าน `app/neural/gemini_client.py`

**Spec:** `docs/superpowers/specs/2026-11-17-final-demo-payload-design.md`

## Global Constraints

- 12–15 คำสั่ง ใช้เวลาเล่นสดรวมไม่เกิน 10 นาที
- คำสั่งส่วนใหญ่ผ่าน Gemini; ผ่านตัวแปลในเครื่องได้บางคำสั่ง แต่ทุกคำสั่งต้องประกาศเส้นทางไว้และเทสต้องตรงกับที่ประกาศ
- การถามตัวละครเป็นคำสั่งเดี่ยว; คำสั่งพ่วงใช้กับการเดินและการตรวจของ
- เริ่มจากสถานะเริ่มเกมปกติของคดี A (`data/story.json`, ตู้ 5 กับกิเดียน)
- ตัดจบที่จังหวะ 9 (ถามกิเดียนเรื่องข่าวเลื่อนนัด) ห้ามกล่าวหาให้คดีปิด และห้ามมีข้อความที่บอกตรงๆ ว่ากิเดียนเป็นคนร้าย
- สคริปต์ live เว้นอย่างน้อย 5 วินาทีระหว่างคำสั่ง (ตามแนวที่ `docs/natural-rollout-guide.md` ใช้) เพื่อไม่ชนโควตาฟรี
- ไม่แก้โค้ดเกม ถ้าเจอบั๊กให้จดไว้ในเอกสารสคริปต์และเลือกถ้อยคำเลี่ยง

## Review Focus

- Gemini ตีความคำสั่งเดิมต่างไปในวันเดโม (temperature 0 แต่โมเดลอาจเปลี่ยน) → ทุกจังหวะต้องมีคำสั่งสำรองที่ตรวจแล้ว (Task 1 เทสเส้นทางของคำสั่งสำรองด้วย)
- Gemini ล่มหรือโควตาหมดวันเดโม → สคริปต์ live ต้องหยุดพร้อมบอกว่าเป็นปัญหาบริการ ไม่ใช่รายงานว่าผลผิด (Task 2)
- คำสั่งในจังหวะหลังพึ่งสถานะจากจังหวะก่อน (เช่นนาฬิกาพกต้องตรวจร่างก่อน) → สคริปต์ live ต้องรันต่อเนื่องในเซสชันเดียวและหยุดที่ขั้นแรกที่ผลไม่ตรง (Task 2)
- เวลาในเกมจริงนับตามนาฬิกาจริง ถ้าผู้นำเสนอพูดนานคดีอาจใกล้หมดเวลา → 90 นาทีเหลือเฟือ แต่บันทึกเวลาที่ใช้จริงลงเอกสาร (Task 3)
- คำสั่งหลอกระบบ (จังหวะ 7) ต้องไม่เปลี่ยนสถานะเกม → เทส live ตรวจว่า `new_state` เท่าเดิม (Task 2)

---

### Task 1: ข้อมูลชุดคำสั่ง + เทสเส้นทางออฟไลน์

**Files:**
- Create: `data/demo/final_demo_payload.json`
- Test: `tests/test_demo_payload.py`

**Interfaces:**
- Produces: ไฟล์ JSON รูปแบบ
  `{"case_id": "case_01_gideon", "steps": [{"beat": int, "text": str, "route": "gemini"|"typed", "expect": {...}, "fallback": [{"text": str, "route": ...}]}]}`
  โดย `expect` มีได้: `"action"` (ค่า `ActionType`), `"target"`, `"topic"`, `"allowed"` (bool), `"sequence"` (bool), `"state_unchanged"` (bool), `"evidence_add"` (list ของ evidence id ที่ต้องปรากฏใน `discovered_evidence` หลังขั้นนี้)
  ตรวจค่า `case_id` จริงจาก `app/cases.py` ก่อนเขียน

- [ ] **Step 1: เขียนเทส**

```python
def test_payload_fits_demo_budget():           # 12 <= len(steps) <= 15, beats ครอบ 1..9 ครบ
def test_every_declared_route_matches_parser(): # parse_typed_command(text, state_at_step, world) is None  <=>  route == "gemini"
def test_fallbacks_route_as_declared():         # เหมือนข้อบน สำหรับทุก fallback
def test_most_commands_go_to_gemini():          # นับ route == "gemini" > ครึ่งหนึ่งของ steps
def test_no_step_closes_the_case():             # ไม่มี expect.action == "accuse" ที่ expect.allowed เป็น True
```

`state_at_step` ใช้ `GameState` เริ่มต้นของคดี ยกเว้นคำสั่งที่ตัวแปลในเครื่องอาจเปลี่ยนผลตามตำแหน่ง ให้ตั้ง `current_location` ตามตู้ที่ผู้เล่นอยู่ในจังหวะนั้น (เก็บเป็นฟิลด์ `"location"` ของแต่ละ step)

- [ ] **Step 2: รันให้เทสพังก่อน** — `.venv/Scripts/python.exe -m pytest tests/test_demo_payload.py -q` คาดว่า FAIL เพราะยังไม่มีไฟล์ข้อมูล

- [ ] **Step 3: เขียน `data/demo/final_demo_payload.json`** ตามโครง 9 จังหวะใน spec ร่างถ้อยคำภาษาไทยที่เป็นธรรมชาติ จังหวะ 2 ต้องมีคำสั่งพ่วงอย่างน้อยหนึ่งคำสั่ง (`expect.sequence: true`), จังหวะ 4 เป็นคำกล่าวหาที่คาดว่า `allowed: false`, จังหวะ 6 คาด `action: "ambiguous"` และ `sequence: false`, จังหวะ 7 คาด `action: "unknown"` และ `state_unchanged: true`, จังหวะ 9 คาด `action: "interrogate"`, `target: "gideon_hart"`, `topic: "message"` เป้าหมาย/หัวข้อเอาจาก `data/story.json` (เช่น `car_attendant` topic `service`, `dr_liora_venn` topic `examination`)

- [ ] **Step 4: รันเทสให้ผ่าน** — คำสั่งเดิม คาดว่า PASS ถ้าคำสั่งไหนโดนตัวแปลในเครื่องดักทั้งที่อยากให้ไป Gemini ให้ปรับถ้อยคำ ไม่ใช่ปรับ route

- [ ] **Step 5: Commit** — `git commit -m "test: add final demo payload with offline routing checks"`

---

### Task 2: สคริปต์เล่นทั้งชุดกับ Gemini จริง

**Files:**
- Create: `scripts/run_demo_payload.py`

**Interfaces:**
- Consumes: `data/demo/final_demo_payload.json` จาก Task 1
- Produces: `python scripts/run_demo_payload.py [--live] [--gap 5]` พิมพ์ผลรายขั้น: เวลา, เส้นทางจริง (`parsed.parser_mode`), action/target/topic, allowed, rule ที่ปฏิเสธ, หลักฐานที่เพิ่ม และ `OK`/`MISMATCH`; exit code 0 เมื่อทุกขั้นตรง, 1 เมื่อผลไม่ตรง, 2 เมื่อบริการ Gemini ขัดข้อง (`/command` ตอบ 502)

- [ ] **Step 1: เขียนสคริปต์** ใช้ `fastapi.testclient.TestClient(app.main.app)` เรียก `/scene` (และ `/new-game` พร้อม case ถ้า Task 1 ต้องเลือกคดี ดูพารามิเตอร์จริงใน `app/main.py:241`) แล้วส่ง `/command` ทีละขั้นในเซสชันเดียว เทียบ `expect` แต่ละช่องกับ `CommandResponse` ถ้าได้ 502 ให้หยุด exit 2 พร้อมข้อความว่าเป็นปัญหาบริการ ไม่มี `--live` ให้รันเฉพาะขั้น `route: "typed"` (ไม่ใช้โควตา) เว้น `--gap` วินาทีระหว่างคำสั่งที่ไป Gemini

- [ ] **Step 2: รันแบบไม่ live** — `.venv/Scripts/python.exe scripts/run_demo_payload.py` คาดว่าขั้น typed ทั้งหมด `OK`

- [ ] **Step 3: รันแบบ live หนึ่งรอบ** — `.venv/Scripts/python.exe scripts/run_demo_payload.py --live` คาดว่า exit 0 ถ้า `MISMATCH` ให้ลองคำสั่งสำรองของขั้นนั้น หรือปรับถ้อยคำแล้วกลับไปผ่าน Task 1 Step 4 ก่อน ถ้าการถามตัวละครในคำสั่งพ่วงกลายเป็นใช้ได้ (server มี `execute_sequence` ใน `app/main.py:635`) ให้จดไว้ แต่คงข้อกำหนดเดิม ถ้า exit 2 รอแล้วรันใหม่ อย่าวนยิงซ้ำติดกัน

- [ ] **Step 4: รัน live ซ้ำอีกหนึ่งรอบ** ยืนยันว่าผลนิ่ง (Gemini temperature 0) จดขั้นที่ผลต่างระหว่างสองรอบ

- [ ] **Step 5: Commit** — `git commit -m "feat: add live demo payload runner"`

---

### Task 3: เอกสารสคริปต์สำหรับผู้นำเสนอ

**Files:**
- Create: `docs/final-demo-script-2026-11-17.md`

**Interfaces:**
- Consumes: ผลรัน live สองรอบจาก Task 2

- [ ] **Step 1: เขียนเอกสาร** แต่ละขั้นเป็นรายการลำดับเลข (ไม่ใช้ตาราง) มี: จังหวะ, ข้อความที่พิมพ์ (ใน code block ให้คัดลอกได้), เส้นทาง, ผลที่ควรเห็นบนจอ, ประโยคสั้นที่ผู้นำเสนอพูด (หนึ่งบรรทัด), คำสั่งสำรอง หัวเอกสารมีวิธีซ้อมด้วย `scripts/run_demo_payload.py --live` เช้าวันเดโม เวลาที่ใช้จริงจากผลรัน และแผนสำรองตอน Gemini ล่ม: ใช้คำสั่ง typed ในชุดเล่นต่อ + อธิบายด้วยหน้าจอสายเหตุผล และเตรียมวิดีโอบันทึกการรันจริงไว้ล่วงหน้า

- [ ] **Step 2: ตรวจเอกสารกับไฟล์ข้อมูล** — ทุกข้อความในเอกสารต้องตรงกับ `data/demo/final_demo_payload.json` ตัวต่อตัว (เทียบด้วยสคริปต์สั้นหรือ grep)

- [ ] **Step 3: Commit** — `git commit -m "docs: add final demo presenter script"`
