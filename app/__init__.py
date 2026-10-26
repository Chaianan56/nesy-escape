"""
app — แกนหลักของระบบ NeSy-Escape (Neuro-Symbolic Detective Game)

สถาปัตยกรรมระบบแบ่งออกเป็น 4 ชั้นหลัก:
1. Interaction Layer (app/main.py, app/sessions.py, app/game_clock.py):
   - จัดการเซิร์ฟเวอร์ FastAPI, Session ของผู้เล่น, คุกกี้, และนาฬิกาคดี (Game Clock)
   - ควบคุมการไหลของข้อมูล: User Input -> Neural Parsing -> Symbolic Adjudication -> State Update -> Client Response

2. Neuro AI Layer (app/neural/):
   - ใช้ Gemini API ทำการตีความภาษาธรรมชาติภาษาไทยของผู้เล่นให้ออกมาเป็น ParsedCommand
   - มีระบบ Dynamic kNN Few-Shot (Retriever), Dynamic Entity Pruning, และ Symbolic Repair Loop

3. Symbolic Layer (app/symbolic/):
   - ตัดสินความถูกต้องของคำสั่งด้วยตรรกะและกฎที่เข้มงวด (Domain Invariants) 100% โดยไม่พึ่งพา LLM
   - สร้าง Explainable Reasoning Chain (XAI) และตรวจสอบความคืบหน้าของ 4 เสาหลักคดี (Pillars)

4. Player Profiler & Adaptation Layer (app/profiler/):
   - วิเคราะห์พฤติกรรมผู้เล่นแบบเรียลไทม์ (5 มิติพฤติกรรม และ 5 Archetypes)
   - ปรับแต่งคำใบ้ (Scaffolding) และปฏิกิริยาของ NPC เชิงพลวัตตามรูปแบบการเล่น
"""
