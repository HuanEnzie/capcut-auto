@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  echo [!] Chua cai. Chay cai_dat.bat truoc.
  pause & exit /b 1
)

echo Dang mo CapCut Auto Editor... (dong cua so nay la tat app)
start "" http://127.0.0.1:8765
%PY% app.py
pause
