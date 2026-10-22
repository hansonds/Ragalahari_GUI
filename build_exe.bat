@echo off
title Building Ragalahari Downloader EXE
cd /d "%~dp0"
echo.
echo  ============================================
echo    Ragalahari Downloader - one-click EXE build
echo  ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo  [!] Python is not installed.
    echo      Install it from https://www.python.org/downloads/
    echo      IMPORTANT: tick "Add python.exe to PATH" during install, then run this again.
    echo.
    pause
    exit /b 1
)

echo  [1/3] Installing required packages...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail

echo.
echo  [2/3] Building the EXE (takes 1-3 minutes)...
python -m PyInstaller ragalahari_gui.py --name Ragalahari_Downloader --onefile --windowed --noconfirm --clean --icon logo.ico --add-data "logo.ico;." --add-data "logo.png;." --collect-data customtkinter --hidden-import pystray._win32
if errorlevel 1 goto fail

echo.
echo  [3/3] Done!
echo      Your EXE is here: %~dp0dist\Ragalahari_Downloader.exe
echo.
explorer "%~dp0dist"
pause
exit /b 0

:fail
echo.
echo  [X] Build failed. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
