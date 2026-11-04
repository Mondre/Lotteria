@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creare prima il virtualenv seguendo il README.
  exit /b 1
)
.venv\Scripts\python.exe main.py %*
