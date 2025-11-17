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
    with open(file_path, 'a') as f:
        json.dump(data, f)
        f.write('\n')


def save_losses(lost_dict, file_path):
    if lost_dict:  # Only save if there is data
        with open(file_path, 'w') as f:
            json.dump(lost_dict, f)


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

    # Ensure current log exists
    if not os.path.exists(current_log_file):
        open(current_log_file, 'a').close()

    # Load existing losses if exists
    lost_by_minute = {}
    if os.path.exists(current_losses_file):
        with open(current_losses_file, 'r') as f:
            lost_by_minute = json.load(f)

    last_trace_time = time.time()
    last_rotation_time = time.time()

    while True:
        start_time = time.time()

        # Одиночный пинг каждые 10 секунд
        single_ping = await async_ping(host, count=1)
        print(f"Single ping: {single_ping}")
        append_to_log(single_ping, current_log_file)

        # Calculate lost for single ping
        lost_single = 1 if single_ping['avg_ms'] is None else 0
        if lost_single > 0:
            minute_key = datetime.now().strftime("%Y-%m-%d %H:%M")
            lost_by_minute[minute_key] = lost_by_minute.get(minute_key, 0) + lost_single
            save_losses(lost_by_minute, current_losses_file)

        if single_ping['avg_ms'] is None:  # Если одиночный пинг не прошел
            full_ping = await async_ping(host, count=4)
            print(f"Full ping: {full_ping}")
            append_to_log(full_ping, current_log_file)

            # Calculate lost for full ping
            lost_full = 4 - len(full_ping['times_ms'])
            if lost_full > 0:
                minute_key = datetime.now().strftime("%Y-%m-%d %H:%M")
                lost_by_minute[minute_key] = lost_by_minute.get(minute_key, 0) + lost_full
                save_losses(lost_by_minute, current_losses_file)

            if len(full_ping['times_ms']) < 4:  # Если есть хотя бы одна потеря
                trace_result = await async_trace(host)
                print(f"Trace due to packet loss: {trace_result}")
                append_to_log(trace_result, current_log_file)

        # Проверка на каждые 5 минут для отдельного trace
        current_time = time.time()
        if current_time - last_trace_time >= 300:  # 5 минут = 300 секунд
            trace_result = await async_trace(host)
            print(f"Periodic trace: {trace_result}")
            append_to_log(trace_result, current_log_file)
            last_trace_time = current_time

        # Check for rotation every hour
        if current_time - last_rotation_time >= 3600:
            # Save losses (though already saved if changed)
            save_losses(lost_by_minute, current_losses_file)

            # Create zip in sending and delete originals
            stamp = current_stamp  # Use the current one before updating
            zip_name = f'archive_{stamp}.zip'
            zip_path = os.path.join(SENDING_DIR, zip_name)
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(current_log_file, os.path.basename(current_log_file))
                if os.path.exists(current_losses_file):
                    zipf.write(current_losses_file, os.path.basename(current_losses_file))

            # Delete originals
            os.remove(current_log_file)
            if os.path.exists(current_losses_file):
                os.remove(current_losses_file)

            # New stamp and files
            current_stamp = datetime.now().strftime("%Y%m%d_%H")
            current_log_file = os.path.join(DATA_DIR, f'log_{current_stamp}.jsonl')
            current_losses_file = os.path.join(DATA_DIR, f'losses_{current_stamp}.json')
            open(current_log_file, 'a').close()
            lost_by_minute = {}
            last_rotation_time = current_time

        # Sleep с учетом времени выполнения
        elapsed = time.time() - start_time
        sleep_time = max(0.0, 10.0 - elapsed)
        await asyncio.sleep(sleep_time)


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
