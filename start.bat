@echo off
echo ========================================
echo       V Push Quick Start Script
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment not found, creating...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [DONE] Virtual environment created successfully!
    echo.
)

REM Activate virtual environment and install dependencies
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Checking and installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

REM Check config files
if not exist "config.yaml" (
    echo [INFO] Config file not found, copying from example...
    copy config.example.yaml config.yaml
)

if not exist ".env" (
    echo [INFO] .env file not found, copying from example...
    copy .env.example .env
    echo.
    echo [INFO] Please edit .env file to configure your credentials!
    echo.
)

echo.
echo ========================================
echo       Starting V Push Service...
echo ========================================
echo [INFO] Service URL: http://127.0.0.1:8888
echo [TIP] Press Ctrl+C to stop the service
echo.

REM Start the service
uvicorn app.main:app --reload

pause
