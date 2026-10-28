@echo off
title Mars Council Launcher

if not defined MARSLOG (
  set MARSLOG=1
  call "%~f0" %* > "%~dp0launch.log" 2>&1
  echo ====== Mars Council launch log ======
  type "%~dp0launch.log"
  echo ====== Full log saved to launch.log next to start.bat ======
  pause
  exit /b 0
)

if not exist "%~dp0backend\.env" (
  echo [!] backend\.env not found. Copying template - add your keys, then rerun.
  copy "%~dp0backend\.env.example" "%~dp0backend\.env" >nul
  echo     backend\.env created. Edit it, then run start again.
  exit /b 1
)

set HASKEY=
set HASOFF=
for /f "usebackq tokens=1* delims==" %%A in ("%~dp0backend\.env") do (
  set "NM=%%A"
  set "VL=%%B"
  call :checkline
)
if defined HASOFF goto modeok
if defined HASKEY goto modeok
set COUNCIL_OFFLINE=1
echo.
echo *** No keys found - starting in REHEARSAL mode (labeled on screen). ***
echo *** Add keys to backend\.env later for live models. ***
echo.
:modeok

if not exist "%~dp0frontend\out\index.html" (
  echo [!] Prebuilt dashboard missing. It ships with the project; re-download it.
  exit /b 1
)

cd /d "%~dp0backend"
if exist .venv\Scripts\python.exe goto havevenv
set PYCMD=python
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [!] No Python found and no virtualenv yet. Install Python 3.12, reopen this file.
    exit /b 1
  )
  set PYCMD=py -3
)
echo [*] Creating virtual environment (first run only)...
%PYCMD% -m venv .venv
:havevenv
call .venv\Scripts\activate.bat
echo [*] Installing requirements (first run only)...
pip install -q -r requirements.txt
if errorlevel 1 (
  echo [!] Dependency install failed. Re-running visibly...
  pip install -r requirements.txt
  exit /b 1
)
echo [*] Checking code...
python -m compileall -q app
if errorlevel 1 (
  echo [!] Python syntax error above. Send launch.log for a fix.
  exit /b 1
)
python "%~dp0backend\freshcheck.py" >nul 2>nul
if not errorlevel 1 (
  echo [*] A current server is already answering on :8000 - reusing it.
  goto serverup
)
taskkill /FI "WINDOWTITLE eq MarsCouncil-API" /T /F >nul 2>nul
python "%~dp0backend\killport.py" 8000 >nul 2>nul
echo [*] Starting Mars Council on :8000 ...
start "MarsCouncil-API" cmd /k "uvicorn app.main:app --port 8000"
:serverup

echo [*] Waiting for the server (up to ~5 min)...
python "%~dp0backend\waitfor.py" http://localhost:8000/health 100 3
if errorlevel 1 (
  echo [!] Server never came up. Close EVERY black window with X, including old terminals, then rerun start.bat.
  exit /b 1
)
echo [*] Up. Opening the dashboard...
start http://localhost:8000/
echo.
echo    RUNNING: http://localhost:8000/
echo    Run stop.bat to quit.
exit /b 0

:checkline
if "%NM%"=="" exit /b 0
if "%NM:~0,1%"=="#" exit /b 0
if not "%NM:_API_KEY=%"=="%NM%" if defined VL set HASKEY=1
if "%VL%"=="1" if not "%NM:COUNCIL_OFFLINE=%"=="%NM%" set HASOFF=1
exit /b 0
