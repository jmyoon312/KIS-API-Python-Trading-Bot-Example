@echo off
title Windows Network Bypass for WSL
echo ==================================================
echo Infinity Quant Hub - WSL Network Proxy Setup
echo ==================================================

:: Request Admin
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Requesting Administrator privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

echo.
echo [1/3] Detecting WSL Container IP Address...
for /f "delims=" %%i in ('wsl -d Ubuntu-24.04 bash -c "hostname -I | awk '{print $1}'"') do set RAW_WSL_IP=%%i
:: Trim whitespace/carriage returns
for /f "tokens=* delims= " %%a in ("%RAW_WSL_IP%") do set WSL_IP=%%a
echo [Target WSL IP] : %WSL_IP%

echo.
echo [2/3] Setting Network PortProxy (5173, 5050) to Windows...
netsh interface portproxy delete v4tov4 listenport=5173 listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy delete v4tov4 listenport=5050 listenaddress=0.0.0.0 >nul 2>&1
netsh interface portproxy add v4tov4 listenport=5173 listenaddress=0.0.0.0 connectport=5173 connectaddress=%WSL_IP%
netsh interface portproxy add v4tov4 listenport=5050 listenaddress=0.0.0.0 connectport=5050 connectaddress=%WSL_IP%
echo PortProxy configured successfully!

echo.
echo [3/3] Opening Windows Defender Firewall...
netsh advfirewall firewall delete rule name="Infinity Quant WSL" >nul 2>&1
netsh advfirewall firewall add rule name="Infinity Quant WSL" dir=in action=allow protocol=TCP localport=5050,5173
echo Firewall rules added successfully!

echo.
echo ==================================================
echo Network Setup Completely Finished!
echo Now you can connect from external devices via Nginx.
echo ==================================================
pause
