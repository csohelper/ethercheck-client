@echo off
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"
set "LOG_FILE=%SCRIPT_DIR%startup_log.txt"
set "PYTHONW_PATH=pythonw.exe"  :: Можно зашить, или найти как в add_to_startup.bat

"%PYTHONW_PATH%" "%SCRIPT_PATH%" > "%LOG_FILE%" 2>&1