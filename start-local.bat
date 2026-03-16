@echo off
REM Start Quantum Raspberry Tie locally without Docker
REM Useful for development and testing on Windows

echo.
echo 🚀 Quantum Raspberry Tie - Local Startup
echo ==========================================

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.9 or later.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set VERSION=%%i
echo ✓ Found %VERSION%

REM Create/activate virtual environment
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -q -r requirements-docker.txt

REM Create necessary directories
if not exist "svg" mkdir svg
if not exist "credentials" mkdir credentials

REM Show startup info
echo.
echo ==========================================
echo ✨ Setup complete!
echo.
echo 🌐 Web Dashboard will be available at:
echo    http://localhost:5000
echo.
echo 📝 Press Ctrl+C to stop the server
echo ==========================================
echo.

REM Start the dashboard
python web_dashboard.py

pause
