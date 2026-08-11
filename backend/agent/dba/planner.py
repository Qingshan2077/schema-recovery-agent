"""DDL planner boundary: model output is a candidate, never an execution authorization."""

from __future__ import annotations

import re
from typing import Protocol

from backend.agent.dba.contracts import DDLPlan


class DDLPlanAdapter(Protocol):
    async def plan(self, request: str, context: dict) -> dict: ...


class DDLPlanner:
    def __init__(self, adapter: DDLPlanAdapter | None = None): self.adapter = adapter

    async def plan(self, request: str, *, connection_id: str, environment: str, dialect: str) -> DDLPlan:
        if self.adapter:
            return DDLPlan.model_validate(await self.adapter.plan(request, {"connection_id": connection_id, "environment": environment, "dialect": dialect}))
        sql = _extract_sql(request)
        if not sql: raise ValueError("structured_ddl_plan_unavailable")
        kind = sql.lstrip().split(None, 1)[0].casefold()
        intent = {"create": "create_table", "alter": "alter_table", "drop": "drop_table", "rename": "rename"}.get(kind, "other")
        targets = re.findall(r"(?i)\b(?:TABLE|INDEX|VIEW)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?[`\"]?([A-Za-z_][A-Za-z0-9_.$]*)", sql)
        return DDLPlan(intent=intent, dialect=dialect, connection_id=connection_id, environment=environment, statements=[sql], target_objects=targets or ["unresolved"], requested_change={"request_summary": request[:1000]}, risk_hints=[], verification_goals=[])


def _extract_sql(text: str) -> str | None:
    fenced = re.search(r"```sql\s*(.*?)```", text, re.I | re.S)
    value = fenced.group(1).strip() if fenced else text.strip()
    return value if re.match(r"(?is)^(CREATE|ALTER|DROP|RENAME)\b", value) else None
