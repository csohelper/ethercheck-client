@echo off
setlocal

:: Get full path to main.py
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"

:: Check if main.py exists
if not exist "%SCRIPT_PATH%" (
    echo Error: main.py not found in the same folder as add_to_startup.bat
    pause
    exit /b 1
)

:: Find pythonw.exe
where pythonw.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: pythonw.exe not found in PATH. Ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('where pythonw.exe') do set "PYTHONW_PATH=%%i" & goto :found

:found
:: Startup folder
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=MyBackgroundScript.lnk"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%"

:: Create shortcut using PowerShell in a single line
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $shortcut = $ws.CreateShortcut('%SHORTCUT_PATH%'); $shortcut.TargetPath = '%SCRIPT_DIR%run_script.bat'; $shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $shortcut.WindowStyle = 7; $shortcut.Save();"

if exist "%SHORTCUT_PATH%" (
    echo Shortcut added to startup: %SHORTCUT_PATH%
) else (
    echo Error: Failed to create shortcut.
    pause
    exit /b 1
)

echo "To check: Open Task Manager > Startup tab."
pause

endlocal