@echo off
cd /d "%~dp0"

echo Checking for Python...
where python >nul 2>&1
if %errorlevel% equ 0 (
    goto :install_deps
)

echo Python was not found. Attempting automatic install via winget...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo winget (Windows package manager) was not found on this PC.
    echo Please update Windows, or install Python manually from:
    echo https://www.python.org/downloads/
    echo (Be sure to check "Add Python to PATH" during setup.)
    pause
    exit /b 1
)

winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if %errorlevel% neq 0 (
    echo.
    echo Automatic Python install failed. Please install it manually from:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo Python has been installed.
echo Please close this window and run install.bat again
echo (this window can't see the newly installed Python yet).
pause
exit /b 0

:install_deps
echo Installing required packages... (this only takes a while the first time)
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong while installing packages. See the error above.
    pause
    exit /b 1
)

echo.
echo Setup complete. Starting the app...
python app.py
pause
