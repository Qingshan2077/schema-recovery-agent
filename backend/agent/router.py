"""Router for planning worker scheduling."""


class Router:
    def plan_analysis(self, survey_result: dict) -> dict:
        anomalies = []
        warnings = []
        summary = survey_result.get("summary", {})
        table_count = summary.get("total_tables", 0)
        sp_count = summary.get("total_procedures", 0)
        view_count = summary.get("total_views", 0)
        orm_count = summary.get("total_orm_files", 0)

        if table_count == 0:
            anomalies.append("No tables found; analysis cannot continue")
        if table_count > 100:
            warnings.append(f"Large schema with {table_count} tables may take longer to analyze")
        if sp_count == 0 and view_count == 0 and orm_count == 0:
            warnings.append("No procedures, views, or ORM files found; only naming and column analysis will be used")

        estimated_calls = 6 + table_count * 2 + sp_count + view_count + orm_count
        return {
            "phases": [
                {"phase": 1, "name": "Database Survey", "workers": ["survey"], "parallel": False, "description": "Collect database inventory"},
                {"phase": 2, "name": "Schema Analysis", "workers": ["column", "name"], "parallel": True, "description": "Analyze columns and naming"},
                {"phase": 3, "name": "Code & ORM Analysis", "workers": ["code", "orm"], "parallel": True, "description": "Analyze SQL and ORM evidence"},
                {"phase": 4, "name": "Evidence Fusion", "workers": ["merge"], "parallel": False, "description": "Fuse all evidence"},
            ],
            "schedule_strategy": "serial_phases_with_parallel_workers",
            "anomalies": anomalies,
            "warnings": warnings,
            "total_estimated_tool_calls": estimated_calls,
            "summary": {"tables": table_count, "views": view_count, "stored_procedures": sp_count, "orm_files": orm_count},
        }

