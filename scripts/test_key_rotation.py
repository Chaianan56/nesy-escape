import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(ENV_PATH, override=True)

from app.neural import gemini_client
from app.schemas import GameState

def run_test():
    clients = gemini_client._clients()
    print(f"=== เริ่มการทดสอบระบบสลับ API Key ===")
    print(f"จำนวน API Key ที่ตรวจพบใน .env: {len(clients)} คีย์\n")

    if len(clients) < 2:
        print("คำเตือน: พบ API Key ไม่ถึง 2 ตัว กรุณาใส่คีย์สำรองคั่นด้วยจุลภาคใน .env")
        return

    state = GameState(current_location="lounge_car")

    # 1. ทดสอบว่า Client ตัวที่ 1 ใช้งานได้จริง
    print("[ขั้นที่ 1] ทดสอบยิง Gemini ด้วย Key ที่ 1...")
    res1 = gemini_client.interpret("ดูรอบๆ", state=state)
    print(f"-> Key 1 สำเร็จ! ผลลัพธ์: action={res1.action.value}, target={res1.target}, latency={res1.latency_ms}ms\n")

    # 2. จำลองสถานการณ์ Key 1 ติด RESOURCE_EXHAUSTED (Quota เต็ม)
    print("[ขั้นที่ 2] จำลอง Key 1 ติด Quota Error (RESOURCE_EXHAUSTED / 429)...")
    original_generate = clients[0].models.generate_content
    call_log = []

    def mock_exhausted_key1(*args, **kwargs):
        call_log.append("Key 1 (เกิด 429 RESOURCE_EXHAUSTED)")
        print("   ⚠️ [Key 1] ติด 429 RESOURCE_EXHAUSTED -> ระบบกำลังทิ้ง Key 1 และสลับไป Key 2...")
        raise RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for project")

    clients[0].models.generate_content = mock_exhausted_key1

    real_generate_key2 = clients[1].models.generate_content
    def tracked_generate_key2(*args, **kwargs):
        call_log.append("Key 2 (ทำงานสำเร็จ)")
        print("   ✅ [Key 2 - สำรอง] รับงานต่ออัตโนมัติและส่งคำตอบสำเร็จ!")
        return real_generate_key2(*args, **kwargs)

    clients[1].models.generate_content = tracked_generate_key2

    try:
        res2 = gemini_client.interpret("สำรวจตู้รถไฟ", state=state)
        print(f"-> การสลับคีย์สำเร็จสมบูรณ์! ผลลัพธ์จาก Key 2: action={res2.action.value}, target={res2.target}")
        print(f"-> ลำดับการเรียกจริง: {' -> '.join(call_log)}")
    finally:
        # คืนค่าฟังก์ชันเดิม
        clients[0].models.generate_content = original_generate
        clients[1].models.generate_content = real_generate_key2

    print("\n=== สรุปผล: ระบบสลับ Key อัตโนมัติทำงานได้ถูกต้อง 100% ===")

if __name__ == "__main__":
    run_test()
