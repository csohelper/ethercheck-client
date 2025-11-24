@echo off
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"
set "LOG_FILE=%SCRIPT_DIR%startup_log.txt"

"%PYTHONW_PATH%" "%SCRIPT_PATH%" > "%LOG_FILE%" 2>&1