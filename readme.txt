NeSy-Escape (draft1) — Neuro-Symbolic Escape Room
==================================================

เกมสอบสวนบนขบวนรถไฟ ผู้เล่นพิมพ์ภาษาไทยล้วน ไม่มีปุ่มกด
สาธิตแนวคิด Neuro-Symbolic คือแยก "ตีความภาษา" ออกจาก "ตัดสินตามกฎ"

    ข้อความไทย -> Neural (Gemini) ตีความ -> ParsedCommand
                                          -> Symbolic ตัดสินตามกฎ -> Decision

หมายเหตุ  draft1 เป็นเวอร์ชันตัดทอนไว้อธิบายโค้ด
          ส่วนการทดลองเปรียบเทียบอยู่ในสาขา episode-experiment

โครงสร้าง
    app/schemas.py           สัญญากลางระหว่างสองเลเยอร์
    app/neural/              ตีความภาษาไทย -> ParsedCommand   (เรียก Gemini)
    app/symbolic/engine.py   ตัดสินตามกฎ -> Decision          (ไม่เรียก LLM เด็ดขาด)
    app/walkthrough.py       เส้นทางเฉลย ใช้ในเทส
    app/main.py              FastAPI endpoints

    data/rules.json          กฎทั้ง 15 ข้อ แก้กฎที่นี่ ไม่แก้ในโค้ด
    data/story.json          โลกของเกม แก้ id ที่นี่ที่เดียว ทั้งสองเลเยอร์อ่านไฟล์นี้
    data/walkthrough.json    เส้นทางเฉลย 29 ตา

ติดตั้งและรัน
    pip install -r requirements.txt
    cp .env.example .env          ใส่ GEMINI_API_KEY
    uvicorn app.main:app --reload
    เอกสาร API: http://127.0.0.1:8000/docs

ทดสอบ
    python -m pytest -v           47 เทส (ชุดที่ต้องใช้ LLM จะ skip เองถ้าไม่มีคีย์)

Endpoints
    GET  /health    สถานะระบบ
    GET  /scene     ทะเบียน id ทั้งหมด + briefing + initial_state
    POST /command   {text, mode, state} -> {parsed, decision, new_state}

    เซิร์ฟเวอร์ไม่จำสถานะ ฝั่ง client ถือ GameState เองแล้วส่งไปกับทุก request

หลักการที่ห้ามละเมิด
    1. engine.py ห้ามเรียก LLM
    2. reasoning_chain ต้องมาจากกฎที่ถูกตรวจจริง ห้ามให้ LLM เขียนย้อนหลัง
    3. ห้ามนำ confidence จาก LLM มาใช้ตัดสิน
    4. เพิ่มกฎ = แก้ rules.json + เขียน checker ใหม่ใน engine.py แล้วลงทะเบียนใน CHECKERS
    5. id (service_pantry) และรหัสกฎ (R005_...) เป็นภาษาอังกฤษเสมอ
       เพราะเป็นสัญญาระหว่างสองเลเยอร์ ส่วนที่ผู้เล่นอ่านเป็นภาษาไทยทั้งหมด
