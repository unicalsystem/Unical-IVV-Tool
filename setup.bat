@echo off
REM One-time set-up on Windows: creates .venv and installs dependencies.
REM Needs internet ONCE for pip, or use an offline wheel folder:  setup.bat wheels
cd /d "%~dp0"
py -3.11 -m venv .venv 2>nul || python -m venv .venv
if "%~1"=="" (
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
    .venv\Scripts\python.exe -m pip install --no-index --find-links "%~1" -r requirements.txt
)
.venv\Scripts\python.exe -m pytest -q
echo.
echo Set-up complete. Start the tool with run.bat
pause
