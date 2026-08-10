@echo off
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python was not found. Please run install.bat first.
    pause
    exit /b 1
)

python app.py
pause
