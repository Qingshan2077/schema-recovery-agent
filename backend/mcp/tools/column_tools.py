"""Column and index metadata tools."""

from backend.mcp.tool_registry import ToolRegistry
from backend.sim_env.mysql_simulator import MySQLSimulator


def analyze_table_columns(table_name: str):
    columns = MySQLSimulator.execute_query(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
               COLUMN_COMMENT, COLUMN_KEY, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )
    pk_columns = {r["COLUMN_NAME"] for r in columns if r["COLUMN_KEY"] == "PRI"}
    return {
        "table": table_name,
        "column_count": len(columns),
        "columns": [
            {
                "column_name": c["COLUMN_NAME"],
                "data_type": c["COLUMN_TYPE"],
                "is_nullable": c["IS_NULLABLE"] == "YES",
                "default_value": c["COLUMN_DEFAULT"],
                "comment": c["COLUMN_COMMENT"] or "",
                "is_primary_key": c["COLUMN_NAME"] in pk_columns,
            }
            for c in columns
        ],
    }


def check_indexes(table_name: str):
    indexes = MySQLSimulator.execute_query(
        """
        SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX, INDEX_TYPE, COMMENT
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
        """,
        (table_name,),
    )
    idx_map: dict[str, dict] = {}
    for idx in indexes:
        name = idx["INDEX_NAME"]
        idx_map.setdefault(
            name,
            {"index_name": name, "is_unique": idx["NON_UNIQUE"] == 0, "index_type": idx["INDEX_TYPE"], "columns": []},
        )
        idx_map[name]["columns"].append(idx["COLUMN_NAME"])
    return {"table": table_name, "index_count": len(idx_map), "indexes": list(idx_map.values())}


def check_auto_increment(table_name: str):
    result = MySQLSimulator.execute_query(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
          AND EXTRA LIKE '%%auto_increment%%'
        """,
        (table_name,),
    )
    return {"table": table_name, "has_auto_increment": bool(result), "auto_increment_columns": result}


def register_all(registry: ToolRegistry):
    registry.register("analyze_table_columns", analyze_table_columns, "Analyze table columns")
    registry.register("check_indexes", check_indexes, "Check table indexes")
    registry.register("check_auto_increment", check_auto_increment, "Check auto increment columns")

