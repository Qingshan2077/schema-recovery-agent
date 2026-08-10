"""Application configuration loaded from .env and environment variables."""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal

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

    AGENT_RUNTIME_V2: str = "enabled"
    MODEL_PROVIDER_MODE: str = "live"
    MODEL_PROVIDER: str = "openai_compatible"
    MODEL_FAST: str = ""
    MODEL_REASONING: str = ""
    MODEL_SYNTHESIS: str = ""
    MODEL_JUDGE: str = ""
    MODEL_EMBEDDING: str = ""
    MODEL_TIMEOUT_SECONDS: float = 60.0
    MODEL_MAX_RETRIES: int = 2
    MODEL_MAX_CONTEXT_TOKENS: int | None = None
    MODEL_STRICT_SCHEMA_PROFILES: str = ""
    MODEL_STREAMING_PROFILES: str = ""
    MODEL_TOOL_PROFILES: str = ""
    MODEL_FAST_TEMPERATURE: float = 0.1
    MODEL_REASONING_TEMPERATURE: float = 0.1
    MODEL_SYNTHESIS_TEMPERATURE: float = 0.2
    MODEL_JUDGE_TEMPERATURE: float = 0.1
    MODEL_EMBEDDING_TEMPERATURE: float | None = None

    TOOL_RUNTIME_ENFORCEMENT: str = "enforce"
    STRUCTURED_OUTPUT_REPAIR_ENABLED: bool = True
    RUNTIME_MAX_MODEL_CALLS: int = 12
    RUNTIME_MAX_TOOL_CALLS: int = 100
    RUNTIME_MAX_INPUT_TOKENS: int = 120000
    RUNTIME_MAX_OUTPUT_TOKENS: int = 24000
    RUNTIME_MAX_COST_USD: Decimal | None = None
    RUNTIME_MAX_LOOP_ITERATIONS: int = 20
    RUNTIME_MAX_TOOL_ARGUMENT_BYTES: int = 262144
    RUNTIME_DEADLINE_SECONDS: int | None = 300
    TOOL_ARTIFACT_DIR: str = "data/runtime/artifacts"

    DATA_DIR: str = "data"
    DOCKER_DATA_DIR: str = "/app/data"
    LANGGRAPH_ENABLED: bool = True
    RUNTIME_IDENTITY_V2: bool = True
    STREAM_EVENTS_V2: bool = True
    QA_REGEX_BASELINE_FIX: bool = True
    TENANT_ID: str = "default"
    PROJECT_ID: str = "default"
    EVAL_REPORT_DIR: str = "data/eval/reports"

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

    AGENT_RUNTIME_V2 = settings.AGENT_RUNTIME_V2
    MODEL_PROVIDER_MODE = settings.MODEL_PROVIDER_MODE
    MODEL_PROVIDER = settings.MODEL_PROVIDER
    MODEL_FAST = settings.MODEL_FAST or settings.LLM_MODEL
    MODEL_REASONING = settings.MODEL_REASONING or settings.LLM_MODEL
    MODEL_SYNTHESIS = settings.MODEL_SYNTHESIS or settings.LLM_MODEL
    MODEL_JUDGE = settings.MODEL_JUDGE or settings.LLM_MODEL
    MODEL_EMBEDDING = settings.MODEL_EMBEDDING or settings.LLM_MODEL
    MODEL_TIMEOUT_SECONDS = settings.MODEL_TIMEOUT_SECONDS
    MODEL_MAX_RETRIES = settings.MODEL_MAX_RETRIES
    MODEL_MAX_CONTEXT_TOKENS = settings.MODEL_MAX_CONTEXT_TOKENS
    MODEL_STRICT_SCHEMA_PROFILES = tuple(
        item.strip() for item in settings.MODEL_STRICT_SCHEMA_PROFILES.split(",") if item.strip()
    )
    MODEL_STREAMING_PROFILES = tuple(
        item.strip() for item in settings.MODEL_STREAMING_PROFILES.split(",") if item.strip()
    )
    MODEL_TOOL_PROFILES = tuple(
        item.strip() for item in settings.MODEL_TOOL_PROFILES.split(",") if item.strip()
    )
    MODEL_FAST_TEMPERATURE = settings.MODEL_FAST_TEMPERATURE
    MODEL_REASONING_TEMPERATURE = settings.MODEL_REASONING_TEMPERATURE
    MODEL_SYNTHESIS_TEMPERATURE = settings.MODEL_SYNTHESIS_TEMPERATURE
    MODEL_JUDGE_TEMPERATURE = settings.MODEL_JUDGE_TEMPERATURE
    MODEL_EMBEDDING_TEMPERATURE = settings.MODEL_EMBEDDING_TEMPERATURE

    TOOL_RUNTIME_ENFORCEMENT = settings.TOOL_RUNTIME_ENFORCEMENT
    STRUCTURED_OUTPUT_REPAIR_ENABLED = settings.STRUCTURED_OUTPUT_REPAIR_ENABLED
    RUNTIME_MAX_MODEL_CALLS = settings.RUNTIME_MAX_MODEL_CALLS
    RUNTIME_MAX_TOOL_CALLS = settings.RUNTIME_MAX_TOOL_CALLS
    RUNTIME_MAX_INPUT_TOKENS = settings.RUNTIME_MAX_INPUT_TOKENS
    RUNTIME_MAX_OUTPUT_TOKENS = settings.RUNTIME_MAX_OUTPUT_TOKENS
    RUNTIME_MAX_COST_USD = settings.RUNTIME_MAX_COST_USD
    RUNTIME_MAX_LOOP_ITERATIONS = settings.RUNTIME_MAX_LOOP_ITERATIONS
    RUNTIME_MAX_TOOL_ARGUMENT_BYTES = settings.RUNTIME_MAX_TOOL_ARGUMENT_BYTES
    RUNTIME_DEADLINE_SECONDS = settings.RUNTIME_DEADLINE_SECONDS
    TOOL_ARTIFACT_DIR = settings.TOOL_ARTIFACT_DIR

    DATA_DIR = settings.DATA_DIR
    DOCKER_DATA_DIR = settings.DOCKER_DATA_DIR
    LANGGRAPH_ENABLED = settings.LANGGRAPH_ENABLED
    RUNTIME_IDENTITY_V2 = settings.RUNTIME_IDENTITY_V2
    STREAM_EVENTS_V2 = settings.STREAM_EVENTS_V2
    QA_REGEX_BASELINE_FIX = settings.QA_REGEX_BASELINE_FIX
    TENANT_ID = settings.TENANT_ID
    PROJECT_ID = settings.PROJECT_ID
    EVAL_REPORT_DIR = settings.EVAL_REPORT_DIR

    WEIGHT_CODE = settings.WEIGHT_CODE
    WEIGHT_ORM = settings.WEIGHT_ORM
    WEIGHT_COLUMN = settings.WEIGHT_COLUMN
    WEIGHT_NAME = settings.WEIGHT_NAME
