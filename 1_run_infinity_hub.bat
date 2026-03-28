@echo off
title Infinity Quant Hub - RUN
echo ==========================================
echo Starting Infinity Quant Hub...
echo ==========================================

set USER_NAME=jmyoon312
set DISTRO=Ubuntu-24.04

echo [1/4] Force releasing ports (5050, 5173) and old processes...
wsl -d %DISTRO% -u root bash -c "fuser -k 5050/tcp; fuser -k 5173/tcp; pkill -9 -f main.py; pkill -9 -f vite; pkill -9 node; exit 0"
timeout /t 2 > nul

echo [2/4] Starting Trading Bot (main.py)...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd /home/%USER_NAME% && (nohup ./venv/bin/python3 main.py > bot.log 2>&1 &) && sleep 2"

echo [3/4] Starting Integrated Web Server (web_server.py on Port 5050)...
wsl -d %DISTRO% -u %USER_NAME% bash -c "cd /home/%USER_NAME% && (nohup ./venv/bin/python3 web_server.py > web.log 2>&1 &) && sleep 2"

echo [3/4] Ready! Integrated Dashboard is accessible.
echo.
echo Login Details for Proxy:
echo - URL: http://[YOUR-IP]:5050
echo - Strategy: Integrated Hub V22.2
echo.
echo [4/4] ALL SYSTEMS GO!
echo ==========================================
echo [NOTICE] Only ONE background process (main.py) is now required.
echo UI is served directly from the trading engine.
echo ==========================================
timeout /t 5
