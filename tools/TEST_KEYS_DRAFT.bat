@echo off
setlocal
cd /d "%~dp0.."
echo Running Keys-Shop private draft test...
py -X utf8 keys_shop_draft_test.py
echo.
pause
