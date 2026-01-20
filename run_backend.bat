@echo off
title DeepResearcher Backend
cd /d "%~dp0"

echo ========================================
echo   DeepResearcher Backend Server
echo ========================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    pause
    exit /b 1
)

:: Activate virtual environment if exists
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: Run the backend server
echo [INFO] Starting FastAPI backend server...
echo [INFO] API will be available at http://localhost:8000
echo [INFO] API Docs: http://localhost:8000/docs
echo.
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

:: If server stops, pause to see errors
pause
