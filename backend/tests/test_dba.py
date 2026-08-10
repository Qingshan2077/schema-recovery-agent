from backend.agent.workers.dba import DBAWorker
from backend.mcp.tool_registry import ToolRegistry


def test_dba_worker_requires_confirmation_for_add_column():
    worker = DBAWorker(ToolRegistry())

    result = worker.run({"question": "add nickname varchar(64) to customers table"})

    assert result["status"] == "need_confirmation"
    assert result["safety_level"] == "confirm"
    assert "ALTER TABLE" in result["pending_operation"]["ddl_statement"]


def test_dba_worker_parses_show_create_as_safe_read():
    registry = ToolRegistry()
    registry.clear()
    registry.register("show_create_table", lambda table_name: {"table": table_name, "create_sql": f"CREATE TABLE `{table_name}` (`id` bigint)"})
    worker = DBAWorker(registry)

    result = worker.run({"question": "show create table orders"})

    assert result["status"] == "success"
    assert "CREATE TABLE" in result["message"]
