"""Application configuration loaded from .env and environment variables."""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal
from typing import Literal

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
    QA_AGENT_V2: str = "enabled"
    QA_MAX_TOOL_CALLS: int = 6
    QA_MAX_TOOL_ROUNDS: int = 2
    QA_MAX_CONTEXT_MESSAGES: int = 12
    QA_MAX_QUESTION_CHARS: int = 4000
    QA_CHAT_DB_PATH: str = "data/chat/chat.db"

    WORKER_IMPL_SURVEY: Literal["legacy", "hybrid", "shadow"] = "legacy"
    WORKER_IMPL_COLUMN: Literal["legacy", "hybrid", "shadow"] = "legacy"
    WORKER_IMPL_NAME: Literal["legacy", "hybrid", "shadow"] = "legacy"
    WORKER_IMPL_CODE: Literal["legacy", "hybrid", "shadow"] = "legacy"
    WORKER_IMPL_ORM: Literal["legacy", "hybrid", "shadow"] = "legacy"
    WORKER_IMPL_MERGE: Literal["legacy", "hybrid", "shadow"] = "legacy"
    EVIDENCE_LEDGER_DUAL_WRITE: bool = True
    EVIDENCE_DB_PATH: str = "data/evidence/evidence.db"
    CRITIC_ENABLED: bool = False
    RUN_MAX_EVIDENCE_ROUNDS: int = 2
    WORK_UNIT_TIMEOUT_SECONDS: int = 120
    WORK_UNIT_MAX_MODEL_CALLS: int = 2
    FUSION_MODEL_VERSION: str = "log_odds_v2"
    FUSION_WEIGHT_VERSION: str = "phase3-default-v1"
    RECOVERY_ENGINE: Literal["legacy", "manual_v2", "langgraph_v2", "auto_v2", "shadow"] = "legacy"
    CHECKPOINT_BACKEND: Literal["sqlite", "postgres"] = "sqlite"
    STORE_BACKEND: Literal["sqlite", "postgres"] = "sqlite"
    WORKFLOW_VERSION: str = "schema-recovery-v2"
    STATE_SCHEMA_VERSION: str = "2"
    RECOVERY_RUN_DB_PATH: str = "data/workflow/runs.db"
    LANGGRAPH_CHECKPOINT_DB_PATH: str = "data/workflow/langgraph-checkpoints.db"
    LANGGRAPH_POSTGRES_DSN: str = ""
    AUTO_FALLBACK_ENABLED: bool = True
    RUN_MAX_AUTO_FALLBACKS: int = 1
    WORKFLOW_MAX_CONCURRENCY: int = 4
    WORKFLOW_MAX_STAGE_ATTEMPTS: int = 2
    WORKFLOW_RECURSION_LIMIT: int = 32
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
    QA_AGENT_V2 = settings.QA_AGENT_V2
    QA_MAX_TOOL_CALLS = settings.QA_MAX_TOOL_CALLS
    QA_MAX_TOOL_ROUNDS = settings.QA_MAX_TOOL_ROUNDS
    QA_MAX_CONTEXT_MESSAGES = settings.QA_MAX_CONTEXT_MESSAGES
    QA_MAX_QUESTION_CHARS = settings.QA_MAX_QUESTION_CHARS
    QA_CHAT_DB_PATH = settings.QA_CHAT_DB_PATH

    WORKER_IMPL_SURVEY = settings.WORKER_IMPL_SURVEY
    WORKER_IMPL_COLUMN = settings.WORKER_IMPL_COLUMN
    WORKER_IMPL_NAME = settings.WORKER_IMPL_NAME
    WORKER_IMPL_CODE = settings.WORKER_IMPL_CODE
    WORKER_IMPL_ORM = settings.WORKER_IMPL_ORM
    WORKER_IMPL_MERGE = settings.WORKER_IMPL_MERGE
    EVIDENCE_LEDGER_DUAL_WRITE = settings.EVIDENCE_LEDGER_DUAL_WRITE
    EVIDENCE_DB_PATH = settings.EVIDENCE_DB_PATH
    CRITIC_ENABLED = settings.CRITIC_ENABLED
    RUN_MAX_EVIDENCE_ROUNDS = settings.RUN_MAX_EVIDENCE_ROUNDS
    WORK_UNIT_TIMEOUT_SECONDS = settings.WORK_UNIT_TIMEOUT_SECONDS
    WORK_UNIT_MAX_MODEL_CALLS = settings.WORK_UNIT_MAX_MODEL_CALLS
    FUSION_MODEL_VERSION = settings.FUSION_MODEL_VERSION
    FUSION_WEIGHT_VERSION = settings.FUSION_WEIGHT_VERSION
    RECOVERY_ENGINE = settings.RECOVERY_ENGINE
    CHECKPOINT_BACKEND = settings.CHECKPOINT_BACKEND
    STORE_BACKEND = settings.STORE_BACKEND
    WORKFLOW_VERSION = settings.WORKFLOW_VERSION
    STATE_SCHEMA_VERSION = settings.STATE_SCHEMA_VERSION
    RECOVERY_RUN_DB_PATH = settings.RECOVERY_RUN_DB_PATH
    LANGGRAPH_CHECKPOINT_DB_PATH = settings.LANGGRAPH_CHECKPOINT_DB_PATH
    LANGGRAPH_POSTGRES_DSN = settings.LANGGRAPH_POSTGRES_DSN
    AUTO_FALLBACK_ENABLED = settings.AUTO_FALLBACK_ENABLED
    RUN_MAX_AUTO_FALLBACKS = settings.RUN_MAX_AUTO_FALLBACKS
    WORKFLOW_MAX_CONCURRENCY = settings.WORKFLOW_MAX_CONCURRENCY
    WORKFLOW_MAX_STAGE_ATTEMPTS = settings.WORKFLOW_MAX_STAGE_ATTEMPTS
    WORKFLOW_RECURSION_LIMIT = settings.WORKFLOW_RECURSION_LIMIT
    TENANT_ID = settings.TENANT_ID
    PROJECT_ID = settings.PROJECT_ID
    EVAL_REPORT_DIR = settings.EVAL_REPORT_DIR

    WEIGHT_CODE = settings.WEIGHT_CODE
    WEIGHT_ORM = settings.WEIGHT_ORM
    WEIGHT_COLUMN = settings.WEIGHT_COLUMN
    WEIGHT_NAME = settings.WEIGHT_NAME
