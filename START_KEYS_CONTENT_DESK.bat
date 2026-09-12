@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PYTHON_CMD="
where py >nul 2>nul && set "PYTHON_CMD=py -X utf8"
if not defined PYTHON_CMD (
  where python >nul 2>nul && set "PYTHON_CMD=python -X utf8"
)
if not defined PYTHON_CMD (
  echo.
  echo ============================================
  echo   Python is not installed on this computer
  echo ============================================
  echo.
  echo Install Python 3.11 or newer from:
  echo   https://www.python.org/downloads/windows/
  echo.
  echo IMPORTANT: during setup tick "Add python.exe to PATH".
  echo Then close this window and double-click START_KEYS_CONTENT_DESK.bat again.
  echo.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)

echo Checking Keys-Shop Content Desk requirements...
%PYTHON_CMD% -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
  echo.
  echo ERROR: Python packages could not be installed.
  echo Check the internet connection and try again.
  pause
  exit /b 1
)

echo Starting Keys-Shop Content Desk on http://127.0.0.1:5002/batch
start "" http://127.0.0.1:5002/batch
%PYTHON_CMD% keys_app.py

echo.
pause
