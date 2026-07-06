# 鏂囨。 2/5锛歁CP 宸ュ叿瀹氫箟

> **缁?GPT 鐨勮緭鍏ユ枃妗?* 鈥?璇蜂弗鏍兼寜鐓ф鏂囨。瀹炵幇銆?> 鍏堢‘淇濇枃妗?1锛堥」鐩鏋?+ 妯℃嫙鏁版嵁搴擄級宸插疄鐜板苟璺戦€氾紝鍐嶅紑濮嬫湰妯″潡銆?> 鏈ā鍧楁槸 Worker 鐨勫熀纭€璁炬柦锛屾墍鏈?Worker 鐨勫伐鍏烽€氳繃杩欓噷璋冪敤鏁版嵁搴撱€?
---

## 涓€銆佸伐鍏锋敞鍐屾満鍒?
鎵€鏈夊伐鍏锋敞鍐屽埌涓€涓粺涓€鐨勬敞鍐岃〃 `ToolRegistry`銆俉orker 閫氳繃宸ュ叿鍚嶈皟鐢ㄥ搴斿嚱鏁般€?
### 鏂囦欢锛歚backend/mcp/tool_registry.py`

```python
"""
宸ュ叿娉ㄥ唽琛?鈥?鎵€鏈?MCP 宸ュ叿鐨勬敞鍐屽拰璋冪敤鍏ュ彛銆?璁捐涓哄崟渚嬫ā寮忥紝鎵€鏈?Worker 閫氳繃鐩稿悓鍏ュ彛璋冪敤宸ュ叿銆?"""

from typing import Any, Callable


class ToolRegistry:
    """宸ュ叿娉ㄥ唽琛?""

    _tools: dict[str, dict] = {}  # {tool_name: {fn, input_schema, output_schema, description}}

    @classmethod
    def register(cls, name: str, fn: Callable, description: str = "", input_schema: dict = None):
        """娉ㄥ唽涓€涓伐鍏?""
        cls._tools[name] = {
            "fn": fn,
            "description": description,
            "input_schema": input_schema or {},
        }

    @classmethod
    def execute(cls, name: str, **kwargs) -> Any:
        """鎵ц涓€涓凡娉ㄥ唽鐨勫伐鍏?""
        if name not in cls._tools:
            raise ValueError(f"Tool '{name}' not registered. Available: {list(cls._tools.keys())}")
        return cls._tools[name]["fn"](**kwargs)

    @classmethod
    def list_tools(cls) -> list[dict]:
        """鍒楀嚭鎵€鏈夊凡娉ㄥ唽鐨勫伐鍏凤紙鍚弿杩板拰鍙傛暟 Schema锛?""
        return [
            {"name": name, "description": meta["description"], "input_schema": meta["input_schema"]}
            for name, meta in cls._tools.items()
        ]
```

---

## 浜屻€丼urvey 宸ュ叿闆?
### 鏂囦欢锛歚backend/mcp/tools/survey_tools.py`

杩欎簺宸ュ叿鐢?SurveyWorker 璋冪敤锛岀敤浜庡垵鍕樻暟鎹簱銆?
### 宸ュ叿 1锛歚connect_database`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `connect_database` |
| 鎻忚堪 | 娴嬭瘯涓庣洰鏍囨暟鎹簱鐨勮繛鎺ユ槸鍚︽甯?|
| 鍙傛暟 | 鏃狅紙杩炴帴淇℃伅浠?Config 璇诲彇锛?|
| 杩斿洖 | `{"connected": bool, "server_version": str, "database": str}` |

```python
def connect_database():
    from backend.sim_env.mysql_simulator import MySQLSimulator
    try:
        result = MySQLSimulator.execute_query("SELECT VERSION() AS version")
        return {
            "connected": True,
            "server_version": result[0]["version"],
            "database": Config.DB_NAME
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


def register(registry: ToolRegistry):
    registry.register(
        name="connect_database",
        fn=connect_database,
        description="娴嬭瘯鏁版嵁搴撹繛鎺ワ紝杩斿洖鐗堟湰鍙峰拰鏁版嵁搴撳悕",
        input_schema={"type": "object", "properties": {}},
    )
```

### 宸ュ叿 2锛歚list_tables`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `list_tables` |
| 鎻忚堪 | 鍒楀嚭鏁版嵁搴撲腑鎵€鏈変笟鍔¤〃锛堜笉鍚郴缁熻〃锛?|
| 鍙傛暟 | 鏃?|
| 杩斿洖 | `{"table_count": int, "tables": [{"name": str, "engine": str, "table_comment": str, "row_estimate": int}]}` |

```python
def list_tables():
    result = MySQLSimulator.execute_query("""
        SELECT TABLE_NAME, ENGINE, TABLE_COMMENT, TABLE_ROWS
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    return {
        "table_count": len(result),
        "tables": [
            {
                "name": r["TABLE_NAME"],
                "engine": r["ENGINE"],
                "table_comment": r["TABLE_COMMENT"] or "",
                "row_estimate": r["TABLE_ROWS"] or 0
            }
            for r in result
        ]
    }
```

### 宸ュ叿 3锛歚list_views`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `list_views` |
| 鎻忚堪 | 鍒楀嚭鏁版嵁搴撲腑鎵€鏈夎鍥?|
| 杩斿洖 | `{"view_count": int, "views": [{"name": str, "definition": str}]}` |

```python
def list_views():
    result = MySQLSimulator.execute_query("""
        SELECT TABLE_NAME AS view_name, VIEW_DEFINITION
        FROM information_schema.VIEWS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME
    """)
    return {
        "view_count": len(result),
        "views": [{"name": r["view_name"], "definition": r["VIEW_DEFINITION"]} for r in result]
    }
```

### 宸ュ叿 4锛歚list_stored_procedures`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `list_stored_procedures` |
| 鎻忚堪 | 鍒楀嚭鏁版嵁搴撲腑鎵€鏈夊瓨鍌ㄨ繃绋嬶紝鍚畾涔夋簮鐮?|
| 杩斿洖 | `{"procedure_count": int, "procedures": [{"name": str, "definition": str}]}` |

```python
def list_stored_procedures():
    result = MySQLSimulator.execute_query("""
        SELECT ROUTINE_NAME, ROUTINE_DEFINITION
        FROM information_schema.ROUTINES
        WHERE ROUTINE_SCHEMA = DATABASE()
          AND ROUTINE_TYPE = 'PROCEDURE'
        ORDER BY ROUTINE_NAME
    """)
    return {
        "procedure_count": len(result),
        "procedures": [{"name": r["ROUTINE_NAME"], "definition": r["ROUTINE_DEFINITION"]} for r in result]
    }
```

### 宸ュ叿 5锛歚find_orm_configs`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `find_orm_configs` |
| 鎻忚堪 | 鎵弿鎸囧畾璺緞涓嬬殑 ORM 閰嶇疆鏂囦欢 |
| 鍙傛暟 | `{"path": {"type": "string", "description": "鎵弿鐩綍", "default": "/app/data/orm"}}` |
| 杩斿洖 | `{"file_count": int, "files": [{"path": str, "content": str}]}` |

```python
import os

def find_orm_configs(path: str = "/app/data/orm"):
    if not os.path.exists(path):
        return {"file_count": 0, "files": [], "error": f"Path {path} not found"}
    files = []
    for f in os.listdir(path):
        if f.endswith(".xml"):
            filepath = os.path.join(path, f)
            with open(filepath, "r", encoding="utf-8") as fh:
                content = fh.read()
            files.append({"path": filepath, "content": content})
    return {"file_count": len(files), "files": files}
```

### 宸ュ叿 6锛歚list_triggers`

| 灞炴€?| 鍊?|
|------|-----|
| 鍚嶇О | `list_triggers` |
| 鎻忚堪 | 鍒楀嚭鏁版嵁搴撲腑鎵€鏈夎Е鍙戝櫒 |
| 杩斿洖 | `{"trigger_count": int, "triggers": [{"name": str, "event": str, "table": str, "definition": str}]}` |

```python
def list_triggers():
    result = MySQLSimulator.execute_query("""
        SELECT TRIGGER_NAME, EVENT_MANIPULATION, EVENT_OBJECT_TABLE, ACTION_TIMING, ACTION_STATEMENT
        FROM information_schema.TRIGGERS
        WHERE TRIGGER_SCHEMA = DATABASE()
        ORDER BY TRIGGER_NAME
    """)
    return {
        "trigger_count": len(result),
        "triggers": [
            {
                "name": r["TRIGGER_NAME"],
                "event": f"{r['ACTION_TIMING']} {r['EVENT_MANIPULATION']}",
                "table": r["EVENT_OBJECT_TABLE"],
                "definition": r["ACTION_STATEMENT"]
            }
            for r in result
        ]
    }
```

### 娉ㄥ唽鍑芥暟

```python
def register_all(registry: ToolRegistry):
    registry.register(
        name="connect_database", fn=connect_database,
        description="娴嬭瘯鏁版嵁搴撹繛鎺ワ紝杩斿洖鐗堟湰鍙峰拰鏁版嵁搴撳悕",
        input_schema={"type": "object", "properties": {}}
    )
    registry.register(
        name="list_tables", fn=list_tables,
        description="鍒楀嚭鎵€鏈変笟鍔¤〃",
        input_schema={"type": "object", "properties": {}}
    )
    registry.register(name="list_views", fn=list_views, ...)
    registry.register(name="list_stored_procedures", fn=list_stored_procedures, ...)
    registry.register(name="find_orm_configs", fn=find_orm_configs, ...)
    registry.register(name="list_triggers", fn=list_triggers, ...)
```

---

## 涓夈€丆olumn 宸ュ叿闆?
### 鏂囦欢锛歚backend/mcp/tools/column_tools.py`

鐢?ColumnWorker 璋冪敤锛屽垎鏋愬垪鍜岀储寮曠骇鍒殑淇℃伅銆?
### 宸ュ叿 1锛歚analyze_table_columns`

```python
def analyze_table_columns(table_name: str):
    """
    鍒嗘瀽涓€寮犺〃鐨勫垪淇℃伅銆?    杩斿洖姣忓垪鐨勶細鍒楀悕銆佹暟鎹被鍨嬨€佹槸鍚﹀彲绌恒€侀粯璁ゅ€笺€佹敞閲娿€佹槸鍚︿富閿€?    """
    # 鑾峰彇鍒椾俊鎭?    columns = MySQLSimulator.execute_query("""
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
               COLUMN_COMMENT, COLUMN_KEY, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """, (table_name,))

    # 鑾峰彇涓婚敭鍒?    pk_result = MySQLSimulator.execute_query("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_KEY = 'PRI'
    """, (table_name,))
    pk_columns = {r["COLUMN_NAME"] for r in pk_result}

    result = []
    for col in columns:
        result.append({
            "column_name": col["COLUMN_NAME"],
            "data_type": col["COLUMN_TYPE"],
            "is_nullable": col["IS_NULLABLE"] == "YES",
            "default_value": col["COLUMN_DEFAULT"],
            "comment": col["COLUMN_COMMENT"] or "",
            "is_primary_key": col["COLUMN_NAME"] in pk_columns,
        })

    return {"table": table_name, "column_count": len(result), "columns": result}
```

### 宸ュ叿 2锛歚check_indexes`

```python
def check_indexes(table_name: str):
    """鍒楀嚭琛ㄤ笂鐨勬墍鏈夌储寮曪紙鍚储寮曠被鍨嬨€佸垪鍚嶃€佹槸鍚﹀敮涓€锛?""
    indexes = MySQLSimulator.execute_query("""
        SELECT INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX,
               INDEX_TYPE, COMMENT
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY INDEX_NAME, SEQ_IN_INDEX
    """, (table_name,))

    # 鎸夌储寮曞悕鍒嗙粍
    idx_map = {}
    for idx in indexes:
        name = idx["INDEX_NAME"]
        if name not in idx_map:
            idx_map[name] = {
                "index_name": name,
                "is_unique": idx["NON_UNIQUE"] == 0,
                "index_type": idx["INDEX_TYPE"],
                "columns": []
            }
        idx_map[name]["columns"].append(idx["COLUMN_NAME"])

    return {
        "table": table_name,
        "index_count": len(idx_map),
        "indexes": list(idx_map.values())
    }
```

### 宸ュ叿 3锛歚check_auto_increment`

```python
def check_auto_increment(table_name: str):
    """妫€鏌ヨ〃涓殑鑷鍒?""
    result = MySQLSimulator.execute_query("""
        SELECT COLUMN_NAME, COLUMN_TYPE, EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
          AND EXTRA LIKE '%auto_increment%'
    """, (table_name,))
    return {
        "table": table_name,
        "has_auto_increment": len(result) > 0,
        "auto_increment_columns": result
    }
```

---

## 鍥涖€丯ame 宸ュ叿闆?
### 鏂囦欢锛歚backend/mcp/tools/name_tools.py`

鐢?NameWorker 璋冪敤锛屽仛璺ㄨ〃鍛藉悕妯″紡鍒嗘瀽銆?
### 宸ュ叿 1锛歚analyze_naming_convention`

```python
def analyze_naming_convention():
    """璇嗗埆鏁翠釜鏁版嵁搴撶殑鍛藉悕妯″紡"""
    tables = MySQLSimulator.execute_query("""
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)

    columns = MySQLSimulator.execute_query("""
        SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)

    # 鍒嗘瀽鍛藉悕妯″紡
    table_prefixes = {}
    id_column_count = 0
    fk_suffix_count = 0  # 浠?_id 缁撳熬鐨勫垪
    other_columns = 0

    for col in columns:
        name = col["COLUMN_NAME"]
        if name.lower() == "id":
            id_column_count += 1
        elif name.lower().endswith("_id"):
            fk_suffix_count += 1
        else:
            other_columns += 1

    return {
        "convention": "snake_case",  # 鏁版嵁搴撻€氬父鐢?snake_case
        "table_count": len(tables),
        "table_names": [t["TABLE_NAME"] for t in tables],
        "column_stats": {
            "total_columns": len(columns),
            "id_columns": id_column_count,
            "fk_suffix_columns": fk_suffix_count,  # 浠?_id 缁撳熬鈥旀綔鍦ㄥ閿?            "other_columns": other_columns,
        }
    }
```

### 宸ュ叿 2锛歚find_column_name_matches`

```python
def find_column_name_matches():
    """
    璺ㄨ〃鏌ユ壘鍛藉悕涓€鑷寸殑鍒楀銆?    杩斿洖鎵€鏈?_id 缁撳熬鐨勫垪锛屽強鍏跺彲鑳藉紩鐢ㄧ殑鐩爣琛ㄣ€?    瑙勫垯锛氬 orders.user_id 鍙兘寮曠敤 users.id銆?    """
    # 鏌ユ壘鎵€鏈変互 _id 缁撳熬鐨勫垪锛堟帓闄よ〃鐨勪富閿?id锛?    fk_candidates = MySQLSimulator.execute_query("""
        SELECT c.TABLE_NAME AS source_table, c.COLUMN_NAME AS column_name,
               c.COLUMN_TYPE AS column_type
        FROM information_schema.COLUMNS c
        JOIN information_schema.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
          AND t.TABLE_SCHEMA = DATABASE()
        WHERE c.TABLE_SCHEMA = DATABASE()
          AND c.COLUMN_NAME LIKE '%_id'
          AND c.COLUMN_NAME != 'id'
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY c.TABLE_NAME, c.COLUMN_NAME
    """)

    # 鏌ユ壘鎵€鏈夎〃鐨勪富閿垪
    pk_columns = MySQLSimulator.execute_query("""
        SELECT c.TABLE_NAME AS table_name, c.COLUMN_NAME AS column_name,
               c.COLUMN_TYPE AS column_type
        FROM information_schema.COLUMNS c
        JOIN information_schema.TABLES t ON c.TABLE_NAME = t.TABLE_NAME
          AND t.TABLE_SCHEMA = DATABASE()
        WHERE c.TABLE_SCHEMA = DATABASE()
          AND c.COLUMN_KEY = 'PRI'
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY c.TABLE_NAME
    """)

    # 鏋勫缓 琛ㄥ悕鈫掍富閿?鏄犲皠
    pk_map = {}
    for pk in pk_columns:
        pk_map[pk["table_name"]] = {"column": pk["column_name"], "type": pk["column_type"]}

    # 鍖归厤
    matches = []
    for fk in fk_candidates:
        col_name = fk["column_name"]
        # 浠?_id 鍚庣紑鎻愬彇鐩爣琛ㄥ悕锛歶ser_id 鈫?users锛堝幓鎺?_id + 鍔?s/es 鎴?exact match锛?        base_name = col_name[:-3]  # 鍘绘帀 _id
        candidates = [base_name, base_name + "s", base_name + "es"]

        found = None
        for cand in candidates:
            if cand in pk_map and pk_map[cand]["type"] == fk["column_type"]:
                found = {
                    "source_table": fk["source_table"],
                    "fk_column": col_name,
                    "target_table": cand,
                    "pk_column": pk_map[cand]["column"],
                    "data_type": fk["column_type"],
                    "exact_type_match": True,
                    "evidence": "鍛藉悕鍖归厤 + 绫诲瀷涓€鑷?
                }
                break
            elif cand in pk_map:
                # 绫诲瀷涓嶅尮閰嶄絾浠嶆湁鍏宠仈鍙兘鎬?                found = {
                    "source_table": fk["source_table"],
                    "fk_column": col_name,
                    "target_table": cand,
                    "pk_column": pk_map[cand]["column"],
                    "data_type": fk["column_type"],
                    "exact_type_match": False,
                    "evidence": "鍛藉悕鍖归厤浣嗙被鍨嬩笉涓€鑷?
                }
                # 涓?break 鈥?绫诲瀷涓嶄竴鑷寸殑鍖归厤浼樺厛绾т綆
        if found:
            matches.append(found)

    return {"match_count": len(matches), "matches": matches}
```

### 宸ュ叿 3锛歚detect_associative_tables`

```python
def detect_associative_tables():
    """
    璇嗗埆鍏宠仈琛紙澶氬澶氫腑闂磋〃锛夈€?    鍒ゆ柇淇″彿锛?    - 琛ㄥ悕鐢变袱涓疄浣撳悕鐢ㄤ笅鍒掔嚎杩炴帴锛堝 user_role锛?    - 鍙湁涓ゅ垪锛堜笉鍚嚜澧炰富閿級鎴栦袱鍒?涓€鏉′富閿?    - 涓ゅ垪閮芥槸浠?_id 缁撳熬
    - 鏈夎仈鍚堝敮涓€绱㈠紩鎴栬仈鍚堜富閿?    """
    tables = MySQLSimulator.execute_query("""
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
    """)

    results = []
    for t in tables:
        table_name = t["TABLE_NAME"]
        # 琛ㄥ悕鍖呭惈涓嬪垝绾垮彲鑳芥槸鍏宠仈琛?        if "_" not in table_name:
            continue

        cols = MySQLSimulator.execute_query("""
            SELECT COLUMN_NAME, COLUMN_KEY, COLUMN_TYPE, EXTRA
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (table_name,))

        non_pk_cols = [c for c in cols if c["COLUMN_KEY"] != "PRI" and "auto_increment" not in (c.get("EXTRA") or "")]
        id_cols = [c["COLUMN_NAME"] for c in cols if c["COLUMN_NAME"].endswith("_id")]
        pk_cols = [c["COLUMN_NAME"] for c in cols if c["COLUMN_KEY"] == "PRI"]

        is_associative = (
            len(id_cols) >= 2  # 鑷冲皯涓ゅ垪 _id
            and len(cols) <= 4  # 鎬诲垪鏁板皯锛?~4鍒楋級
            and (len(pk_cols) >= 2 or len(non_pk_cols) <= 1)  # 鑱斿悎涓婚敭鎴栫函鍏宠仈琛ㄧ粨鏋?        )

        if is_associative:
            results.append({
                "table": table_name,
                "total_columns": len(cols),
                "id_columns": id_cols,
                "primary_key_columns": pk_cols,
                "is_associative": True,
            })

    return {"associative_table_count": len(results), "tables": results}
```

---

## 浜斻€丆ode 宸ュ叿闆?
### 鏂囦欢锛歚backend/mcp/tools/code_tools.py`

鐢?CodeWorker 璋冪敤锛岃В鏋?SQL 浠ｇ爜鎻愬彇鍏崇郴銆?
### 宸ュ叿 1锛歚parse_view_definition`

浣跨敤 sqlparse 搴撹В鏋愯鍥惧畾涔夛紝鎻愬彇 FROM/JOIN 瀛愬彞涓殑琛ㄥ銆?
```python
import re

def parse_view_definition(view_name: str, definition: str):
    """
    瑙ｆ瀽瑙嗗浘鐨?SQL 瀹氫箟锛屾彁鍙栨墍鏈夎〃闂?JOIN 鍏崇郴銆?    杩斿洖锛氳瑙嗗浘涓嚭鐜扮殑鎵€鏈夎〃瀵瑰拰杩炴帴鏉′欢銆?    """
    relations = []
    # 鐢ㄦ鍒欏尮閰?JOIN ... ON ... 妯″紡
    # 鍖归厤: JOIN <table> [AS <alias>] ON <condition>
    join_pattern = re.compile(
        r'(?:INNER\s+|LEFT\s+|RIGHT\s+|OUTER\s+|CROSS\s+)?JOIN\s+`?(\w+)`?(?:\s+AS\s+`?(\w+)`?)?\s+ON\s+(.+?)(?=JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|LIMIT|$|\()',
        re.IGNORECASE | re.DOTALL
    )

    # 鍏堟壘鍑?FROM 瀛愬彞鐨勪富琛?    from_match = re.search(r'\bFROM\s+`?(\w+)`?(?:\s+AS\s+`?(\w+)`?)?', definition, re.IGNORECASE)
    from_table = from_match.group(1) if from_match else None

    for match in join_pattern.finditer(definition):
        joined_table = match.group(1)
        alias = match.group(2) or joined_table
        condition = match.group(3).strip()

        # 浠?condition 涓彁鍙栧瓧娈靛
        col_pairs = extract_column_pairs(condition)

        relations.append({
            "from_table": from_table or "(unknown)",
            "joined_table": joined_table,
            "alias": alias,
            "condition": condition,
            "column_pairs": col_pairs  # [{"left": "orders.user_id", "right": "users.id"}, ...]
        })

    return {"view": view_name, "relation_count": len(relations), "relations": relations}


def extract_column_pairs(condition: str):
    """
    浠?ON 鏉′欢涓彁鍙栧瓧娈靛銆?    渚嬪锛歰rders.user_id = users.id 鈫?{"left": "orders.user_id", "right": "users.id"}
    """
    pairs = []
    # 鐢?AND 鍒嗗壊澶氫釜鏉′欢
    parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
    for part in parts:
        eq_match = re.match(r'\s*`?(\w+)`?\.`?(\w+)`?\s*=\s*`?(\w+)`?\.`?(\w+)`?\s*', part)
        if eq_match:
            pairs.append({
                "left": f"{eq_match.group(1)}.{eq_match.group(2)}",
                "right": f"{eq_match.group(3)}.{eq_match.group(4)}"
            })
    return pairs
```

### 宸ュ叿 2锛歚parse_stored_procedure_sql`

```python
def parse_stored_procedure_sql(proc_name: str, definition: str):
    """
    瑙ｆ瀽瀛樺偍杩囩▼鐨?SQL 瀹氫箟锛屾彁鍙?JOIN 鍏崇郴鍜屽瓙鏌ヨ鍏崇郴銆?    涓?parse_view_definition 绫讳技锛屼絾棰濆澶勭悊瀛樺偍杩囩▼涓殑涓存椂琛ㄥ拰鍔ㄦ€丼QL銆?    """
    # 鍏堢Щ闄ゆ敞閲婂拰瀛楃涓插瓧闈㈤噺
    cleaned = remove_sql_comments(definition)

    relations = []
    from_tables = []

    # 鎻愬彇鎵€鏈?SELECT 璇彞涓殑 FROM 瀛愬彞
    select_blocks = re.finditer(
        r'\bSELECT\b.+?\bFROM\b\s+`?(\w+)`?(?:\s+AS\s+`?(\w+)`?)?',
        cleaned, re.IGNORECASE | re.DOTALL
    )
    for block in select_blocks:
        from_tables.append(block.group(1))

    # 鎻愬彇 JOIN
    join_pattern = re.compile(
        r'(?:INNER\s+|LEFT\s+|RIGHT\s+|OUTER\s+|CROSS\s+)?JOIN\s+`?(\w+)`?(?:\s+AS\s+`?(\w+)`?)?\s+ON\s+(.+?)(?=JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|LIMIT|\)\s*;|\bEND\b)',
        re.IGNORECASE | re.DOTALL
    )

    for match in join_pattern.finditer(cleaned):
        joined_table = match.group(1)
        condition = match.group(3).strip()
        col_pairs = extract_column_pairs(condition)

        relations.append({
            "from_tables": list(set(from_tables)),
            "joined_table": joined_table,
            "condition": condition,
            "column_pairs": col_pairs
        })

    # 棰濆锛氭彁鍙栧瓙鏌ヨ涓殑琛ㄥ叧绯?    # SELECT ... FROM (SELECT ...) AS sub
    subquery_relations = extract_subquery_relations(cleaned)

    return {
        "procedure": proc_name,
        "relation_count": len(relations) + len(subquery_relations),
        "relations": relations + subquery_relations
    }


def remove_sql_comments(sql: str) -> str:
    """绉婚櫎 SQL 涓殑娉ㄩ噴锛堝崟琛?-- 鍜屽琛?/* */锛?""
    sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql


def extract_subquery_relations(sql: str):
    """浠庡瓙鏌ヨ涓彁鍙栬〃闂村叧绯?""
    # 绠€鐗堝疄鐜帮細鍖归厤 SELECT ... FROM (SELECT ...) AS sub 妯″紡
    relations = []
    subquery_pattern = re.compile(
        r'\(\s*SELECT\s+.+?\s+FROM\s+`?(\w+)`?',
        re.IGNORECASE | re.DOTALL
    )
    for match in subquery_pattern.finditer(sql):
        # 瀛愭煡璇腑鍑虹幇鐨勮〃
        inner_table = match.group(1)
        # 鏌ユ壘瀛愭煡璇㈠鐨勪笂涓嬫枃锛堢畝鍖栧鐞嗭紝鍙褰曡〃鍚嶏級
        relations.append({
            "from_tables": ["(subquery)"],
            "joined_table": inner_table,
            "condition": "(subquery context)",
            "column_pairs": [],
            "relation_type": "subquery_ref"
        })
    return relations
```

### 宸ュ叿 3锛歚analyze_trigger_body`

```python
def analyze_trigger_body(trigger_name: str, event: str, table: str, definition: str):
    """鍒嗘瀽瑙﹀彂鍣ㄤ綋涓秹鍙婄殑琛ㄥ叧绯?""
    # 鎻愬彇 UPDATE/INSERT/DELETE 涓殑琛ㄥ悕
    referenced_tables = set()
    table_refs = re.findall(r'\b(FROM|JOIN|UPDATE|INTO|TABLE)\s+`?(\w+)`?', definition, re.IGNORECASE)
    for ref_type, ref_table in table_refs:
        referenced_tables.add(ref_table.lower())

    # 鎺掗櫎鑷韩
    referenced_tables.discard(table.lower())

    return {
        "trigger": trigger_name,
        "on_table": table,
        "event": event,
        "referenced_tables": list(referenced_tables),
        "table_count": len(referenced_tables)
    }
```

---

## 鍏€丱RM 宸ュ叿闆?
### 鏂囦欢锛歚backend/mcp/tools/orm_tools.py`

鐢?ORMWorker 璋冪敤锛岃В鏋?MyBatis XML 鍜?JPA 娉ㄨВ銆?
### 宸ュ叿 1锛歚parse_mybatis_xml`

```python
import re

def parse_mybatis_xml(xml_content: str, file_name: str):
    """
    瑙ｆ瀽 MyBatis XML 鏄犲皠鏂囦欢锛屾彁鍙?association 鍜?collection 鏍囩銆?    """
    relations = []

    # 鎻愬彇 namespace锛堝搴斿疄浣撶被/琛級
    ns_match = re.search(r'namespace="([^"]+)"', xml_content)
    namespace = ns_match.group(1) if ns_match else "unknown"

    # 鎻愬彇 association 鏍囩锛坢any-to-one / one-to-one锛?    assoc_pattern = re.compile(
        r'<association\s+property="(\w+)"\s+(?:javaType="([^"]*)"\s+)?'
        r'column="([^"]*)"\s+(?:select="([^"]*)"|(?:fetchType="[^"]*")?\s*/>)',
        re.IGNORECASE
    )
    for match in assoc_pattern.finditer(xml_content):
        relations.append({
            "type": "association",
            "property": match.group(1),
            "java_type": match.group(2) or "",
            "column": match.group(3),
            "select_method": match.group(4) or "(inline)",
            "source_file": file_name
        })

    # 鎻愬彇 collection 鏍囩锛坥ne-to-many锛?    coll_pattern = re.compile(
        r'<collection\s+property="(\w+)"\s+(?:ofType="([^"]*)"\s+)?'
        r'column="([^"]*)"\s+(?:select="([^"]*)"|(?:fetchType="[^"]*")?\s*/>)',
        re.IGNORECASE
    )
    for match in coll_pattern.finditer(xml_content):
        relations.append({
            "type": "collection",
            "property": match.group(1),
            "of_type": match.group(2) or "",
            "column": match.group(3),
            "select_method": match.group(4) or "(inline)",
            "source_file": file_name
        })

    # 鎻愬彇 resultMap 涓畾涔夌殑鍏宠仈锛堟洿澶嶆潅鐨勬儏鍐甸渶瑕侀澶栧鐞嗭級
    # 绠€鍗曟彁鍙栨墍鏈?resultMap 涓殑 id/result 鏄犲皠
    column_mappings = re.findall(
        r'<(?:id|result)\s+property="(\w+)"\s+column="(\w+)"',
        xml_content
    )

    return {
        "namespace": namespace,
        "file": file_name,
        "relation_count": len(relations),
        "relations": relations,
        "column_count": len(column_mappings),
        "column_mappings": column_mappings
    }
```

### 宸ュ叿 2锛歚parse_jpa_annotations`锛堝鐢級

```python
def parse_jpa_annotations(java_content: str, file_name: str):
    """
    瑙ｆ瀽 JPA 瀹炰綋绫讳腑鐨勬敞瑙ｏ紙@ManyToOne, @OneToMany, @JoinColumn, @JoinTable锛?    浣滀负 MyBatis 鐨勬浛浠ｆ柟妗堬紙褰撻」鐩娇鐢?JPA 鏃讹級銆?    鏈」鐩富瑕佺敤 MyBatis锛屾鍑芥暟淇濈暀浣滀负鎵╁睍鐐广€?    """
    # 鐣?鈥?鍚庣画闇€瑕佹椂鍐嶅疄鐜?    return {
        "file": file_name,
        "has_annotations": False,
        "message": "JPA parsing not implemented (project uses MyBatis)",
        "relations": []
    }
```

---

## 涓冦€佸伐鍏锋敞鍐屽叆鍙?
### 鏂囦欢锛歚backend/mcp/server.py`

```python
"""
MCP 宸ュ叿娉ㄥ唽鍏ュ彛 鈥?娉ㄥ唽鎵€鏈?Worker 鐨?MCP 宸ュ叿闆嗐€?鍦ㄥ簲鐢ㄥ惎鍔ㄦ椂璋冪敤涓€娆°€?"""

from backend.mcp.tool_registry import ToolRegistry


def init_mcp_tools():
    """鍒濆鍖栨墍鏈?MCP 宸ュ叿锛屽湪 FastAPI 鍚姩鏃惰皟鐢?""
    registry = ToolRegistry()

    from backend.mcp.tools import survey_tools
    from backend.mcp.tools import column_tools
    from backend.mcp.tools import name_tools
    from backend.mcp.tools import code_tools
    from backend.mcp.tools import orm_tools

    survey_tools.register_all(registry)
    column_tools.register_all(registry)
    name_tools.register_all(registry)
    code_tools.register_all(registry)
    orm_tools.register_all(registry)

    return registry
```

鍦?`backend/main.py` 鐨?`startup` 浜嬩欢涓皟鐢細

```python
@app.on_event("startup")
async def startup():
    from backend.mcp.server import init_mcp_tools
    app.state.tool_registry = init_mcp_tools()
```

---

## 鍏€侀獙璇?
瀹炵幇鍚庤繍琛屼互涓嬪懡浠ょ‘璁ゅ伐鍏峰彲姝ｅ父璋冪敤锛?
```python
# tests/test_tools.py
from backend.mcp.tool_registry import ToolRegistry
from backend.mcp.server import init_mcp_tools


def test_tools_register():
    registry = init_mcp_tools()
    tools = registry.list_tools()
    assert len(tools) >= 15  # 鑷冲皯15涓伐鍏?    tool_names = [t["name"] for t in tools]
    assert "connect_database" in tool_names
    assert "list_tables" in tool_names
    assert "analyze_table_columns" in tool_names
    assert "find_column_name_matches" in tool_names
    assert "parse_view_definition" in tool_names


def test_connect_database():
    registry = init_mcp_tools()
    result = registry.execute("connect_database")
    assert result["connected"] is True


def test_list_tables():
    registry = init_mcp_tools()
    result = registry.execute("list_tables")
    assert result["table_count"] == 30
```

娴嬭瘯閫氳繃鏉′欢锛?- `pytest tests/test_tools.py -v` 鍏ㄩ儴閫氳繃
- 鍙互鍦?Python 浜や簰寮忕幆澧冧腑鎵嬪姩璋冪敤浠绘剰宸ュ叿骞舵煡鐪嬭繑鍥炴牸寮?
