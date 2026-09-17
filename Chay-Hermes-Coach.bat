@echo off
rem ============================================================
rem  Hermes Coach - bam dup vao file nay de chay
rem
rem  Tu lam ba viec: build giao dien neu can, khoi dong backend,
rem  va mo trinh duyet kem token. Cua so nay phai giu mo trong
rem  suot phien lam viec - dong no la tat server.
rem ============================================================

rem Chuyen ve thu muc chua file nay, de bam dup tu bat ky dau cung dung.
cd /d "%~dp0"

rem Console Windows mac dinh dung codepage cu, khong in duoc tieng Viet.
chcp 65001 >nul
set PYTHONUTF8=1

title Hermes Coach

echo.
echo   Hermes Coach
echo   ============
echo.

rem --- Kiem tra moi truong Python ---
if not exist ".venv\Scripts\python.exe" (
    echo   [LOI] Khong tim thay .venv\Scripts\python.exe
    echo.
    echo   Chay lenh nay mot lan de tao moi truong:
    echo       python -m venv .venv
    echo       .venv\Scripts\python.exe -m pip install -e .
    echo.
    pause
    exit /b 1
)

rem --- Build giao dien neu chua co ---
rem Chi build khi thieu, vi build lai moi lan se lam cham khoi dong ma
rem khong duoc gi: ma nguon khong tu doi giua hai lan bam.
if not exist "apps\hermes-coach\dist\index.html" (
    echo   Chua co giao dien, dang build lan dau...
    echo.
    if not exist "node_modules" (
        echo   Cai dat goi npm ^(chi lan dau, hoi lau^)...
        call npm install
        if errorlevel 1 goto npm_failed
    )
    call npm run -w apps/hermes-coach build
    if errorlevel 1 goto npm_failed
    echo.
    echo   Build xong.
    echo.
)

rem --- Chay ---
echo   Dang khoi dong... trinh duyet se tu mo sau vai giay.
echo   Giu cua so nay mo. Nhan Ctrl+C de dung.
echo.

.venv\Scripts\python.exe -m hermes_cli.main coach --open

rem Toi day nghia la server da dung, do Ctrl+C hoac do loi.
echo.
echo   Hermes Coach da dung.
pause
exit /b 0

:npm_failed
echo.
echo   [LOI] Build giao dien that bai.
echo   Kiem tra da cai Node.js chua: node --version
echo.
pause
exit /b 1
