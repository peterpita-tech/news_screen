@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title News Screen Dashboard - keep open (close = stop server)
cd /d "%~dp0"

rem Use full python path to avoid the Microsoft Store python alias
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=python"

echo ============================================
echo   News Screen Dashboard (global news -^> indicators -^> global screener)
echo   First launch fetches data (~30-60s). Browser opens http://localhost:8763
echo   KEEP THIS WINDOW OPEN. Close it to stop the server.
echo ============================================
echo.

start "" /b cmd /c "ping -n 8 127.0.0.1 >nul & start "" http://localhost:8763"

"%PY%" app.py %*

echo.
echo [server stopped] If there is an error above, please screenshot it.
pause
