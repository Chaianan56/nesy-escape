# สิ่งที่ยังต้องทำ — NeSy-Escape

> อัปเดตจากสถานะจริงบน branch `main` commit ล่าสุด (51 commits)
> ตอนนี้: ตู้รถไฟ 6 ตู้ | กฎ 11 ข้อ | หลักฐาน 34 ชิ้น | ข้อสรุป 18 ข้อ | ฉากจบ 6 แบบ
> เทส Python 250 ข้อ (245 unit tests ผ่าน 100%, 5 LLM markers) และเทสหน้าเว็บ Node 37 ข้อ ผ่านหมด 100%
> เล่นจบจริงแล้วบนหน้าเว็บ พิมพ์ไทยและปุ่มคำสั่งผ่าน Neural-Symbolic เก็บหลักฐานครบ 34 ชิ้น
> เสาครบ 4 จาก 4 ปิดคดีได้ฉากจบแท้ (True Ending) พร้อมฉากย้อนหลัง Reconstruction

---

## สถานะงาน Frontend (ผสานเข้า main แล้ว 100%)

branch `frontend` ได้รับการผสาน (Merge) เข้าสู่ `main` อย่างสมบูรณ์แล้ว พร้อมคุณสมบัติต่อไปนี้:

1. **Zero-Hallucination Policy**: กำจัดตัวจำลองที่แต่ง reasoning chain ปลอมออกทั้งหมด หาก Backend เชื่อมต่อไม่ได้จะรายงานข้อผิดพลาดตรงไปตรงมา ไม่มีการแต่งรหัสกฎย้อนหลัง
2. **Server-Owned Sessions**: ควบคุมสถานะเกมที่ Backend 100% ผ่าน Session Cookie ป้องกันการโกงสถานะจากฝั่ง Client
3. **Stylized Art & Novel Scenes**: มีภาพประกอบหลักฐาน ฉากเหตุการณ์ และระบบเล่าเรื่องสไตล์นิยายภาพ (`frontend/novel.js`, `frontend/art.js`, `frontend/narrative.js`)
4. **Case Board & Evidence Journal**: กระดานสำนวนคดีและสมุดบันทึกหลักฐานตามสเปก 4 เสา
5. **Confirmation Recovery & Timeout Handling**: ป้องกันการส่งคำสั่งซ้ำ, มีปุ่มกดยืนยันการกระทำสำคัญ และแสดงผลฉากจบเมื่อหมดเวลาอย่างถูกต้องในหน้าต่างเดียวกัน
6. **Smart Sequential Execution**: ประมวลผลคำสั่งพ่วงหรือคำสั่งต่อเนื่องได้จบครบในลูปเดียว

---

## งานฝั่งระบบและงานวิจัยที่เพิ่มเข้ามาล่าสุด (เสร็จสมบูรณ์แล้ว)

### 1. Player Behavior Profiler & Dynamic Adaptation (`app/profiler/`)
- ตรวจจับและวิเคราะห์พฤติกรรมผู้เล่นออกเป็น **5 Archetypes**:
  - `Forensic Analyst` (เน้นตรวจหลักฐานกายภาพ ละเอียดรอบคอบ)
  - `Psychological Interrogator` (เน้นสอบเค้นพยานและผู้ต้องสงสัย)
  - `Maverick Trailblazer` (เน้นสำรวจสถานที่ เดินทางข้ามตู้)
  - `Intuitive Rusher` (เน้นสรุปผลและกล่าวหาอย่างรวดเร็ว)
  - `Balanced Investigator` (สืบสวนอย่างสมดุลรอบด้าน)
- **Dynamic Adaptation Engine**: ปรับเปลี่ยนน้ำเสียงและท่าทีของ NPC ตาม Archetype และแทรก Contextual Scaffolding ช่วยเหลือเมื่อผู้เล่นเกิดสภาวะติดขัด (Stuck Detection)
- **Research Telemetry & Export**: บันทึกข้อมูลสถิติเชิงปริมาณสำหรับงานวิจัย พร้อม Endpoint ดาวน์โหลดไฟล์ JSON/CSV (`/profiler/profile`, `/research/telemetry`, `/research/export`)

### 2. Dynamic Entity Pruning & Latency Optimization
- ตัดทอนทะเบียน Entity ใน Prompt ส่งเฉพาะตู้รถไฟที่ผู้เล่นยืนอยู่ ช่วยลด Token Consumption และ Latency ของ Gemini ลงกว่า 30-50%
- มีชุดสคริปต์ Benchmark ตรวจวัดผลใน `scripts/benchmark_pruning.py` และ `scripts/evaluate_neural_parser.py`

### 3. Typed Direct Commands & Baseline Neural Engine
- เพิ่มระบบคำสั่งพิมพ์ตรง (`app/neural/typed_commands.py`) ตอบสนองการตรวจฉากและเดินข้ามตู้ได้ทันทีแบบ Zero-latency
- เพิ่มตัวประเมินผลเปรียบเทียบ `Neural-only Game Master` (`app/neural/game_master.py`) ทดสอบกับคลังคำตัดสิน `data/research/adjudication-corpus-v1.json` สำหรับใช้ในรายงานวิจัย

---

## งานฝั่งระบบ

### 1. เทสที่เรียก LLM จริง — ทำแล้ว

`tests/test_neural.py` มี 5 ข้อที่ยิง Gemini จริง มาร์กไว้ด้วย `llm`
ไม่มีคีย์ก็ข้ามเองอัตโนมัติ เรียกไม่ได้ก็ข้าม ไม่ฟ้องว่าโค้ดพัง

| เทส | ยืนยันอะไร |
|---|---|
| `test_a_plain_thai_sentence_grounds_to_an_id_that_exists` | ภาษาไทยจริงออกมาเป็น id ที่มีในทะเบียน |
| `test_a_thai_command_plays_all_the_way_through_to_a_decision` | เดินครบท่อ interpret ถึง apply_changes |
| `test_intent_is_extracted_even_when_the_action_breaks_a_rule` | เจตนาผิดกฎยังถูกสกัด แล้ว symbolic เป็นคนปฏิเสธ |
| `test_a_prompt_injection_never_becomes_a_playable_command` | คำสั่งหลอกระบบออกมาเป็น unknown |
| `test_two_actions_in_one_sentence_come_back_as_separate_steps` | สั่งพ่วงแตกเป็นขั้นที่ id ถูกต้องทุกขั้น |

เพิ่ม `tests/test_api.py` อีก 9 ข้อ ทดสอบเส้นทาง HTTP จริงโดยสวม `interpret()` ด้วยตัวปลอม
จับสิ่งที่ `test_engine.py` จับไม่ได้ เช่น ชั้น neural ล้มแล้ว API ตอบอะไร
และตัวเลือกที่ยื่นกลับไปเฉลยของที่ผู้เล่นยังหาไม่เจอหรือเปล่า

อยากรันเร็วๆ ตอนแก้โค้ดโดยไม่กินโควตา: `pytest -m "not llm"`

### 2. สเปกยังทำไม่ครบสามข้อ

| ข้อ | เนื้อหา | สถานะ |
|---|---|---|
| R-SYS-02 | player claim ไม่ใช่ fact | ยังไม่มี action ให้เสนอสมมติฐาน พิมพ์ว่า วินเซนต์ฆ่าแคสเซียน จะได้ `unknown` |
| R-SYS-04 | ขอบเขตความรู้ของ NPC | `testimony` เป็นข้อความเดียวตายตัว ไม่ได้กรองว่าใครควรรู้อะไร |
| R-SYS-05 | discovered ไม่เท่ากับ identified ไม่เท่ากับ linked | เจอของแล้วถือว่ารู้ทันที ไม่มีขั้น ยังไม่รู้ว่าเป็นของใคร |

ทั้งสามข้อต้องเพิ่ม action หรือเพิ่มสถานะ กระทบทั้งระบบ
แนะนำให้ทำหลังเนื้อเรื่องนิ่งแล้ว และควรตัดสินใจร่วมกันก่อนว่าจะเอาข้อไหน

### 3. action สี่ตัวที่ไม่มีกฎคุม — ทำแล้ว

เพิ่มกฎ `R007_ACTION_SUPPORTED` คุม `take` `use` `unlock` `burn`
และเติม `burn` เข้า `applies_to` ของ `R005_SAME_LOCATION` ที่เดิมตกหล่นไป
(เผาของข้ามขบวนได้โดยไม่ต้องเดินไปหา)

กฎอ่านจากฟิลด์ `supports` ของแต่ละ object ใน `story.json` ฉากนี้ไม่มีชิ้นไหนประกาศไว้เลย
สี่คำสั่งนั้นจึงถูกปฏิเสธหมด ซึ่งตรงกับความจริงของคดี ทุกอย่างเป็นหลักฐานที่ดูได้อย่างเดียว

**ไม่ได้ลบ action ทิ้ง** เพราะหน้าที่ของชั้น neural คือสกัดเจตนาให้ได้ก่อน
แล้วให้ชั้น symbolic เป็นคนปฏิเสธพร้อมบอกว่าติดกฎข้อไหน
ถ้าลบออกจาก `ActionType` การปฏิเสธจะย้ายไปอยู่ที่ LLM ซึ่งเป็นสิ่งที่งานนี้ตั้งใจไม่ให้เกิด

วันไหนฉากอยากมีของที่หยิบได้จริง เติมแบบนี้ลง `story.json` พอ ไม่ต้องแก้โค้ด

```json
"gideon_signet_ring": { "supports": ["take"] }
```

ระหว่างตรวจเรื่องนี้เจอด้วยว่า prompt สอน id ที่ไม่มีอยู่จริง
เงื่อนไขคัดตัวอย่างอ้างฟิลด์ `takeable` กับ `locked` ที่ฉากนี้ไม่มี จึงไม่มีตัวไหนผ่าน
แล้วค่า `None` ถูกเอาไปต่อเป็นสตริง กลายเป็นสอน LLM ว่ามีของชื่อ None อยู่บนขบวน 15 บรรทัด
แก้ให้เงื่อนไขอ้าง `supports` กับ `restricted` ที่มีจริง และมีเทสกันไว้แล้ว

### 3.5 สองเรื่องที่ตัดสินใจแล้ว ไม่ต้องแก้

**นาฬิกาเดินตามเวลาจริง** `app/game_clock.py` คิด `elapsed_seconds` จาก `started_at`
ไม่ได้บวกเวลาต่อหนึ่งตาแล้ว เวลาที่รอ Gemini ตอบจึงกินเวลาผู้เล่นไปด้วย
ตั้งใจให้กดดันแบบเรียลไทม์ 90 นาทีเหลือเฟือสำหรับ 34 ขั้น (เล่นจริงหมดไป 5 นาที)

**`unproven` ไปไม่ถึงแล้ว** `_accusation_ready` นับเฉพาะฉากจบที่ `accuse` ตรงชื่อคนที่ถูกชี้
ตัว `accuse: "*"` จึงไม่เคยถูกนับ และ R012 จะปฏิเสธก่อนตกมาถึงมัน
ตั้งใจ ไม่ให้การกล่าวหาที่ไม่มีหลักฐานรองรับกลายเป็นฉากจบที่เล่นได้
ตัวข้อมูลยังอยู่ใน story.json เผื่อเปลี่ยนใจทีหลัง แต่ตอนนี้ถือว่าฉากจบที่เล่นถึงมี 5 เส้น

### 4. เอกสารในเกมยังไม่ถูกใช้หนึ่งไฟล์

`data/documents/` มีสามไฟล์ ผูกกับของในเกมแล้วสองไฟล์

| ไฟล์ | ผูกกับ |
|---|---|
| `burnt_memo_fragment.md` | `burnt_folder_c` |
| `autopsy_report.md` | `secret_file` |
| `voss_telegram_draft.md` | **ยังไม่ได้ผูกกับอะไร** |

ตัวโทรเลขของวอสส์เป็นหลักฐานสำคัญในเนื้อเรื่อง 1923 แต่ตอนนี้ผู้เล่นเข้าไม่ถึงเลย
ต้องตัดสินใจว่าจะให้เจอที่ไหน หรือจะไม่ใช้

---

## งานที่ต้องทำในหน้าเว็บ Render

Render ยัง auto-deploy จาก branch `draft1` ซึ่งเป็นฉากเก่าทั้งหมด
กฎ 18 ข้อ ผู้ต้องสงสัย 7 คน คนละคดีกับที่ทำอยู่ตอนนี้

1. เข้า Render แล้วเปลี่ยน Settings ให้ deploy จาก `main`
2. ตรวจว่า `GEMINI_API_KEY` ยังอยู่ในหน้า Environment
3. รอ deploy แล้วเปิดลิงก์เช็กว่าขึ้นฉากใหม่
4. เสร็จแล้วค่อยลบ branch `draft1` ทิ้ง

---

## บทพูดตัวละคร

ตอนนี้มีบทพูดครบสามคนแล้ว เกมจึงเล่นได้เต็มระบบ
แต่เป็นชุดที่เขียนไว้ให้ระบบเดินได้ก่อน **เปลี่ยนทับได้ทันที**

ถ้าจะเขียนใหม่ อ่านข้อกำหนดใน `docs/dialogue_brief.md`
แก้แค่ฟิลด์ `testimony` ของแต่ละคนใน `data/story.json` ไม่กระทบตรรกะเลย
เพราะหลักฐานผูกกับ `grants_evidence` ซึ่งแยกจากตัวข้อความ

**ข้อบังคับสองข้อ** มีเทสคอยตรวจอยู่
- ทุกคนต้องมี `testimony` และต้องไม่ตกไปใช้ข้อความสำรอง
- บทพูดห้ามเอ่ยชื่อเต็มของหลักฐานที่ตัวเองไม่ได้ให้ ไม่งั้นตัวละครเฉลยเกมแทนผู้เล่น

---

## วิธีเช็กว่าของตัวเองไม่พัง

```bash
git pull
python -m pytest -m "not llm" -q
node --test frontend/chat.test.mjs frontend/art.test.mjs frontend/novel.test.mjs
```

ต้องได้ 245 passed (5 skipped สำหรับ LLM marker) และ node tests 37 pass 100% ถ้าแดงแปลว่าของที่แก้ไปชนกับส่วนอื่น
(ไม่ได้ตั้ง `GEMINI_API_KEY` ข้อที่เรียก Gemini จริง 5 ข้อจะขึ้น skipped ซึ่งถือว่าปกติ)

เทสที่ควรรู้จักไว้สามข้อ เพราะมันจับปัญหาที่มองด้วยตาไม่เห็น

| เทส | จับอะไร |
|---|---|
| `test_a_player_who_only_reads_the_game_can_finish` | จำลองคนเล่นที่รู้เท่าที่เกมบอก ถ้าเพิ่มหลักฐานแล้วลืมเขียนเบาะแสชี้ทาง ข้อนี้จะแดง |
| `test_every_deduction_needs_all_of_its_evidence` | ถ้าเผลอทำให้สรุปได้ทั้งที่หลักฐานไม่ครบ |
| `test_only_the_culprit_can_ever_close_the_case` | ถ้าเผลอทำให้คนที่ไม่ใช่คนร้ายปิดคดีได้ |

