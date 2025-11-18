import asyncio
import os
from pathlib import Path

import aiohttp

ROOM = int(os.getenv("ROOM", "536"))  # по умолчанию 536, если не задано

# Адрес твоего Flask-приёмника
SERVER_URL = os.getenv(
    "UPLOAD_SERVER",
    "http://127.0.0.1:5000"  # ← замени на реальный IP/домен сервера
).rstrip("/")

# Таймауты (секунды)
TIMEOUT_CONNECT = 10
TIMUPLOAD_TOTAL = 300  # 5 минут на большой архив


async def send_to_server(zip_path: str | Path) -> bool:
    """
    Отправка ZIP-архива на сервер.
    Возвращает True только если сервер вернул 200 OK.
    """
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        print(f"[SEND] File not found: {zip_path}")
        return False

    url = f"{SERVER_URL}/upload/{ROOM}/"
    print(f"[SEND] Sending {zip_path.name} ({zip_path.stat().st_size // 1024} KB) → {url}")

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
                    print(f"[SEND] Successfully sent {zip_path.name}")
                    return True
                else:
                    text = await resp.text()
                    print(f"[SEND] Server returned {resp.status}: {text}")
                    return False

    except aiohttp.ClientResponseError as e:
        print(f"[SEND] HTTP error {e.status}: {e.message}")
        return False
    except asyncio.TimeoutError:
        print(f"[SEND] Timeout while sending {zip_path}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error while sending {zip_path}: {e}")
        return False
