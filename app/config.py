from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_NAME: Optional[str] = None

    RABBITMQ_HOST: Optional[str] = None
    RABBITMQ_PORT: Optional[int] = None
    RABBITMQ_USER: Optional[str] = None
    RABBITMQ_PASSWORD: Optional[str] = None
    QUEUE_NAME: Optional[str] = None

    APP_NAME: Optional[str] = None
    API_VERSION: Optional[str] = None
    DEBUG: Optional[bool] = None

    JWT_SECRET_KEY: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    UPLOAD_DIR: str = "/app/uploads"

    @property
    def DATABASE_URL_psycopg(self):
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    def validate(self) -> None:
        if not all([
            self.DB_HOST, self.DB_USER, self.DB_PASSWORD, self.DB_NAME,
            self.RABBITMQ_HOST, self.RABBITMQ_PORT, self.RABBITMQ_USER,
            self.RABBITMQ_PASSWORD, self.QUEUE_NAME, self.JWT_SECRET_KEY,
        ]):
            raise ValueError("Missing required configuration")


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.validate()
    return settings
