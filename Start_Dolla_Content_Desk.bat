@echo off
setlocal
title Dolla Content Desk - Update and Start

set "DESK_DIR=%~dp0"
for %%I in ("%DESK_DIR%..\dollacasino-content") do set "ENGINE_DIR=%%~fI"

cd /d "%DESK_DIR%"

echo Updating Dolla Content Desk...
git fetch origin main
if errorlevel 1 goto :gitfail
git reset --hard origin/main
if errorlevel 1 goto :gitfail

if exist "%ENGINE_DIR%\.git" (
  echo Updating content engine safely...
  git -C "%ENGINE_DIR%" pull --ff-only origin main
)

set "CONTENT_REPO=%ENGINE_DIR%"
set "PORT=5001"
echo Starting on http://127.0.0.1:5001
py bulk_launcher.py
goto :eof

:gitfail
echo.
echo ERROR: Could not update Content Desk from GitHub.
echo The app was NOT started with stale code.
pause
exit /b 1
