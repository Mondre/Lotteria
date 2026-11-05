@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Crea prima il virtualenv e installa requirements-dev.txt.
  exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name LottoPredictAI --add-data "config\games.json;config" main.py
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe scripts\check_windows_package.py dist\LottoPredictAI\LottoPredictAI.exe
exit /b %errorlevel%
