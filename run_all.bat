@echo off
title DeepResearcher Launcher
cd /d "%~dp0"

echo ========================================
echo   DeepResearcher - Starting All Services
echo ========================================
echo.

:: Start backend in new window
echo [INFO] Starting Backend Server...
start "DeepResearcher Backend" cmd /k run_backend.bat

:: Wait a moment for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend in new window
echo [INFO] Starting Frontend Server...
start "DeepResearcher Frontend" cmd /k run_frontend.bat

echo.
echo ========================================
echo   Services Started!
echo ========================================
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/docs
echo ========================================
echo.

pause
