# 鏂囨。 4/5锛氭牳蹇冪紪鎺?鈥?Router + Orchestrator + 涓夌骇璁板繂

> **缁?GPT 鐨勮緭鍏ユ枃妗?* 鈥?璇蜂弗鏍兼寜鐓ф鏂囨。瀹炵幇銆?> 纭繚鏂囨。 3 鍏ㄩ儴瀹炵幇骞堕€氳繃娴嬭瘯鍚庡啀寮€濮嬫湰妯″潡銆?
---

## 涓€銆丱rchestrator锛堟€荤紪鎺掑櫒锛?
### 鏂囦欢锛歚backend/agent/orchestrator.py`

Orchestrator 鏄?Agent 鐨勬牳蹇冩帶鍒跺櫒锛岃礋璐ｏ細
1. 鎸夐『搴忚皟鐢?Worker
2. 绠＄悊 Worker 涔嬮棿鐨勪笂涓嬫枃浼犻€?3. 澶勭悊闄嶇骇閾捐矾
4. 璁板綍姣忎釜姝ラ鐨勬棩蹇楋紙缁?Monitor 鐢級

### 鎵ц椤哄簭

```
Step 1: SurveyWorker锛堝繀缁忥級鈥?鍒濆嫎鏁版嵁搴?    鈫?杈撳嚭 鈫?context["survey_result"]
Step 2: Router 鍒嗘瀽 鈫?鍐冲畾骞惰/涓茶璋冨害绛栫暐
    鈫?Step 3a: ColumnWorker锛堝缁堟墽琛?鈥?瑕嗙洊闈㈠箍锛屾垚鏈綆锛?Step 3b: NameWorker锛堝缁堟墽琛?鈥?绾湰鍦板垎鏋愶紝鏃犲閮ㄨ皟鐢級
    鈫?骞惰鎴栦覆琛岋紙鏃犳暟鎹緷璧栵級
Step 4: CodeWorker锛堝缁堟墽琛?鈥?鏈€楂樿川閲忚瘉鎹級
    鈫?渚濊禆 Step 1 鐨勮鍥?SP 娓呭崟
Step 5: ORMWorker锛堝彧鍦ㄦ湁 ORM 鏂囦欢鏃舵墽琛岋級
    鈫?Step 6: MergeWorker 鈥?鏀堕泦鎵€鏈夎瘉鎹紝铻嶅悎杈撳嚭
```

### 瀹炵幇

```python
"""
Orchestrator 鈥?鎬荤紪鎺掑櫒
"""

import time
import uuid
from typing import Any

from backend.mcp.tool_registry import ToolRegistry
from backend.agent.workers.survey import SurveyWorker
from backend.agent.workers.column import ColumnWorker
from backend.agent.workers.name import NameWorker
from backend.agent.workers.code import CodeWorker
from backend.agent.workers.orm import ORMWorker
from backend.agent.workers.merge import MergeWorker
from backend.agent.router import Router
from backend.monitor.recorder import MonitorRecorder


class Orchestrator:
    """
    缂栨帓鍣?鈥?鎺у埗鏁翠釜鍒嗘瀽娴佺▼銆?    
    鐢ㄦ硶锛?        orch = Orchestrator(tool_registry)
        result = orch.run_full_analysis()
    """

    def __init__(self, tool_registry: ToolRegistry):
        self.tool_registry = tool_registry
        self.router = Router()
        self.recorder = MonitorRecorder()

        # 鍒濆鍖栨墍鏈?Worker
        self.workers = {
            "survey": SurveyWorker(tool_registry),
            "column": ColumnWorker(tool_registry),
            "name": NameWorker(tool_registry),
            "code": CodeWorker(tool_registry),
            "orm": ORMWorker(tool_registry),
            "merge": MergeWorker(tool_registry),
        }

    def run_full_analysis(self) -> dict:
        """
        鎵ц涓€娆″畬鏁寸殑 Schema 鍒嗘瀽銆?        杩斿洖浠?Survey 鈫?鎵€鏈?Worker 鈫?Merge 鐨勫叏閾捐矾缁撴灉銆?        """
        session_id = self._new_session_id()
        context: dict[str, Any] = {"session_id": session_id}
        steps: list[dict] = []

        # 鈹€鈹€ Step 1: SurveyWorker锛堝繀缁忥級鈹€鈹€
        step1 = self._run_worker("survey", context, steps)
        if step1["status"] == "error":
            return self._build_result(session_id, "error", steps, error=step1.get("error"))

        context["survey_result"] = step1["output"]

        # 鈹€鈹€ Step 2: Router 鍒嗘瀽 鈹€鈹€
        plan = self.router.plan_analysis(context["survey_result"])
        steps.append({
            "step": 2,
            "worker": "router",
            "status": "success",
            "duration_ms": 0,
            "output": plan,
        })

        # 鈹€鈹€ Step 3a: ColumnWorker 鈹€鈹€
        step3a = self._run_worker("column", context, steps)
        if step3a["status"] == "success":
            context["column_result"] = step3a["output"]

        # 鈹€鈹€ Step 3b: NameWorker 鈹€鈹€
        step3b = self._run_worker("name", context, steps)
        if step3b["status"] == "success":
            context["name_result"] = step3b["output"]

        # 鈹€鈹€ Step 4: CodeWorker锛堥渶瑕?survey_result 涓殑瑙嗗浘/SP 娓呭崟锛夆攢鈹€
        step4 = self._run_worker("code", context, steps)
        if step4["status"] == "success":
            context["code_result"] = step4["output"]

        # 鈹€鈹€ Step 5: ORMWorker锛堝彧鍦ㄦ湁 ORM 鏂囦欢鏃舵墽琛岋級鈹€鈹€
        survey = context.get("survey_result", {})
        if survey.get("orm_files", {}).get("count", 0) > 0:
            step5 = self._run_worker("orm", context, steps)
            if step5["status"] == "success":
                context["orm_result"] = step5["output"]
        else:
            steps.append({
                "step": 5,
                "worker": "orm",
                "status": "skipped",
                "duration_ms": 0,
                "output": {"message": "No ORM files found, skipping"},
            })
            context["orm_result"] = {"total_relations": 0, "relations": []}

        # 鈹€鈹€ Step 6: MergeWorker 鈹€鈹€
        step6 = self._run_worker("merge", context, steps)
        if step6["status"] == "success":
            context["merge_result"] = step6["output"]

        # 鈹€鈹€ 璁板綍鍒?Monitor 鈹€鈹€
        self.recorder.record_analysis(session_id, context, steps)

        return self._build_result(session_id, "completed", steps, context)

    def _run_worker(self, worker_id: str, context: dict, steps: list[dict]) -> dict:
        """杩愯涓€涓?Worker锛岃褰曡€楁椂鍜岀粨鏋?""
        start = time.time()
        try:
            worker = self.workers[worker_id]
            output = worker.run(context)
            duration = int((time.time() - start) * 1000)
            status = "success" if output.get("status") == "success" else "partial"
            step = {
                "step": len(steps) + 1,
                "worker": worker_id,
                "status": status,
                "duration_ms": duration,
                "tool_calls": worker.get_call_log(),
                "output": output,
            }
            steps.append(step)
            return {"status": status, "output": output, "duration_ms": duration}
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            error_step = {
                "step": len(steps) + 1,
                "worker": worker_id,
                "status": "error",
                "duration_ms": duration,
                "error": str(e),
            }
            steps.append(error_step)
            return {"status": "error", "error": str(e)}

    def _new_session_id(self) -> str:
        return f"ana_{uuid.uuid4().hex[:12]}"

    def _build_result(self, session_id: str, status: str,
                      steps: list[dict], context: dict = None,
                      error: str = None) -> dict:
        """鏋勫缓鏈€缁堣緭鍑?""
        result = {
            "session_id": session_id,
            "status": status,
            "total_steps": len(steps),
            "steps": steps,
        }
        if context and "merge_result" in context:
            result["er_diagram"] = self._build_er_diagram(context["merge_result"])
            result["merge_result"] = context["merge_result"]
        if error:
            result["error"] = error
        return result

    def _build_er_diagram(self, merge_result: dict) -> dict:
        """浠?MergeWorker 鐨勮緭鍑烘彁鍙栫畝娲佺殑 ER 鍥撅紙缁欏墠绔睍绀虹敤锛?""
        high = merge_result.get("high_confidence_relations", [])
        medium = merge_result.get("medium_confidence_relations", [])

        # 鏋勫缓浠ヨ〃涓轰腑蹇冪殑 ER 鍥?        er_tables = {}  # table_name 鈫?{relations: [...]}
        for rel in high + medium:
            src = rel["source_table"]
            tgt = rel["target_table"]
            for table in [src, tgt]:
                if table not in er_tables:
                    er_tables[table] = {"relations": [], "relation_count": 0}

            er_tables[src]["relations"].append({
                "type": "has",
                "target": tgt,
                "via": rel["fk_column"],
                "confidence": rel.get("fused_confidence", 0),
            })
            er_tables[src]["relation_count"] += 1

        return {
            "table_count": len(er_tables),
            "tables": er_tables,
        }
```

---

## 浜屻€丷outer

### 鏂囦欢锛歚backend/agent/router.py`

Router 璐熻矗鍒嗘瀽 SurveyWorker 鐨勮緭鍑烘潵鍐冲畾璋冨害绛栫暐銆傚湪杩欎釜椤圭洰涓紝鐢变簬 Worker 涔嬮棿鐨勬暟鎹緷璧栨瘮杈冩槑纭紙Column/Name 涓嶄緷璧栧郊姝わ紝浣嗛兘渚濊禆 Survey锛夛紝Router 鐨勪富瑕佽亴璐ｆ槸锛?
1. 鍒ゆ柇鏄惁鎵€鏈?Worker 閮藉叿澶囪繍琛屾潯浠?2. 璇嗗埆 Worker 涔嬮棿鐨勪緷璧栧叧绯伙紝鍐冲畾骞惰/涓茶璋冨害
3. 妫€娴嬪紓甯告儏鍐碉紙鏁版嵁搴撲负绌恒€佹棤浠ｇ爜瀵硅薄绛夛級骞惰皟鏁寸瓥鐣?
```python
"""
Router 鈥?鍒嗘瀽 Survey 缁撴灉锛屽埗瀹?Worker 璋冨害璁″垝
"""


class Router:
    """
    璺敱鍒嗘瀽鍣?鈥?鏍规嵁 SurveyWorker 鐨勮緭鍑猴紝鍐冲畾濡備綍璋冨害鍚?Worker銆?    
    鍦ㄨ繖涓?Schema 閫嗗悜椤圭洰閲岋紝璋冨害鐩稿纭畾锛?    - Survey 鈫?(Column + Name) 鈫?(Code + ORM) 鈫?Merge
    - Column 鍜?Name 鏃犳暟鎹緷璧栵紝鍙苟琛?    - Code 鍜?ORM 鏃犳暟鎹緷璧栵紝鍙苟琛?    - 鎵€鏈?Worker 渚濊禆 Survey 鐨勮緭鍑轰綔涓鸿緭鍏?    """

    def plan_analysis(self, survey_result: dict) -> dict:
        """
        鍒嗘瀽 Survey 缁撴灉锛岀敓鎴愯皟搴﹁鍒掋€?        
        杩斿洖 plan dict锛?        {
            "phases": [
                {"phase": 1, "workers": ["survey"], "parallel": false},
                {"phase": 2, "workers": ["column", "name"], "parallel": true},
                {"phase": 3, "workers": ["code", "orm"], "parallel": true},
                {"phase": 4, "workers": ["merge"], "parallel": false},
            ],
            "schedule_strategy": "serial_phases",  
            "anomalies": [...],
            "total_estimated_calls": int,
        }
        """
        anomalies = []
        warnings = []

        summary = survey_result.get("summary", {})
        table_count = summary.get("total_tables", 0)
        sp_count = summary.get("total_procedures", 0)
        view_count = summary.get("total_views", 0)
        orm_count = summary.get("total_orm_files", 0)

        # 寮傚父妫€娴?        if table_count == 0:
            anomalies.append("鏁版嵁搴撲腑娌℃湁琛紝鍒嗘瀽鏃犳硶杩涜")
        if table_count > 100:
            warnings.append(f"琛ㄦ暟閲忚緝澶?({table_count})锛屽垎鏋愬彲鑳介渶瑕佽緝闀挎椂闂?)
        if sp_count == 0 and view_count == 0 and orm_count == 0:
            warnings.append("娌℃湁瀛樺偍杩囩▼銆佽鍥炬垨 ORM 閰嶇疆锛屼粎鑳藉熀浜庡垪鍚嶅拰鍛藉悕绾﹀畾鎺ㄧ悊")

        # 浼拌宸ュ叿璋冪敤娆℃暟
        estimated_calls = (
            1 +  # connect_database
            1 +  # list_tables
            1 +  # list_views
            1 +  # list_stored_procedures
            1 +  # list_triggers
            1 +  # find_orm_configs
            table_count * 2 +  # column_analyze + check_indexes 姣忓紶琛?            sp_count * 1 +    # parse 姣忎釜 SP
            view_count * 1 +  # parse 姣忎釜瑙嗗浘
            orm_count * 1     # parse 姣忎釜 ORM
        )

        return {
            "phases": [
                {
                    "phase": 1,
                    "name": "Database Survey",
                    "workers": ["survey"],
                    "parallel": False,
                    "description": "鎵弿鏁版嵁搴撳叏閮ㄥ璞?,
                },
                {
                    "phase": 2,
                    "name": "Schema Analysis",
                    "workers": ["column", "name"],
                    "parallel": True,
                    "description": "鍒楀垎鏋愬拰鍛藉悕鍒嗘瀽锛堜簰涓嶄緷璧栵紝鍙苟琛岋級",
                },
                {
                    "phase": 3,
                    "name": "Code & ORM Analysis",
                    "workers": ["code", "orm"],
                    "parallel": True,
                    "description": "SQL浠ｇ爜鍜孫RM閰嶇疆鍒嗘瀽锛堜緷璧朠hase1杈撳嚭锛?,
                },
                {
                    "phase": 4,
                    "name": "Evidence Fusion",
                    "workers": ["merge"],
                    "parallel": False,
                    "description": "铻嶅悎鎵€鏈夎瘉鎹紝杈撳嚭ER鍥?,
                },
            ],
            "schedule_strategy": "serial_phases_with_parallel_workers",
            "anomalies": anomalies,
            "warnings": warnings,
            "total_estimated_tool_calls": estimated_calls,
            "summary": {
                "tables": table_count,
                "views": view_count,
                "stored_procedures": sp_count,
                "orm_files": orm_count,
            },
        }
```

---

## 涓夈€佷笁绾ц蹇?
鍦?Schema 閫嗗悜鐨勫満鏅腑锛岃蹇嗙殑鐢ㄩ€旀槸**璺ㄥ垎鏋愪細璇濅繚鎸佸凡鍙戠幇鐨勬ā寮?*銆備緥濡傦細

- L1 Session锛氬綋鍓嶅垎鏋愪細璇濈殑涓婁笅鏂囷紙Worker 涔嬮棿鐨勬暟鎹紶閫掞級
- L2 Schema锛氬凡鍙戠幇鐨勮〃鍏崇郴缃戠粶锛堝涓垎鏋愪細璇濅箣闂村叡浜級
- L3 Global锛氶€氱敤鏁版嵁搴撹璁℃ā寮忥紙鍏ㄥ眬鐨勩€佷笉渚濊禆鍏蜂綋琛ㄧ殑锛?
### 3.1 鏂囦欢锛歚backend/agent/memory/session_memory.py`

```python
"""
L1: Session 绾ц蹇嗭紙鍐呭瓨锛?浣滅敤锛氬瓨鍌ㄥ綋鍓嶅垎鏋愪細璇濅腑 Worker 涔嬮棿鐨勬暟鎹紶閫掋€?姣忎釜鍒嗘瀽杩愯鏈夊敮涓€鐨?session_id銆?"""


class SessionMemory:
    """
    浼氳瘽绾ц蹇?鈥?瀛樺偍褰撳墠鍒嗘瀽浼氳瘽鐨勪腑闂寸姸鎬併€?    鍦ㄥ唴瀛樹腑缁存姢锛屽垎鏋愬畬鎴愬悗鍙涪寮冦€?    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._data: dict = {
            "survey_result": None,
            "column_result": None,
            "name_result": None,
            "code_result": None,
            "orm_result": None,
            "merge_result": None,
        }
        self._messages: list[dict] = []

    def set(self, key: str, value: dict):
        """瀛樺偍 Worker 鐨勮緭鍑?""
        if key in self._data:
            self._data[key] = value
            self._messages.append({
                "type": "worker_output",
                "key": key,
                "timestamp": self._now(),
            })

    def get(self, key: str) -> dict | None:
        """鑾峰彇 Worker 鐨勮緭鍑?""
        return self._data.get(key)

    def get_all(self) -> dict:
        """鑾峰彇鍏ㄩ儴涓婁笅鏂?""
        return dict(self._data)

    def add_message(self, role: str, content: str):
        """璁板綍鍒嗘瀽杩囩▼涓殑娑堟伅锛堢敤浜庤拷婧級"""
        self._messages.append({
            "role": role,
            "content": content[:500],
            "timestamp": self._now(),
        })

    def get_messages(self) -> list[dict]:
        return self._messages

    def _now(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
```

### 3.2 鏂囦欢锛歚backend/agent/memory/schema_memory.py`

```python
"""
L2: Schema 绾ц蹇嗭紙SQLite锛?浣滅敤锛氬瓨鍌ㄥ凡鍙戠幇鐨勮〃鍏崇郴缃戠粶銆傝法鍒嗘瀽浼氳瘽鎸佷箙鍖栥€?褰撳娆″垎鏋愬悓涓€涓暟鎹簱鏃讹紙渚嬪淇浜?Schema 鍚庨噸鏂板垎鏋愶級锛?涓婃鍙戠幇鐨勫叧绯诲彲浠ュ鐢ㄦ垨浣滀负瀵圭収銆?"""

import json
import sqlite3
import os
from datetime import datetime


class SchemaMemory:
    """
    Schema 绾ц蹇?鈥?璺ㄤ細璇濆瓨鍌ㄥ苟妫€绱㈠凡鍙戠幇鐨勮〃鍏崇郴銆?    
    鐢ㄩ€旓細
    1. 鍚屼竴鏁版嵁搴撳娆″垎鏋愭椂锛屽姣斿墠鍚庡樊寮?    2. 鏂?Worker 鍦ㄥ垎鏋愭椂锛屽彲浠ユ煡璇㈠巻鍙插彂鐜扮殑鍏崇郴浣滀负鍙傝€?    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.environ.get("DATA_DIR", "/app/data"),
                "schema_memory.db"
            )
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """鍒濆鍖?SQLite 琛?""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS discovered_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_table TEXT NOT NULL,
                    target_table TEXT NOT NULL,
                    fk_column TEXT NOT NULL,
                    pk_column TEXT,
                    relation_type TEXT DEFAULT 'N:1',
                    confidence REAL DEFAULT 0.0,
                    top_evidence TEXT,         -- JSON: 鏈€浣宠瘉鎹憳瑕?                    first_discovered TEXT DEFAULT (datetime('now')),
                    last_verified TEXT DEFAULT (datetime('now')),
                    discover_count INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_relation
                ON discovered_relations(source_table, target_table, fk_column)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    database_name TEXT,
                    analysis_date TEXT DEFAULT (datetime('now')),
                    table_count INTEGER,
                    relation_count INTEGER,
                    high_confidence_count INTEGER,
                    summary TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def save_relations(self, relations: list[dict], session_id: str):
        """灏嗚瀺鍚堝悗鐨勫叧绯讳繚瀛樺埌 Schema 璁板繂"""
        conn = sqlite3.connect(self.db_path)
        try:
            for rel in relations:
                top_ev = (rel.get("evidence_chain") or [{}])[0] if rel.get("evidence_chain") else {}
                conn.execute("""
                    INSERT INTO discovered_relations
                        (source_table, target_table, fk_column, pk_column,
                         relation_type, confidence, top_evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_table, target_table, fk_column)
                    DO UPDATE SET
                        confidence = (confidence + excluded.confidence) / 2,
                        discover_count = discover_count + 1,
                        last_verified = datetime('now'),
                        top_evidence = CASE WHEN excluded.confidence > confidence
                                            THEN excluded.top_evidence ELSE top_evidence END
                """, (
                    rel.get("source_table", ""),
                    rel.get("target_table", ""),
                    rel.get("fk_column", ""),
                    rel.get("pk_column", ""),
                    rel.get("relation_type", "N:1"),
                    rel.get("fused_confidence", 0.0),
                    json.dumps(top_ev, ensure_ascii=False),
                ))
            conn.commit()
        finally:
            conn.close()

    def save_analysis_history(self, session_id: str, database: str,
                               table_count: int, relation_count: int,
                               high_count: int, summary: str):
        """璁板綍涓€娆″垎鏋愮殑鍘嗗彶"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT INTO analysis_history
                    (session_id, database_name, table_count,
                     relation_count, high_confidence_count, summary)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session_id, database, table_count, relation_count,
                  high_count, summary))
            conn.commit()
        finally:
            conn.close()

    def query_similar_relations(self, source_table: str = None,
                                 target_table: str = None) -> list[dict]:
        """
        鏌ヨ鍘嗗彶鍏崇郴銆傚彲鐢ㄤ簬褰撳墠 Worker 鍙傝€冦€?        
        鍙傛暟锛?        - source_table: 婧愯〃鍚嶏紙鍙€夛級
        - target_table: 鐩爣琛ㄥ悕锛堝彲閫夛級
        """
        conn = sqlite3.connect(self.db_path)
        try:
            query = "SELECT * FROM discovered_relations WHERE is_active = 1"
            params = []
            if source_table:
                query += " AND source_table = ?"
                params.append(source_table)
            if target_table:
                query += " AND target_table = ?"
                params.append(target_table)
            query += " ORDER BY confidence DESC LIMIT 20"

            rows = conn.execute(query, params).fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "source_table": row[1],
                    "target_table": row[2],
                    "fk_column": row[3],
                    "pk_column": row[4],
                    "relation_type": row[5],
                    "confidence": row[6],
                    "top_evidence": json.loads(row[7]) if row[7] else {},
                    "first_discovered": row[8],
                    "last_verified": row[9],
                    "discover_count": row[10],
                })
            return results
        finally:
            conn.close()

    def get_history(self, limit: int = 10) -> list[dict]:
        """鑾峰彇鏈€杩戠殑鍒嗘瀽鍘嗗彶"""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("""
                SELECT * FROM analysis_history
                ORDER BY analysis_date DESC LIMIT ?
            """, (limit,)).fetchall()
            return [
                {
                    "id": r[0],
                    "session_id": r[1],
                    "database": r[2],
                    "date": r[3],
                    "tables": r[4],
                    "relations": r[5],
                    "high_confidence": r[6],
                    "summary": r[7],
                }
                for r in rows
            ]
        finally:
            conn.close()
```

### 3.3 鏂囦欢锛歚backend/agent/memory/global_memory.py`

```python
"""
L3: 鍏ㄥ眬绾ц蹇嗭紙SQLite锛?浣滅敤锛氬瓨鍌ㄩ€氱敤鐨勬暟鎹簱璁捐妯″紡鍜屽父瑙佸懡鍚嶇害瀹氥€?涓嶄緷璧栧叿浣撹〃锛岀敤浜庢寚瀵?Worker 鐨勬帹鐞嗐€?"""

import sqlite3
import json
import os


class GlobalMemory:
    """
    鍏ㄥ眬绾ц蹇?鈥?瀛樺偍閫氱敤鐨勬暟鎹簱璁捐鐭ヨ瘑鍜岀粡楠岃鍒欍€?    
    鍐呭绀轰緥锛?    - 甯歌鍏宠仈琛ㄥ懡鍚嶆ā寮?    - 甯歌澶栭敭鍛藉悕绾﹀畾
    - 宸茬煡鐨勫垪鍚嶁啋鍚箟鏄犲皠锛堝 status鈫掓灇涓撅紝涓嶅彲鑳芥槸澶栭敭锛?    - 鍘嗗彶鍒嗘瀽涓Н绱殑缁忛獙瑙勫垯
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.environ.get("DATA_DIR", "/app/data"),
                "global_memory.db"
            )
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

            # 鎻掑叆榛樿鐭ヨ瘑锛堝鏋滆〃涓虹┖锛?            existing = conn.execute("SELECT COUNT(*) FROM global_knowledge").fetchone()[0]
            if existing == 0:
                self._seed_default_knowledge(conn)
                conn.commit()
        finally:
            conn.close()

    def _seed_default_knowledge(self, conn):
        """鍒濆鍖栭粯璁ょ殑鍏ㄥ眬鐭ヨ瘑"""
        defaults = [
            # 鍛藉悕绾﹀畾瑙勫垯
            ("naming", "fk_suffix", "_id",
             "浠ヤ笅鍒掔嚎鍔爄d缁撳熬鐨勫垪鍚嶉€氬父鏄閿垪"),
            ("naming", "associative_table_pattern", "table1_table2",
             "鐢变袱涓疄浣撳悕鐢ㄤ笅鍒掔嚎杩炴帴鐨勯€氬父鏄瀵瑰鍏宠仈琛?),
            ("naming", "primary_key_name", "id",
             "澶ч儴鍒嗘暟鎹簱浣跨敤'id'浣滀负涓婚敭鍒楀悕"),

            # 闈炲閿垪鍚嶆ā寮?            ("non_fk", "status_columns", "status,state,flag,type,stage",
             "杩欎簺鍒楀悕閫氬父琛ㄧず鐘舵€佹灇涓撅紝涓嶆槸澶栭敭"),
            ("non_fk", "time_columns", "created_at,updated_at,deleted_at,start_time,end_time",
             "鏃堕棿鍒椾笉鍙兘鏄閿?),
            ("non_fk", "descriptive_columns", "name,title,description,comment,content,note,remark,address,url,email,phone,image,avatar",
             "鎻忚堪鎬ф枃鏈垪涓嶅彲鑳芥槸澶栭敭"),

            # 甯歌鍏崇郴妯″紡
            ("common_pattern", "user_x", "<table>.user_id 鈫?users.id",
             "user_id 鏄渶甯歌鐨勫閿紝鍑犱箮鎬绘槸寮曠敤 users 琛?),
            ("common_pattern", "order_x", "<table>.order_id 鈫?orders.id",
             "order_id 涔熸槸甯歌澶栭敭"),
            ("common_pattern", "product_x", "<table>.product_id 鈫?products.id",
             "product_id 寮曠敤 products 琛?),
        ]
        conn.executemany("""
            INSERT INTO global_knowledge (category, key, value, description, priority)
            VALUES (?, ?, ?, ?, 1)
        """, defaults)

    def get_by_category(self, category: str) -> list[dict]:
        """鎸夌被鍒幏鍙栫煡璇?""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("""
                SELECT * FROM global_knowledge
                WHERE category = ?
                ORDER BY priority DESC
            """, (category,)).fetchall()
            return [
                {"id": r[0], "category": r[1], "key": r[2],
                 "value": r[3], "description": r[4], "priority": r[5]}
                for r in rows
            ]
        finally:
            conn.close()

    def add_experience_rule(self, pattern: str, rule: str):
        """
        娣诲姞涓€鏉℃柊鐨勭粡楠岃鍒欙紙鐢?Monitor 鎴栦汉宸ユ坊鍔狅級銆?        
        渚嬪锛氱粡杩囧娆″垎鏋愬彂鐜?'type_code' 鍒楀悕涓嶆槸澶栭敭锛?        鍙互娣诲姞涓€鏉′緥澶栬鍒欍€?        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO global_knowledge
                    (category, key, value, description, priority)
                VALUES ('experience', ?, ?, ?, 5)
            """, (pattern, rule, f"鑷姩绉疮鐨勭粡楠岃鍒? {rule}"))
            conn.commit()
        finally:
            conn.close()
```

### 3.4 鏂囦欢锛歚backend/agent/memory/memory_manager.py`

```python
"""
Memory Manager 鈥?涓夌骇璁板繂鐨勭粺涓€绠＄悊鍏ュ彛銆?Orchestrator 閫氳繃姝ゆ帴鍙ｈ闂墍鏈夌骇鍒殑璁板繂銆?"""

from backend.agent.memory.session_memory import SessionMemory
from backend.agent.memory.schema_memory import SchemaMemory
from backend.agent.memory.global_memory import GlobalMemory


class MemoryManager:
    """
    涓夌骇璁板繂绠＄悊鍣ㄣ€?    
    L1 Session 鈥?褰撳墠浼氳瘽涓婁笅鏂囷紙鍐呭瓨锛?    L2 Schema  鈥?璺ㄤ細璇濈殑琛ㄥ叧绯荤煡璇嗭紙SQLite锛?    L3 Global  鈥?閫氱敤鏁版嵁搴撹璁＄煡璇嗭紙SQLite锛?    """

    def __init__(self, session_id: str):
        self.session = SessionMemory(session_id)
        self.schema = SchemaMemory()
        self.global_ctx = GlobalMemory()

    def save_analysis_result(self, session_id: str, database: str,
                              merge_result: dict):
        """鍒嗘瀽瀹屾垚鍚庯紝灏嗙粨鏋滄寔涔呭寲鍒?Schema 璁板繂"""
        # 淇濆瓨楂樼疆淇″害鍏崇郴
        relations = merge_result.get("high_confidence_relations", [])
        self.schema.save_relations(relations, session_id)

        # 淇濆瓨鍒嗘瀽鍘嗗彶
        summary = merge_result.get("summary", {})
        self.schema.save_analysis_history(
            session_id, database,
            summary.get("total_relations", 0),
            summary.get("total_relations", 0),
            summary.get("high_confidence", 0),
            f"鍙戠幇 {summary.get('high_confidence', 0)} 鏉￠珮缃俊搴﹀叧绯?
        )

    def get_non_fk_keywords(self) -> list[str]:
        """鑾峰彇宸茬煡鐨勯潪澶栭敭鍒楀悕鍏抽敭瀛楀垪琛紙杈呭姪 ColumnWorker 杩囨护锛?""
        rules = self.global_ctx.get_by_category("non_fk")
        keywords = []
        for rule in rules:
            keywords.extend(rule["value"].split(","))
        return [k.strip() for k in keywords if k.strip()]

    def get_naming_rules(self) -> list[dict]:
        """鑾峰彇鍛藉悕绾﹀畾瑙勫垯"""
        return self.global_ctx.get_by_category("naming")
```

---

## 鍥涖€佹暣鍚堬細鍦?Orchestrator 涓娇鐢?MemoryManager

鍦?`backend/agent/orchestrator.py` 鐨?`run_full_analysis` 鏂规硶鏈熬锛屽姞涓婅蹇嗘寔涔呭寲锛?
```python
def run_full_analysis(self) -> dict:
    # ... 鍓嶉潰鎵€鏈夋楠や笉鍙?...

    # 鈹€鈹€ 鍦?return 涔嬪墠娣诲姞璁板繂鎸佷箙鍖?鈹€鈹€
    if context.get("merge_result"):
        try:
            memory = MemoryManager(session_id)
            db_name = context["survey_result"].get("server_info", {}).get("database", "unknown")
            memory.save_analysis_result(session_id, db_name, context["merge_result"])
        except Exception as e:
            # 璁板繂鎸佷箙鍖栧け璐ヤ笉搴旈樆濉炰富娴佺▼
            steps.append({
                "step": len(steps) + 1,
                "worker": "memory",
                "status": "warning",
                "error": f"Failed to persist memory: {e}",
            })

    # ... return 涓嶅彉 ...
```

鍦?`backend/main.py` 涓惎鍔ㄦ椂鍒濆鍖栵細

```python
@app.on_event("startup")
async def startup():
    from backend.mcp.server import init_mcp_tools
    app.state.tool_registry = init_mcp_tools()
    
    # 纭繚 GlobalMemory 鍒濆鏁版嵁瀛樺湪
    from backend.agent.memory.global_memory import GlobalMemory
    GlobalMemory()  # 鍒濆鍖栭粯璁ゆ暟鎹?```

---

## 浜斻€侀獙璇?
```python
# tests/test_orchestrator.py
from backend.mcp.server import init_mcp_tools
from backend.agent.orchestrator import Orchestrator


def test_orchestrator_full_analysis():
    registry = init_mcp_tools()
    orch = Orchestrator(registry)
    result = orch.run_full_analysis()

    assert result["status"] == "completed"
    assert result["total_steps"] >= 6  # 鑷冲皯 6 姝?    assert "er_diagram" in result
    assert result["er_diagram"]["table_count"] > 0


def test_orchestrator_has_relations():
    registry = init_mcp_tools()
    orch = Orchestrator(registry)
    result = orch.run_full_analysis()

    merge = result.get("merge_result", {})
    assert merge["summary"]["high_confidence"] > 0  # 鑷冲皯鍙戠幇涓€浜涢珮缃俊搴﹀叧绯?

def test_router():
    from backend.agent.router import Router
    router = Router()
    plan = router.plan_analysis({
        "summary": {
            "total_tables": 30,
            "total_views": 3,
            "total_procedures": 8,
            "total_orm_files": 5,
        }
    })
    assert len(plan["phases"]) == 4
    assert plan["summary"]["tables"] == 30
```

杩愯锛?```bash
pytest tests/test_orchestrator.py -v
```

---

## 鍏€丄PI 绔偣锛堟湰妯″潡鐢熸晥鐨勶級

### `POST /api/analyze`

瑙﹀彂涓€娆″畬鏁寸殑 Schema 鍒嗘瀽銆?
```python
# 娣诲姞鍒?backend/main.py

@app.post("/api/analyze")
async def run_analysis():
    """
    瑙﹀彂涓€娆″畬鏁寸殑 Schema 閫嗗悜鍒嗘瀽銆?    杩斿洖瀹屾暣鐨勫垎鏋愮粨鏋滐紝鍖呮嫭锛欵R 鍥俱€佽瘉鎹摼銆佸悇 Worker 鏃ュ織銆?    """
    registry = app.state.tool_registry
    orch = Orchestrator(registry)
    result = orch.run_full_analysis()
    return result


@app.get("/api/analyze/{session_id}")
async def get_analysis(session_id: str):
    """
    鏌ヨ鏌愭鍒嗘瀽鐨勭粨鏋滐紙浠?Schema 璁板繂璇诲彇锛夈€?    娉ㄦ剰锛氬綋鍓嶇畝鍖栧疄鐜版槸姣忔閲嶆柊鍒嗘瀽銆?    濡傞渶瑕佺紦瀛橈紝浼氬皢鍒嗘瀽缁撴灉瀛樺叆 SQLite 骞跺湪姝ょ鐐硅繑鍥炪€?    """
    from backend.agent.memory.schema_memory import SchemaMemory
    memory = SchemaMemory()
    history = memory.get_history(limit=1)
    return {"history": history, "note": "Current implementation re-runs analysis each time"}
```

### `GET /api/memory/query`

鏌ヨ Schema 璁板繂涓殑鍘嗗彶鍏崇郴銆?
```python
@app.get("/api/memory/query")
async def query_memory(source_table: str = None, target_table: str = None):
    """鏌ヨ Schema 璁板繂涓瓨鍌ㄧ殑鍘嗗彶鍏崇郴"""
    from backend.agent.memory.schema_memory import SchemaMemory
    memory = SchemaMemory()
    relations = memory.query_similar_relations(source_table, target_table)
    history = memory.get_history(limit=10)
    return {"relations": relations, "history": history}
```

