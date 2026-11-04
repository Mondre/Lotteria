@echo off
setlocal
cd /d "%~dp0"
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name LottoPredictAI --add-data "config\games.json;config" main.py
exit /b %errorlevel%
