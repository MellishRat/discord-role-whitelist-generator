@echo off
setlocal
cd /d "%~dp0"
title Discord Role Whitelist Generator

echo.
echo ========================================
echo Discord Role Whitelist Generator
echo ========================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed or not added to PATH.
    echo Download Python from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b
)

python -m pip install -r requirements.txt
python discord_role_whitelist_generator.py

echo.
echo Application closed.
echo.
pause
