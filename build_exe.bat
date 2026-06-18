@echo off
setlocal
cd /d "%~dp0"
title Build Discord Role Whitelist Generator EXE

echo.
echo ========================================
echo Build Discord Role Whitelist Generator
 echo ========================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python was not found on PATH.
    echo.
    echo Try installing Python from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure "Add Python to PATH" is ticked during install.
    echo.
    pause
    exit /b 1
)

echo Installing/updating required packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install --upgrade pyinstaller

if %errorlevel% neq 0 (
    echo.
    echo Package install failed.
    pause
    exit /b 1
)

echo.
echo Building EXE...
python -m PyInstaller ^
 --onefile ^
 --windowed ^
 --clean ^
 --name DiscordRoleWhitelistGenerator ^
 discord_role_whitelist_generator.py

if %errorlevel% neq 0 (
    echo.
    echo EXE build failed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Done.
echo Your EXE should be here:
echo %cd%\dist\DiscordRoleWhitelistGenerator.exe
echo ========================================
echo.
pause
