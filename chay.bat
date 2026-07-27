@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM TAT QuickEdit cua cua so console.
REM Windows bat san che do nay: BAM CHUOT vao cua so den la tien trinh BI DUNG
REM cho toi khi bam phim. Dang boc loi 10 phut ma lo click vao xem log -> app
REM "treo", trinh duyet bao mat ket noi, ma khong co loi nao trong log.
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>nul

if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  echo [!] Chua cai. Chay cai_dat.bat truoc.
  pause & exit /b 1
)

echo ============================================
echo   CapCut Auto Editor dang chay
echo   Mo: http://127.0.0.1:8765
echo.
echo   DUNG BAM CHUOT vao cua so nay khi dang
echo   chay viec nang - de yen cho no chay.
echo   Dong cua so nay = tat app.
echo ============================================
echo.

start "" http://127.0.0.1:8765
%PY% app.py
pause
