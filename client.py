import asyncio
import logging
import os
from pathlib import Path

import aiohttp

import config

ROOM = config.config.room
if ROOM is None:
    env_room = os.getenv("room")
    if env_room is None:
        logging.info("[ERROR] No room specified")
        exit(1)
    ROOM = int(env_room)

SERVER_URL = config.config.endpoint
if SERVER_URL is None:
    SERVER_URL = os.getenv("UPLOAD_SERVER")
    if SERVER_URL is None:
        logging.info('[ERROR] No endpoint specified')
        exit(1)

# Таймауты (секунды)
TIMEOUT_CONNECT = config.config.timing.timeouts.connect_secs
TIMUPLOAD_TOTAL = config.config.timing.timeouts.upload_secs


async def send_to_server(zip_path: str | Path) -> bool:
    """
    Отправка ZIP-архива на сервер.
    Возвращает True только если сервер вернул 200 OK.
    """
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        logging.info(f"[SEND] File not found: {zip_path}")
        return False

    url = f"{SERVER_URL}/upload/{ROOM}/"
    logging.info(f"[SEND] Sending {zip_path.name} ({zip_path.stat().st_size // 1024} KB) → {url}")

    # Формируем multipart-данные вручную, чтобы контролировать имя поля и filename
    data = aiohttp.FormData()
    data.add_field(
        'file',
        zip_path.open('rb'),
        filename=zip_path.name,
        content_type='application/zip'
    )

    timeout = aiohttp.ClientTimeout(
        total=TIMUPLOAD_TOTAL,
        connect=TIMEOUT_CONNECT
    )

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=data) as resp:
                if resp.status == 200:
                    logging.info(f"[SEND] Successfully sent {zip_path.name}")
                    return True
                else:
                    text = await resp.text()
                    logging.info(f"[SEND] Server returned {resp.status}: {text}")
                    return False

    except aiohttp.ClientResponseError as e:
        logging.info(f"[SEND] HTTP error {e.status}: {e.message}")
        return False
    except asyncio.TimeoutError:
        logging.info(f"[SEND] Timeout while sending {zip_path}")
        return False
    except Exception as e:
        logging.info(f"[ERROR] Unexpected error while sending {zip_path}: {e}")
        return False
