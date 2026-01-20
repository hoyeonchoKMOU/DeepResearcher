@echo off
title DeepResearcher Frontend
cd /d "%~dp0\frontend"

echo ========================================
echo   DeepResearcher Frontend Server
echo ========================================
echo.

:: Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH
    pause
    exit /b 1
)

:: Check if node_modules exists
if not exist "node_modules" (
    echo [INFO] Installing dependencies...
    npm install
    echo.
)

:: Run the frontend development server
echo [INFO] Starting Next.js frontend server...
echo [INFO] Frontend will be available at http://localhost:3000
echo.
npm run dev

:: If server stops, pause to see errors
pause
