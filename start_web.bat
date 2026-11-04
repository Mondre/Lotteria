@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe web_main.py %*
