from backend.agent.workers.qa import QAWorker
from backend.mcp.tool_registry import ToolRegistry


def test_qa_worker_columns_intent():
    registry = ToolRegistry()
    registry.clear()
    registry.register(
        "query_table_columns",
        lambda table_name: {"table": table_name, "columns": [{"name": "id", "type": "bigint", "nullable": False, "key": "PRI", "comment": "", "default": None, "extra": ""}], "column_count": 1},
    )
    worker = QAWorker(registry)

    result = worker.run({"question": "what columns does users have"})

    assert result["status"] == "success"
    assert result["intent"] == "table_columns"
    assert "Table users has 1 columns" in result["answer"]


def test_qa_worker_relation_intent():
    registry = ToolRegistry()
    registry.clear()
    registry.register(
        "query_saved_relations",
        lambda source_table=None, target_table=None: {
            "relation_count": 1,
            "relations": [
                {
                    "source_table": source_table,
                    "target_table": target_table,
                    "fk_column": "order_id",
                    "pk_column": "id",
                    "relation_type": "N:1",
                    "confidence": 0.92,
                }
            ],
        },
    )
    worker = QAWorker(registry)

    result = worker.run({"question": "orders order_items relationship"})

    assert result["intent"] == "table_relations"
    assert "confidence=0.92" in result["answer"]


def test_qa_worker_extracts_ascii_table_next_to_chinese_text():
    registry = ToolRegistry()
    captured = {}
    registry.register(
        "query_table_columns",
        lambda table_name: captured.update(table_name=table_name)
        or {"table": table_name, "columns": [], "column_count": 0},
    )

    result = QAWorker(registry).run({"question": "products表有哪些字段"})

    assert result["intent"] == "table_columns"
    assert captured["table_name"] == "products"


def test_qa_worker_does_not_fall_back_to_overview_when_table_is_missing():
    registry = ToolRegistry()
    calls = []
    registry.register("database_overview", lambda: calls.append("overview") or {})

    result = QAWorker(registry).run({"question": "这个表有哪些字段"})

    assert result["intent"] == "table_columns"
    assert result["data"]["error"] == "missing_table_name"
    assert calls == []
