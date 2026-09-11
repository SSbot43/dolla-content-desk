@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
echo Starting Keys-Shop Content Desk on http://127.0.0.1:5002
start "" http://127.0.0.1:5002
py -X utf8 keys_app.py
echo.
pause
