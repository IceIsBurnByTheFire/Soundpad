@echo off
title Soundboard
cd /d "%~dp0"

rem Find Python. "py" is the official launcher; plain "python" may be a Microsoft Store shortcut.
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo Getting things ready. The first time this downloads about 150 MB and takes a few minutes...
%PY% -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto nopip

echo Starting Soundboard...
%PY% soundboard.py
if errorlevel 1 goto crashed
exit /b

:nopython
echo.
echo  Python is not installed.
echo  Opening the download page: install it, and tick "Add python.exe to PATH" in the installer.
echo  Then double-click start.bat again.
echo.
start "" https://www.python.org/downloads/
pause
exit /b

:nopip
echo.
echo  Could not download what the app needs. Check your internet connection and try again.
echo.
pause
exit /b

:crashed
echo.
echo  The app closed with an error. The details are above, and saved in error.log.
echo.
pause
