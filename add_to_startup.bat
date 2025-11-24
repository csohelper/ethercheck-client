@echo off
setlocal

:: Get full path to main.py and run_script.bat
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"
set "RUN_BAT_PATH=%SCRIPT_DIR%run_script.bat"

:: Check if main.py exists
if not exist "%SCRIPT_PATH%" (
    echo Error: main.py not found in the same folder as add_to_startup.bat
    pause
    exit /b 1
)

:: Check if run_script.bat exists (create it if needed, but assume it's there)
if not exist "%RUN_BAT_PATH%" (
    echo Error: run_script.bat not found. Create it first as per instructions.
    pause
    exit /b 1
)

:: Find pythonw.exe (for reference, but not used directly here)
where pythonw.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: pythonw.exe not found in PATH. Ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

:: Startup folder
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=MyBackgroundScript.lnk"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%"

:: Create shortcut to run_script.bat using PowerShell, with proper quote escaping
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $shortcut = $ws.CreateShortcut('%SHORTCUT_PATH%'); $shortcut.TargetPath = '%RUN_BAT_PATH%'; $shortcut.Arguments = ''; $shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $shortcut.WindowStyle = 7; $shortcut.Save();"

if exist "%SHORTCUT_PATH%" (
    echo Shortcut added to startup: %SHORTCUT_PATH%
) else (
    echo Error: Failed to create shortcut.
    pause
    exit /b 1
)

echo To check: Open Task Manager ^> Startup tab.
pause

endlocal