import asyncio
import json
import logging
import os
import sys
import time
import zipfile
from datetime import datetime

import config
import logger
from client import send_to_server
from nettools import async_ping, async_trace

# Константы для имен директорий
DATA_DIR = 'data'
SENDING_DIR = 'sending'


def append_to_log(data, file_path):
    """
    Добавляет заданные данные в виде JSON-объекта в указанный файл, за которым следует новая строка.
    Обеспечивает немедленную запись данных на диск.

    :param data: Данные для добавления в формате JSON (dict).
    :param file_path: Путь к файлу журнала.
    """
    try:
        with open(file_path, 'a') as f:
            json.dump(data, f)
            f.write('\n')
            f.flush()  # Принудительная запись на диск
        logging.info(f"[LOG] Добавлены данные в {file_path}, размер теперь: {os.stat(file_path).st_size} байт")
    except Exception as e:
        logging.info(f"[ERROR] Не удалось добавить в журнал: {e}")


def zip_files(zip_path, files):
    """
    Создает ZIP-архив по указанному пути, содержащий заданные файлы.

    :param zip_path: Путь, где будет создан ZIP-файл.
    :param files: Список кортежей (путь_к_исходному_файлу, имя_в_архиве).
    :return: True, если создание ZIP удалось, иначе False.
    """
    try:
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_LZMA) as zipf:
            for src, arcname in files:
                if os.path.exists(src):
                    zipf.write(src, arcname)
        logging.info(f"[ZIP] Создан zip {zip_path}")
        return True
    except Exception as e:
        logging.info(f"[ERROR] Не удалось заархивировать файлы: {e}")
        return False


def recover():
    """
    Восстанавливает и архивирует оставшиеся файлы ping, trace и losses из DATA_DIR и SENDING_DIR.
    Группирует файлы по временной метке, создает ZIP-архивы для каждой группы в SENDING_DIR
    и удаляет оригинальные файлы после архивирования.
    """
    os.makedirs(SENDING_DIR, exist_ok=True)

    # Собираем все релевантные файлы из обеих директорий
    for dirpath in [DATA_DIR, SENDING_DIR]:
        if not os.path.exists(dirpath):
            continue
        files = [f for f in os.listdir(dirpath) if f.startswith(('ping_', 'trace_', 'losses_'))]

        # Группируем файлы по временной метке (все после префикса до расширения)
        stamps = {}
        for f in files:
            parts = f.split('_', 1)
            if len(parts) < 2:
                continue
            stamp = parts[1].rsplit('.', 1)[0]
            stamps.setdefault(stamp, []).append((dirpath, f))

        # Создаем архивы для каждой группы временных меток
        for stamp, file_list in stamps.items():
            zip_path = os.path.join(SENDING_DIR, f'archive_{stamp}.zip')
            if not os.path.exists(zip_path):
                files_to_zip = [(os.path.join(dp, f), f) for dp, f in file_list]
                if zip_files(zip_path, files_to_zip):
                    for dp, f in file_list:
                        src_path = os.path.join(dp, f)
                        if os.path.exists(src_path):
                            os.remove(src_path)
                    logging.info(f"[RECOVER] Создан архив {zip_path}")


async def initialize_monitor_files(current_stamp):
    """
    Инициализирует файлы ping, trace и losses для текущей временной метки, если они не существуют.

    :param current_stamp: Строка временной метки для именования файлов.
    :return: Кортеж путей к файлам ping_file, trace_file, losses_file.
    """
    current_ping_file = os.path.join(DATA_DIR, f'ping_{current_stamp}.jsonl')
    current_trace_file = os.path.join(DATA_DIR, f'trace_{current_stamp}.jsonl')
    current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)

    if not os.path.exists(current_ping_file):
        open(current_ping_file, 'a').close()
        logging.info(f"[INFO] Создан файл ping {current_ping_file}")

    if not os.path.exists(current_trace_file):
        open(current_trace_file, 'a').close()
        logging.info(f"[INFO] Создан файл trace {current_trace_file}")

    return current_ping_file, current_trace_file, current_losses_file


def load_losses(current_losses_file):
    """
    Загружает существующие данные о потерях пакетов из файла losses,
    или инициализирует пустой словарь, если файл некорректен.

    :param current_losses_file: Путь к JSON-файлу losses.
    :return: Загруженные данные о потерях по минутам (dict).
    """
    lost_by_minute = {}
    if os.path.exists(current_losses_file):
        with open(current_losses_file, 'r') as f:
            try:
                lost_by_minute = json.load(f)
                logging.info(f"[INFO] Загружены существующие потери из {current_losses_file}")
            except json.JSONDecodeError:
                lost_by_minute = {}
    return lost_by_minute


async def perform_default_ping(host, ping_file, lost_by_minute, current_minute):
    """
    Выполняет стандартный ping и обновляет журналы и счетчики потерь.

    :param host: Хост для ping.
    :param ping_file: Путь к файлу журнала ping.
    :param lost_by_minute: Словарь данных о потерях.
    :param current_minute: Текущая минута в формате строки.
    :return: Обновленные minute_sent, minute_reached.
    """
    default_ping = await async_ping(host, count=config.config.ping.standart.packet_count)
    append_to_log(default_ping, ping_file)
    minute_sent = config.config.ping.standart.packet_count
    minute_reached = len(default_ping['times_ms'])

    lost_by_minute[current_minute] = {
        "packets": minute_sent,
        "reached": minute_reached
    }
    return minute_sent, minute_reached


async def handle_packet_loss(host, ping_file, trace_file, lost_by_minute, current_minute, minute_sent, minute_reached):
    """
    Обрабатывает обнаруженные потери пакетов, выполняя полный ping, обновляя журналы,
    и, при необходимости, трассировку и непрерывный ping до восстановления соединения.

    :param host: Хост для ping/trace.
    :param ping_file: Путь к файлу журнала ping.
    :param trace_file: Путь к файлу журнала trace.
    :param lost_by_minute: Словарь данных о потерях.
    :param current_minute: Текущая минута в формате строки.
    :param minute_sent: Текущее количество отправленных пакетов за минуту.
    :param minute_reached: Текущее количество дошедших пакетов за минуту.
    :return: Обновленные minute_sent, minute_reached.
    """
    full_ping = await async_ping(host, count=config.config.ping.check.packet_count)
    append_to_log(full_ping, ping_file)
    sent = config.config.ping.check.packet_count
    reached = len(full_ping['times_ms'])
    minute_sent += sent
    minute_reached += reached

    lost_by_minute[current_minute] = {
        "packets": minute_sent,
        "reached": minute_reached
    }

    if reached < config.config.ping.check.packet_count:
        trace_result = await async_trace(host)
        append_to_log(trace_result, trace_file)

        logging.info("[PING LOOP] Запуск непрерывного ping до восстановления соединения")
        while True:
            ping_res = await async_ping(host, count=config.config.ping.continious.packet_count)
            append_to_log(ping_res, ping_file)
            minute_sent += config.config.ping.continious.packet_count
            minute_reached += len(ping_res['times_ms'])

            lost_by_minute[current_minute] = {
                "packets": minute_sent,
                "reached": minute_reached
            }

            if ping_res['avg_ms'] is not None:
                logging.info("[PING LOOP] Соединение восстановлено!")
                break
            await asyncio.sleep(config.config.ping.continious.delay)

    return minute_sent, minute_reached


async def perform_periodic_trace(host, trace_file, last_trace_time):
    """
    Выполняет трассировку, если истек интервал периодической проверки.

    :param host: Хост для трассировки.
    :param trace_file: Путь к файлу журнала trace.
    :param last_trace_time: Временная метка последней трассировки.
    :return: Обновленная last_trace_time.
    """
    if time.time() - last_trace_time >= config.config.timing.trace_check_secs:
        trace_result = await async_trace(host)
        append_to_log(trace_result, trace_file)
        last_trace_time = time.time()
    return last_trace_time


def update_minute(current_minute, minute_sent, minute_reached):
    """
    Проверяет смену минуты, очищает данные о потерях (удаляет минуты без потерь)
    и сбрасывает счетчики при начале новой минуты.

    :param current_minute: Текущая минута в формате строки.
    :param minute_sent: Текущее количество отправленных пакетов за минуту.
    :param minute_reached: Текущее количество дошедших пакетов за минуту.
    :return: Новая current_minute, minute_sent, minute_reached.
    """
    new_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    if new_minute != current_minute:
        current_minute = new_minute
        minute_sent = 0
        minute_reached = 0
    return current_minute, minute_sent, minute_reached


async def rotate_files(
        current_stamp,
        current_ping_file,
        current_trace_file,
        current_losses_file,
        last_rotation_time,
        lost_by_minute
):
    """
    Проверяет интервал ротации файлов и выполняет ротацию при необходимости.
    """
    new_lost_by_minute = lost_by_minute  # значение по умолчанию, если ротации нет

    # Проверка наступления времени ротации
    if (datetime.now() - last_rotation_time).total_seconds() >= config.config.timing.rotation_secs:

        zip_name = f'archive_{current_stamp}.zip'
        zip_path = os.path.join(SENDING_DIR, zip_name)

        files_to_zip = [
            (current_ping_file, os.path.basename(current_ping_file)),
            (current_trace_file, os.path.basename(current_trace_file)),
            (current_losses_file, os.path.basename(current_losses_file))
        ]

        # Архивирование
        if zip_files(zip_path, files_to_zip):
            for f, _ in files_to_zip:
                if os.path.exists(f):
                    os.remove(f)

        # Подготовка новых файлов
        current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        current_ping_file, current_trace_file, current_losses_file = await initialize_monitor_files(current_stamp)

        # Сброс данных о потерях
        new_lost_by_minute = {}
        last_rotation_time = datetime.now()

    return (
        current_stamp, current_ping_file, current_trace_file,
        current_losses_file, last_rotation_time, new_lost_by_minute
    )


async def monitor_host(host):
    """
    Основной цикл мониторинга хоста:
    - Инициализирует файлы и данные о потерях.
    - Выполняет регулярные ping, обрабатывает потери с трассировками и непрерывными ping.
    - Периодически выполняет трассировки.
    - Обновляет отслеживание потерь по минутам.
    - Ротирует файлы по интервалам.
    - Сохраняет данные о потерях после обновлений.

    :param host: Хост для мониторинга (например, '1.1.1.1').
    """
    current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    current_ping_file, current_trace_file, current_losses_file = await initialize_monitor_files(current_stamp)
    lost_by_minute = load_losses(current_losses_file)

    current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    last_trace_time = 0
    last_rotation_time = datetime.now()

    while True:
        start_time = time.time()

        # Стандартный ping и начальное обновление
        minute_sent, minute_reached = await perform_default_ping(
            host, current_ping_file, lost_by_minute, current_minute
        )

        # Сохранение потерь после стандартного ping
        with open(current_losses_file, 'w') as f:
            json.dump(lost_by_minute, f, indent=2)

        # Проверка на потери и обработка, если есть
        # Примечание: default_ping из perform_default_ping, но не возвращается;
        # предполагается доступность или рефакторинг при необходимости
        if minute_reached < config.config.ping.standart.packet_count:
            minute_sent, minute_reached = await handle_packet_loss(
                host, current_ping_file, current_trace_file, lost_by_minute,
                current_minute, minute_sent, minute_reached
            )

            # Сохранение потерь после обработки потерь
            with open(current_losses_file, 'w') as f:
                json.dump(lost_by_minute, f, indent=2)

        # Периодическая трассировка
        last_trace_time = await perform_periodic_trace(host, current_trace_file, last_trace_time)

        # Обновление минуты
        current_minute, minute_sent, minute_reached = update_minute(
            current_minute, minute_sent, minute_reached
        )

        # Сохранение потерь после обновления минуты
        with open(current_losses_file, 'w') as f:
            json.dump(lost_by_minute, f, indent=2)

        # Ротация файлов
        (current_stamp, current_ping_file, current_trace_file,
         current_losses_file, last_rotation_time, lost_by_minute) = await rotate_files(
            current_stamp,
            current_ping_file,
            current_trace_file,
            current_losses_file,
            last_rotation_time,
            lost_by_minute
        )

        # Сон для поддержания интервала ping
        elapsed = time.time() - start_time
        await asyncio.sleep(max(0.0, config.config.ping.standart.delay - elapsed))


async def periodic_sender():
    """
    Периодически проверяет директорию SENDING_DIR на наличие ZIP-архивов и пытается отправить их на сервер.
    Удаляет успешно отправленные файлы; оставляет остальные для повторной попытки.
    """
    while True:
        await asyncio.sleep(config.config.timing.sender_check_secs)

        zip_files_list = [f for f in os.listdir(SENDING_DIR) if f.endswith('.zip')]
        if zip_files_list:
            logging.info(f"[SENDER] Найдено {len(zip_files_list)} архив(ов) для отправки")

        for f in zip_files_list:
            zip_path = os.path.join(SENDING_DIR, f)
            logging.info(f"[SENDER] Обработка {f}")

            if await send_to_server(zip_path):
                os.remove(zip_path)
                logging.info(f"[SENDER] Удален отправленный файл {f}")
            else:
                logging.info(f"[SENDER] {f} оставлен в директории sending для повторной попытки")


async def main(host):
    """
    Основная точка входа скрипта:
    - Обеспечивает существование директорий.
    - Выполняет восстановление старых файлов.
    - Запускает задачи мониторинга и отправки параллельно.

    :param host: Хост для мониторинга.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)

    recover()
    await asyncio.gather(
        monitor_host(host),
        periodic_sender()
    )


if __name__ == "__main__":
    print("Starting")
    try:
        logging.info("Скрипт запущен. Директория: %s", logger.script_dir)
        asyncio.run(main('1.1.1.1'))
    except Exception as e:
        logging.error("Критическая ошибка: %s", e, exc_info=True)
        # Опционально: вывод в консоль для тестирования
        print(f"Error: {e}", file=sys.stderr)
        exit(1)
