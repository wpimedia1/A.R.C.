@echo off
taskkill /FI "WINDOWTITLE eq MarsCouncil-API" /T /F >nul 2>nul
if exist "%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\killport.py" 8000 >nul 2>nul
echo Mars Council stopped.
pause
