import logging
import shutil
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import Field, BaseModel, ValidationError


class TimeoutsConfig(BaseModel):
    connect_secs: int = Field(default=10)
    upload_secs: int = Field(default=300)


class TimingConfig(BaseModel):
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    trace_check_secs: int = Field(default=300)
    rotation_secs: int = Field(default=1000)
    sender_check_secs: int = Field(default=60)


class ContiniousPingConfig(BaseModel):
    packet_count: int = Field(default=1)
    delay: int = Field(default=1)


class CheckPingConfig(BaseModel):
    packet_count: int = Field(default=10)


class StandartPingConfig(BaseModel):
    packet_count: int = Field(default=2)
    delay: int = Field(default=10)


class PingConfig(BaseModel):
    standart: StandartPingConfig = Field(default_factory=StandartPingConfig)
    check: CheckPingConfig = Field(default_factory=CheckPingConfig)
    continious: ContiniousPingConfig = Field(default_factory=ContiniousPingConfig)


class AppConfig(BaseModel):
    room: int = Field(default=None)
    endpoint: str = Field(default="https://monitor.slavapmk.ru")
    timing: TimingConfig = Field(default_factory=TimingConfig)
    ping: PingConfig = Field(default_factory=PingConfig)


DEFAULT_CONFIG = AppConfig()

CONFIG_PATH = Path("config.yaml")


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        logging.info(f"Config file not found: {CONFIG_PATH}, creating default config")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        logging.info(f"Loading config from: {CONFIG_PATH}")

        # Асинхронное чтение файла
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            raw_data = yaml.safe_load(content) or {}

        # Валидация через Pydantic
        app_config = AppConfig(**raw_data)

        # Если структура изменилась (добавились новые поля с дефолтами) - пересохраняем
        if app_config.model_dump() != raw_data:
            logging.info("Config structure updated, saving normalized version")
            save_config(app_config)

        logging.info("Config loaded successfully")
        return app_config

    except (yaml.YAMLError, ValidationError, TypeError):
        # При ошибке парсинга или валидации - восстанавливаем дефолтный конфиг
        logging.info(f"Invalid config file, restoring defaults")
        traceback.print_exc()
        backup_corrupted_config()
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    except Exception:
        # При любой другой ошибке - тоже восстанавливаем дефолтный
        logging.info(f"Unexpected error loading config")
        traceback.print_exc()
        backup_corrupted_config()
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG


def save_config(app_config: AppConfig):
    try:
        logging.info(f"Saving config to: {CONFIG_PATH}")

        # Сериализация в YAML
        yaml_content = yaml.dump(
            app_config.model_dump(),
            allow_unicode=True,
            sort_keys=False
        )

        # Асинхронная запись
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        logging.info("Config saved successfully")
    except Exception as e:
        logging.info(f"Failed to save config to {CONFIG_PATH}", e)
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
    logging.info(f"Corrupted config backed up to: {backup_path}")


def init_config() -> AppConfig:
    """
    Инициализировать конфигурацию приложения.

    Должна быть вызвана при старте приложения.

    Returns:
        Загруженная конфигурация

    Raises:
        Exception: При критической ошибке инициализации
    """
    logging.info("Initializing application config")
    try:
        cfg = load_config()
        logging.info("Application config initialized successfully")
        return cfg
    except Exception as e:
        logging.info("Failed to initialize application config", e)
        raise Exception() from e


# Глобальный экземпляр конфигурации (инициализируется через init_config())
config: AppConfig | None = init_config()
