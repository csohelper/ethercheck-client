@echo off
echo Детальная проверка автозагрузки...
echo.

echo 1. Проверка реестра автозагрузки:
reg query "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v "MyBackgroundScript" 2>nul
if %errorlevel% equ 0 (
    echo Запись в реестре найдена
) else (
    echo Запись в реестре не найдена
)

echo.
echo 2. Проверка процессов Python:
wmic process where "name='pythonw.exe'" get processid,commandline /format:table 2>nul
if %errorlevel% neq 0 (
    echo Процессы pythonw.exe не найдены
)

echo.
echo 3. Проверка файла VBScript:
if exist "invisible.vbs" (
    echo Файл invisible.vbs существует
    echo.
    echo Содержимое VBScript:
    type "invisible.vbs"
) else (
    echo Файл invisible.vbs не найден
)

echo.
echo 4. Проверка в Диспетчере задач:
echo Откройте Диспетчер задач (Ctrl+Shift+Esc) и посмотрите вкладку "Автозагрузка"

pause