@echo off
setlocal
cd /d "%~dp0"
echo Testing Keys-Shop WordPress connection...
python keys_shop_connection_test.py
echo.
pause
