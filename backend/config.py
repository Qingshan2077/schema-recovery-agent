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

    WORKER_IMPL_SURVEY: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    WORKER_IMPL_COLUMN: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    WORKER_IMPL_NAME: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    WORKER_IMPL_CODE: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    WORKER_IMPL_ORM: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    WORKER_IMPL_MERGE: Literal["legacy", "hybrid", "shadow"] = "hybrid"
    EVIDENCE_LEDGER_DUAL_WRITE: bool = True
    EVIDENCE_DB_PATH: str = "data/evidence/evidence.db"
    CRITIC_ENABLED: bool = True
    RUN_MAX_EVIDENCE_ROUNDS: int = 2
    WORK_UNIT_TIMEOUT_SECONDS: int = 120
    WORK_UNIT_MAX_MODEL_CALLS: int = 2
    FUSION_MODEL_VERSION: str = "log_odds_v3"
    FUSION_WEIGHT_VERSION: str = "phase5-feature-schema-v1"
    RECOVERY_ENGINE: Literal["legacy", "manual_v2", "langgraph_v2", "auto_v2", "shadow"] = "auto_v2"
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
    MEMORY_V2_READ_ENABLED: bool = True
    MEMORY_V2_WRITE_ENABLED: bool = True
    MEMORY_VECTOR_ENABLED: bool = True
    EVIDENCE_LEDGER_ENABLED: bool = True
    FUSION_V2_ENABLED: bool = True
    CALIBRATION_ENABLED: bool = True
    MEMORY_INSPECTOR_ENABLED: bool = True
    MEMORY_V2_DB_PATH: str = "data/memory/memory-v2.db"
    MEMORY_L1_ACTIVE_TTL_DAYS: int = 7
    MEMORY_L1_COMPLETED_TTL_DAYS: int = 30
    MEMORY_L3_CANDIDATE_TTL_DAYS: int = 60
    MEMORY_CONTEXT_MAX_TOKENS: int = 4000
    MEMORY_RETRIEVAL_TOP_K: int = 20
    MEMORY_VECTOR_PROVIDER: str = ""
    FUSION_POLICY_PATH: str = "data/calibration/fusion-policy.json"
    FUSION_FEATURE_SCHEMA_PATH: str = "data/calibration/fusion-feature-schema.json"
    TENANT_ID: str = "default"
    PROJECT_ID: str = "default"
    EVAL_REPORT_DIR: str = "data/eval/reports"
    EVAL_V2_ENABLED: bool = True
    EVAL_V2_DB_PATH: str = "data/eval/eval-v2.db"
    EVAL_ARTIFACT_DIR: str = "data/eval/eval-artifacts"
    EVAL_DATASET_REGISTRY_PATH: str = "data/eval/registry.json"
    OTEL_ENABLED: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "schema-recovery-agent"
    TRACE_DB_PATH: str = "data/observability/traces.db"
    TRACE_PAYLOAD_CAPTURE: bool = False
    JUDGE_V2_ENABLED: bool = False
    CI_GATE_ENFORCED: bool = False
    DBA_V2_ENABLED: bool = True
    DBA_PLAN_ENABLED: bool = True
    DBA_EXECUTION_ENABLED: bool = False
    DBA_OPERATION_DB_PATH: str = "data/dba/operations.db"
    DBA_OPERATION_TTL_MINUTES: int = 30
    DBA_ALLOWED_ENVIRONMENTS: str = "dev,staging"
    DBA_EXECUTION_CONNECTION_ALLOWLIST: str = ""
    AGENT_WORKBENCH_ENABLED: bool = True
    RUN_INSPECTOR_ENABLED: bool = True
    EVIDENCE_WORKBENCH_ENABLED: bool = True
    ER_EXPLORER_V2_ENABLED: bool = True
    APPROVAL_CENTER_ENABLED: bool = True
    DEPLOYMENT_GIT_SHA: str = "unknown"
    DEPLOYMENT_DIRTY_WORKTREE: bool = True

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
    MEMORY_V2_READ_ENABLED = settings.MEMORY_V2_READ_ENABLED
    MEMORY_V2_WRITE_ENABLED = settings.MEMORY_V2_WRITE_ENABLED
    MEMORY_VECTOR_ENABLED = settings.MEMORY_VECTOR_ENABLED
    EVIDENCE_LEDGER_ENABLED = settings.EVIDENCE_LEDGER_ENABLED
    FUSION_V2_ENABLED = settings.FUSION_V2_ENABLED
    CALIBRATION_ENABLED = settings.CALIBRATION_ENABLED
    MEMORY_INSPECTOR_ENABLED = settings.MEMORY_INSPECTOR_ENABLED
    MEMORY_V2_DB_PATH = settings.MEMORY_V2_DB_PATH
    MEMORY_L1_ACTIVE_TTL_DAYS = settings.MEMORY_L1_ACTIVE_TTL_DAYS
    MEMORY_L1_COMPLETED_TTL_DAYS = settings.MEMORY_L1_COMPLETED_TTL_DAYS
    MEMORY_L3_CANDIDATE_TTL_DAYS = settings.MEMORY_L3_CANDIDATE_TTL_DAYS
    MEMORY_CONTEXT_MAX_TOKENS = settings.MEMORY_CONTEXT_MAX_TOKENS
    MEMORY_RETRIEVAL_TOP_K = settings.MEMORY_RETRIEVAL_TOP_K
    MEMORY_VECTOR_PROVIDER = settings.MEMORY_VECTOR_PROVIDER
    FUSION_POLICY_PATH = settings.FUSION_POLICY_PATH
    FUSION_FEATURE_SCHEMA_PATH = settings.FUSION_FEATURE_SCHEMA_PATH
    TENANT_ID = settings.TENANT_ID
    PROJECT_ID = settings.PROJECT_ID
    EVAL_REPORT_DIR = settings.EVAL_REPORT_DIR
    EVAL_V2_ENABLED = settings.EVAL_V2_ENABLED
    EVAL_V2_DB_PATH = settings.EVAL_V2_DB_PATH
    EVAL_ARTIFACT_DIR = settings.EVAL_ARTIFACT_DIR
    EVAL_DATASET_REGISTRY_PATH = settings.EVAL_DATASET_REGISTRY_PATH
    OTEL_ENABLED = settings.OTEL_ENABLED
    OTEL_EXPORTER_OTLP_ENDPOINT = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    OTEL_SERVICE_NAME = settings.OTEL_SERVICE_NAME
    TRACE_DB_PATH = settings.TRACE_DB_PATH
    TRACE_PAYLOAD_CAPTURE = settings.TRACE_PAYLOAD_CAPTURE
    JUDGE_V2_ENABLED = settings.JUDGE_V2_ENABLED
    CI_GATE_ENFORCED = settings.CI_GATE_ENFORCED
    DBA_V2_ENABLED = settings.DBA_V2_ENABLED
    DBA_PLAN_ENABLED = settings.DBA_PLAN_ENABLED
    DBA_EXECUTION_ENABLED = settings.DBA_EXECUTION_ENABLED
    DBA_OPERATION_DB_PATH = settings.DBA_OPERATION_DB_PATH
    DBA_OPERATION_TTL_MINUTES = settings.DBA_OPERATION_TTL_MINUTES
    DBA_ALLOWED_ENVIRONMENTS = tuple(
        item.strip() for item in settings.DBA_ALLOWED_ENVIRONMENTS.split(",") if item.strip()
    )
    DBA_EXECUTION_CONNECTION_ALLOWLIST = tuple(
        item.strip() for item in settings.DBA_EXECUTION_CONNECTION_ALLOWLIST.split(",") if item.strip()
    )
    AGENT_WORKBENCH_ENABLED = settings.AGENT_WORKBENCH_ENABLED
    RUN_INSPECTOR_ENABLED = settings.RUN_INSPECTOR_ENABLED
    EVIDENCE_WORKBENCH_ENABLED = settings.EVIDENCE_WORKBENCH_ENABLED
    ER_EXPLORER_V2_ENABLED = settings.ER_EXPLORER_V2_ENABLED
    APPROVAL_CENTER_ENABLED = settings.APPROVAL_CENTER_ENABLED
    DEPLOYMENT_GIT_SHA = settings.DEPLOYMENT_GIT_SHA
    DEPLOYMENT_DIRTY_WORKTREE = settings.DEPLOYMENT_DIRTY_WORKTREE

    WEIGHT_CODE = settings.WEIGHT_CODE
    WEIGHT_ORM = settings.WEIGHT_ORM
    WEIGHT_COLUMN = settings.WEIGHT_COLUMN
    WEIGHT_NAME = settings.WEIGHT_NAME
