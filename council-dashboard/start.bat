@echo off
title Arcadia Mission Launcher
setlocal
rem Windows tools (cmd, netstat, taskkill) live in System32; put it first in case PATH lost it.
set "PATH=%SystemRoot%\System32;%PATH%"
cd /d "%~dp0backend"
echo [*] Arcadia mission launcher - %CD%

if not exist .env (
  set "MSG=backend\.env not found. Copy backend\.env.example to backend\.env and set MODEL_API_KEY."
  goto fail
)
if not exist "%~dp0frontend\out\index.html" (
  set "MSG=frontend\out is missing. Build it once: cd frontend, npm ci, npm run build."
  goto fail
)

if exist .venv\Scripts\python.exe goto venv
echo [*] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
  set "MSG=Could not create a virtual environment. Python 3.10 or newer must be on PATH."
  goto fail
)
:venv
call .venv\Scripts\activate.bat
python --version
echo [*] Installing requirements...
python -m pip install -r requirements-mission.txt
if errorlevel 1 (
  set "MSG=Dependency install failed. See the pip output above."
  goto fail
)

echo [*] Checking MODEL_API_KEY...
python -c "from mission.provider import credential, fingerprint; k, src = credential(); print('    key from', src, 'fingerprint', fingerprint(k))"
if errorlevel 1 (
  set "MSG=MODEL_API_KEY is missing or empty in backend\.env. There is no offline mode."
  goto fail
)
echo [*] Validating environment package...
python -m mission.package
if errorlevel 1 (
  set "MSG=Environment package is invalid. See the output above."
  goto fail
)

set COOKIE_SECURE=false
set PUBLIC_ORIGIN=http://127.0.0.1:8000
if not defined DATABASE_URL set DATABASE_URL=sqlite:///mission.db
python killport.py 8000 >nul 2>nul
echo [*] Starting API and worker in their own windows...
start "Arcadia-API" cmd /k "uvicorn mission.api:app --host 127.0.0.1 --port 8000"
start "Arcadia-Worker" cmd /k "python -m mission.worker"

python waitfor.py http://127.0.0.1:8000/api/v1/health 60 2
if errorlevel 1 (
  set "MSG=API is not healthy. The reason is printed above and in the Arcadia-API window."
  goto fail
)
start http://127.0.0.1:8000/
echo.
echo RUNNING: http://127.0.0.1:8000/   Run stop.bat to quit.
pause
exit /b 0

:fail
echo.
echo [FAIL] %MSG%
echo.
pause
exit /b 1
