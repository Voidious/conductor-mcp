@echo off
REM Activate the virtual environment and run main.py

REM Change to the script's directory (project root)
cd /d %~dp0

REM Activate the virtual environment
call .venv\Scripts\activate.bat

REM Run the main Python script
python main.py %* 
