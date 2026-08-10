"""Worker-specific collectors; facts are separated from semantic proposals."""

from __future__ import annotations

import re
from typing import Any

from backend.agent.collectors.base import CollectedFacts, CollectorRuntime
from backend.agent.domain.relation_keys import build_claim_key
from backend.agent.runtime.hybrid_contracts import WorkUnit
from backend.config import Config


class SurveyCollector:
    worker_id = "survey"
    version = "survey-collector-v2"

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        baseline = dict(context.get("_survey_collector_output") or context.get("survey_result") or {})
        if not baseline:
            return CollectedFacts(
                content={"inventory": {}, "candidate_facts": []},
                completeness=0.0,
                missing_capabilities=["survey_inventory"],
                collector_version=self.version,
            )
        summary = baseline.get("summary") or {}
        plan = {
            "table_batches": _batches(baseline.get("tables", {}).get("list", []), 25),
            "code_assets": _asset_refs(baseline),
            "orm_assets": [item.get("path") for item in baseline.get("orm_files", {}).get("details", [])],
            "priority": ["column", "name", "code", "orm", "merge"],
            "incremental": False,
        }
        completeness = 1.0 if baseline.get("status") == "success" else 0.7
        return CollectedFacts(
            content={"inventory": summary, "survey_plan": plan, "candidate_facts": []},
            legacy_output={**baseline, "plan": plan},
            completeness=completeness,
            missing_capabilities=list(baseline.get("missing_capabilities") or []),
            tool_call_ids=list(baseline.get("tool_call_ids") or []),
            collector_version=self.version,
        )


class ColumnCollector:
    worker_id = "column"
    version = "column-collector-v2"

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        catalog = _catalog(context)
        pk_map = {
            table["name"].casefold(): [
                column for column in table.get("columns", [])
                if column.get("is_primary_key") or column.get("key") == "PRI"
            ]
            for table in catalog
        }
        facts: list[dict[str, Any]] = []
        missing: list[str] = []
        profile_limit = min(12, unit.budget_slice.max_tool_calls)
        for table in catalog:
            source_table = str(table.get("name") or "").casefold()
            for column in table.get("columns", []):
                source_column = str(column.get("column_name") or column.get("name") or "").casefold()
                if not source_column or column.get("is_primary_key"):
                    continue
                base = source_column[:-3] if source_column.endswith("_id") else source_column
                for target_table, primary_keys in pk_map.items():
                    if not primary_keys:
                        continue
                    target_column = str(primary_keys[0].get("column_name") or primary_keys[0].get("name") or "id").casefold()
                    name_match = _name_match(base, target_table)
                    exact_key_match = source_column == target_column
                    if not (name_match or exact_key_match):
                        continue
                    source_type = str(column.get("data_type") or column.get("type") or "")
                    target_type = str(primary_keys[0].get("data_type") or primary_keys[0].get("type") or "")
                    compatible = _type_family(source_type) == _type_family(target_type)
                    claim = _claim(unit, source_table, [source_column], target_table, [target_column])
                    facts.append({
                        "claim_key": claim,
                        "source_table": source_table,
                        "source_columns": [source_column],
                        "target_table": target_table,
                        "target_columns": [target_column],
                        "cardinality": "N:1",
                        "source_type": "column_profile",
                        "polarity": "support" if compatible else "oppose",
                        "strength": 0.78 if name_match and compatible else 0.58 if compatible else 1.0,
                        "reliability": 0.82,
                        "summary": f"independent candidate {source_table}.{source_column} -> {target_table}.{target_column}",
                        "validation_flags": [] if compatible else [f"type_mismatch:{source_column}:{target_column}"],
                        "source_locator": {"table": source_table, "column": source_column},
                        "correlation_seed": f"column:{source_table}:{source_column}:{target_table}",
                    })
        # Profiles remain pair-local. A failed or exhausted profile never
        # leaks a score from one target candidate into another candidate.
        for fact in facts[:profile_limit]:
            try:
                profile = await runtime.call(
                    "recovery.profile_relationship",
                    source_table=fact["source_table"],
                    source_column=fact["source_columns"][0],
                    target_table=fact["target_table"],
                    target_column=fact["target_columns"][0],
                )
                overlap = float(profile.get("overlap_ratio") or 0.0)
                orphan = float(profile.get("orphan_ratio") or 0.0)
                fact["profile"] = profile
                fact["polarity"] = "oppose" if orphan >= 0.75 else "support" if overlap >= 0.70 else "neutral"
                fact["strength"] = max(overlap, orphan) if fact["polarity"] != "neutral" else 0.35
                fact["reliability"] = 0.92
                fact["summary"] += f"; aggregate overlap={overlap:.4f}; orphan={orphan:.4f}"
                fact["correlation_seed"] += ":aggregate-profile"
            except Exception as exc:
                missing.append(f"relationship_profile:{fact['claim_key']}:{type(exc).__name__}")
        if len(facts) > profile_limit:
            missing.append(f"relationship_profile_budget:{len(facts) - profile_limit}_candidates")
        return CollectedFacts(
            content={"candidate_facts": facts, "catalog": catalog, "privacy_mode": "metadata_only"},
            completeness=(min(1.0, profile_limit / max(len(facts), 1)) if catalog else 0.0),
            missing_capabilities=(missing if catalog else ["schema_catalog"]),
            tool_call_ids=runtime.tool_call_ids,
            collector_version=self.version,
        )


class NameCollector:
    worker_id = "name"
    version = "name-collector-v2"
    _oppose = {"status", "type", "time", "date", "description", "comment", "name", "title"}

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        catalog = _catalog(context)
        tables = {str(table.get("name") or "").casefold(): table for table in catalog}
        facts: list[dict[str, Any]] = []
        for source_table, table in tables.items():
            for column in table.get("columns", []):
                name = str(column.get("column_name") or column.get("name") or "").casefold()
                tokens = [token for token in re.split(r"[_\W]+", name) if token]
                base = name[:-3] if name.endswith("_id") else name.removesuffix("_no").removesuffix("_key")
                polarity = "oppose" if any(token in self._oppose for token in tokens) else "support"
                for target, target_table in tables.items():
                    semantic_self_reference = target == source_table and base in {"parent", "ancestor", "root"}
                    if (target == source_table and not semantic_self_reference) or (
                        target != source_table and not _name_match(base, target)
                    ):
                        continue
                    target_pk = next((item for item in target_table.get("columns", []) if item.get("is_primary_key")), None)
                    if not target_pk:
                        continue
                    target_column = str(target_pk.get("column_name") or "id").casefold()
                    facts.append({
                        "claim_key": _claim(unit, source_table, [name], target, [target_column]),
                        "source_table": source_table,
                        "source_columns": [name],
                        "target_table": target,
                        "target_columns": [target_column],
                        "cardinality": "unknown",
                        "source_type": "name_semantics",
                        "polarity": polarity,
                        "strength": 0.74 if semantic_self_reference else 0.68 if name.endswith(("_id", "_no", "_key")) else 0.45,
                        "reliability": 0.72,
                        "summary": f"tokens={tokens}; concept={base}; target={target}; self_reference={semantic_self_reference}",
                        "validation_flags": ["semantic_only"] + (["self_reference"] if semantic_self_reference else []),
                        "source_locator": {"table": source_table, "column": name, "tokens": tokens},
                        "correlation_seed": f"name:{source_table}:{name}",
                    })
        return CollectedFacts(
            content={"candidate_facts": facts, "dictionary_version": "project-default-v1", "catalog": catalog},
            completeness=1.0 if catalog else 0.0,
            missing_capabilities=[] if catalog else ["schema_catalog"],
            collector_version=self.version,
        )


class CodeCollector:
    worker_id = "code"
    version = "code-collector-v2"

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        survey = context.get("survey_result") or {}
        assets = [
            ("view", item.get("name"), item.get("definition")) for item in survey.get("views", {}).get("details", [])
        ] + [
            ("procedure", item.get("name"), item.get("definition")) for item in survey.get("stored_procedures", {}).get("details", [])
        ] + [
            ("trigger", item.get("name"), item.get("definition")) for item in survey.get("triggers", {}).get("details", [])
        ]
        facts: list[dict[str, Any]] = []
        missing: list[str] = []
        for kind, name, sql in assets:
            if not sql:
                missing.append(f"source_definition:{kind}:{name}")
                continue
            parsed = await runtime.call(
                "recovery.parse_sql_asset",
                sql=str(sql), dialect="mysql", source_uri=f"database://{kind}/{name}", asset_kind=kind,
            )
            for item in parsed.get("facts", []):
                left_table, right_table = item.get("left_table"), item.get("right_table")
                left_column, right_column = item.get("left_column"), item.get("right_column")
                if not all((left_table, right_table, left_column, right_column)):
                    facts.append({
                        "source_type": "sql_ast",
                        "polarity": "neutral",
                        "strength": 0.0,
                        "reliability": item.get("reliability", 0.5),
                        "summary": f"table-level {item.get('fact_kind')} reference",
                        "source_locator": item.get("locator", {}),
                        "unresolved": True,
                    })
                    continue
                source_table, source_column, target_table, target_column = _orient(left_table, left_column, right_table, right_column)
                facts.append({
                    "claim_key": _claim(unit, source_table, [source_column], target_table, [target_column]),
                    "source_table": source_table,
                    "source_columns": [source_column],
                    "target_table": target_table,
                    "target_columns": [target_column],
                    "cardinality": "N:1",
                    "source_type": "sql_ast" if parsed.get("parser") != "regex_fallback" else "sql_llm",
                    "polarity": "support",
                    "strength": 0.95 if item.get("fact_kind") in {"join", "update_join"} else 0.75,
                    "reliability": item.get("reliability", 0.5),
                    "summary": f"{item.get('fact_kind')} lineage in {kind} {name}",
                    "validation_flags": [f"code_fact:{item.get('fact_kind')}"] + (["parser_fallback"] if parsed.get("fallback_used") else []),
                    "source_locator": item.get("locator", {}),
                    "source_uri": item.get("locator", {}).get("source_uri"),
                    "correlation_seed": f"sql:{parsed.get('source_hash')}:{item.get('locator', {}).get('fragment_hash')}",
                })
        return CollectedFacts(
            content={"candidate_facts": facts, "asset_count": len(assets)},
            completeness=1.0 if not missing else max(0.0, (len(assets) - len(missing)) / max(len(assets), 1)),
            missing_capabilities=missing,
            tool_call_ids=runtime.tool_call_ids,
            collector_version=self.version,
        )


class ORMCollector:
    worker_id = "orm"
    version = "orm-collector-v2"

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        files = (context.get("survey_result") or {}).get("orm_files", {}).get("details", [])
        facts: list[dict[str, Any]] = []
        missing: list[str] = []
        frameworks: dict[str, int] = {}
        for asset in files:
            uri = str(asset.get("path") or "unknown")
            content = str(asset.get("content") or "")
            if not content:
                missing.append(f"empty_orm_asset:{uri}")
                continue
            extracted = await runtime.call("recovery.extract_orm_asset", source_uri=uri, content=content)
            framework = str(extracted.get("framework") or "unsupported")
            frameworks[framework] = frameworks.get(framework, 0) + 1
            if not extracted.get("supported"):
                missing.append(f"unsupported_orm:{uri}")
                continue
            for item in extracted.get("relations", []):
                source_table, target_table = item.get("source_table"), item.get("target_table")
                source_columns, target_columns = item.get("source_columns") or [], item.get("target_columns") or []
                if not (source_table and target_table and source_columns and target_columns):
                    continue
                facts.append({
                    "claim_key": _claim(unit, source_table, source_columns, target_table, target_columns),
                    "source_table": source_table,
                    "source_columns": source_columns,
                    "target_table": target_table,
                    "target_columns": target_columns,
                    "cardinality": item.get("cardinality", "unknown"),
                    "source_type": "orm",
                    "polarity": "support",
                    "strength": 0.95 if item.get("explicit_mapping") else 0.62,
                    "reliability": item.get("reliability", 0.7),
                    "summary": f"{framework} mapping {item.get('source_entity')} -> {item.get('target_entity')}",
                    "validation_flags": [] if item.get("explicit_mapping") else ["implicit_orm_mapping"],
                    "source_locator": item.get("source_locator", {}),
                    "source_uri": uri,
                    "correlation_seed": f"orm:{framework}:{uri}:{item.get('source_locator')}",
                })
        return CollectedFacts(
            content={"candidate_facts": facts, "frameworks": frameworks, "asset_count": len(files)},
            completeness=1.0 if not missing else max(0.0, (len(files) - len(missing)) / max(len(files), 1)),
            missing_capabilities=missing,
            tool_call_ids=runtime.tool_call_ids,
            collector_version=self.version,
        )


class MergeCollector:
    worker_id = "merge"
    version = "merge-collector-v2"

    async def collect(self, unit: WorkUnit, context: dict[str, Any], runtime: CollectorRuntime) -> CollectedFacts:
        candidates = context.get("_ledger_relations") or []
        evidence = context.get("_ledger_evidence") or []
        return CollectedFacts(
            content={"candidate_facts": [], "relations": candidates, "evidence": evidence, "ledger_revision": context.get("ledger_revision")},
            completeness=1.0,
            collector_version=self.version,
        )


_COLLECTORS = {
    "survey": SurveyCollector,
    "column": ColumnCollector,
    "name": NameCollector,
    "code": CodeCollector,
    "orm": ORMCollector,
    "merge": MergeCollector,
}


def collector_for(worker: str):
    return _COLLECTORS[worker]()


def _catalog(context: dict[str, Any]) -> list[dict[str, Any]]:
    return list((context.get("survey_result") or {}).get("schema_catalog") or [])


def _claim(unit: WorkUnit, source: str, source_columns: list[str], target: str, target_columns: list[str]) -> str:
    return build_claim_key(
        project_id=Config.PROJECT_ID,
        connection_id=unit.database_fingerprint,
        schema_name=Config.DB_NAME,
        snapshot_id=unit.snapshot_id,
        source_table=source,
        source_columns=source_columns,
        target_table=target,
        target_columns=target_columns,
    )


def _batches(values: list[str], size: int) -> list[list[str]]:
    return [values[offset:offset + size] for offset in range(0, len(values), size)]


def _asset_refs(survey: dict[str, Any]) -> list[str]:
    return [
        f"{kind}:{item.get('name')}"
        for kind, key in (("view", "views"), ("procedure", "stored_procedures"), ("trigger", "triggers"))
        for item in survey.get(key, {}).get("details", [])
    ]


def _name_match(base: str, target: str) -> bool:
    target = target.casefold()
    base = base.casefold()
    return target in {base, f"{base}s", f"{base}es"} or target.rstrip("s") == base


def _type_family(value: str) -> str:
    value = value.casefold()
    if "int" in value:
        return "integer"
    if any(item in value for item in ("char", "text")):
        return "text"
    if any(item in value for item in ("decimal", "numeric", "float", "double")):
        return "decimal"
    return value.split("(", 1)[0]


def _orient(left_table: str, left_column: str, right_table: str, right_column: str) -> tuple[str, str, str, str]:
    if left_column.casefold() == "id" and right_column.casefold() != "id":
        return right_table, right_column, left_table, left_column
    return left_table, left_column, right_table, right_column
