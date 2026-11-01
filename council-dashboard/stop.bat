@echo off
set "PATH=%SystemRoot%\System32;%PATH%"
taskkill /FI "WINDOWTITLE eq Arcadia-API*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Arcadia-Worker*" /T /F >nul 2>nul
if exist "%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\killport.py" 8000 >nul 2>nul
echo Arcadia mission stopped.
