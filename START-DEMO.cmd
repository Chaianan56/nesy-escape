@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment missing. See DEMO-GUIDE.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\start_demo.py
pause
