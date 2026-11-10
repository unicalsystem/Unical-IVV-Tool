@echo off
REM Start the Unical DO-178 IV&V Review Tool from source (Windows)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe main.py
