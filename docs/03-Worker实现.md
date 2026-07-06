# 鏂囨。 3/5锛歐orker 瀹炵幇

> **缁?GPT 鐨勮緭鍏ユ枃妗?* 鈥?璇蜂弗鏍兼寜鐓ф鏂囨。瀹炵幇銆?> 纭繚鏂囨。 1锛堥」鐩鏋讹級鍜屾枃妗?2锛圡CP 宸ュ叿瀹氫箟锛夊疄鐜板苟閫氳繃娴嬭瘯鍚庡啀寮€濮嬫湰妯″潡銆?
---

## 涓€銆乄orker 鍩虹被

### 鏂囦欢锛歚backend/agent/workers/base.py`

```python
"""
Worker 鍩虹被 鈥?鎵€鏈?Worker 缁ф壙姝ょ被銆?鎻愪緵鏍囧噯鎺ュ彛锛歳un() 鏂规硶 + 宸ュ叿璋冪敤鏈哄埗銆?"""
from abc import ABC, abstractmethod
from typing import Any
from backend.mcp.tool_registry import ToolRegistry


class BaseWorker(ABC):
    """Worker 鍩虹被"""

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self._call_log: list[dict] = []  # 璁板綍姣忔宸ュ叿璋冪敤锛堢敤浜?Monitor锛?
    @abstractmethod
    def run(self, context: dict) -> dict:
        """
        姣忎釜 Worker 鐨勬牳蹇冮€昏緫銆?        context 鍖呭惈涓婄骇浼犲叆鐨勫垎鏋愪笂涓嬫枃銆?        杩斿洖鍒嗘瀽缁撴灉 dict銆?        """
        pass

    def call_tool(self, name: str, **kwargs) -> Any:
        """璋冪敤 MCP 宸ュ叿骞惰褰曟棩蹇?""
        result = self.tool_registry.execute(name, **kwargs)
        self._call_log.append({
            "tool": name,
            "params": kwargs,
            "result_summary": str(result)[:200]  # 鎴柇淇濆瓨
        })
        return result

    def get_call_log(self) -> list[dict]:
        """鑾峰彇宸ュ叿璋冪敤鏃ュ織锛堢粰 Monitor 鐢級"""
        return self._call_log

    @property
    def worker_id(self) -> str:
        """Worker 鐨勫敮涓€鏍囪瘑绗?""
        return self.__class__.__name__.replace("Worker", "").lower()
```

---

## 浜屻€丼urveyWorker锛堝垵鍕樺憳锛?
### 鏂囦欢锛歚backend/agent/workers/survey.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `survey` |
| 鑱岃矗 | 杩炴帴鍒版暟鎹簱锛屾壂鎻忔墍鏈夊璞★紝杈撳嚭瀹屾暣娓呭崟 |
| 璋冨害鏂瑰紡 | **蹇呯粡** 鈥?Orchestrator 绗竴涓皟鐢ㄦ Worker |
| 浣跨敤宸ュ叿 | `connect_database`, `list_tables`, `list_views`, `list_stored_procedures`, `list_triggers`, `find_orm_configs` |

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class SurveyWorker(BaseWorker):
    """鍒濆嫎鍛?鈥?鎵弿鏁版嵁搴撳叏閮ㄥ璞″苟杈撳嚭娓呭崟"""

    def run(self, context: dict) -> dict:
        # Step 1: 娴嬭瘯杩炴帴
        conn = self.call_tool("connect_database")
        if not conn.get("connected"):
            return {"status": "error", "error": conn.get("error", "Connection failed")}

        # Step 2: 鑾峰彇鎵€鏈夎〃
        tables = self.call_tool("list_tables")
        table_names = [t["name"] for t in tables["tables"]]

        # Step 3: 鑾峰彇鎵€鏈夎鍥?        views = self.call_tool("list_views")
        view_names = [v["name"] for v in views["views"]]

        # Step 4: 鑾峰彇鎵€鏈夊瓨鍌ㄨ繃绋?        procs = self.call_tool("list_stored_procedures")
        proc_names = [p["name"] for p in procs["procedures"]]

        # Step 5: 鑾峰彇鎵€鏈夎Е鍙戝櫒
        triggers = self.call_tool("list_triggers")
        trigger_info = triggers["triggers"]

        # Step 6: 鎵弿 ORM 閰嶇疆鏂囦欢
        orm_configs = self.call_tool("find_orm_configs")

        inventory = {
            "status": "success",
            "server_info": {
                "version": conn.get("server_version"),
                "database": conn.get("database"),
            },
            "tables": {
                "count": tables["table_count"],
                "list": table_names,
                "details": tables["tables"],
            },
            "views": {
                "count": views["view_count"],
                "list": view_names,
                "details": views["views"],
            },
            "stored_procedures": {
                "count": procs["procedure_count"],
                "list": proc_names,
                "details": procs["procedures"],
            },
            "triggers": {
                "count": triggers["trigger_count"],
                "details": trigger_info,
            },
            "orm_files": {
                "count": orm_configs["file_count"],
                "details": orm_configs["files"],
            },
            "summary": {
                "total_tables": tables["table_count"],
                "total_views": views["view_count"],
                "total_procedures": procs["procedure_count"],
                "total_triggers": triggers["trigger_count"],
                "total_orm_files": orm_configs["file_count"],
            }
        }
        return inventory
```

---

## 涓夈€丆olumnWorker锛堝垪鍒嗘瀽鍛橈級

### 鏂囦欢锛歚backend/agent/workers/column.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `column` |
| 鑱岃矗 | 閫愯〃鍒嗘瀽鍒椾俊鎭紝浠庢暟鎹被鍨嬨€佸彲绌烘€с€佺储寮曘€佸懡鍚嶄腑鎺ㄦ祴娼滃湪澶栭敭鍏崇郴 |
| 浣跨敤宸ュ叿 | `analyze_table_columns`, `check_indexes`, `check_auto_increment` |

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class ColumnWorker(BaseWorker):
    """鍒楀垎鏋愬憳 鈥?閫愯〃鍒嗘瀽锛屾帹娴嬫綔鍦ㄥ閿叧绯?""

    def run(self, context: dict) -> dict:
        """
        context 闇€瑕佸寘鍚?survey 鐨勮緭鍑猴紝鑷冲皯闇€瑕?table_names銆?        """
        survey_result = context.get("survey_result", {})
        tables = survey_result.get("tables", {})
        table_names = tables.get("list", [])

        if not table_names:
            return {"status": "error", "error": "No tables to analyze"}

        # 绗竴姝ワ細鏀堕泦鎵€鏈夎〃鐨勪富閿俊鎭紙鐢ㄤ簬鍚庣画鍖归厤锛?        pk_map = self._collect_primary_keys(table_names)

        # 绗簩姝ワ細瀵规瘡寮犺〃鍒嗘瀽鍒?        table_analyses = {}
        for table in table_names:
            analysis = self._analyze_single_table(table, pk_map)
            table_analyses[table] = analysis

        # 绗笁姝ワ細姹囨€绘墍鏈夋帹娴嬬殑鍏崇郴
        all_relations = []
        for table, analysis in table_analyses.items():
            for rel in analysis["potential_relations"]:
                all_relations.append({
                    "source_table": table,
                    "target_table": rel["target_table"],
                    "fk_column": rel["fk_column"],
                    "pk_column": rel["pk_column"],
                    "confidence": rel["confidence"],
                    "evidence": rel["evidence"],
                })

        return {
            "status": "success",
            "table_count": len(table_names),
            "analyzed_tables": table_analyses,
            "potential_relations": all_relations,
            "relation_count": len(all_relations),
        }

    def _collect_primary_keys(self, table_names: list[str]) -> dict:
        """鏀堕泦鎵€鏈夎〃鐨勪富閿俊鎭?""
        pk_map = {}
        for table in table_names:
            columns = self.call_tool("analyze_table_columns", table_name=table)
            pk_cols = [c for c in columns["columns"] if c["is_primary_key"]]
            if pk_cols:
                # 涓婚敭鍒楀彲鑳芥湁澶氫釜锛堣仈鍚堜富閿級锛屼絾閫氬父绗竴涓槸涓婚敭
                pk_map[table] = {
                    "columns": [c["column_name"] for c in pk_cols],
                    "types": [c["data_type"] for c in pk_cols],
                }
            # 涔熸鏌ヨ嚜澧炲垪锛堥€氬父涔熸槸涓婚敭锛?            auto_inc = self.call_tool("check_auto_increment", table_name=table)
            if auto_inc["has_auto_increment"] and table not in pk_map:
                pk_map[table] = {
                    "columns": [c["COLUMN_NAME"] for c in auto_inc["auto_increment_columns"]],
                    "types": [c["COLUMN_TYPE"] for c in auto_inc["auto_increment_columns"]],
                }
        return pk_map

    def _analyze_single_table(self, table: str, pk_map: dict) -> dict:
        """鍒嗘瀽涓€寮犺〃锛屾壘鍑烘綔鍦ㄥ閿?""
        columns = self.call_tool("analyze_table_columns", table_name=table)
        indexes = self.call_tool("check_indexes", table_name=table)

        potential_relations = []

        for col in columns["columns"]:
            col_name = col["column_name"]

            # 璺宠繃涓婚敭鍒楄嚜韬?            if col["is_primary_key"]:
                continue

            # 璺宠繃鏄庢樉涓嶆槸澶栭敭鐨勫垪锛堟椂闂淬€佹弿杩般€佺姸鎬佺瓑锛?            if self._is_not_fk_candidate(col_name, col["data_type"]):
                continue

            # 鏋勫缓璇佹嵁
            evidence = []
            confidence = 0.0

            # 淇″彿 1: 浠?_id 缁撳熬锛堝己淇″彿锛?            if col_name.lower().endswith("_id"):
                evidence.append({
                    "source": "column_name_suffix",
                    "strength": 0.8,
                    "detail": f"鍒楀悕 '{col_name}' 浠?_id 缁撳熬锛屾槸澶栭敭鍛藉悕鐨勫父瑙佹ā寮?
                })
                confidence += 0.3

            # 淇″彿 2: 鍒楀悕绛変簬鍙︿竴寮犺〃鐨勪富閿垪鍚嶏紙绮剧‘鍖归厤锛?            base_name = col_name[:-3] if col_name.endswith("_id") else col_name
            for target_table, pk_info in pk_map.items():
                if target_table == table:
                    continue
                for pk_col in pk_info["columns"]:
                    if col_name == pk_col:
                        evidence.append({
                            "source": "primary_key_name_match",
                            "strength": 0.9,
                            "detail": f"鍒楀悕 '{col_name}' 绛変簬 {target_table} 鐨勪富閿垪鍚?
                        })
                        confidence += 0.4
                    # 妯＄硦鍖归厤锛歜ase_name == target_table or target_table鍘绘帀s
                    elif base_name and (base_name == target_table or base_name + "s" == target_table or target_table + "_id" == col_name):
                        evidence.append({
                            "source": "naming_convention_match",
                            "strength": 0.7,
                            "detail": f"鍒楀悕 '{col_name}' 閫氳繃鍛藉悕绾﹀畾鍖归厤 {target_table}.{pk_col}"
                        })
                        confidence += 0.35

            # 淇″彿 3: 璇ュ垪鏈夌储寮曚笖涓嶆槸鍞竴绱㈠紩锛堝閿€氬父鏈夌储寮曪級
            for idx in indexes["indexes"]:
                if col_name in idx["columns"] and not idx["is_unique"]:
                    evidence.append({
                        "source": "index_exists",
                        "strength": 0.5,
                        "detail": f"鍒?'{col_name}' 鏈夐潪鍞竴绱㈠紩 '{idx['index_name']}' 鈥?澶栭敭甯歌妯″紡"
                    })
                    confidence += 0.15
                    break

            # 淇″彿 4: 鍒楀悕浠?fk_ 鎴?ref_ 寮€澶达紙鏄惧紡澶栭敭鏍囪锛?            if col_name.lower().startswith("fk_") or col_name.lower().startswith("ref_"):
                evidence.append({
                    "source": "explicit_fk_prefix",
                    "strength": 1.0,
                    "detail": f"鍒楀悕 '{col_name}' 浠?fk_/ref_ 寮€澶达紝寮虹儓鏆楃ず鏄閿?
                })
                confidence += 0.5

            if evidence:
                # 鎵惧嚭鏈€浣冲尮閰嶇殑鐩爣琛ㄥ拰涓婚敭
                best_target = self._resolve_target_table(col_name, base_name, pk_map, col["data_type"])
                if best_target:
                    potential_relations.append({
                        "fk_column": col_name,
                        "fk_type": col["data_type"],
                        "target_table": best_target["table"],
                        "pk_column": best_target["pk_column"],
                        "confidence": min(confidence, 1.0),
                        "evidence": evidence,
                    })

        return {
            "table": table,
            "column_count": columns["column_count"],
            "potential_relations": potential_relations,
            "relation_count": len(potential_relations),
        }

    def _is_not_fk_candidate(self, col_name: str, data_type: str) -> bool:
        """鍒ゆ柇鏌愬垪鏄惁鏄庢樉涓嶆槸澶栭敭鍊欓€?""
        non_fk_keywords = [
            "time", "date", "at$", "status", "flag", "type", "desc",
            "comment", "content", "title", "name", "email", "phone",
            "address", "url", "image", "price", "amount", "count",
            "created", "updated", "deleted", "_at$", "json", "text",
            "config", "remark", "note", "intro",
        ]
        import re
        if any(re.search(k, col_name, re.IGNORECASE) for k in non_fk_keywords):
            # 渚嬪锛氬鏋滀互 _id 缁撳熬涓旀槸鏁板€肩被鍨嬶紝杩樻槸瑕佽€冭檻
            if col_name.endswith("_id") and ("int" in data_type.lower() or "bigint" in data_type.lower()):
                return False
            return True
        return False

    def _resolve_target_table(self, col_name: str, base_name: str, pk_map: dict, col_type: str) -> dict | None:
        """纭畾娼滃湪鍏崇郴鎸囧悜鐨勭洰鏍囪〃"""
        # 1. 绮剧‘鍖归厤锛氬垪鍚嶇洿鎺ョ瓑浜庢煇寮犺〃鐨勪富閿垪鍚?        for target_table, pk_info in pk_map.items():
            for pk_col in pk_info["columns"]:
                if col_name == pk_col:
                    return {"table": target_table, "pk_column": pk_col}

        # 2. 鍛藉悕绾﹀畾鍖归厤锛氫粠 _id 鍚庣紑鍙嶆帹
        if base_name:
            candidates = [base_name, base_name + "s", base_name + "es"]
            for target_table, pk_info in pk_map.items():
                if target_table in candidates:
                    for pk_col in pk_info["columns"]:
                        # 妫€鏌ョ被鍨嬫槸鍚﹀吋瀹?                        return {"table": target_table, "pk_column": pk_col}

        # 3. 绫诲瀷鍖归厤 + 鍛藉悕妯＄硦鍖归厤锛堜綆浼樺厛绾э級
        for target_table, pk_info in pk_map.items():
            for pk_col in pk_info["columns"]:
                # 濡傛灉鍒楀悕鍖呭惈鐩爣琛ㄥ悕鐨勪竴閮ㄥ垎
                if target_table in col_name.lower() or base_name in target_table:
                    return {"table": target_table, "pk_column": pk_col}

        return None
```

---

## 鍥涖€丯ameWorker锛堝懡鍚嶆ā寮忓垎鏋愬憳锛?
### 鏂囦欢锛歚backend/agent/workers/name.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `name` |
| 鑱岃矗 | 璺ㄨ〃鍒嗘瀽鍛藉悕妯″紡锛岃瘑鍒叧鑱旇〃鍜屽瀵瑰鍏崇郴 |
| 浣跨敤宸ュ叿 | `analyze_naming_convention`, `find_column_name_matches`, `detect_associative_tables` |

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class NameWorker(BaseWorker):
    """鍛藉悕妯″紡鍒嗘瀽鍛?鈥?浠庤〃鍚嶅拰鍒楀悕鐨勬ā寮忎腑鎺ㄧ悊鍏崇郴"""

    def run(self, context: dict) -> dict:
        # 1. 鍒嗘瀽鍏ㄥ簱鍛藉悕妯″紡
        naming = self.call_tool("analyze_naming_convention")

        # 2. 璺ㄨ〃鏌ユ壘鍛藉悕涓€鑷寸殑鍒?        column_matches = self.call_tool("find_column_name_matches")

        # 3. 璇嗗埆鍏宠仈琛?        assoc_tables = self.call_tool("detect_associative_tables")

        # 4. 瀵规瘡涓懡鍚嶅尮閰嶇殑鍏崇郴锛屾瀯寤哄甫鏈夋潵婧愭爣娉ㄧ殑璇佹嵁
        relations = []
        for match in column_matches["matches"]:
            relations.append({
                "source_table": match["source_table"],
                "fk_column": match["fk_column"],
                "target_table": match["target_table"],
                "pk_column": match["pk_column"],
                "confidence": 0.7 if match.get("exact_type_match") else 0.4,
                "evidence": [
                    {
                        "source": "naming_cross_table",
                        "strength": 0.7 if match.get("exact_type_match") else 0.4,
                        "detail": match.get("evidence", "鍛藉悕鍖归厤"),
                    }
                ],
                "relation_type": "naming_convention",
            })

        # 5. 鍏宠仈琛ㄦ帹鏂?        assoc_details = []
        for t in assoc_tables["tables"]:
            # 浠庤〃鍚嶆彁鍙栧疄浣撳悕锛歶ser_role 鈫?user, role
            parts = t["table"].split("_")
            if len(parts) >= 2:
                # 鍙兘鍏宠仈鐨勮〃鍛藉悕
                entity_a = parts[0]
                entity_b = "_".join(parts[1:])
                assoc_details.append({
                    "table": t["table"],
                    "id_columns": t["id_columns"],
                    "inferred_entities": [entity_a, entity_b],
                    "primary_key_columns": t["primary_key_columns"],
                })

        return {
            "status": "success",
            "naming_convention": naming,
            "column_name_matches": {
                "count": column_matches["match_count"],
                "matches": relations,
            },
            "associative_tables": {
                "count": assoc_tables["associative_table_count"],
                "tables": assoc_details,
            },
            "total_relations": len(relations),
        }
```

---

## 浜斻€丆odeWorker锛堜唬鐮佸垎鏋愬憳锛?
### 鏂囦欢锛歚backend/agent/workers/code.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `code` |
| 鑱岃矗 | 浠庡瓨鍌ㄨ繃绋嬨€佽鍥俱€佽Е鍙戝櫒涓彁鍙栬〃闂村叧绯伙紙鏈€楂樿川閲忚瘉鎹級 |
| 浣跨敤宸ュ叿 | `parse_view_definition`, `parse_stored_procedure_sql`, `analyze_trigger_body` |

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class CodeWorker(BaseWorker):
    """浠ｇ爜鍒嗘瀽鍛?鈥?浠?SQL 浠ｇ爜涓洿鎺ユ彁鍙?JOIN 鍏崇郴"""

    def run(self, context: dict) -> dict:
        survey_result = context.get("survey_result", {})
        views = survey_result.get("views", {})
        procs = survey_result.get("stored_procedures", {})
        triggers = survey_result.get("triggers", {})

        all_relations = []
        source_stats = {"views": 0, "procedures": 0, "triggers": 0}

        # 1. 鍒嗘瀽瑙嗗浘
        for view in views.get("details", []):
            result = self.call_tool(
                "parse_view_definition",
                view_name=view["name"],
                definition=view["definition"]
            )
            for rel in result.get("relations", []):
                for pair in rel.get("column_pairs", []):
                    all_relations.append(self._build_code_relation(
                        source_type="view",
                        source_name=view["name"],
                        pair=pair,
                        confidence=0.9,
                    ))
            source_stats["views"] += result.get("relation_count", 0)

        # 2. 鍒嗘瀽瀛樺偍杩囩▼
        for proc in procs.get("details", []):
            result = self.call_tool(
                "parse_stored_procedure_sql",
                proc_name=proc["name"],
                definition=proc["definition"]
            )
            for rel in result.get("relations", []):
                for pair in rel.get("column_pairs", []):
                    confidence = 0.95 if rel.get("relation_type") != "subquery_ref" else 0.7
                    all_relations.append(self._build_code_relation(
                        source_type="stored_procedure",
                        source_name=proc["name"],
                        pair=pair,
                        confidence=confidence,
                    ))
            source_stats["procedures"] += result.get("relation_count", 0)

        # 3. 鍒嗘瀽瑙﹀彂鍣?        for trigger in triggers.get("details", []):
            result = self.call_tool(
                "analyze_trigger_body",
                trigger_name=trigger["name"],
                event=trigger["event"],
                table=trigger["table"],
                definition=trigger["definition"]
            )
            source_stats["triggers"] += result.get("table_count", 0)

        # 瀵硅Е鍙戝櫒涓殑琛ㄥ紩鐢ㄤ篃鐢熸垚鍏崇郴锛堢疆淇″害绋嶄綆锛屽洜涓烘病鏈夋樉寮?JOIN 鏉′欢锛?        # 锛堣繖閲岀畝鍖栧鐞嗭紝triggers 浣滀负杈呭姪璇佹嵁锛?
        return {
            "status": "success",
            "source_stats": source_stats,
            "relations": all_relations,
            "relation_count": len(all_relations),
            "highest_quality_evidence": len(all_relations),
        }

    def _build_code_relation(self, source_type: str, source_name: str,
                              pair: dict, confidence: float) -> dict:
        """
        浠庡垪瀵规瀯寤哄叧绯昏瘉鎹€?        pair 鏍煎紡: {"left": "orders.user_id", "right": "users.id"}
        """
        left_parts = pair.get("left", "").split(".")
        right_parts = pair.get("right", "").split(".")

        return {
            "source_table": left_parts[0] if len(left_parts) >= 2 else pair.get("left", ""),
            "fk_column": left_parts[1] if len(left_parts) >= 2 else "",
            "target_table": right_parts[0] if len(right_parts) >= 2 else pair.get("right", ""),
            "pk_column": right_parts[1] if len(right_parts) >= 2 else "",
            "confidence": confidence,
            "evidence": [
                {
                    "source": f"sql_{source_type}",
                    "strength": confidence,
                    "detail": f"鍦?{source_type} '{source_name}' 涓彂鐜版樉寮?JOIN: "
                              f"{pair.get('left', '')} = {pair.get('right', '')}"
                }
            ],
            "relation_type": "sql_join",
            "source_file": source_type,
            "source_name": source_name,
        }
```

---

## 鍏€丱RMWorker锛圤RM 閰嶇疆鍒嗘瀽鍛橈級

### 鏂囦欢锛歚backend/agent/workers/orm.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `orm` |
| 鑱岃矗 | 瑙ｆ瀽 MyBatis XML 涓殑 association/collection 鏍囩鎻愬彇鍏崇郴 |
| 浣跨敤宸ュ叿 | `parse_mybatis_xml` |

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class ORMWorker(BaseWorker):
    """ORM 閰嶇疆鍒嗘瀽鍛?鈥?浠?MyBatis XML 涓彁鍙栬〃鍏崇郴"""

    def run(self, context: dict) -> dict:
        survey_result = context.get("survey_result", {})
        orm_files = survey_result.get("orm_files", {})

        if not orm_files.get("details"):
            return {"status": "success", "total_relations": 0, "relations": [],
                    "message": "No ORM configuration files found"}

        all_relations = []

        for file_info in orm_files["details"]:
            file_path = file_info.get("path", "")
            content = file_info.get("content", "")

            if not content:
                continue

            result = self.call_tool(
                "parse_mybatis_xml",
                xml_content=content,
                file_name=file_path,
            )

            # 灏?XML 涓殑鍏崇郴杞崲涓烘爣鍑嗗叧绯绘牸寮?            # 浠?namespace 鎺ㄦ柇琛ㄥ悕锛堝 com.example.mapper.OrderMapper 鈫?orders锛?            namespace = result.get("namespace", "")
            inferred_table = self._infer_table_from_namespace(namespace)

            for rel in result.get("relations", []):
                confidence = 0.8  # ORM 閰嶇疆鏄紑鍙戣€呮墜鍐欑殑锛屽彲闈犲害楂?                if rel["type"] == "association":
                    # association: 褰撳墠琛?鈫?鍏宠仈琛紙澶氬涓€锛?                    # column 鏄綋鍓嶈〃鐨勫閿垪
                    all_relations.append({
                        "source_table": inferred_table,
                        "target_table": rel.get("java_type", "").lower(),
                        "fk_column": rel.get("column", ""),
                        "relation_type": "orm_association",
                        "confidence": confidence,
                        "evidence": [
                            {
                                "source": "mybatis_xml",
                                "strength": confidence,
                                "detail": f"鍦?{file_path} 鐨?<association> 鏍囩涓彂鐜?"
                                          f"column='{rel.get('column', '')}' 鈫?{rel.get('java_type', '')}"
                            }
                        ],
                        "source_file": file_path,
                    })
                elif rel["type"] == "collection":
                    # collection: 褰撳墠琛?鈫?瀛愯〃锛堜竴瀵瑰锛?                    all_relations.append({
                        "source_table": inferred_table,
                        "target_table": rel.get("of_type", "").lower(),
                        "fk_column": rel.get("column", ""),
                        "relation_type": "orm_collection",
                        "sub_confidence": confidence,
                        "evidence": [
                            {
                                "source": "mybatis_xml",
                                "strength": confidence,
                                "detail": f"鍦?{file_path} 鐨?<collection> 鏍囩涓彂鐜?"
                                          f"column='{rel.get('column', '')}' 鈫?{rel.get('of_type', '')}"
                            }
                        ],
                        "source_file": file_path,
                    })

            # 浠?column_mappings 涓篃鎻愬彇鍏崇郴锛坧roperty鈫抍olumn 鏄犲皠锛?            for mapping in result.get("column_mappings", []):
                pass  # 杩欎簺鏄瓧娈垫槧灏勶紝涓嶇洿鎺ヨ〃绀鸿〃鍏崇郴

        return {
            "status": "success",
            "total_relations": len(all_relations),
            "relations": all_relations,
            "parsed_files_count": len(orm_files.get("details", [])),
        }

    def _infer_table_from_namespace(self, namespace: str) -> str:
        """浠?MyBatis namespace 鎺ㄦ柇琛ㄥ悕"""
        # com.example.mapper.OrderMapper 鈫?orders
        mapper_name = namespace.split(".")[-1]  # OrderMapper
        table_name = mapper_name.replace("Mapper", "").replace("DAO", "").replace("Dao", "")
        # 杞笅鍒掔嚎 + 灏忓啓
        import re
        table_name = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', table_name).lower()
        # 鍔?s锛堝亣璁捐〃鍚嶆槸澶嶆暟锛?        if not table_name.endswith("s"):
            table_name = table_name + "s"
        return table_name
```

---

## 涓冦€丮ergeWorker锛堣瀺鍚堝憳锛?
### 鏂囦欢锛歚backend/agent/workers/merge.py`

| 灞炴€?| 鍊?|
|------|-----|
| Worker ID | `merge` |
| 鑱岃矗 | 鏀堕泦鎵€鏈?Worker 鐨勮緭鍑猴紝鍋氬姞鏉冭瀺鍚堛€佸啿绐佹秷瑙ｏ紝杈撳嚭鏈€缁?ER 鍥?|
| 渚濊禆 | 鎵€鏈夊叾浠?Worker 鐨勮緭鍑?|

### 璇佹嵁鏉冮噸閰嶇疆

| 璇佹嵁鏉ユ簮 | 鏉冮噸 | 鍘熷洜 |
|---------|------|------|
| `sql_join` (CodeWorker) | 0.40 | SQL 浠ｇ爜涓樉寮忓啓鐨?JOIN锛屾渶鍙潬 |
| `orm_association` / `orm_collection` (ORMWorker) | 0.25 | 寮€鍙戣€呮墜鍐欑殑 ORM 閰嶇疆锛屽彲闈?|
| `column_name_suffix` / `primary_key_name_match` / `naming_convention_match` (ColumnWorker) | 0.20 | 鍒楀悕鎺ㄦ祴锛岃鐩栭潰骞夸絾鍙兘璇垽 |
| `naming_cross_table` (NameWorker) | 0.15 | 璺ㄨ〃鍛藉悕鍖归厤锛岃鍒ょ巼鏈€楂?|

### 瀹炵幇

```python
from backend.agent.workers.base import BaseWorker


class MergeWorker(BaseWorker):
    """铻嶅悎鍛?鈥?鏁村悎鎵€鏈夎瘉鎹簮锛岃緭鍑烘渶缁?ER 鍥?""

    # 璇佹嵁婧愭潈閲嶉厤缃?    SOURCE_WEIGHTS = {
        "sql_join": 0.40,
        "orm_association": 0.25,
        "orm_collection": 0.25,
        "column_name_suffix": 0.20,
        "primary_key_name_match": 0.20,
        "naming_convention_match": 0.18,
        "index_exists": 0.10,
        "naming_cross_table": 0.15,
        "explicit_fk_prefix": 0.25,
        "subquery_ref": 0.10,
    }

    # 铻嶅悎鍚庣疆淇″害闃堝€?    HIGH_CONFIDENCE = 0.70
    MEDIUM_CONFIDENCE = 0.40

    def run(self, context: dict) -> dict:
        """
        浠?context 涓敹闆嗘墍鏈?Worker 鐨勭粨鏋溿€?        context 涓瘡涓?key 瀵瑰簲涓€涓?Worker 鐨勮緭鍑恒€?        """
        all_evidence = []

        # 1. 鏀堕泦 CodeWorker 鐨勮瘉鎹紙鏈€楂樹紭鍏堢骇锛?        code_result = context.get("code_result", {})
        for rel in code_result.get("relations", []):
            all_evidence.append(self._normalize_evidence(rel))

        # 2. 鏀堕泦 ORMWorker 鐨勮瘉鎹?        orm_result = context.get("orm_result", {})
        for rel in orm_result.get("relations", []):
            all_evidence.append(self._normalize_evidence(rel))

        # 3. 鏀堕泦 ColumnWorker 鐨勮瘉鎹?        column_result = context.get("column_result", {})
        for rel in column_result.get("potential_relations", []):
            for ev in rel.get("evidence", []):
                all_evidence.append(self._normalize_evidence({
                    "source_table": rel["source_table"],
                    "target_table": rel["target_table"],
                    "fk_column": rel.get("fk_column", ""),
                    "pk_column": rel.get("pk_column", ""),
                    "confidence": min(rel.get("confidence", 0.5), 0.95),
                    "evidence": [ev],
                    "relation_type": ev.get("source", "column_analysis"),
                }))

        # 4. 鏀堕泦 NameWorker 鐨勮瘉鎹?        name_result = context.get("name_result", {})
        for rel in name_result.get("column_name_matches", {}).get("matches", []):
            for ev in rel.get("evidence", []):
                all_evidence.append(self._normalize_evidence({
                    "source_table": rel["source_table"],
                    "target_table": rel["target_table"],
                    "fk_column": rel.get("fk_column", ""),
                    "pk_column": rel.get("pk_column", ""),
                    "confidence": rel.get("confidence", 0.5),
                    "evidence": [ev],
                    "relation_type": "naming_cross_table",
                }))

        # 5. 铻嶅悎锛氭寜 (source_table, target_table, fk_column) 鍒嗙粍
        return self._fuse_evidence(all_evidence)

    def _normalize_evidence(self, rel: dict) -> dict:
        """灏嗕笉鍚?Worker 鐨勮緭鍑虹粺涓€涓烘爣鍑嗗寲鏍煎紡"""
        return {
            "source_table": rel.get("source_table", ""),
            "target_table": rel.get("target_table", ""),
            "fk_column": rel.get("fk_column", ""),
            "pk_column": rel.get("pk_column", ""),
            "raw_confidence": min(rel.get("confidence", rel.get("sub_confidence", 0.5)), 1.0),
            "evidence_list": rel.get("evidence", []),
            "relation_type": rel.get("relation_type", "unknown"),
            "source_file": rel.get("source_file", ""),
            "source_name": rel.get("source_name", ""),
        }

    def _fuse_evidence(self, all_evidence: list[dict]) -> dict:
        """灏嗘墍鏈夎瘉鎹寜鍏崇郴鍒嗙粍骞跺仛鍔犳潈铻嶅悎"""

        # 鍒嗙粍 key: (source_table, fk_column) 鈫?鍞竴璇嗗埆涓€涓叧绯?        groups = {}
        for ev in all_evidence:
            source_table = ev["source_table"]
            target_table = ev["target_table"]
            fk_column = ev["fk_column"]
            pk_column = ev["pk_column"]

            # 鏍囧噯鍖栬〃鍚嶅拰鍒楀悕锛堢粺涓€灏忓啓锛?            source_table = source_table.lower()
            target_table = target_table.lower()
            fk_column = fk_column.lower()
            pk_column = pk_column.lower()

            key = (source_table, target_table, fk_column, pk_column)
            if key not in groups:
                groups[key] = {
                    "source_table": source_table,
                    "target_table": target_table,
                    "fk_column": fk_column,
                    "pk_column": pk_column,
                    "evidences": [],
                }
            groups[key]["evidences"].append(ev)

        # 瀵规瘡缁勮绠楃患鍚堢疆淇″害
        fused_relations = []
        for key, group in groups.items():
            fused = self._fuse_single_group(group)
            if fused:
                fused_relations.append(fused)

        # 鎸夌疆淇″害鎺掑簭锛堜粠楂樺埌浣庯級
        fused_relations.sort(key=lambda x: x["fused_confidence"], reverse=True)

        # 鍒嗙骇杈撳嚭
        high_confidence = [r for r in fused_relations if r["fused_confidence"] >= self.HIGH_CONFIDENCE]
        medium_confidence = [r for r in fused_relations
                             if self.MEDIUM_CONFIDENCE <= r["fused_confidence"] < self.HIGH_CONFIDENCE]
        low_confidence = [r for r in fused_relations if r["fused_confidence"] < self.MEDIUM_CONFIDENCE]

        # 缁熻鍚勬簮璐＄尞鐜?        source_contributions = self._calculate_source_contributions(fused_relations)

        return {
            "status": "success",
            "summary": {
                "total_relations": len(fused_relations),
                "high_confidence": len(high_confidence),
                "medium_confidence": len(medium_confidence),
                "low_confidence": len(low_confidence),
            },
            "high_confidence_relations": high_confidence,
            "medium_confidence_relations": medium_confidence,
            "low_confidence_relations": low_confidence,
            "source_contributions": source_contributions,
            "evidence_detail": {
                # 浠呭湪闇€瑕佹椂灞曞紑锛岄粯璁や笉鍖呭惈鍏ㄩ儴鍏宠仈缁嗚妭
            }
        }

    def _fuse_single_group(self, group: dict) -> dict | None:
        """瀵逛竴缁勫叧浜庡悓涓€鍏崇郴鐨勮瘉鎹仛鍔犳潈铻嶅悎"""
        if not group["evidences"]:
            return None

        weighted_sum = 0.0
        total_weight = 0.0
        evidence_details = []
        relation_type_counts = {}

        for ev in group["evidences"]:
            rel_type = ev.get("relation_type", "unknown")
            weight = self.SOURCE_WEIGHTS.get(rel_type, 0.10)
            raw_conf = ev.get("raw_confidence", 0.5)

            # 鍔犳潈
            weighted_sum += weight * raw_conf
            total_weight += weight

            relation_type_counts[rel_type] = relation_type_counts.get(rel_type, 0) + 1

            for e in ev.get("evidence_list", []):
                evidence_details.append({
                    "type": rel_type,
                    "weight": weight,
                    "detail": e.get("detail", ""),
                    "strength": e.get("strength", 0),
                })

        if total_weight == 0:
            return None

        fused_confidence = round(weighted_sum / total_weight, 4)

        # 纭畾鍏崇郴绫诲瀷浼樺厛绾ч『搴忥細濡傛灉 evidence 涓寘鍚?sql_join 鈫?1:N锛堥粯璁わ級
        # 鍖呭惈 orm_association 鈫?N:1锛屽寘鍚?orm_collection 鈫?1:N
        relation_type = "N:1"
        if "orm_collection" in relation_type_counts:
            relation_type = "1:N"
        if "sql_join" in relation_type_counts:
            relation_type = "N:1"  # JOIN 閫氬父鏄瀵逛竴

        return {
            "source_table": group["source_table"],
            "target_table": group["target_table"],
            "fk_column": group["fk_column"],
            "pk_column": group["pk_column"],
            "relation_type": relation_type,
            "fused_confidence": fused_confidence,
            "evidence_count": len(evidence_details),
            "evidence_sources": list(relation_type_counts.keys()),
            "evidence_chain": evidence_details,
        }

    def _calculate_source_contributions(self, relations: list[dict]) -> dict:
        """璁＄畻鍚勮瘉鎹簮鍦ㄦ渶缁堢粨鏋滀腑鐨勮础鐚巼"""
        source_counts = {}
        for rel in relations:
            for src in rel.get("evidence_sources", []):
                source_counts[src] = source_counts.get(src, 0) + 1

        total = sum(source_counts.values()) or 1
        return {
            source: {
                "count": count,
                "percentage": round(count / total * 100, 1)
            }
            for source, count in sorted(source_counts.items(), key=lambda x: -x[1])
        }
```

---

## 鍏€乄orker 娉ㄥ唽

鎵€鏈?Worker 鍦?`backend/agent/orchestrator.py` 涓敞鍐岋紝鐢变笅涓€浠芥枃妗ｏ紙Doc 4锛夊畬鎴愩€?
---

## 涔濄€侀獙璇?
瀹炵幇鍚庤繍琛屼互涓嬫祴璇曪細

```python
# tests/test_workers.py
"""
娴嬭瘯鍓嶇‘淇?Docker Compose 宸插惎鍔紙MySQL 瀹瑰櫒姝ｅ湪杩愯锛夈€?"""

from backend.mcp.server import init_mcp_tools
from backend.agent.workers.survey import SurveyWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.code import CodeWorker


def test_survey_worker():
    registry = init_mcp_tools()
    worker = SurveyWorker(registry)
    result = worker.run({})
    assert result["status"] == "success"
    assert result["summary"]["total_tables"] == 30
    assert result["summary"]["total_views"] == 3
    assert result["summary"]["total_procedures"] >= 8


def test_column_worker():
    registry = init_mcp_tools()
    survey = SurveyWorker(registry)
    survey_result = survey.run({})

    worker = ColumnWorker(registry)
    result = worker.run({"survey_result": survey_result})
    assert result["status"] == "success"
    assert result["relation_count"] > 0  # 鑷冲皯鍙戠幇涓€浜涘叧绯?

def test_name_worker():
    registry = init_mcp_tools()
    worker = NameWorker(registry)
    result = worker.run({})
    assert result["status"] == "success"
    assert result["column_name_matches"]["count"] > 0


def test_code_worker():
    registry = init_mcp_tools()
    survey = SurveyWorker(registry)
    survey_result = survey.run({})

    worker = CodeWorker(registry)
    result = worker.run({"survey_result": survey_result})
    assert result["status"] == "success"
    assert result["relation_count"] > 0  # 鑷冲皯浠?SP 鍜岃鍥句腑鎻愬彇鍒?JOIN 鍏崇郴
```

杩愯锛?```bash
pytest tests/test_workers.py -v
```

鎵€鏈夋祴璇曢€氳繃鍚庯紝寮€濮嬩笅涓€浠芥枃妗ｏ紙Router + Orchestrator + Memory锛夈€?
