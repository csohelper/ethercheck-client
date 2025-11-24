@echo off
setlocal

:: Полный путь к main.py
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"

:: Проверка существования main.py
if not exist "%SCRIPT_PATH%" (
    echo Error: main.py not found in the same folder as add_to_startup.bat
    pause
    exit /b 1
)

:: Путь к pythonw.exe (ищем в PATH; если не найден, укажите полный путь вручную, например: set "PYTHONW_PATH=C:\Python\pythonw.exe")
set "PYTHONW_PATH=pythonw.exe"
where "%PYTHONW_PATH%" >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: pythonw.exe not found in PATH. Ensure Python is installed and added to PATH.
    pause
    exit /b 1
)

:: Папка автозагрузки
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=InternetMonitoring.lnk"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\%SHORTCUT_NAME%"

:: Лог-файл (опционально, для отладки)
set "LOG_FILE=%SCRIPT_DIR%startup_log.txt"

:: Создание ярлыка через PowerShell: прямой запуск pythonw.exe main.py с перенаправлением вывода в лог
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $shortcut = $ws.CreateShortcut('%SHORTCUT_PATH%'); $shortcut.TargetPath = '%PYTHONW_PATH%'; $shortcut.Arguments = '\"%SCRIPT_PATH%\" > \"%LOG_FILE%\" 2>&1'; $shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $shortcut.WindowStyle = 7; $shortcut.Save();"

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