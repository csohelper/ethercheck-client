@echo off
setlocal

:: Delete shortcut from Startup
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=MyBackgroundScript.lnk"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%"

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo Shortcut removed from startup.
) else (
    echo Shortcut not found in startup.
)

:: Delete from registry (in case old method was used)
reg delete "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v "MyBackgroundScript" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo Entry removed from registry.
) else (
    echo Entry not found in registry.
)

echo Operation completed.
pause

endlocal