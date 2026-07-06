"""SurveyWorker implementation."""

from backend.agent.workers.base import BaseWorker


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

        return {
            "status": "success",
            "server_info": {"version": conn.get("server_version"), "database": conn.get("database")},
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

