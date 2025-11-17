import asyncio
import json
import os
import shutil
import time
import zipfile
from datetime import datetime

from nettools import ping, trace


# Define async versions since they might not be in nettools
async def async_ping(host, count=4):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ping, host, count)


async def async_trace(host):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, trace, host)


DATA_DIR = 'data'
SENDING_DIR = 'sending'
SENT_DIR = 'sent'
SEND_PREFIX = '536'


def append_to_log(data, file_path):
    try:
        with open(file_path, 'a') as f:
            json.dump(data, f)
            f.write('\n')
        print(f"[LOG] Appended data to {file_path}")
    except Exception as e:
        print(f"[ERROR] Failed to append log: {e}")


def save_losses(minute_key, sent_packets, received_packets, file_path):
    """
    Сохраняет потери в формате:
    {
        "YYYY-MM-DD HH:MM": {"packets": int, "reached": int, "losses": float}, ...
    }
    """
    # Загружаем старые данные, если есть
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                lost_by_minute = json.load(f)
            except json.JSONDecodeError:
                lost_by_minute = {}
    else:
        lost_by_minute = {}

    # Обновляем для текущей минуты
    existing = lost_by_minute.get(minute_key, {"packets": 0, "reached": 0, "losses": 0.0})
    existing['packets'] += sent_packets
    existing['reached'] += received_packets
    existing['losses'] = round(
        100 * (existing['packets'] - existing['reached']) / existing['packets'], 2
    ) if existing['packets'] > 0 else 0.0

    lost_by_minute[minute_key] = existing

    # Записываем обратно
    with open(file_path, 'w') as f:
        json.dump(lost_by_minute, f, indent=2)


# Обновленная запись потерь пакетов
def update_losses(lost_by_minute, sent, reached):
    losses_percent = round((sent - reached) / sent * 100, 2) if sent else 0
    minute_key = datetime.now().strftime("%Y-%m-%d %H:%M")
    lost_by_minute[minute_key] = {
        "packets": sent,
        "reached": reached,
        "losses": losses_percent
    }
    print(f"[LOSS] {minute_key}: {lost_by_minute[minute_key]}")
    return lost_by_minute


def zip_files(zip_path, files):
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for src, arcname in files:
                if os.path.exists(src):
                    zipf.write(src, arcname)
                    print(f"[ZIP] Added {src} as {arcname}")
                else:
                    print(f"[ZIP] File not found: {src}")
        print(f"[ZIP] Created zip {zip_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to zip files: {e}")
        return False


async def send_to_server(zip_path):
    print(f"Sending packed data to server: {zip_path}")
    return True  # Stub, can be modified to return False on failure


def recover():
    # Recover old files in data
    current_stamp = datetime.now().strftime("%Y%m%d_%H")
    data_files = os.listdir(DATA_DIR) if os.path.exists(DATA_DIR) else []
    old_stamps = set()
    for f in data_files:
        if f.startswith('log_') and f.endswith('.jsonl'):
            stamp = f[4:-6]
            if stamp != current_stamp:
                old_stamps.add(stamp)

    for stamp in old_stamps:
        log_file = f'log_{stamp}.jsonl'
        log_path = os.path.join(DATA_DIR, log_file)
        losses_file = f'losses_{stamp}.json'
        losses_path = os.path.join(DATA_DIR, losses_file) if losses_file in data_files else None

        zip_name = f'archive_{stamp}.zip'
        zip_path = os.path.join(SENDING_DIR, zip_name)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            zipf.write(log_path, log_file)
            if losses_path and os.path.exists(losses_path):
                zipf.write(losses_path, losses_file)

        os.remove(log_path)
        if losses_path and os.path.exists(losses_path):
            os.remove(losses_path)

    # Recover in sending: if there are loose log/losses, zip them and remove
    sending_files = os.listdir(SENDING_DIR) if os.path.exists(SENDING_DIR) else []
    loose_stamps = set()
    for f in sending_files:
        if f.startswith('log_') and f.endswith('.jsonl'):
            stamp = f[4:-6]
            loose_stamps.add(stamp)

    for stamp in loose_stamps:
        log_file = f'log_{stamp}.jsonl'
        log_path = os.path.join(SENDING_DIR, log_file)
        losses_file = f'losses_{stamp}.json'
        losses_path = os.path.join(SENDING_DIR, losses_file) if losses_file in sending_files else None

        zip_name = f'archive_{stamp}.zip'
        zip_path = os.path.join(SENDING_DIR, zip_name)

        # If zip already exists, remove loose files
        if os.path.exists(zip_path):
            if os.path.exists(log_path):
                os.remove(log_path)
            if losses_path and os.path.exists(losses_path):
                os.remove(losses_path)
        else:
            # Create zip
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(log_path, log_file)
                if losses_path and os.path.exists(losses_path):
                    zipf.write(losses_path, losses_file)

            os.remove(log_path)
            if losses_path and os.path.exists(losses_path):
                os.remove(losses_path)


async def monitor_host(host):
    current_stamp = datetime.now().strftime("%Y%m%d_%H")
    current_log_file = os.path.join(DATA_DIR, f'log_{current_stamp}.jsonl')
    current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(current_log_file):
        open(current_log_file, 'a').close()
        print(f"[INFO] Created log file {current_log_file}")

    lost_by_minute = {}
    if os.path.exists(current_losses_file):
        with open(current_losses_file, 'r') as f:
            lost_by_minute = json.load(f)
        print(f"[INFO] Loaded existing losses from {current_losses_file}")

    last_trace_time = time.time()
    last_rotation_time = time.time()

    while True:
        start_time = time.time()
        single_ping = await async_ping(host, count=1)
        print(f"[PING] Single ping: {single_ping}")
        append_to_log(single_ping, current_log_file)

        # Update losses
        sent = 1
        reached = 0 if single_ping['avg_ms'] is None else 1
        lost_by_minute = update_losses(lost_by_minute, sent, reached)
        minute_key = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_losses(minute_key, sent, reached, current_losses_file)

        # Full ping if lost
        if single_ping['avg_ms'] is None:
            full_ping = await async_ping(host, count=4)
            print(f"[PING] Full ping: {full_ping}")
            append_to_log(full_ping, current_log_file)
            sent = 4
            reached = len(full_ping['times_ms'])
            lost_by_minute = update_losses(lost_by_minute, sent, reached)
            save_losses(minute_key, sent, reached, current_losses_file)

            if reached < 4:
                trace_result = await async_trace(host)
                print(f"[TRACE] Due to packet loss: {trace_result}")
                append_to_log(trace_result, current_log_file)

        # Periodic trace every 5 minutes
        if time.time() - last_trace_time >= 300:
            trace_result = await async_trace(host)
            print(f"[TRACE] Periodic trace: {trace_result}")
            append_to_log(trace_result, current_log_file)
            last_trace_time = time.time()

        # Hourly rotation
        if time.time() - last_rotation_time >= 3600:
            os.makedirs(SENDING_DIR, exist_ok=True)
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
                        print(f"[INFO] Deleted original file {f}")

            current_stamp = datetime.now().strftime("%Y%m%d_%H")
            current_log_file = os.path.join(DATA_DIR, f'log_{current_stamp}.jsonl')
            current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
            open(current_log_file, 'a').close()
            lost_by_minute = {}
            last_rotation_time = time.time()

        # Sleep with adjustment
        elapsed = time.time() - start_time
        await asyncio.sleep(max(0.0, 10.0 - elapsed))


async def periodic_sender():
    while True:
        await asyncio.sleep(60)  # Check every minute

        if not os.path.exists(SENDING_DIR):
            continue

        sending_files = os.listdir(SENDING_DIR)
        for f in sending_files:
            if f.startswith('archive_') and f.endswith('.zip'):
                zip_path = os.path.join(SENDING_DIR, f)
                success = await send_to_server(zip_path)
                if success:
                    shutil.move(zip_path, os.path.join(SENT_DIR, f))
                # If not success, leave for next attempt


async def main(host):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SENDING_DIR, exist_ok=True)
    os.makedirs(SENT_DIR, exist_ok=True)

    recover()

    monitor_task = asyncio.create_task(monitor_host(host))
    sender_task = asyncio.create_task(periodic_sender())
    await asyncio.gather(monitor_task, sender_task)


if __name__ == "__main__":
    asyncio.run(main('1.1.1.1'))
