"""Application configuration using pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NMS_",
        case_sensitive=False,
    )

    # Application
    app_name: str = "NMS Simulator"
    app_version: str = "0.1.0"
    debug: bool = False

    # Management API server
    host: str = "0.0.0.0"
    port: int = 8000

    # HTTP Mock Server
    mock_host: str = "0.0.0.0"
    mock_port: int = 8080

    # Database
    db_path: str = str(Path("data") / "nms.db")

    # CORS
    cors_origins: list[str] = ["*"]

    # Logging
    log_level: str = "INFO"
    log_dir: str = "logs"


settings = Settings()
