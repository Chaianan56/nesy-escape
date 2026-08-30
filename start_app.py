"""
start_app.py — Launch NeSy-Escape Web Application
"""

import webbrowser
import uvicorn
from threading import Timer

def open_browser():
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("🚂 Starting NeSy-Escape Web App on http://127.0.0.1:8000 ...")
    Timer(1.2, open_browser).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
