@echo off
setlocal

:: Получить полный путь к main.py
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_PATH=%SCRIPT_DIR%main.py"

:: Проверить, существует ли main.py
if not exist "%SCRIPT_PATH%" (
    echo Ошибка: main.py не найден в той же папке, что и add_to_startup.bat
    pause
    exit /b 1
)

:: Найти pythonw.exe
where pythonw.exe >nul 2>&1
if %errorlevel% neq 0 (
    echo Ошибка: pythonw.exe не найден в PATH. Убедитесь, что Python установлен и добавлен в PATH.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('where pythonw.exe') do set "PYTHONW_PATH=%%i" & goto :found

:found
:: Теперь добавляем в реестр
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v "MyBackgroundScript" /t REG_SZ /d "\"%PYTHONW_PATH%\" \"%SCRIPT_PATH%\"" /f

echo Скрипт добавлен в автозагрузку.

endlocal