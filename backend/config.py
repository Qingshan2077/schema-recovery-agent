"""Application configuration loaded from .env and environment variables."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"
load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 3307
    DB_USER: str = "root"
    DB_PASSWORD: str = "schema_recovery_pwd"
    DB_NAME: str = "schema_recovery_demo"

    MYSQL_ROOT_PASSWORD: str = "schema_recovery_pwd"
    MYSQL_DATABASE: str = "schema_recovery_demo"
    MYSQL_HOST_PORT: int = 3307
    MYSQL_CONTAINER_PORT: int = 3306

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    DATA_DIR: str = "data"
    DOCKER_DATA_DIR: str = "/app/data"
    LANGGRAPH_ENABLED: bool = True

    WEIGHT_CODE: float = 0.40
    WEIGHT_ORM: float = 0.25
    WEIGHT_COLUMN: float = 0.20
    WEIGHT_NAME: float = 0.15

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")


settings = Settings()


class Config:
    DB_HOST = settings.DB_HOST
    DB_PORT = settings.DB_PORT
    DB_USER = settings.DB_USER
    DB_PASSWORD = settings.DB_PASSWORD
    DB_NAME = settings.DB_NAME

    MYSQL_ROOT_PASSWORD = settings.MYSQL_ROOT_PASSWORD
    MYSQL_DATABASE = settings.MYSQL_DATABASE
    MYSQL_HOST_PORT = settings.MYSQL_HOST_PORT
    MYSQL_CONTAINER_PORT = settings.MYSQL_CONTAINER_PORT

    API_HOST = settings.API_HOST
    API_PORT = settings.API_PORT

    LLM_API_KEY = settings.LLM_API_KEY
    LLM_BASE_URL = settings.LLM_BASE_URL
    LLM_MODEL = settings.LLM_MODEL

    DATA_DIR = settings.DATA_DIR
    DOCKER_DATA_DIR = settings.DOCKER_DATA_DIR
    LANGGRAPH_ENABLED = settings.LANGGRAPH_ENABLED

    WEIGHT_CODE = settings.WEIGHT_CODE
    WEIGHT_ORM = settings.WEIGHT_ORM
    WEIGHT_COLUMN = settings.WEIGHT_COLUMN
    WEIGHT_NAME = settings.WEIGHT_NAME
