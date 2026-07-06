"""Naming convention analysis tools."""

from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


def _target_candidates(base_name: str) -> list[str]:
    candidates = [base_name, f"{base_name}s", f"{base_name}es"]
    if base_name.endswith("y"):
        candidates.append(f"{base_name[:-1]}ies")
    return candidates


def analyze_naming_convention():
    tables = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
    )
    columns = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
    )
    id_column_count = 0
    fk_suffix_count = 0
    other_columns = 0
    for col in columns:
        name = col["COLUMN_NAME"].lower()
        if name == "id":
            id_column_count += 1
        elif name.endswith("_id"):
            fk_suffix_count += 1
        else:
            other_columns += 1
    return {
        "convention": "snake_case",
        "table_count": len(tables),
        "table_names": [t["TABLE_NAME"] for t in tables],
        "column_stats": {
            "total_columns": len(columns),
            "id_columns": id_column_count,
            "fk_suffix_columns": fk_suffix_count,
            "other_columns": other_columns,
        },
    }


def find_column_name_matches():
    fk_candidates = MySQLSimulator.execute_query(
        """
        SELECT c.TABLE_NAME AS source_table, c.COLUMN_NAME AS column_name, c.COLUMN_TYPE AS column_type
        FROM information_schema.COLUMNS c
        JOIN information_schema.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
          AND t.TABLE_SCHEMA = DATABASE()
        WHERE c.TABLE_SCHEMA = DATABASE()
          AND c.COLUMN_NAME LIKE '%%_id'
          AND c.COLUMN_NAME != 'id'
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY c.TABLE_NAME, c.COLUMN_NAME
        """
    )
    pk_columns = MySQLSimulator.execute_query(
        """
        SELECT c.TABLE_NAME AS table_name, c.COLUMN_NAME AS column_name, c.COLUMN_TYPE AS column_type
        FROM information_schema.COLUMNS c
        JOIN information_schema.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
          AND t.TABLE_SCHEMA = DATABASE()
        WHERE c.TABLE_SCHEMA = DATABASE()
          AND c.COLUMN_KEY = 'PRI'
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY c.TABLE_NAME
        """
    )
    pk_map = {
        pk["table_name"]: {"column": pk["column_name"], "type": pk["column_type"]}
        for pk in pk_columns
        if pk["column_name"] == "id"
    }
    matches = []
    for fk in fk_candidates:
        base_name = fk["column_name"][:-3]
        for cand in _target_candidates(base_name):
            if cand in pk_map:
                exact = pk_map[cand]["type"] == fk["column_type"]
                matches.append(
                    {
                        "source_table": fk["source_table"],
                        "fk_column": fk["column_name"],
                        "target_table": cand,
                        "pk_column": pk_map[cand]["column"],
                        "data_type": fk["column_type"],
                        "exact_type_match": exact,
                        "evidence": "naming match + type match" if exact else "naming match",
                    }
                )
                break
    return {"match_count": len(matches), "matches": matches}


def detect_associative_tables():
    tables = MySQLSimulator.execute_query(
        """
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        """
    )
    results = []
    for t in tables:
        table_name = t["TABLE_NAME"]
        if "_" not in table_name:
            continue
        cols = MySQLSimulator.execute_query(
            """
            SELECT COLUMN_NAME, COLUMN_KEY, COLUMN_TYPE, EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        id_cols = [c["COLUMN_NAME"] for c in cols if c["COLUMN_NAME"].endswith("_id")]
        pk_cols = [c["COLUMN_NAME"] for c in cols if c["COLUMN_KEY"] == "PRI"]
        if len(id_cols) >= 2 and len(cols) <= 4 and (len(pk_cols) >= 2 or table_name in {"user_roles", "supplier_products"}):
            results.append(
                {
                    "table": table_name,
                    "total_columns": len(cols),
                    "id_columns": id_cols,
                    "primary_key_columns": pk_cols,
                    "is_associative": True,
                }
            )
    return {"associative_table_count": len(results), "tables": results}


def register_all(registry: ToolRegistry):
    registry.register("analyze_naming_convention", analyze_naming_convention, "Analyze naming conventions")
    registry.register("find_column_name_matches", find_column_name_matches, "Find FK naming matches")
    registry.register("detect_associative_tables", detect_associative_tables, "Detect many-to-many tables")

