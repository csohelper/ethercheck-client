import shutil
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import Field, BaseModel, ValidationError


class AppConfig(BaseModel):
    room: int | None = Field(default=None)
    endpoint: str = Field(default="https://monitor.slavapmk.ru")


DEFAULT_CONFIG = AppConfig()

CONFIG_PATH = Path("config.yaml")


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        print(f"Config file not found: {CONFIG_PATH}, creating default config")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        print(f"Loading config from: {CONFIG_PATH}")

        # Асинхронное чтение файла
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            raw_data = yaml.safe_load(content) or {}

        # Валидация через Pydantic
        app_config = AppConfig(**raw_data)

        # Если структура изменилась (добавились новые поля с дефолтами) - пересохраняем
        if app_config.model_dump() != raw_data:
            print("Config structure updated, saving normalized version")
            save_config(app_config)

        print("Config loaded successfully")
        return app_config

    except (yaml.YAMLError, ValidationError, TypeError):
        # При ошибке парсинга или валидации - восстанавливаем дефолтный конфиг
        print(f"Invalid config file, restoring defaults")
        traceback.print_exc()
        backup_corrupted_config()
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    except Exception:
        # При любой другой ошибке - тоже восстанавливаем дефолтный
        print(f"Unexpected error loading config")
        traceback.print_exc()
        backup_corrupted_config()
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG


async def save_config(app_config: AppConfig):
    try:
        print(f"Saving config to: {CONFIG_PATH}")

        # Сериализация в YAML
        yaml_content = yaml.dump(
            app_config.model_dump(),
            allow_unicode=True,
            sort_keys=False
        )

        # Асинхронная запись
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        print("Config saved successfully")
    except Exception as e:
        print(f"Failed to save config to {CONFIG_PATH}", e)
        raise


def backup_corrupted_config():
    """
    Создать бэкап поврежденного конфига.

    Синхронная функция для надежности при критических ошибках.
    Создает копию файла с временной меткой в том же каталоге.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S%z")
    backup_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.stem}_backup_{timestamp}{CONFIG_PATH.suffix}")
    shutil.copy(CONFIG_PATH, backup_path)
    print(f"Corrupted config backed up to: {backup_path}")


def init_config() -> AppConfig:
    """
    Инициализировать конфигурацию приложения.

    Должна быть вызвана при старте приложения.

    Returns:
        Загруженная конфигурация

    Raises:
        Exception: При критической ошибке инициализации
    """
    print("Initializing application config")
    try:
        cfg = load_config()
        print("Application config initialized successfully")
        return cfg
    except Exception as e:
        print("Failed to initialize application config", e)
        raise Exception() from e


# Глобальный экземпляр конфигурации (инициализируется через init_config())
config: AppConfig | None = init_config()
