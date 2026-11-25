
@echo off
title VeriDoc AI Launcher

echo ========================================
echo          VERIDOC AI LAUNCHER
echo ========================================
echo.

cd /d "C:\Users\Sabarish\Projects\VeriDoc-AI"

echo Starting Flask Backend...
start "VeriDoc AI - Backend" cmd /k "cd /d C:\Users\Sabarish\Projects\VeriDoc-AI && .\backend\venv\Scripts\python.exe backend\app.py"

timeout /t 3 /nobreak >nul

echo Starting React Frontend...
start "VeriDoc AI - Frontend" cmd /k "cd /d C:\Users\Sabarish\Projects\VeriDoc-AI\frontend && npm.cmd run dev"

echo.
echo ========================================
echo Backend:  http://127.0.0.1:5000
echo Frontend: http://localhost:5173
echo ========================================
echo.

timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"

exit
