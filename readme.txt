NeSy-Escape — Neuro-Symbolic Escape Room (Nocturne Express)
===========================================================

โครงสร้าง
    app/schemas.py           สัญญากลางระหว่างสองเลเยอร์ (แก้ต้องตกลงกันทั้งทีม)
    app/neural/              ตีความภาษาธรรมชาติ -> ParsedCommand   (Gemini + fallback)
    app/symbolic/engine.py   ตัดสินตามกฎ -> Decision               (ไม่เรียก LLM เด็ดขาด)
    app/main.py              ท่อเชื่อม + FastAPI endpoints
    data/rules.json          กฎทั้งหมด แก้กฎที่นี่ ไม่แก้ในโค้ด
    data/story.json          โลกของเกม แก้ id ที่นี่ที่เดียว ทั้งสองเลเยอร์อ่านไฟล์นี้

ติดตั้งและรัน
    pip install -r requirements.txt
    cp .env.example .env          # ใส่ GEMINI_API_KEY (ไม่ใส่ก็รันได้ แต่ใช้ fallback)
    uvicorn app.main:app --reload
    เอกสาร API: http://127.0.0.1:8000/docs

ทดสอบ
    python play.py                 พิมพ์ภาษาไทยเล่นในเทอร์มินัล เห็น reasoning chain ทุกกฎ
    python -m pytest -v            ชุดทดสอบทั้งหมด
    ชุดที่ต้องใช้ LLM จริงจะถูก skip อัตโนมัติเมื่อไม่มีคีย์หรือชนโควตา

⚠️ NEURAL_STRICT — ต้องตั้งเป็น 1 ทุกครั้งที่เก็บข้อมูลการทดลอง
    ปกติถ้าเรียก Gemini ไม่สำเร็จ (429 / API ล่ม) ระบบจะเงียบๆ ตกไปใช้ fallback heuristic
    ซึ่งทำให้ log ปนผลของ heuristic กับผลของ LLM โดยไม่มีอะไรบอกว่าแถวไหนเป็นของใคร
    ตั้ง NEURAL_STRICT=1 แล้วระบบจะโยน NeuralUnavailable แทนการเงียบ

โควตา free tier
    จำกัด request ต่อนาที ยิงรัวๆ จะเจอ 429
    gemini-3.5-flash-lite โควตาเยอะกว่าตัวเต็มมาก จึงตั้งเป็นค่าเริ่มต้นไว้ใน .env

Endpoints สำหรับ frontend
    GET  /health    สถานะระบบ + llm_online (False = กำลังใช้ fallback parser)
    GET  /scene     ทะเบียน id ทั้งหมด (locations/objects/suspects) + initial_state
    POST /command   {text, mode, state} -> {parsed, decision, new_state}
    POST /pillars   GameState -> ความคืบหน้าสี่เสาหลักของผู้ต้องสงสัยทุกคน

โหมดการทดลอง (mode ใน /command)
    "A"  LLM ตีความ + ตัดสินเอง        (baseline)
    "B"  LLM ตีความ -> Symbolic ตัดสิน  (ระบบที่นำเสนอ)
    ตัวแปรที่ต่างกันมีเพียง "ใครเป็นผู้ตัดสิน" เท่านั้น อย่าเปลี่ยนอย่างอื่น
    ทุกคำสั่งถูกบันทึกลง logs/YYYYMMDD_mode_X.jsonl (หนึ่งบรรทัดต่อคำสั่ง อ่านเข้า pandas ได้)

ข้อกำหนดที่ห้ามละเมิด
    1. engine.py ห้ามเรียก LLM
    2. reasoning_chain ต้องมาจากกฎที่ถูกตรวจจริง ห้ามให้ LLM เขียนย้อนหลัง
    3. ห้ามนำ confidence จาก LLM มาใช้ตัดสิน
    4. เพิ่มกฎ = แก้ rules.json + เขียน checker ใหม่ใน engine.py แล้วลงทะเบียนใน CHECKERS
