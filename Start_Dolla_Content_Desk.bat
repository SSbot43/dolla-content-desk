@echo off
setlocal
title Dolla Content Desk - Update and Start

REM This BAT may live inside the repo OR be copied to the Windows desktop.
REM Prefer the folder containing this BAT when it is a git repo; otherwise use the normal office-PC path.
set "DESK_DIR=%~dp0"
if not exist "%DESK_DIR%.git" set "DESK_DIR=E:\Claude work\dolla-content-desk\"

if not exist "%DESK_DIR%.git" (
  echo.
  echo ERROR: Could not find the Dolla Content Desk repo.
  echo Expected: E:\Claude work\dolla-content-desk
  echo.
  pause
  exit /b 1
)

for %%I in ("%DESK_DIR%..\dollacasino-content") do set "ENGINE_DIR=%%~fI"

cd /d "%DESK_DIR%"

echo Updating Dolla Content Desk...
git fetch origin main
if errorlevel 1 goto :gitfail
git reset --hard origin/main
if errorlevel 1 goto :gitfail

REM Home/secondary PCs may have only the desk repo from the old ZIP. Self-heal by cloning
REM the content engine beside it when missing.
if not exist "%ENGINE_DIR%\.git" (
  echo Content engine not found. Downloading it now...
  git clone https://github.com/SSbot43/dollacasino-content.git "%ENGINE_DIR%"
  if errorlevel 1 goto :enginefail
) else (
  REM Content repo can legitimately be dirty while articles/images are being queued.
  REM A failed ff-only pull must never prevent the desk from starting.
  echo Checking content engine updates...
  git -C "%ENGINE_DIR%" pull --ff-only origin main >nul 2>&1
)

REM Ensure Python dependencies are present on a fresh PC. Keep output quiet unless install fails.
if exist "%DESK_DIR%requirements.txt" (
  py -X utf8 -m pip install -r "%DESK_DIR%requirements.txt" >nul 2>&1
)
if exist "%ENGINE_DIR%\requirements.txt" (
  py -X utf8 -m pip install -r "%ENGINE_DIR%\requirements.txt" >nul 2>&1
)

set "CONTENT_REPO=%ENGINE_DIR%"
set "PORT=5001"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo Starting on http://127.0.0.1:5001
start "" http://127.0.0.1:5001
py -X utf8 bulk_launcher.py
goto :eof

:gitfail
echo.
echo ERROR: Could not update Content Desk from GitHub.
echo The app was NOT started with stale code.
echo.
pause
exit /b 1

:enginefail
echo.
echo ERROR: Could not download the dollacasino-content engine repo.
echo Check GitHub sign-in / internet access, then run this BAT again.
echo.
pause
exit /b 1
