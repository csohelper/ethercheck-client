import asyncio
import json
import os
import shutil
import time
import zipfile
from datetime import datetime

from client import send_to_server
from nettools import async_ping, async_trace  # async врапперы из nettools

DATA_DIR = 'data'
SENDING_DIR = 'sending'
SENT_DIR = 'sent'


def append_to_log(data, file_path):
    try:
        with open(file_path, 'a') as f:
            json.dump(data, f)
            f.write('\n')
        # print(f"[LOG] Appended data to {file_path}")
    except Exception as e:
        print(f"[ERROR] Failed to append log: {e}")


def save_losses(minute_key, sent_packets, received_packets, file_path):
    """Сохраняет потери пакетов с аккумулированием по минутам, не сохраняя 0% потерь"""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                lost_by_minute = json.load(f)
            except json.JSONDecodeError:
                lost_by_minute = {}
    else:
        lost_by_minute = {}

    existing = lost_by_minute.get(minute_key, {"packets": 0, "reached": 0, "losses": 0.0})
    existing['packets'] += sent_packets
    existing['reached'] += received_packets
    existing['losses'] = round(
        100 * (existing['packets'] - existing['reached']) / existing['packets'], 2
    ) if existing['packets'] > 0 else 0.0

    # Сохраняем только если есть реальные потери
    if existing['losses'] > 0.0:
        lost_by_minute[minute_key] = existing
    elif minute_key in lost_by_minute:
        # Убираем старую запись с 0.0, если она есть
        del lost_by_minute[minute_key]

    with open(file_path, 'w') as f:
        json.dump(lost_by_minute, f, indent=2)
    if existing['losses'] > 0.0:
        print(f"[LOSS] {minute_key}: {lost_by_minute[minute_key]}")


def zip_files(zip_path, files):
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for src, arcname in files:
                if os.path.exists(src):
                    zipf.write(src, arcname)
        print(f"[ZIP] Created zip {zip_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to zip files: {e}")
        return False


def recover():
    os.makedirs(SENDING_DIR, exist_ok=True)

    # Собираем все файлы log_ и losses_ из DATA_DIR и SENDING_DIR
    for dirpath in [DATA_DIR, SENDING_DIR]:
        if not os.path.exists(dirpath):
            continue
        files = [f for f in os.listdir(dirpath) if f.startswith('log_') or f.startswith('losses_')]

        # Группируем файлы по штампу времени
        stamps = {}
        for f in files:
            parts = f.split('_', 1)
            if len(parts) < 2:
                continue
            # Берем всё после log_ или losses_ до расширения
            stamp = parts[1].rsplit('.', 1)[0]
            stamps.setdefault(stamp, []).append(f)

        # Создаем архивы для каждого штампа
        for stamp, file_list in stamps.items():
            zip_path = os.path.join(SENDING_DIR, f'archive_{stamp}.zip')
            if not os.path.exists(zip_path):
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for f in file_list:
                        src_path = os.path.join(dirpath, f)
                        if os.path.exists(src_path):
                            zipf.write(src_path, f)
                            os.remove(src_path)
                print(f"[RECOVER] Created archive {zip_path}")


async def continuous_ping(host, log_file, losses_file):
    """Бесконечный цикл пингов каждые 2 сек до восстановления"""
    print("[PING LOOP] Starting continuous ping until connection restores")
    while True:

        # Выполняем 10 пингов за раз
        ping_res = await async_ping(host, count=10)
        append_to_log(ping_res, log_file)

        # Сколько отправлено и успешно получено?
        sent = 10
        reached = len(ping_res['times_ms'])  # сколько ответило

        minute_key = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_losses(minute_key, sent, reached, losses_file)

        # Если ХОТЯ БЫ ОДИН пинг успешен — связь восстановлена
        if reached > 0:
            print("[PING LOOP] Connection restored!")
            break

        await asyncio.sleep(1)


async def monitor_host(host):
    # ИЗМЕНЕНИЕ: единый формат YYYY-MM-DD_HH-MM для всех файлов
    current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    current_log_file = os.path.join(DATA_DIR, f'log_{current_stamp}.jsonl')
    current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)

    if not os.path.exists(current_log_file):
        open(current_log_file, 'a').close()
        print(f"[INFO] Created log file {current_log_file}")

    lost_by_minute = {}
    if os.path.exists(current_losses_file):
        with open(current_losses_file, 'r') as f:
            try:
                lost_by_minute = json.load(f)
                print(f"[INFO] Loaded existing losses from {current_losses_file}")
            except json.JSONDecodeError:
                lost_by_minute = {}

    current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    minute_sent = 0
    minute_reached = 0
    last_trace_time = time.time()
    last_rotation_time = time.time()

    while True:
        start_time = time.time()

        # 1. Single ping
        single_ping = await async_ping(host, count=1)
        append_to_log(single_ping, current_log_file)
        minute_sent += 1
        minute_reached += 1 if single_ping['avg_ms'] is not None else 0

        # 2. Всегда обновляем losses файл
        losses_percent = round((minute_sent - minute_reached) / minute_sent * 100, 2) if minute_sent else 0
        lost_by_minute[current_minute] = {
            "packets": minute_sent,
            "reached": minute_reached,
            "losses": losses_percent
        }
        with open(current_losses_file, 'w') as f:
            json.dump(lost_by_minute, f, indent=2)

        # 3. Если потеря соединения, выполняем полный пинг + trace + аварийный цикл
        if single_ping['avg_ms'] is None:
            # Полный пинг 4 пакета
            full_ping = await async_ping(host, count=4)
            append_to_log(full_ping, current_log_file)
            sent = 4
            reached = len(full_ping['times_ms'])
            minute_sent += sent
            minute_reached += reached

            # Обновляем losses
            losses_percent = round((minute_sent - minute_reached) / minute_sent * 100, 2)
            lost_by_minute[current_minute] = {
                "packets": minute_sent,
                "reached": minute_reached,
                "losses": losses_percent
            }
            with open(current_losses_file, 'w') as f:
                json.dump(lost_by_minute, f, indent=2)

            if reached < 4:
                # Трассировка
                trace_result = await async_trace(host)
                append_to_log(trace_result, current_log_file)

                # Аварийный цикл пинга каждые 2 секунды
                print("[PING LOOP] Starting continuous ping until connection restores")
                while True:
                    ping_res = await async_ping(host, count=1)
                    append_to_log(ping_res, current_log_file)
                    minute_sent += 1
                    minute_reached += 1 if ping_res['avg_ms'] is not None else 0

                    # Обновляем losses
                    losses_percent = round((minute_sent - minute_reached) / minute_sent * 100, 2)
                    lost_by_minute[current_minute] = {
                        "packets": minute_sent,
                        "reached": minute_reached,
                        "losses": losses_percent
                    }
                    with open(current_losses_file, 'w') as f:
                        json.dump(lost_by_minute, f, indent=2)

                    if ping_res['avg_ms'] is not None:
                        print("[PING LOOP] Connection restored!")
                        break
                    await asyncio.sleep(2)

        # 4. Периодический trace каждые 5 минут
        if time.time() - last_trace_time >= 300:
            trace_result = await async_trace(host)
            append_to_log(trace_result, current_log_file)
            last_trace_time = time.time()

        # 5. Проверка смены минуты
        new_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        if new_minute != current_minute:
            # Убираем старые минуты с 0% потерь
            lost_by_minute = {k: v for k, v in lost_by_minute.items() if v['losses'] > 0.0}
            with open(current_losses_file, 'w') as f:
                json.dump(lost_by_minute, f, indent=2)

            # Сброс счетчиков
            current_minute = new_minute
            minute_sent = 0
            minute_reached = 0

        # 6. Часовая ротация
        if time.time() - last_rotation_time >= 3600:
            # ИЗМЕНЕНИЕ: используем тот же формат для архива
            zip_name = f'archive_{current_stamp}.zip'
            zip_path = os.path.join(SENDING_DIR, zip_name)
            files_to_zip = [
                (current_log_file, os.path.basename(current_log_file)),
                (current_losses_file, os.path.basename(current_losses_file))
            ]
            if zip_files(zip_path, files_to_zip):
                for f, _ in files_to_zip:
                    if os.path.exists(f):
                        os.remove(f)

            # ИЗМЕНЕНИЕ: новая временная метка в том же формате
            current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            current_log_file = os.path.join(DATA_DIR, f'log_{current_stamp}.jsonl')
            current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
            open(current_log_file, 'a').close()
            lost_by_minute = {}
            last_rotation_time = time.time()

        # 7. Sleep с учетом времени выполнения
        elapsed = time.time() - start_time
        await asyncio.sleep(max(0.0, 10.0 - elapsed))


async def periodic_sender():
    """
    Периодически проверяет папку sending и пытается отправить архивы на сервер.
    Перемещает в sent только успешно отправленные файлы.
    """
    os.makedirs(SENT_DIR, exist_ok=True)
    while True:
        await asyncio.sleep(60)

        zip_files = [f for f in os.listdir(SENDING_DIR) if f.endswith('.zip')]
        if zip_files:
            print(f"[SENDER] Found {len(zip_files)} archive(s) to send")

        for f in zip_files:
            zip_path = os.path.join(SENDING_DIR, f)
            print(f"[SENDER] Processing {f}")

            if await send_to_server(zip_path):
                dest_path = os.path.join(SENT_DIR, f)
                shutil.move(zip_path, dest_path)
                print(f"[SENDER] Moved {f} to sent directory")
            else:
                print(f"[SENDER] Keeping {f} in sending directory for retry")


async def main(host):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)
    os.makedirs(SENT_DIR, exist_ok=True)

    recover()
    await asyncio.gather(
        monitor_host(host),
        periodic_sender()
    )


if __name__ == "__main__":
    asyncio.run(main('1.1.1.1'))
