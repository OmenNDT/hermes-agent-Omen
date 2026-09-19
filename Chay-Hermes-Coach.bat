@echo off
setlocal EnableDelayedExpansion
rem ============================================================
rem  Hermes Coach - bam dup vao file nay de chay
rem
rem  Lan dau se mat vai phut de chuan bi moi truong. Nhung lan
rem  sau chay ngay. Cua so den nay phai giu mo trong suot phien
rem  lam viec - dong no la tat chuong trinh.
rem ============================================================

rem Chuyen ve thu muc chua file nay, de bam dup tu bat ky dau cung dung.
cd /d "%~dp0"

rem Console Windows mac dinh dung codepage cu, khong in duoc tieng Viet.
chcp 65001 >nul
set PYTHONUTF8=1
title Hermes Coach

echo.
echo   ============================================
echo     Hermes Coach
echo   ============================================
echo.

rem ============================================================
rem  BUOC 1 - Kiem tra Python va Node
rem ============================================================
set "CAN_PYTHON="
set "CAN_NODE="
set "PYEXE="
set "PY_SAI_BAN="

rem Tim mot Python that, dung phien ban. Khong dung "where python" mot
rem minh vi hai ly do da kiem chung:
rem   - Windows dat san mot tep 0 byte o WindowsApps\python.exe. No khong
rem     phai Python; goi no se mo Microsoft Store. "where" van thay no.
rem   - Mot may co the co san Python 3.10 hoac 3.14; ca hai deu qua duoc
rem     "where" roi chet o buoc cai thu vien, voi thong bao kho hieu.
for /f "delims=" %%p in ('where python 2^>nul') do (
    if not defined PYEXE (
        echo %%p| find /i "WindowsApps" >nul
        if errorlevel 1 (
            "%%p" -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>&1
            if not errorlevel 1 (
                set "PYEXE=%%p"
            ) else (
                set "PY_SAI_BAN=1"
            )
        )
    )
)
rem Trinh khoi chay "py" biet nhung ban Python khong nam tren PATH.
if not defined PYEXE (
    for %%v in (3.13 3.12 3.11) do (
        if not defined PYEXE (
            py -%%v -c "raise SystemExit(0)" >nul 2>&1
            if not errorlevel 1 set "PYEXE=py -%%v"
        )
    )
)
if not defined PYEXE set "CAN_PYTHON=1"

rem Node phai tu ban 20 tro len; ban cu qua se hong o buoc dung giao dien.
where node >nul 2>&1
if errorlevel 1 (
    set "CAN_NODE=1"
) else (
    node -e "process.exit(parseInt(process.versions.node,10) >= 20 ? 0 : 1)" >nul 2>&1
    if errorlevel 1 set "CAN_NODE=1"
)

if not defined CAN_PYTHON if not defined CAN_NODE goto co_du_runtime

echo   May nay con thieu phan mem can thiet:
echo.
if defined CAN_PYTHON if defined PY_SAI_BAN echo       - Python 3.11-3.13 ^(may dang co ban khac, khong dung duoc^)
if defined CAN_PYTHON if not defined PY_SAI_BAN echo       - Python 3.12   ^(ngon ngu chay phan loi chuong trinh^)
if defined CAN_NODE   echo       - Node.js 20 tro len ^(dung de dung giao dien web^)
echo.
echo   Chuong trinh co the tu tai va cai giup ban, tu kho phan mem
echo   chinh thuc cua Microsoft. Viec nay can ket noi mang va mat
echo   vai phut.
echo.
rem Hoi truoc khi cai. Mot cu bam dup khong dong nghia voi viec
rem dong y cho cai them phan mem len may.
set "DONG_Y="
set /p "DONG_Y=  Ban dong y cai dat khong? (g = dong y / k = khong): "
if /i not "!DONG_Y!"=="g" goto tu_cai_tay

where winget >nul 2>&1
if errorlevel 1 goto khong_co_winget

if defined CAN_PYTHON (
    echo.
    echo   Dang cai Python...
    winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 goto cai_that_bai
)
if defined CAN_NODE (
    echo.
    echo   Dang cai Node.js...
    winget install --id OpenJS.NodeJS.LTS --source winget --accept-package-agreements --accept-source-agreements --silent
    if errorlevel 1 goto cai_that_bai
)

echo.
echo   ============================================
echo     Da cai xong.
echo.
echo     Hay DONG cua so nay va BAM DUP lai vao file
echo     Chay-Hermes-Coach.bat mot lan nua.
echo   ============================================
echo.
rem Phai chay lai that: bien PATH duoc doc mot lan luc cua so nay
rem mo ra, nen phan mem vua cai chua co trong danh sach cua no.
pause
exit /b 0

:co_du_runtime

rem ============================================================
rem  BUOC 2 - Moi truong Python rieng cua chuong trinh
rem ============================================================
if not exist ".venv\Scripts\python.exe" (
    echo   Dang tao moi truong Python rieng... ^(lan dau, hoi lau^)
    %PYEXE% -m venv .venv
    if errorlevel 1 goto venv_that_bai
    echo   Xong.
    echo.
)

rem Kiem tra thu vien da cai chua, thay vi cai lai moi lan chay.
rem Thu nhap mot goi that chac chan hon la tin vao mot tep danh dau:
rem neu moi truong hong giua chung thi buoc nay tu phat hien.
.venv\Scripts\python.exe -c "import fastapi, uvicorn, anthropic" >nul 2>&1
if errorlevel 1 (
    echo   Dang cai thu vien Python... ^(lan dau, vai phut^)
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
    .venv\Scripts\python.exe -m pip install -e . --quiet
    if errorlevel 1 goto pip_that_bai
    echo   Xong.
    echo.
)

rem ============================================================
rem  BUOC 3 - Giao dien web
rem ============================================================
if not exist "apps\hermes-coach\dist\index.html" (
    if not exist "node_modules" (
        echo   Dang tai thu vien giao dien... ^(lan dau, vai phut^)
        call npm install --silent
        if errorlevel 1 goto npm_that_bai
    )
    echo   Dang dung giao dien...
    call npm run -w apps/hermes-coach build
    if errorlevel 1 goto npm_that_bai
    echo   Xong.
    echo.
)

rem ============================================================
rem  BUOC 4 - Tai khoan Claude
rem ============================================================
rem Moi nguoi dung tai khoan Claude cua chinh minh. Khong dung chung
rem API key: chia se khoa nghia la chia se ca chi phi lan quyen truy cap,
rem va khong go lai duoc cho tung nguoi.
rem
rem Dang nhap la thao tac cua con nguoi - trinh duyet se mo ra. Khong tu
rem dong hoa duoc, nhung dan duoc tung buoc.
if exist "%USERPROFILE%\.claude\.credentials.json" goto co_tai_khoan

rem Mot khoa API da dat san cung dung duoc - khong can tai khoan Claude.
if defined ANTHROPIC_API_KEY goto co_tai_khoan
if defined OPENAI_API_KEY goto co_tai_khoan
if defined GEMINI_API_KEY goto co_tai_khoan

echo   ------------------------------------------------------------
echo     Chua thay cach nao de goi mo hinh AI.
echo.
echo     Hermes Coach can mot mo hinh AI de tao cau hoi. Co hai duong,
echo     chon duong nao ban da co san:
echo.
echo       1. Tai khoan Claude   - neu ban co goi Claude tra phi
echo       2. Khoa API           - Google Gemini, OpenAI GPT hoac Claude
echo                               ^(Gemini co muc mien phi^)
echo   ------------------------------------------------------------
echo.
set "DANG_NHAP="
set /p "DANG_NHAP=  Chon 1, 2, hay de sau? (1 / 2 / k): "
if /i "!DANG_NHAP!"=="2" goto huong_dan_api_key
if /i not "!DANG_NHAP!"=="1" goto bo_qua_dang_nhap

rem Cong cu dang nhap di kem Claude Code. Node da chac chan co o buoc 1.
where claude >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Dang cai cong cu dang nhap Claude...
    call npm install -g @anthropic-ai/claude-code
    if errorlevel 1 goto claude_cai_that_bai
    echo.
)

echo.
echo   Trinh duyet se mo ra de ban dang nhap.
echo   Xong thi quay lai cua so nay.
echo.
rem `claude auth login`, khong phai `claude login` - lenh thu hai khong ton tai.
call claude auth login

echo.
if exist "%USERPROFILE%\.claude\.credentials.json" (
    echo   Da dang nhap.
    echo.
) else (
    echo   Chua thay thong tin dang nhap. Chuong trinh van chay duoc,
    echo   nhung phan tro chuyen se bao "provider_not_configured".
    echo.
)
goto co_tai_khoan

:huong_dan_api_key
echo.
echo   ------------------------------------------------------------
echo     Dat khoa API
echo.
echo     Lay khoa mien phi cua Google Gemini tai:
echo         https://aistudio.google.com/apikey
echo.
echo     Roi mo Command Prompt va chay lenh duoi day MOT LAN
echo     ^(thay YOUR_KEY bang khoa vua lay^):
echo.
echo         setx GEMINI_API_KEY "YOUR_KEY"
echo.
echo     Neu dung OpenAI thi thay GEMINI_API_KEY bang OPENAI_API_KEY,
echo     dung Claude tra phi thi dung ANTHROPIC_API_KEY.
echo.
echo     Dat xong, DONG cua so nay va bam dup lai vao file.
echo   ------------------------------------------------------------
echo.
rem setx ghi vao ho so nguoi dung, nhung cua so dang mo khong thay duoc
rem gia tri moi - PATH va bien moi truong chi doc mot lan luc khoi tao.
pause
exit /b 0

:bo_qua_dang_nhap
echo.
echo   Bo qua. Chuong trinh van mo duoc va xem duoc du lieu da luu,
echo   nhung chua tro chuyen duoc voi Coach.
echo.
echo   Khi nao muon dung day du, chay lai file nay va chon "g".
echo.

:co_tai_khoan

rem ============================================================
rem  BUOC 5 - Chay
rem ============================================================
echo   Dang khoi dong... trinh duyet se tu mo sau vai giay.
echo   Giu cua so nay mo. Nhan Ctrl+C de dung.
echo.

.venv\Scripts\python.exe -m hermes_cli.main coach --open
set "MA_LOI=%errorlevel%"

echo.
if not "%MA_LOI%"=="0" (
    rem Thong bao cua phan loi chuong trinh la tieng Anh. Nguyen nhan
    rem hay gap nhat la bam dup hai lan, nen dich san o day.
    echo   ------------------------------------------------------------
    echo     Chuong trinh dung lai kem mot thong bao loi o tren.
    echo.
    echo     Neu dong do co chu "already holds profile" thi nghia la
    echo     Hermes Coach DANG CHAY o mot cua so den khac. Hay tim cua
    echo     so do de dung, hoac khoi dong lai may.
    echo   ------------------------------------------------------------
) else (
    echo   Hermes Coach da dung.
)
echo.
pause
exit /b %MA_LOI%

rem ============================================================
rem  Cac nhanh loi
rem ============================================================
:tu_cai_tay
echo.
echo   Ban da chon khong cai tu dong. De tu cai:
echo.
if defined CAN_PYTHON echo       Python : https://www.python.org/downloads/
if defined CAN_PYTHON echo                Nho tich o "Add python.exe to PATH" khi cai.
if defined CAN_NODE   echo       Node.js: https://nodejs.org/  ^(ban LTS^)
echo.
echo   Cai xong thi bam dup lai vao file nay.
echo.
pause
exit /b 1

:khong_co_winget
echo.
echo   [LOI] May nay khong co cong cu cai dat tu dong cua Windows.
echo   Vui long tu tai va cai:
echo.
if defined CAN_PYTHON echo       Python : https://www.python.org/downloads/
if defined CAN_PYTHON echo                Nho tich o "Add python.exe to PATH" khi cai.
if defined CAN_NODE   echo       Node.js: https://nodejs.org/  ^(ban LTS^)
echo.
pause
exit /b 1

:cai_that_bai
echo.
echo   [LOI] Cai dat khong thanh cong.
echo   Thu kiem tra ket noi mang, hoac tu tai tai:
echo       Python : https://www.python.org/downloads/
echo       Node.js: https://nodejs.org/
echo.
pause
exit /b 1

:venv_that_bai
echo.
echo   [LOI] Khong tao duoc moi truong Python.
echo   Kiem tra phien ban: python --version  ^(can tu 3.11 den 3.13^)
echo.
pause
exit /b 1

:pip_that_bai
echo.
echo   [LOI] Khong cai duoc thu vien Python.
echo   Thuong la do mat mang. Kiem tra ket noi roi chay lai file nay.
echo.
pause
exit /b 1

:npm_that_bai
echo.
echo   [LOI] Khong dung duoc giao dien web.
echo   Kiem tra Node.js: node --version  ^(can tu 20 tro len^)
echo.
pause
exit /b 1

:claude_cai_that_bai
echo.
echo   [LOI] Khong cai duoc cong cu dang nhap Claude.
echo   Thu mo Command Prompt va chay tay:
echo       npm install -g @anthropic-ai/claude-code
echo       claude auth login
echo.
pause
exit /b 1
