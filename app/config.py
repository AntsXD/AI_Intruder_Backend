import os
from pathlib import Path
from dotenv import load_dotenv

from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    app_name: str = "Intruder Detection Backend"
    env: str = "dev"
    api_prefix: str = "/api/v1"

    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY")
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 7
    stream_token_minutes: int = 10

    database_url: str = "sqlite:///./intruder_demo.db"
    storage_root: str = "./storage"

    webhook_api_key: str = "change-me"
    webhook_signing_secret: str = ""
    webhook_signature_tolerance_seconds: int = 300

    firebase_credentials_path: str = ""
    environment: str = "development"
    fcm_enabled: bool = False
    smtp_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_app_password: str = ""
    smtp_from: str = ""

    sms_enabled: bool = False
    sms_demo_target: str = ""

    cors_origins: str = "http://localhost:3000"
    auto_create_tables: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_root_path(self) -> Path:
        return Path(self.storage_root)


settings = Settings()
