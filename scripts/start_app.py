"""
start_app.py — เปิดเซิร์ฟเวอร์ NeSy-Escape

รันในเครื่อง:  python start_app.py        เปิดเบราว์เซอร์ให้อัตโนมัติ
บนคลาวด์:      แพลตฟอร์มจะกำหนดพอร์ตมาให้ทาง environment variable PORT
               และไม่ควรเปิดเบราว์เซอร์ ตั้ง NO_BROWSER=1 หรือปล่อยให้ตรวจ PORT เอง
"""

import os
import webbrowser
from threading import Timer

import uvicorn

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "127.0.0.1")
# แพลตฟอร์มคลาวด์กำหนด PORT มาให้เสมอ ใช้เป็นสัญญาณว่าไม่ได้รันในเครื่อง
IS_CLOUD = bool(os.getenv("PORT")) or os.getenv("NO_BROWSER") == "1"


def open_browser():
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    if IS_CLOUD:
        HOST = "0.0.0.0"          # คลาวด์ต้องรับ request จากภายนอก
    else:
        Timer(1.2, open_browser).start()
    print(f"NeSy-Escape กำลังเปิดที่ http://{HOST}:{PORT}")
    # ไฟล์นี้อยู่ใน scripts/ จึงต้องชี้ root โปรเจกต์ให้ import app ได้ ไม่ว่าจะรันจากโฟลเดอร์ไหน
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=not IS_CLOUD, app_dir=root)
