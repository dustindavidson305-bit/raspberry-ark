@echo off
REM The Raspberry Ark - Windows starter.
REM This file only makes sure Python 3 exists, then hands over to the
REM universal installer (Raspberry-Ark-Setup.py), which detects your
REM system and installs the Windows version of the app.
setlocal
cd /d "%~dp0"

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if defined PYCMD goto run_setup

echo Python 3 was not found - installing it from python.org ...
set "PYEXE=%TEMP%\python-installer.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe' -OutFile '%PYEXE%'"
if errorlevel 1 goto no_python
start /wait "" "%PYEXE%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD goto no_python

:run_setup
%PYCMD% "%~dp0Raspberry-Ark-Setup.py" %*
pause
exit /b 0

:no_python
echo.
echo Python could not be installed automatically.
echo Get it free from https://www.python.org/downloads/ then run this file again.
pause
exit /b 1
