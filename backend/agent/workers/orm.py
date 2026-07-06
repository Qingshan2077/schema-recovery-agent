"""ORMWorker implementation."""

from __future__ import annotations

import re

from backend.agent.workers.base import BaseWorker


class ORMWorker(BaseWorker):
    def run(self, context: dict) -> dict:
        orm_files = context.get("survey_result", {}).get("orm_files", {})
        if not orm_files.get("details"):
            return {"status": "success", "total_relations": 0, "relations": [], "message": "No ORM configuration files found"}

        all_relations = []
        for file_info in orm_files["details"]:
            file_path = file_info.get("path", "")
            content = file_info.get("content", "")
            if not content:
                continue
            result = self.call_tool("parse_mybatis_xml", xml_content=content, file_name=file_path)
            inferred_table = self._infer_table_from_namespace(result.get("namespace", ""))
            for rel in result.get("relations", []):
                confidence = 0.8
                if rel["type"] == "association":
                    all_relations.append(
                        {
                            "source_table": inferred_table,
                            "target_table": self._infer_table_from_class(rel.get("java_type", "")),
                            "fk_column": rel.get("column", ""),
                            "pk_column": "id",
                            "relation_type": "orm_association",
                            "confidence": confidence,
                            "evidence": [
                                {
                                    "source": "mybatis_xml",
                                    "strength": confidence,
                                    "detail": f"{file_path} association column={rel.get('column', '')} type={rel.get('java_type', '')}",
                                }
                            ],
                            "source_file": file_path,
                        }
                    )
                elif rel["type"] == "collection":
                    all_relations.append(
                        {
                            "source_table": inferred_table,
                            "target_table": self._infer_table_from_class(rel.get("of_type", "")),
                            "fk_column": rel.get("column", ""),
                            "pk_column": "id",
                            "relation_type": "orm_collection",
                            "confidence": confidence,
                            "evidence": [
                                {
                                    "source": "mybatis_xml",
                                    "strength": confidence,
                                    "detail": f"{file_path} collection column={rel.get('column', '')} type={rel.get('of_type', '')}",
                                }
                            ],
                            "source_file": file_path,
                        }
                    )

        return {"status": "success", "total_relations": len(all_relations), "relations": all_relations, "parsed_files_count": len(orm_files.get("details", []))}

    def _infer_table_from_namespace(self, namespace: str) -> str:
        return self._pluralize(self._camel_to_snake(namespace.split(".")[-1].replace("Mapper", "").replace("DAO", "").replace("Dao", "")))

    def _infer_table_from_class(self, class_name: str) -> str:
        simple = class_name.split(".")[-1]
        return self._pluralize(self._camel_to_snake(simple))

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value).lower()

    @staticmethod
    def _pluralize(value: str) -> str:
        if value.endswith("y"):
            return f"{value[:-1]}ies"
        if value.endswith("s"):
            return value
        return f"{value}s"

