# Мониторинг Интернета ЦСО-1

Утилита, висящая в фоне системы, выполняющая периодические пинги и трейсы проверки интернета в общежитии МТУСИ

[Панель мониторинга](https://monitor.slavapmk.ru)


### Установка

Для подключения к мониторингу интернета выполните следующие действия

1. **Установите на компьютер Python**
    1. Скачайте [Windows Installer x64](https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe)

        [Для других систем](https://www.python.org/downloads/release/python-31210/) (вероятно уже предустановлен)
    2. Прожмите `Add python.exe to PATH` и нажмите `Customize installation`
        <img src="https://i.imgur.com/jXJB3Dk.png">
    3. `Next`
        <img src="https://i.imgur.com/uwyztyH.png">
    4. `Install Python 3.12 for all users` -> `Install`
        <img src="https://i.imgur.com/EaQDLtz.png">
2. **Скачайте файл проекта**

    Code -> Download ZIP
    <img src="https://i.imgur.com/pGQRdmk.png">
3. **Распакуйте архив в директорию, не содержащую пробелы в имени.**
    
    Например, создайте папку `C:\Monitoring` и распакуйте файлы в директорию
    <img src="https://i.imgur.com/pVrtDGL.png">
4. **Запустите файл `install.bat`**

    Это установит все необходимые библиотеки для работы
    <img src="https://i.imgur.com/bS20hz0.png">
5. **Сделайте начальную настройку**
   1. Сделайте тестовый запуск

       Запустите файл `run.bat`, через несколько секунд закройте окно
       <img src="https://i.imgur.com/UvPAYoX.png">

       Появится файл `config.yaml`, настройте его
       <img src="https://i.imgur.com/UvPAYoX.png">
   2. Установите переменную `room` на свою (только численное значение)
       <img src="https://i.imgur.com/8Il2IHR.png">

       При желании можете более подробно установить свои настройки, описание ниже
6. **Запустите `add_to_startup.bat`, это добавит мониторинг в автозапуск системы**
    <img src="https://i.imgur.com/SaMXbV3.png">

    Для отключения мониторинга либо отключите его в диспечере задач или запустите файл `remove_from_startup.bat`
    <img src="https://i.imgur.com/806tJV1.png">