"""SQL code parsing tools for views, procedures, and triggers."""

from __future__ import annotations

import re

from backend.mcp.tool_registry import ToolRegistry


def _strip_identifier(value: str) -> str:
    return value.strip().strip("`").lower()


def remove_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def extract_aliases(sql: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = re.compile(r"\b(?:FROM|JOIN)\s+`?(\w+)`?(?:\s+(?:AS\s+)?`?(\w+)`?)?", re.IGNORECASE)
    for table, alias in pattern.findall(sql):
        table = _strip_identifier(table)
        alias = _strip_identifier(alias or table)
        if alias.upper() in {"ON", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "GROUP", "ORDER"}:
            alias = table
        aliases[alias] = table
        aliases[table] = table
    return aliases


def extract_column_pairs(condition: str, aliases: dict[str, str] | None = None):
    aliases = aliases or {}
    pairs = []
    parts = re.split(r"\s+AND\s+", condition, flags=re.IGNORECASE)
    for part in parts:
        eq_match = re.search(r"`?(\w+)`?\.`?(\w+)`?\s*=\s*`?(\w+)`?\.`?(\w+)`?", part)
        if eq_match:
            left_alias, left_col, right_alias, right_col = eq_match.groups()
            left_table = aliases.get(_strip_identifier(left_alias), _strip_identifier(left_alias))
            right_table = aliases.get(_strip_identifier(right_alias), _strip_identifier(right_alias))
            pairs.append({"left": f"{left_table}.{left_col.lower()}", "right": f"{right_table}.{right_col.lower()}"})
    return pairs


def _join_relations(sql: str):
    aliases = extract_aliases(sql)
    from_match = re.search(r"\bFROM\s+`?(\w+)`?(?:\s+(?:AS\s+)?`?(\w+)`?)?", sql, re.IGNORECASE)
    from_table = _strip_identifier(from_match.group(1)) if from_match else "(unknown)"
    join_pattern = re.compile(
        r"(?:INNER\s+|LEFT\s+|RIGHT\s+|OUTER\s+|CROSS\s+)?JOIN\s+`?(\w+)`?"
        r"(?:\s+(?:AS\s+)?`?(\w+)`?)?\s+ON\s+(.+?)"
        r"(?=\s+(?:INNER\s+|LEFT\s+|RIGHT\s+|OUTER\s+|CROSS\s+)?JOIN\b|\s+WHERE\b|\s+GROUP\s+BY\b|\s+ORDER\s+BY\b|\s+LIMIT\b|\s*\)|\s*;|$)",
        re.IGNORECASE | re.DOTALL,
    )
    relations = []
    for match in join_pattern.finditer(sql):
        joined_table = _strip_identifier(match.group(1))
        alias = _strip_identifier(match.group(2) or joined_table)
        condition = " ".join(match.group(3).split())
        relations.append(
            {
                "from_table": from_table,
                "joined_table": joined_table,
                "alias": alias,
                "condition": condition,
                "column_pairs": extract_column_pairs(condition, aliases),
            }
        )
    return relations


def parse_view_definition(view_name: str, definition: str):
    cleaned = remove_sql_comments(definition)
    relations = _join_relations(cleaned)
    return {"view": view_name, "relation_count": len(relations), "relations": relations}


def extract_subquery_relations(sql: str):
    relations = []
    for match in re.finditer(r"\(\s*SELECT\s+.+?\s+FROM\s+`?(\w+)`?", sql, re.IGNORECASE | re.DOTALL):
        relations.append(
            {
                "from_tables": ["(subquery)"],
                "joined_table": _strip_identifier(match.group(1)),
                "condition": "(subquery context)",
                "column_pairs": [],
                "relation_type": "subquery_ref",
            }
        )
    return relations


def parse_stored_procedure_sql(proc_name: str, definition: str):
    cleaned = remove_sql_comments(definition)
    relations = _join_relations(cleaned)
    subquery_relations = extract_subquery_relations(cleaned)
    for rel in relations:
        rel["from_tables"] = [rel.get("from_table", "(unknown)")]
    return {
        "procedure": proc_name,
        "relation_count": len(relations) + len(subquery_relations),
        "relations": relations + subquery_relations,
    }


def analyze_trigger_body(trigger_name: str, event: str, table: str, definition: str):
    referenced_tables = set()
    table_refs = re.findall(r"\b(FROM|JOIN|UPDATE|INTO|TABLE)\s+`?(\w+)`?", definition, re.IGNORECASE)
    for _, ref_table in table_refs:
        referenced_tables.add(ref_table.lower())
    referenced_tables.discard(table.lower())
    return {
        "trigger": trigger_name,
        "on_table": table,
        "event": event,
        "referenced_tables": sorted(referenced_tables),
        "table_count": len(referenced_tables),
    }


def register_all(registry: ToolRegistry):
    registry.register("parse_view_definition", parse_view_definition, "Parse view SQL")
    registry.register("parse_stored_procedure_sql", parse_stored_procedure_sql, "Parse stored procedure SQL")
    registry.register("analyze_trigger_body", analyze_trigger_body, "Analyze trigger body")

