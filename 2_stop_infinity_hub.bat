@echo off
title Infinity Quant Hub - STOP
echo ==========================================
echo Stopping Infinity Quant Hub...
echo ==========================================

set USER_NAME=jmyoon312
set DISTRO=Ubuntu-24.04

echo [1/3] Stopping main trading bot...
wsl -d %DISTRO% -u %USER_NAME% bash -c "pkill -9 -f main.py; exit 0"

echo [2/3] Stopping API backend...
wsl -d %DISTRO% -u %USER_NAME% bash -c "pkill -9 -f web_server.py; exit 0"

echo [3/3] Stopping Frontend UI...
wsl -d %DISTRO% -u %USER_NAME% bash -c "pkill -9 -f vite; pkill -9 node; exit 0"

echo.
echo ==========================================
echo All automated processes stopped safely.
echo ==========================================
timeout /t 3
