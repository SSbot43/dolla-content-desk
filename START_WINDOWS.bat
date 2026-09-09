@echo off
setlocal
title Dolla Content Desk

set "DESK_DIR=%~dp0"
for %%I in ("%DESK_DIR%..\dollacasino-content") do set "ENGINE_DIR=%%~fI"
set "APP_URL=http://127.0.0.1:5001"

echo.
echo ============================================
echo   Dolla Content Desk - Update and Start
echo ============================================
echo.

cd /d "%DESK_DIR%"

echo [1/4] Updating Content Desk...
if exist "%DESK_DIR%.git" (
  git pull --ff-only
  if errorlevel 1 echo WARNING: Content Desk update failed; using current local copy.
) else (
  echo Portable copy detected - skipping Content Desk git pull.
)

echo [2/4] Updating content engine...
if exist "%ENGINE_DIR%\.git" (
  git -C "%ENGINE_DIR%" pull --ff-only
  if errorlevel 1 echo WARNING: Content engine update failed; using current local copy.
) else if exist "%ENGINE_DIR%" (
  echo Portable content engine detected - skipping git pull.
) else (
  echo WARNING: Content engine not found at "%ENGINE_DIR%"
)

echo [3/4] Checking Python packages...
py -m pip install -r "%DESK_DIR%requirements.txt"
if errorlevel 1 (
  echo ERROR: Python package installation failed.
  pause
  exit /b 1
)
if exist "%ENGINE_DIR%\requirements.txt" py -m pip install -r "%ENGINE_DIR%\requirements.txt"

echo [4/4] Starting Content Desk...
set "CONTENT_REPO=%ENGINE_DIR%"
start "Dolla Content Desk Server" cmd /k "cd /d ""%DESK_DIR%"" && set PORT=5001 && py bulk_launcher.py"
timeout /t 4 /nobreak >nul
start "" "%APP_URL%"
exit /b 0
