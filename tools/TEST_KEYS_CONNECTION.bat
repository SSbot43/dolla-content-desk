@echo off
setlocal
cd /d "%~dp0.."
echo Testing Keys-Shop WordPress connection...
py -X utf8 keys_shop_connection_test.py
echo.
pause
