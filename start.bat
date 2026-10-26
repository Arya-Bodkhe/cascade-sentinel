@echo off
setlocal
cd /d "%~dp0"
title CASCADE SENTINEL
set "CASCADE_HOST=127.0.0.1"
set "PORT=8000"
set "APP_PY=.venv\Scripts\python.exe"
echo ========================================================
echo  CASCADE SENTINEL - React + FastAPI
echo  http://127.0.0.1:8000
echo ========================================================
if not exist "frontend\dist\index.html" (
    echo [ERROR] Built React files are missing.
    echo If Node.js is installed, run: npm ci ^&^& npm run build
    pause
    exit /b 1
)
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or is not on PATH.
    echo Install Python 3.10 or newer, then run this launcher again.
    pause
    exit /b 1
)
if not exist "%APP_PY%" (
    echo Creating an isolated Python environment...
    python -m venv .venv
    if errorlevel 1 goto :failed
)
"%APP_PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo Installing application dependencies. This may take several minutes...
    "%APP_PY%" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :failed
)
start "" /b powershell.exe -NoProfile -Command "$u='http://127.0.0.1:8000'; for($i=0; $i -lt 90; $i++){try{$r=Invoke-WebRequest -Uri ($u+'/api/health') -TimeoutSec 2; if($r.StatusCode -eq 200){Start-Process $u; exit}}catch{}; Start-Sleep -Seconds 1}"
"%APP_PY%" run.py
if errorlevel 1 goto :failed
exit /b 0
:failed
echo [ERROR] Startup failed. Review the message above, then verify Python and dependency installation.
pause
exit /b 1
