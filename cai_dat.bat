@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   CapCut Auto Editor - cai dat
echo ============================================
echo.

REM --- 1. Python ---
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Chua co Python.
  echo     Tai Python 3.11 tai https://www.python.org/downloads/
  echo     Khi cai NHO tich "Add python.exe to PATH".
  pause & exit /b 1
)
for /f "tokens=2" %%v in ('python -V 2^>^&1') do set PYV=%%v
echo [OK] Python %PYV%

REM --- 2. ffmpeg (bat buoc cho moi buoc dung video) ---
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [!] Chua co ffmpeg trong PATH.
  echo     Tai ban "essentials" tai https://www.gyan.dev/ffmpeg/builds/
  echo     Giai nen roi them thu muc bin vao PATH.
  echo     App van mo duoc nhung KHONG dung duoc draft.
  echo.
) else (
  echo [OK] ffmpeg
)

REM --- 3. Moi truong ao rieng, khong dung chung voi Python he thong ---
if not exist ".venv\Scripts\python.exe" (
  echo [..] Tao moi truong ao .venv
  python -m venv .venv || (echo [X] Tao .venv that bai & pause & exit /b 1)
)
set PY=.venv\Scripts\python.exe

echo [..] Cai thu vien (lan dau mat vai phut)
%PY% -m pip install --upgrade pip --quiet
%PY% -m pip install --quiet fastapi "uvicorn[standard]" python-multipart pydantic ^
  google-genai faster-whisper pyyaml watchdog
if errorlevel 1 (echo [X] Cai thu vien that bai & pause & exit /b 1)
echo [OK] Thu vien

REM --- 4. Tu tao thu muc du lieu + do CapCut ---
%PY% -c "import assetlib; t=assetlib.khoi_tao(); print('[OK] Thu muc du lieu' + (' (tao moi: '+', '.join(t)+')' if t else ''))"
%PY% -c "import assetlib,sys; d=assetlib.find_capcut(); sys.stdout.reconfigure(encoding='utf-8'); print(('[OK] CapCut: ' if d['found'] else '[!] Khong thay CapCut: ')+str(d['draft']))"

REM --- 5. Kiem tra nhanh ---
%PY% -m pytest -q tests 2>nul && echo [OK] Smoke test || echo [!] Bo qua smoke test

echo.
echo ============================================
echo   Xong. Chay app bang: chay.bat
echo   Lan dau mo app, vao muc "Cai dat" nhap API key.
echo ============================================
pause
