import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.app_host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port: int = int(os.getenv("APP_PORT", "8080"))
        self.db_path: Path = Path(os.getenv("DB_PATH", "./data/app.db"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.request_log_max: int = int(os.getenv("REQUEST_LOG_MAX", "10000"))
        self.autosave_interval: int = int(os.getenv("AUTOSAVE_INTERVAL", "60"))


settings = Settings()
