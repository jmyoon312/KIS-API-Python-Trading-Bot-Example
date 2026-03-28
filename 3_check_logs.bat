@echo off
title Infinity Quant Hub - Quick Log Viewer
echo ==========================================
echo Checking Latest Server Unified Logs...
echo ==========================================

set USER_NAME=jmyoon312
set DISTRO=Ubuntu-24.04

echo.
echo [System Logs] Trading Bot & Web Dashboard (bot.log)
wsl -d %DISTRO% -u %USER_NAME% -e bash -c "tail -n 30 /home/%USER_NAME%/bot.log"
echo ------------------------------------------

echo.
echo If you see errors like "ModuleNotFoundError" or "command not found", that's the real problem!
echo ==========================================
pause

