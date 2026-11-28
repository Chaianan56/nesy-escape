"""
scripts/start_demo.py — สคริปต์เปิดเซิร์ฟเวอร์นำเสนอผลงาน (Local Presentation Demo Launcher)

คุณสมบัติ:
- สแกนหาพอร์ตว่างในย่าน 8770-8780 โดยไม่ชนกับเซิร์ฟเวอร์หลักที่กำลังทำงานอยู่
- เปิดเบราว์เซอร์ให้อัตโนมัติไปยังหน้าเล่นเกม
- ใช้สำหรับเปิดรัน Demo นำเสนอโปรเจกต์ได้อย่างราบรื่น
"""
import argparse
from pathlib import Path
import socket
import sys
from threading import Timer
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def available_port():
    for port in range(8770, 8781):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("Ports 8770-8780 are busy. Close an old demo server and try again.")


def check_ai_keys():
    """ลองเรียก Gemini หนึ่งครั้งต่อคีย์ แล้วบอกว่าคีย์ไหนใช้ได้ ติดโควตารายนาที หรือติดโควตารายวัน"""
    import os
    from app.neural.gemini_client import DEFAULT_MODEL, _clients
    from app.neural.narrator import narrator_enabled
    from app.parser_log import LOG_PATH
    clients = _clients()
    if not clients:
        print("AI: ไม่มีคีย์ Gemini (ใส่ GEMINI_API_KEY ในไฟล์ .env) เกมเล่นได้เฉพาะคำสั่งพิมพ์ตรงและปุ่มกด")
        return False
    usable = 0
    for index, client in enumerate(clients, 1):
        try:
            client.models.generate_content(model=DEFAULT_MODEL, contents="ตอบคำเดียวว่า ok")
            print(f"AI คีย์ {index}: ใช้ได้")
            usable += 1
        except Exception as exc:  # noqa: BLE001 - report every failure kind plainly
            text = str(exc).lower()
            if "per day" in text:
                print(f"AI คีย์ {index}: โควตารายวันหมดแล้ว (ใช้ได้อีกครั้งพรุ่งนี้)")
            elif "429" in text or "resource_exhausted" in text:
                print(f"AI คีย์ {index}: ติดโควตารายนาที รอสักครู่แล้วลองใหม่")
            else:
                print(f"AI คีย์ {index}: เรียกไม่ได้ ({type(exc).__name__})")
    narrator = os.getenv("NARRATOR", "").strip().lower()
    print("ผู้เล่าเรื่อง:", "ปิด (NARRATOR=off)" if narrator in ("0", "off", "false", "no")
          else "เปิด และจะหยุดเองชั่วคราวเมื่อโควตาตึง" if narrator_enabled() else "ปิด (ไม่มี AI)")
    print("บันทึกประโยคที่เกมไม่เข้าใจ:", LOG_PATH)
    return usable > 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Check local dependencies without starting a game")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    import uvicorn
    from app.main import app
    port = available_port()
    if args.check:
        print(f"Demo ready: app loaded; available local port {port}")
        if not check_ai_keys():
            print("คำเตือน: ไม่มีคีย์ที่ใช้ได้ ผู้เล่นพิมพ์ประโยคธรรมดาไม่ได้ ใช้ได้แค่คำสั่งพิมพ์ตรงและปุ่มกด")
        return
    url = f"http://127.0.0.1:{port}/"
    print(f"LOCAL PRESENTATION: {url}", flush=True)
    print("Keep this window open. Ctrl+C stops the demo. See DEMO-GUIDE.md.", flush=True)
    if not args.no_browser:
        timer = Timer(2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
