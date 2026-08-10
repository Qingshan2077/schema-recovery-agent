"""Phase 1 runtime composition root and stable public surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.agent.runtime.contracts import (
    AgentError,
    AgentRunResult,
    ModelRequest,
    ModelResult,
    RunBudget,
    ToolCallRequest,
    ToolCallResult,
    ToolSpec,
)
from backend.agent.runtime.context_builder import ContextBuilder
from backend.agent.runtime.model_gateway import ModelGateway
from backend.agent.runtime.model_profiles import ModelProfileRegistry
from backend.agent.runtime.prompt_registry import PromptRegistry
from backend.agent.runtime.providers import FakeProvider, OpenAICompatibleProvider, ProviderAdapter
from backend.agent.runtime.run_context import CancellationToken, RunContext
from backend.agent.runtime.tool_runtime import LocalArtifactStore, ToolRuntime
from backend.core.identity import RunIdentity


@dataclass(frozen=True)
class RuntimeContainer:
    model_gateway: ModelGateway
    tool_runtime: ToolRuntime
    profiles: ModelProfileRegistry
    prompts: PromptRegistry
    default_budget: RunBudget
    deadline_seconds: int | None = None

    def new_context(
        self,
        identity: RunIdentity,
        *,
        agent_id: str,
        event_sink: object | None = None,
        cancellation: CancellationToken | None = None,
    ) -> RunContext:
        budget = self.default_budget.model_copy(deep=True)
        if self.deadline_seconds is not None:
            budget.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=self.deadline_seconds)
        return RunContext.from_identity(
            identity,
            agent_id=agent_id,
            budget=budget,
            event_sink=event_sink,
            cancellation=cancellation,
        )


def build_runtime_container(config: object, *, providers: dict[str, ProviderAdapter] | None = None) -> RuntimeContainer:
    runtime_mode = str(getattr(config, "AGENT_RUNTIME_V2", "enabled")).strip().lower()
    if runtime_mode not in {"false", "shadow", "enabled"}:
        raise ValueError("AGENT_RUNTIME_V2 must be false, shadow, or enabled")
    profiles = ModelProfileRegistry.from_config(config)
    prompts = PromptRegistry()
    prompts.validate_all()
    provider_mode = str(getattr(config, "MODEL_PROVIDER_MODE", "live")).strip().lower()
    if provider_mode not in {"fake", "live"}:
        raise ValueError("MODEL_PROVIDER_MODE must be fake or live")
    if providers is None:
        if provider_mode == "fake":
            providers = {"fake": FakeProvider()}
        else:
            providers = {
                str(getattr(config, "MODEL_PROVIDER", "openai_compatible")): OpenAICompatibleProvider(
                    api_key=str(getattr(config, "LLM_API_KEY", "")),
                    base_url=str(getattr(config, "LLM_BASE_URL", "")),
                )
            }
    artifact_store = LocalArtifactStore(str(getattr(config, "TOOL_ARTIFACT_DIR", "data/runtime/artifacts")))
    tool_runtime = ToolRuntime(
        allowlists=_default_tool_allowlists(),
        artifact_store=artifact_store,
        enforcement=str(getattr(config, "TOOL_RUNTIME_ENFORCEMENT", "enforce")),
        max_argument_bytes=int(getattr(config, "RUNTIME_MAX_TOOL_ARGUMENT_BYTES", 262144)),
    )
    gateway = ModelGateway(
        profiles=profiles,
        prompts=prompts,
        providers=providers,
        context_builder=ContextBuilder(),
        repair_enabled=bool(getattr(config, "STRUCTURED_OUTPUT_REPAIR_ENABLED", True)),
    )
    budget = build_default_budget(config, include_deadline=False)
    deadline_seconds = getattr(config, "RUNTIME_DEADLINE_SECONDS", None)
    return RuntimeContainer(
        model_gateway=gateway,
        tool_runtime=tool_runtime,
        profiles=profiles,
        prompts=prompts,
        default_budget=budget,
        deadline_seconds=int(deadline_seconds) if deadline_seconds is not None else None,
    )


def build_default_budget(config: object, *, include_deadline: bool = True) -> RunBudget:
    deadline_seconds = getattr(config, "RUNTIME_DEADLINE_SECONDS", None)
    deadline = (
        datetime.now(timezone.utc) + timedelta(seconds=int(deadline_seconds))
        if deadline_seconds is not None and include_deadline
        else None
    )
    return RunBudget(
        max_model_calls=int(getattr(config, "RUNTIME_MAX_MODEL_CALLS", 12)),
        max_tool_calls=int(getattr(config, "RUNTIME_MAX_TOOL_CALLS", 100)),
        max_input_tokens=int(getattr(config, "RUNTIME_MAX_INPUT_TOKENS", 120000)),
        max_output_tokens=int(getattr(config, "RUNTIME_MAX_OUTPUT_TOKENS", 24000)),
        max_cost_usd=(
            Decimal(str(getattr(config, "RUNTIME_MAX_COST_USD")))
            if getattr(config, "RUNTIME_MAX_COST_USD", None) is not None
            else None
        ),
        max_loop_iterations=int(getattr(config, "RUNTIME_MAX_LOOP_ITERATIONS", 20)),
        deadline_at=deadline,
    )


def _default_tool_allowlists() -> dict[str, set[str]]:
    return {
        "qa": {
            "query_table_columns",
            "query_table_metadata",
            "query_saved_relations",
            "database_overview",
            "check_indexes",
            "catalog.list_tables",
            "catalog.query_table_columns",
            "catalog.query_table_metadata",
            "catalog.query_indexes",
            "evidence.query_relations",
            "analysis.get_status",
        },
        "dba": {"show_create_table", "execute_ddl"},
        "survey": {"tool:connect_database", "tool:list_tables", "tool:list_views", "tool:list_stored_procedures", "tool:find_orm_configs", "tool:list_triggers"},
        "column": {"tool:analyze_table_columns", "tool:check_indexes", "tool:check_auto_increment"},
        "name": {"tool:analyze_naming_convention", "tool:find_column_name_matches", "tool:detect_associative_tables"},
        "code": {"tool:parse_view_definition", "tool:parse_stored_procedure_sql", "tool:analyze_trigger_body"},
        "orm": {"tool:parse_mybatis_xml", "tool:parse_jpa_annotations"},
    }


__all__ = [
    "AgentError",
    "AgentRunResult",
    "CancellationToken",
    "ModelGateway",
    "ModelRequest",
    "ModelResult",
    "RunContext",
    "RuntimeContainer",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolRuntime",
    "ToolSpec",
    "build_default_budget",
    "build_runtime_container",
]
