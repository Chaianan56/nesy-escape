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
