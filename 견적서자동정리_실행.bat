@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Python이 없습니다. 먼저 설치.bat 을 실행해주세요.
    pause
    exit /b 1
)

echo 견적서 자동 정리 프로그램을 시작합니다...
echo 잠시 후 브라우저에 "견적서 자동 정리" 화면이 열립니다.
echo (이 검은 창은 프로그램이 켜져 있는 동안 그대로 두세요)
python app.py
pause
