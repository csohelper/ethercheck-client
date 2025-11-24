@echo off
setlocal

:: Delete shortcut from Startup
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=InternetMonitoring.lnk"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%"

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo Shortcut removed from startup.
) else (
    echo Shortcut not found in startup.
)

echo Operation completed.
pause

endlocal