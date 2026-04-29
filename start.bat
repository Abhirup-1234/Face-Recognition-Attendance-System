@echo off
title FaceTrack AI
echo.
echo  ====================================
echo   FaceTrack AI - Starting...
echo  ====================================
echo.

REM -- Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else if exist ".venv311\Scripts\activate.bat" (
    call .venv311\Scripts\activate.bat
    echo [OK] Using .venv311
) else (
    echo [ERROR] Virtual environment not found.
    echo Run: python -m venv .venv
    echo Then: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM -- Check if frontend is built
if not exist "frontend\dist\index.html" (
    echo [WARN] Frontend not built. Building now...
    cd frontend
    call npm install
    call npm run build
    cd ..
)

REM -- Start the server
echo.
echo Starting FaceTrack AI server...
echo Press Ctrl+C to stop.
echo.
python run.py

pause
