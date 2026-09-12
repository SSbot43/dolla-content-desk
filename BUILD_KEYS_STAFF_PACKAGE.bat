@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
echo Building isolated Keys-Shop Content Desk staff package...
py -X utf8 build_keys_staff_package.py
if errorlevel 1 (
  echo.
  echo FAILED to build staff package.
  pause
  exit /b 1
)
echo.
echo Done. Open the dist folder and use Keys-Shop-Content-Desk.zip
start "" "%~dp0dist"
pause
