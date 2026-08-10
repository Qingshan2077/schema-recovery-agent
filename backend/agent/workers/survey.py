"""SurveyWorker implementation."""

from backend.agent.workers.base import BaseWorker
from backend.catalog.snapshot_registry import SnapshotRegistry
from backend.config import Config
from backend.core.schema_identity import SnapshotCompleteness, build_database_fingerprint, create_snapshot_ref


class SurveyWorker(BaseWorker):
    def run(self, context: dict) -> dict:
        conn = self.call_tool("connect_database")
        if not conn.get("connected"):
            return {"status": "error", "error": conn.get("error", "Connection failed")}

        tables = self.call_tool("list_tables")
        views = self.call_tool("list_views")
        procs = self.call_tool("list_stored_procedures")
        triggers = self.call_tool("list_triggers")
        orm_configs = self.call_tool("find_orm_configs")

        schema_catalog = []
        snapshot_capture_errors = []
        for table in tables.get("tables", []):
            table_name = table.get("name")
            try:
                columns = self.call_tool("analyze_table_columns", table_name=table_name)
                indexes = self.call_tool("check_indexes", table_name=table_name)
                schema_catalog.append(
                    {
                        "name": table_name,
                        "engine": table.get("engine"),
                        "comment": table.get("table_comment", ""),
                        "columns": columns.get("columns", []),
                        "indexes": indexes.get("indexes", []),
                    }
                )
            except Exception as exc:
                snapshot_capture_errors.append(
                    {"table": table_name, "error_type": type(exc).__name__}
                )

        database_name = conn.get("database") or Config.DB_NAME
        structural_inventory = {
            "tables": schema_catalog,
            "views": [
                {"name": item.get("name"), "definition": item.get("definition")}
                for item in views.get("views", [])
            ],
            "stored_procedures": [
                {"name": item.get("name"), "definition": item.get("definition")}
                for item in procs.get("procedures", [])
            ],
            "triggers": [
                {
                    "name": item.get("name"),
                    "event": item.get("event"),
                    "table": item.get("table"),
                    "definition": item.get("definition"),
                }
                for item in triggers.get("triggers", [])
            ],
        }
        database_fingerprint = build_database_fingerprint(
            provider="mysql",
            dialect="mysql",
            instance_identity=f"{Config.DB_HOST}:{Config.DB_PORT}",
            database_name=database_name,
            schema_names=[database_name],
            tenant_id=Config.TENANT_ID,
            project_id=Config.PROJECT_ID,
        )
        snapshot = create_snapshot_ref(
            database_fingerprint=database_fingerprint,
            schema_names=[database_name],
            schema_metadata=structural_inventory,
            capture_method="survey_inventory_v1",
            completeness=(
                SnapshotCompleteness.COMPLETE
                if not snapshot_capture_errors and len(schema_catalog) == tables.get("table_count", 0)
                else SnapshotCompleteness.PARTIAL
            ),
        )
        SnapshotRegistry(db_path=context.get("snapshot_db_path")).save(snapshot)

        return {
            "status": "partial" if snapshot_capture_errors else "success",
            "server_info": {
                "version": conn.get("server_version"),
                "database": database_name,
                "database_fingerprint": database_fingerprint,
                "snapshot_id": snapshot.snapshot_id,
                "schema_hash": snapshot.schema_hash,
            },
            "snapshot": snapshot.model_dump(mode="json"),
            "schema_catalog": schema_catalog,
            "snapshot_capture_errors": snapshot_capture_errors,
            "tables": {
                "count": tables["table_count"],
                "list": [t["name"] for t in tables["tables"]],
                "details": tables["tables"],
            },
            "views": {
                "count": views["view_count"],
                "list": [v["name"] for v in views["views"]],
                "details": views["views"],
            },
            "stored_procedures": {
                "count": procs["procedure_count"],
                "list": [p["name"] for p in procs["procedures"]],
                "details": procs["procedures"],
            },
            "triggers": {"count": triggers["trigger_count"], "details": triggers["triggers"]},
            "orm_files": {"count": orm_configs["file_count"], "details": orm_configs["files"]},
            "summary": {
                "total_tables": tables["table_count"],
                "total_views": views["view_count"],
                "total_procedures": procs["procedure_count"],
                "total_triggers": triggers["trigger_count"],
                "total_orm_files": orm_configs["file_count"],
            },
        }
