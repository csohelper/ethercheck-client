@echo off
reg delete "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run" /v "MyBackgroundScript" /f
echo Скрипт удален из автозагрузки.