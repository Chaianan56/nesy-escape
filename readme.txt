NeSy-Escape — Neuro-Symbolic Escape Room (นอกเทิร์นเอกซ์เพรส)
===========================================================

โครงสร้าง
    app/schemas.py           สัญญากลางระหว่างสองเลเยอร์ (แก้ต้องตกลงกันทั้งทีม)
    app/neural/              ตีความภาษาธรรมชาติ -> ParsedCommand   (Gemini + fallback)
    app/symbolic/engine.py   ตัดสินตามกฎ -> Decision               (ไม่เรียก LLM เด็ดขาด)
    app/scenario.py          สร้าง GameState ณ checkpoint ของเส้นทางเฉลย
    app/main.py              ท่อเชื่อม + FastAPI endpoints
    play.py                  โหมดเล่นในเทอร์มินัล
    run_experiment.py        รันการทดลองเปรียบเทียบโหมด A กับ B

    data/rules.json          กฎทั้งหมด แก้กฎที่นี่ ไม่แก้ในโค้ด
    data/story.json          โลกของเกม แก้ id ที่นี่ที่เดียว ทั้งสองเลเยอร์อ่านไฟล์นี้
    data/walkthrough.json    เส้นทางเฉลย + checkpoint ใช้ร่วมกันระหว่างเทสกับการทดลอง
    data/commands.json       ชุดคำสั่งทดสอบ 122 ข้อ (A/B/C/D)

ติดตั้งและรัน
    pip install -r requirements.txt
    cp .env.example .env          # ใส่ GEMINI_API_KEY ใน .env เท่านั้น ห้ามใส่ใน .env.example
    uvicorn app.main:app --reload
    เอกสาร API: http://127.0.0.1:8000/docs

เล่นและทดสอบ
    python play.py                 พิมพ์ภาษาไทยเล่นในเทอร์มินัล เห็น reasoning chain ทุกกฎ
    python -m pytest -v            ชุดทดสอบทั้งหมด (ไม่ต้องใช้ LLM ยกเว้นบางข้อที่ skip เอง)

รันการทดลอง
    python run_experiment.py                 รันทั้ง 122 คำสั่ง เข้าทั้งสองโหมด
    python run_experiment.py --group A B     เลือกเฉพาะบางกลุ่ม
    python run_experiment.py --limit 10      ลองสิบข้อแรกก่อน
    python run_experiment.py --rpm 10        ลดจังหวะลงถ้าชนโควตาบ่อย
    python run_experiment.py --report-only   สรุปจาก cache เดิม ไม่เรียก LLM เลย

    ผลออกที่ logs/<เวลา>_mode_A.jsonl และ _mode_B.jsonl (หนึ่งบรรทัดต่อคำสั่ง เข้า pandas ได้ตรง)
    ผลจาก LLM ถูก cache ไว้ที่ logs/llm_cache.json รันซ้ำเพื่อแก้การวิเคราะห์จึงไม่กินโควตาอีก
    ถ้าหยุดกลางคัน รันคำสั่งเดิมซ้ำได้ จะเริ่มต่อจากจุดที่ค้าง

ชุดคำสั่งทดสอบ (data/commands.json)
    A = ถูกกฎ      30 ข้อ   expected_allowed = true
    B = ผิดกฎ      32 ข้อ   expected_allowed = false + ระบุกฎที่ควรถูกละเมิด (ครอบคลุม 14/15 กฎ)
    C = หลอกระบบ   30 ข้อ   ควรถูกจับเป็น unknown ที่ชั้น neural
    D = กำกวม      30 ข้อ   ควรถูกจับเป็น ambiguous ที่ชั้น neural

    ground truth ของกลุ่ม A/B ไม่ใช่ความเห็น — tests/test_dataset.py ตรวจทุกข้อกับ
    symbolic engine ทุกครั้งที่รันเทส ถ้า label ไหนไม่ตรงกับกฎจริงจะฟ้องทันที

⚠️ ข้อควบคุมของการทดลอง (ห้ามละเมิด ไม่งั้นผลชี้กลับไปที่สถาปัตยกรรมไม่ได้)
    1. เรียก interpret() ครั้งเดียวต่อคำสั่ง แล้วใช้ ParsedCommand ตัวเดียวกันทั้งสองโหมด
       ถ้าเรียกแยก ความแปรปรวนจากการสุ่มของ LLM จะกลายเป็นตัวแปรที่สอง
    2. NEURAL_STRICT=1 เสมอ (run_experiment.py ตั้งให้อัตโนมัติ)
       ปกติถ้าเรียก Gemini ไม่สำเร็จ ระบบจะเงียบๆ ตกไปใช้ fallback heuristic ทำให้ log
       ปนผลของสองระบบโดยไม่มีอะไรบอกว่าแถวไหนเป็นของใคร strict mode จะหยุดและฟ้องแทน
    3. ทุกคำสั่งถูกยิงจากสถานะที่ควบคุมไว้ (checkpoint) ทั้งสองโหมดเห็นสถานะเดียวกันเป๊ะ
    4. คำสั่งพ่วงหลายขั้นถูกแตกให้เลือกทีละขั้นที่ชั้น UI ไม่ใช่ที่ schema
       เพื่อรักษาหน่วยวัด 1 คำสั่ง = 1 คำตัดสิน = 1 บรรทัด log
       ถ้าเปลี่ยนเป็นรันรวดเดียว สองโหมดจะเดินไปคนละสถานะกลางประโยค และการเปรียบเทียบ
       จะไม่ใช่การควบคุมตัวแปรอีกต่อไป

โควตา free tier
    gemini-3.5-flash-lite จำกัด 15 request/นาที รันเต็มชุด = 244 calls ราว 18 นาที
    เกินโควตาแล้วถูกปฏิเสธ (429) ไม่ได้ถูกเรียกเก็บเงิน ถ้าไม่ได้ผูก billing ไว้เอง

Endpoints สำหรับ frontend
    GET  /health    สถานะระบบ + llm_online (False = กำลังใช้ fallback parser)
    GET  /scene     ทะเบียน id ทั้งหมด + briefing + initial_state
    POST /command   {text, mode, state} -> {parsed, decision, new_state}
    POST /pillars   GameState -> ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน

    จบเกม = decision.allowed เป็น true ขณะที่ parsed.action เป็น "accuse"

ข้อกำหนดที่ห้ามละเมิด
    1. engine.py ห้ามเรียก LLM
    2. reasoning_chain ต้องมาจากกฎที่ถูกตรวจจริง ห้ามให้ LLM เขียนย้อนหลัง
    3. ห้ามนำ confidence จาก LLM มาใช้ตัดสิน
    4. เพิ่มกฎ = แก้ rules.json + เขียน checker ใหม่ใน engine.py แล้วลงทะเบียนใน CHECKERS
    5. id (service_pantry, mara_voss) และรหัสกฎ (R005_...) เป็นภาษาอังกฤษเสมอ
       เพราะเป็นสัญญาระหว่างสองเลเยอร์ ส่วนที่ผู้เล่นอ่านเป็นภาษาไทยทั้งหมด

ยังไม่ได้ทำ
    - elapsed_seconds ไม่เคยเพิ่ม กฎ R014_TIME_LIMIT จึงยังไม่ทำงานตอนเล่นจริง
      (ตอนทดลองใช้ state_override กำหนดค่าตรงๆ ได้ จึงยังวัดกฎข้อนี้ได้)
    - frontend
