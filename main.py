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

DATA_DIR = 'data'
SENDING_DIR = 'sending'


def append_to_log(data, file_path):
    try:
        with open(file_path, 'a') as f:
            json.dump(data, f)
            f.write('\n')
            f.flush()  # Force flush to disk
        logging.info(f"[LOG] Appended data to {file_path}, size now: {os.stat(file_path).st_size} bytes")
    except Exception as e:
        logging.info(f"[ERROR] Failed to append log: {e}")


def zip_files(zip_path, files):
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for src, arcname in files:
                if os.path.exists(src):
                    zipf.write(src, arcname)
        logging.info(f"[ZIP] Created zip {zip_path}")
        return True
    except Exception as e:
        logging.info(f"[ERROR] Failed to zip files: {e}")
        return False


def recover():
    os.makedirs(SENDING_DIR, exist_ok=True)

    # Собираем все файлы ping_, trace_ и losses_ из DATA_DIR и SENDING_DIR
    for dirpath in [DATA_DIR, SENDING_DIR]:
        if not os.path.exists(dirpath):
            continue
        files = [f for f in os.listdir(dirpath) if f.startswith(('ping_', 'trace_', 'losses_'))]

        # Группируем файлы по штампу времени
        stamps = {}
        for f in files:
            parts = f.split('_', 1)
            if len(parts) < 2:
                continue
            # Берем всё после ping_/trace_/losses_ до расширения
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
                logging.info(f"[RECOVER] Created archive {zip_path}")


async def monitor_host(host):
    current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    current_ping_file = os.path.join(DATA_DIR, f'ping_{current_stamp}.jsonl')
    current_trace_file = os.path.join(DATA_DIR, f'trace_{current_stamp}.jsonl')
    current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)

    if not os.path.exists(current_ping_file):
        open(current_ping_file, 'a').close()
        logging.info(f"[INFO] Created ping file {current_ping_file}")

    if not os.path.exists(current_trace_file):
        open(current_trace_file, 'a').close()
        logging.info(f"[INFO] Created trace file {current_trace_file}")

    lost_by_minute = {}
    if os.path.exists(current_losses_file):
        with open(current_losses_file, 'r') as f:
            try:
                lost_by_minute = json.load(f)
                logging.info(f"[INFO] Loaded existing losses from {current_losses_file}")
            except json.JSONDecodeError:
                lost_by_minute = {}

    current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    minute_sent = 0
    minute_reached = 0
    last_trace_time = 0
    last_rotation_time = datetime.now()

    while True:
        start_time = time.time()

        default_ping = await async_ping(host, count=config.config.ping.standart.packet_count)
        append_to_log(default_ping, current_ping_file)
        minute_sent += config.config.ping.standart.packet_count
        minute_reached += len(default_ping['times_ms'])

        lost_by_minute[current_minute] = {
            "packets": minute_sent,
            "reached": minute_reached
        }
        with open(current_losses_file, 'w') as f:
            json.dump(lost_by_minute, f, indent=2)

        if len(default_ping['times_ms']) < config.config.ping.standart.packet_count:
            full_ping = await async_ping(host, count=config.config.ping.check.packet_count)
            append_to_log(full_ping, current_ping_file)
            sent = config.config.ping.check.packet_count
            reached = len(full_ping['times_ms'])
            minute_sent += sent
            minute_reached += reached

            lost_by_minute[current_minute] = {
                "packets": minute_sent,
                "reached": minute_reached
            }
            with open(current_losses_file, 'w') as f:
                json.dump(lost_by_minute, f, indent=2)

            if reached < config.config.ping.check.packet_count:
                trace_result = await async_trace(host)
                append_to_log(trace_result, current_trace_file)

                logging.info("[PING LOOP] Starting continuous ping until connection restores")
                while True:
                    ping_res = await async_ping(host, count=config.config.ping.continious.packet_count)
                    append_to_log(ping_res, current_ping_file)
                    minute_sent += config.config.ping.continious.packet_count
                    minute_reached += len(ping_res['times_ms'])

                    lost_by_minute[current_minute] = {
                        "packets": minute_sent,
                        "reached": minute_reached
                    }
                    with open(current_losses_file, 'w') as f:
                        json.dump(lost_by_minute, f, indent=2)

                    if ping_res['avg_ms'] is not None:
                        logging.info("[PING LOOP] Connection restored!")
                        break
                    await asyncio.sleep(config.config.ping.continious.delay)

        if time.time() - last_trace_time >= config.config.timing.trace_check_secs:
            trace_result = await async_trace(host)
            append_to_log(trace_result, current_trace_file)
            last_trace_time = time.time()

        new_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
        if new_minute != current_minute:
            lost_by_minute = {k: v for k, v in lost_by_minute.items() if v['packets'] != v['reached']}
            with open(current_losses_file, 'w') as f:
                json.dump(lost_by_minute, f, indent=2)

            current_minute = new_minute
            minute_sent = 0
            minute_reached = 0
        if (datetime.now() - last_rotation_time).total_seconds() >= config.config.timing.rotation_secs:
            zip_name = f'archive_{current_stamp}.zip'
            zip_path = os.path.join(SENDING_DIR, zip_name)
            files_to_zip = [
                (current_ping_file, os.path.basename(current_ping_file)),
                (current_trace_file, os.path.basename(current_trace_file)),
                (current_losses_file, os.path.basename(current_losses_file))
            ]
            if zip_files(zip_path, files_to_zip):
                for f, _ in files_to_zip:
                    if os.path.exists(f):
                        os.remove(f)

            current_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            current_ping_file = os.path.join(DATA_DIR, f'ping_{current_stamp}.jsonl')
            current_trace_file = os.path.join(DATA_DIR, f'trace_{current_stamp}.jsonl')
            current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
            open(current_ping_file, 'a').close()
            open(current_trace_file, 'a').close()
            lost_by_minute = {}
            last_rotation_time = datetime.now()

        elapsed = time.time() - start_time
        await asyncio.sleep(max(0.0, config.config.ping.standart.delay - elapsed))


async def periodic_sender():
    """
    Периодически проверяет папку sending и пытается отправить архивы на сервер.
    Перемещает в sent только успешно отправленные файлы.
    """
    while True:
        await asyncio.sleep(config.config.timing.sender_check_secs)

        zip_files = [f for f in os.listdir(SENDING_DIR) if f.endswith('.zip')]
        if zip_files:
            logging.info(f"[SENDER] Found {len(zip_files)} archive(s) to send")

        for f in zip_files:
            zip_path = os.path.join(SENDING_DIR, f)
            logging.info(f"[SENDER] Processing {f}")

            if await send_to_server(zip_path):
                os.remove(zip_path)
                logging.info(f"[SENDER] Deleted sent file {f}")
            else:
                logging.info(f"[SENDER] Keeping {f} in sending directory for retry")


async def main(host):
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
        # Опционально: вывести в консоль для теста
        print(f"Error: {e}", file=sys.stderr)
        exit(1)
