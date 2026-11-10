@echo off
REM One-click build of the Windows executable: dist\UnicalIVVTool\UnicalIVVTool.exe
REM Needs Python 3.11+ installed. First run needs internet for pip (or: build_exe.bat wheels)
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    py -3.11 -m venv .venv 2>nul || python -m venv .venv
)
if "%~1"=="" (
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
) else (
    .venv\Scripts\python.exe -m pip install --no-index --find-links "%~1" -r requirements.txt
)
.venv\Scripts\python.exe -m pytest -q || (echo Tests failed - build stopped. & pause & exit /b 1)
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name UnicalIVVTool ^
  --icon NONE ^
  --add-data "assets;assets" ^
  --add-data "config;config" ^
  --add-data "database\schema.sql;database" ^
  main.py || (echo PyInstaller failed. & pause & exit /b 1)
xcopy /E /I /Y config dist\UnicalIVVTool\config >nul
xcopy /E /I /Y templates dist\UnicalIVVTool\templates >nul
for %%d in (database logs reports uploaded_documents checklists) do if not exist dist\UnicalIVVTool\%%d mkdir dist\UnicalIVVTool\%%d
echo.
echo Build complete: dist\UnicalIVVTool\UnicalIVVTool.exe
echo Copy the whole dist\UnicalIVVTool folder to any Windows PC - no Python needed there.
pause
