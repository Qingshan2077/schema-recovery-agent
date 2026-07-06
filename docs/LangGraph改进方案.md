# LangGraph 鏀硅繘鏂规 鈥?Schema Recovery Agent

> 褰撳墠鍚庣鏄墜鍐欑紪鎺掑櫒锛圤rchestrator + Router锛夛紝鏈柟妗堟弿杩板浣曠敤 LangGraph 閲嶆瀯涓虹姸鎬佸浘锛圫tateGraph锛夋灦鏋勶紝浠ュ強鎵嬪啓鐗堜笌 LangGraph 鐗堢殑鍙栬垗绛栫暐銆?
---

## 涓€銆佷负浠€涔堢敤 LangGraph锛?
### 褰撳墠鎵嬪啓鐗堢殑闂

| 闂 | 鍏蜂綋琛ㄧ幇 | 闈㈣瘯瀹樺彲鑳借川鐤?|
|------|---------|--------------|
| 涓茶璋冨害鍐欐 | `_run_worker` 涓€涓竴涓皟锛岄『搴忕‖缂栫爜 | "濡傛灉浣犲姞涓€涓柊 Worker锛岃鏀?Orchestrator 鐨?run_full_analysis 鏂规硶鍚楋紵" |
| 鐘舵€佺鐞嗗師濮?| context dict 鍒板浼犻€掞紝绫诲瀷涓嶅畨鍏?| "context['code_result'] 鎷奸敊浜嗘€庝箞鍔烇紵" |
| 鏉′欢鍒嗘敮闈?if | `if orm_count > 0:` 鍐欏湪缂栨帓鍣ㄩ噷 | "鍒嗘敮閫昏緫鍜屾祦绋嬫帶鍒惰€﹀悎鍦ㄤ竴璧凤紝鍙鎬у樊" |
| 鏃犲師鐢熷苟琛?| Column 鍜?Name 铏界劧鍙互骞惰锛屼絾瀹為檯鏄覆琛岃皟鐢ㄧ殑 | "涓轰粈涔堜笉鍋氭垚鐪熸鐨勫苟琛岋紵" |
| 鏃犲彲瑙嗗寲 | 鏁翠釜娴佺▼璺戝畬鎵嶇煡閬撶粨鏋滐紝鏃犳硶鐪嬩腑闂寸姸鎬?| "鑳戒笉鑳藉湪鍒嗘瀽杩囩▼涓湅鍒拌繘搴︼紵" |

### LangGraph 瑙ｅ喅杩欎簺闂鐨勬柟妗?
| LangGraph 鏈哄埗 | 瑙ｅ喅浠€涔堥棶棰?| 闈㈣瘯浜偣 |
|---------------|------------|---------|
| `StateGraph` + `Node` | 鑺傜偣鐙珛锛屽姞 Worker = 鍔?Node锛屼笉鏀规祦绋嬩唬鐮?| "绗﹀悎寮€闂師鍒? |
| `TypedDict` State | 缂栬瘧鏃剁被鍨嬫鏌ワ紝涓嶄細鎷奸敊瀛楁鍚?| "宸ョ▼鍖栨剰璇? |
| `conditional_edge` | 鍒嗘敮閫昏緫浠庣紪鎺掑櫒鎶藉埌杈瑰畾涔夐噷 | "璺敱鍗冲浘缁撴瀯" |
| `Send` API + `fan-out` | 澶╃劧鏀寔骞惰鑺傜偣 | "灞曠ず浜嗕綘鎳傚苟琛屾墽琛? |
| LangGraph Studio / `get_graph()` | 娴佺▼鑷姩鍙鍖?| "闈㈣瘯鏃跺彲浠ョ洿鎺ョ敾鍥捐" |

---

## 浜屻€佹灦鏋勫姣?
### 鎵嬪啓鐗堬紙褰撳墠锛?
```
Orchestrator.run_full_analysis()
    鈫?Step 1: survey.run(context)          鈫?context["survey_result"] = ...
Step 2: router.plan_analysis(...)
Step 3: column.run(context)          鈫?context["column_result"] = ...
Step 4: name.run(context)            鈫?context["name_result"] = ...
Step 5: code.run(context)            鈫?context["code_result"] = ...
Step 6: if orm_count > 0: orm.run() 鈫?context["orm_result"] = ...
Step 7: merge.run(context)           鈫?context["merge_result"] = ...
    鈫?return result
```

### LangGraph 鐗堬紙鐩爣锛?
```
StateGraph(AgentState)
    鈹?    survey_node 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈻?鏇存柊 state.survey_result
    鈹?    鈹屸攢 fan-out 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?    鈻?                     鈻?column_node            name_node
(state.column_result)  (state.name_result)
    鈹?                     鈹?    鈹斺攢鈹€鈹€ sync 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?    鈹?    鈻?code_node 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈻?鏇存柊 state.code_result
    鈹?    鈹溾攢鈹€鈹€ orm_present? 鈹€鈹€鈻?yes 鈫?orm_node 鈫?merge_node
    鈹?                                       鈻?    鈹斺攢鈹€鈹€ orm_present? 鈹€鈹€鈻?no  鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?    鈹?merge_node 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈻?鏇存柊 state.merge_result
    鈹?    鈻?    END
```

---

## 涓夈€佹牳蹇冧唬鐮佽璁?
### 3.1 State 瀹氫箟

```python
# langgraph_state.py
from typing import TypedDict, Optional, Any
from datetime import datetime


class AgentState(TypedDict):
    """LangGraph 鍏变韩鐘舵€?鈥?鎵€鏈?Node 璇诲啓姝ょ姸鎬?""

    # 浼氳瘽淇℃伅
    session_id: str
    started_at: str
    status: str  # running / completed / error

    # Survey 杈撳嚭
    survey_result: Optional[dict]

    # 鍒嗘瀽 Worker 杈撳嚭
    column_result: Optional[dict]
    name_result: Optional[dict]
    code_result: Optional[dict]
    orm_result: Optional[dict]
    merge_result: Optional[dict]

    # 杩愯鏃朵俊鎭?    errors: list[str]
    worker_call_log: list[dict]  # {worker_id, duration_ms, tool_calls, status}
    current_step: int
    total_steps: int
```

### 3.2 Node 瀹氫箟

姣忎釜 Worker 瀵瑰簲涓€涓?Node锛屽嚱鏁扮鍚嶇粺涓€锛?
```python
# nodes/survey_node.py
from langgraph.types import Command
from backend.agent.workers.survey import SurveyWorker


def survey_node(state: AgentState, tool_registry) -> Command:
    """
    SurveyWorker 鑺傜偣 鈥?蹇呯粡鍏ュ彛鑺傜偣銆?    杈撳嚭: 鏇存柊 state.survey_result锛岀劧鍚?fan-out 鍒?column 鍜?name銆?    """
    worker = SurveyWorker(tool_registry)
    result = worker.run(state)

    if result["status"] == "error":
        return Command(
            update={
                "survey_result": result,
                "status": "error",
                "errors": state.get("errors", []) + [result["error"]],
                "current_step": 0,
            },
            goto="__end__"
        )

    return Command(
        update={
            "survey_result": result,
            "current_step": 1,
            "total_steps": 6,
        },
        goto=["column_node", "name_node"]  # 鈫?fan-out锛氬苟琛屽垎鍙?    )
```

```python
# nodes/column_node.py
def column_node(state: AgentState, tool_registry) -> Command:
    worker = ColumnWorker(tool_registry)
    result = worker.run(state)

    # 璁板綍宸ュ叿璋冪敤鏃ュ織
    call_log_entry = {
        "worker_id": "column",
        "tool_calls": worker.get_call_log(),
    }

    return Command(
        update={
            "column_result": result,
            "current_step": state.get("current_step", 0) + 1,
            "worker_call_log": state.get("worker_call_log", []) + [call_log_entry],
        },
        goto="sync_point"  # 鈫?鍚屾鐐圭瓑寰?name_node 瀹屾垚
    )
```

### 3.3 鍚屾鐐硅璁?
```python
# nodes/sync_point.py
def sync_point(state: AgentState) -> Command:
    """
    鍚屾鐐?鈥?绛夊緟 column 鍜?name 閮藉畬鎴愬悗鍐嶈繘鍏?code_node銆?    渚濊禆 LangGraph 鐨?fan-in 鏈哄埗锛堟墍鏈夊墠缃妭鐐瑰畬鎴愬悗瑙﹀彂锛夈€?    """
    # 涓や釜閮藉畬鎴愪簡鍚楋紵
    if state.get("column_result") and state.get("name_result"):
        return Command(goto="code_node")
    # 濡傛灉鍏朵腑涓€涓け璐ワ紝鐢ㄥ彟涓€涓户缁?    if state.get("column_result") or state.get("name_result"):
        return Command(goto="code_node")
    return Command(goto="__end__", update={"status": "error", "errors": ["鍒嗘瀽鑺傜偣鍧囧け璐?]})
```

### 3.4 鏉′欢杈?
```python
# edges/orm_condition.py
def should_run_orm(state: AgentState) -> str:
    """
    鏉′欢杈癸細鍒ゆ柇鏄惁闇€瑕佹墽琛?ORMWorker銆?    杩斿洖鐩爣鑺傜偣鍚嶇О銆?    """
    survey = state.get("survey_result", {})
    orm_count = survey.get("orm_files", {}).get("count", 0)
    if orm_count > 0:
        return "orm_node"
    return "merge_node_direct"  # 璺宠繃 orm_node锛岀洿鎺ヨ繘铻嶅悎
```

### 3.5 鍥炬瀯寤?
```python
# langgraph_builder.py
from langgraph.graph import StateGraph, END
from backend.langgraph_nodes.nodes import (
    survey_node, column_node, name_node,
    code_node, orm_node, merge_node, sync_point,
)


def build_schema_recovery_graph(tool_registry) -> StateGraph:
    """
    鏋勫缓瀹屾暣鐨?LangGraph 鐘舵€佸浘銆?    涓庢墜鍐?Orchestrator 鍔熻兘瀹屽叏绛変环銆?    """

    builder = StateGraph(AgentState)

    # 鈹€鈹€ 娉ㄥ唽鑺傜偣 鈹€鈹€
    builder.add_node("survey_node", lambda s: survey_node(s, tool_registry))
    builder.add_node("column_node", lambda s: column_node(s, tool_registry))
    builder.add_node("name_node", lambda s: name_node(s, tool_registry))
    builder.add_node("sync_point", lambda s: sync_point(s))  # 鍚屾鐐?    builder.add_node("code_node", lambda s: code_node(s, tool_registry))
    builder.add_node("orm_node", lambda s: orm_node(s, tool_registry))
    builder.add_node("merge_node", lambda s: merge_node(s, tool_registry))
    builder.add_node("merge_node_direct", lambda s: merge_node(s, tool_registry))

    # 鈹€鈹€ 瀹氫箟杈?鈹€鈹€
    builder.add_edge("survey_node", "sync_point")  # 闅愬惈 fan-out

    # fan-out: survey 鈫?column + name锛堜娇鐢?Send API 瀹炵幇鐪熸骞惰锛?    builder.add_conditional_edges(
        "survey_node",
        lambda s: [Send("column_node", s), Send("name_node", s)],
    )

    # fan-in: column 鈫?sync_point, name 鈫?sync_point
    builder.add_edge(["column_node", "name_node"], "sync_point")

    # sync_point 鈫?code
    builder.add_edge("sync_point", "code_node")

    # code 鈫?orm (鏉′欢)
    builder.add_conditional_edges(
        "code_node",
        should_run_orm,
        {
            "orm_node": "orm_node",
            "merge_node_direct": "merge_node_direct",
        }
    )

    # orm 鈫?merge
    builder.add_edge("orm_node", "merge_node")
    builder.add_edge("merge_node_direct", "merge_node")

    # merge 鈫?END
    builder.add_edge("merge_node", END)

    return builder.compile()
```

### 3.6 浣跨敤鏂瑰紡

```python
# 鏇挎崲褰撳墠鐨?orchestrator.run_full_analysis()

from backend.langgraph_builder import build_schema_recovery_graph

# 缂栬瘧鍥撅紙涓€娆＄紪璇戯紝澶氭杩愯锛?graph = build_schema_recovery_graph(tool_registry)

# 鎵ц鍒嗘瀽
initial_state = {
    "session_id": f"ana_{uuid.hex[:12]}",
    "started_at": datetime.now().isoformat(),
    "status": "running",
    "survey_result": None,
    "column_result": None,
    "name_result": None,
    "code_result": None,
    "orm_result": None,
    "merge_result": None,
    "errors": [],
    "worker_call_log": [],
    "current_step": 0,
    "total_steps": 6,
}

# 娴佸紡鎵ц锛堝彲瀹炴椂鑾峰彇涓棿鐘舵€侊級
for event in graph.stream(initial_state):
    # event 鍖呭惈姣忎竴姝ョ殑 state 蹇収
    # 鍙互鎺ㄩ€佺粰鍓嶇灞曠ず杩涘害
    print(event)  # 鈫?{"column_node": {"column_result": {...}}, ...}

# 鎴栬€呯洿鎺ユ墽琛?final_state = graph.invoke(initial_state)
```

---

## 鍥涖€佸叚澶ц€冪偣鍦?LangGraph 鐗堜腑鐨勪綋鐜?
| 鑰冪偣 | 鎵嬪啓鐗?| LangGraph 鐗?| 闈㈣瘯宸紓 |
|------|-------|-------------|---------|
| 鈶?鎰忓浘璇嗗埆 | NameWorker 鍐呴儴 | 鍚屼笂 + `should_run_orm` 浣滀负鍥剧骇鍒殑鏉′欢杈?| 澶氫簡涓€灞?鍥捐矾鐢辨剰鍥捐瘑鍒?鈥斺€斾笉鍙槸 Worker 鍐呴儴鍒嗙被锛屽浘鐨勬嫇鎵戠粨鏋勪篃鍦ㄥ仛璺敱鍐崇瓥 |
| 鈶?MCP 宸ュ叿璋冪敤 | ToolRegistry.execute | 鍚屼笂 | 涓嶅彉锛圡CP 灞備笉渚濊禆缂栨帓灞傦級 |
| 鈶?涓夌骇璁板繂 | MemoryManager | 鍙互鍦?Node 鐨?`update` 涓嚜鍔ㄥ仛璁板繂鎸佷箙鍖?| LangGraph 鐨?`Command.update` 澶╃劧閫傚悎鍋?鍐欒蹇?鐨勫壇浣滅敤 |
| 鈶?澶?Agent 璺敱 | Router.plan_analysis + Orchestrator 椤哄簭璋冪敤 | **StateGraph 鐨勮竟鏈韩灏辨槸璺敱** | 闈㈣瘯鏃跺彲浠ヤ寒鍑?`get_graph().draw_mermaid()` 鐢熸垚鐨勬祦绋嬪浘鈥斺€?璺敱閫昏緫灏辨槸鍥剧殑鎷撴墤缁撴瀯" |
| 鈶?Monitor 闂幆 | MonitorRecorder 鎵嬪姩璁板綍 | 鍙互鍦?`sync_point` 鎴栨瘡涓?Node 缁撴潫鏃惰嚜鍔ㄨ褰?| 鍒╃敤 LangGraph 鐨?`checkpoint` 鏈哄埗鍋氭洿缁嗙矑搴︾殑鐩戞帶 |
| 鈶?绔埌绔瘎娴?| 鐩存帴璋?API | 鐢?`graph.stream()` 鍙互閫愯妭鐐归獙璇?| "鍙互鐢?stream 妯″紡鍋氶€愯妭鐐规柇瑷€锛屽畾浣嶆洿绮剧‘" |

---

## 浜斻€侀潰璇曡瘽鏈?
### 闈㈣瘯瀹橀棶锛?涓轰粈涔堜粠鎵嬪啓鐗堟敼鍒?LangGraph锛?

> "鎵嬪啓鐗堟槸鎴戠殑绗竴鐗堚€斺€旂函 Python 缂栨帓锛屼笉渚濊禆浠讳綍妗嗘灦銆傜洰鐨勬槸楠岃瘉 Agent 鏋舵瀯鏈韩鏄惁鍚堢悊銆傜敓浜у寲鐨勬椂鍊欏彂鐜板嚑涓棶棰橈細
>
> **绗竴锛屽彲鎵╁睍鎬с€?* 鍔犱竴涓柊 Worker锛堟瘮濡傛湭鏉ュ姞涓€涓?APISchemaWorker 浠?Swagger 鏂囨。涓彁鍙栧叧绯伙級锛屾垜寰楁敼 Orchestrator 鐨?run_full_analysis 鏂规硶銆傚湪 LangGraph 閲岋紝鎴戝彧闇€瑕佸姞涓€涓?node 鍑芥暟鍜屼竴鏉?edge锛屽浘鐨勭紪璇戜細鑷姩澶勭悊銆傜鍚堝紑闂師鍒欍€?>
> **绗簩锛屽苟琛屾敮鎸併€?* ColumnWorker 鍜?NameWorker 娌℃湁鏁版嵁渚濊禆锛屼絾鎵嬪啓鐗堝彧鑳戒覆琛岃皟銆侺angGraph 鐨?Send API 澶╃劧鏀寔 fan-out 鈫?fan-in锛屽嚑琛屼唬鐮佸氨瀹炵幇浜嗙湡姝ｇ殑骞惰銆?>
> **绗笁锛屽彲瑙傛祴鎬с€?* LangGraph 鐨?stream 妯″紡鍙互閫愯妭鐐硅緭鍑轰腑闂寸姸鎬侊紝鍓嶇鍙互瀹炴椂鏄剧ず鍒嗘瀽杩涘害鈥斺€?姝ｅ湪鎵弿绗?15/30 寮犺〃' 杩欑浣撻獙锛屾墜鍐欑増闇€瑕侀澶栧姞寰堝鍥炶皟浠ｇ爜鎵嶈兘鍋氬埌銆?>
> 浣嗘垜鐨勬墜鍐欑増涔熶笉鏄櫧鍋氱殑銆傛墜鍐欑増璁╂垜鎯虫竻妤氫簡姣忎釜 Worker 鐨勮竟鐣屻€佽瘉鎹瀺鍚堢殑绛栫暐銆佺疆淇″害鐨勮绠椻€斺€旇繖浜涘浘鏃犲叧鐨勬牳蹇冮€昏緫鍦?LangGraph 鐗堥噷瀹屽叏澶嶇敤锛屽彧鏄紪鎺掑眰鎹簡銆傞潰璇曞畼鎯崇湅鐨勬槸鎴戝 Agent 鏋舵瀯鐨勭悊瑙ｏ紝涓嶆槸鎴戜細涓嶄細璋冩煇涓鏋剁殑 API銆?

### 闈㈣瘯瀹樿拷闂細"鎵嬪啓鐗堝拰 LangGraph 鐗堝摢涓洿濂斤紵"

> "娌℃湁缁濆鐨勬洿濂斤紝鐪嬮樁娈点€?>
> **鍘熷瀷闃舵锛氭墜鍐欑増鏇村ソ銆?* 闆朵緷璧栥€佸畬鍏ㄥ彲鎺с€佹帓闅滅洿瑙傘€傚鏋?Worker 杈圭晫杩樻病鎯虫竻妤氬氨涓?LangGraph锛屼綘浼氳姳寰堝鏃堕棿鍦ㄨ皟 graph 缂栬瘧閿欒涓婏紝鑰屼笉鏄紭鍖?Worker 閫昏緫銆?>
> **鐢熶骇鍖栭樁娈碉細LangGraph 鏇村ソ銆?* 褰?Worker 鏁伴噺鍒颁簡 10+锛屾潯浠跺垎鏀鏉備簡锛屾墜鍐欑紪鎺掑櫒鐨?run_full_analysis 浼氬彉鎴愭剰澶у埄闈㈡潯銆侺angGraph 鐨勫浘缁撴瀯銆乧heckpoint銆佹祦寮忚緭鍑恒€佸苟琛岃皟搴︹€斺€旇繖浜涙槸鎵嬪啓寰堥毦澶嶅埗鐨勫伐绋嬩紭鍔裤€?>
> 鎵€浠ユ垜鐨勬柟妗堟槸 **涓ょ増鍏卞瓨**锛氭墜鍐欑増浣滀负 fallback锛堜笉渚濊禆 LangGraph 渚濊禆锛夛紝LangGraph 鐗堜綔涓轰富杩愯鐗堟湰銆傚鏋滈潰璇曞畼鎯崇湅鏋舵瀯璁捐锛屾垜璁叉墜鍐欑増锛堝睍绀烘垜瀵?Agent 搴曞眰鐨勭悊瑙ｏ級锛涘鏋滄兂鐪嬪伐绋嬪寲鑳藉姏锛屾垜璁?LangGraph 鐗堬紙灞曠ず鎴戝鐜颁唬宸ュ叿閾剧殑鎺屾彙锛夈€?

### 闈㈣瘯瀹橀棶锛?LangGraph 鐨?StateGraph 璺熶綘浠暟鎹簱閫嗗悜鐨勫満鏅湁浠€涔堜笉鍖归厤鐨勫悧锛?

> "鏈変竴涓€侺angGraph 鐨?Node 鏄矖绮掑害鐨勨€斺€斾竴涓?Node 灏辨槸鏁翠釜 SurveyWorker锛岃€?SurveyWorker 鍐呴儴瑕佽皟 6 涓?MCP 宸ュ叿銆傚鏋滄垜鎯冲湪宸ュ叿璋冪敤绾у埆鍋氶噸璇曞拰闄嶇骇锛孡angGraph 鐨?Node 绮掑害澶矖浜嗐€?>
> 涓€涓敼杩涙柟鍚戞槸锛?*鎶?MCP 宸ュ叿璋冪敤涔熷仛鎴愬瓙鍥?*銆傛瘮濡?'鍒嗘瀽涓€寮犺〃' 浣滀负涓€涓瓙鍥撅紝鍖呭惈 check_columns 鈫?check_indexes 鈫?check_auto_increment 涓変釜瀛愯妭鐐癸紝濡傛灉 check_indexes 澶辫触锛屽瓙鍥惧彲浠ヨ嚜鍔ㄩ噸璇曟垨璺宠繃銆備絾杩欐牱鍥句細鍙樺緱闈炲父澶э紙30 寮犺〃 脳 姣忓紶琛?3 涓伐鍏?= 90 涓苟鍙戝瓙鑺傜偣锛夛紝闇€瑕佽€冭檻鎬ц兘銆?>
> 鐩墠鎴戠殑閫夋嫨鏄細**MCP 灞備繚鎸佹墜鍐欙紝LangGraph 鍙仛 Worker 绾у埆鐨勭紪鎺掋€?* 杩欐槸涓€涓姟瀹炵殑鎶樹腑鈥斺€擬CP 宸ュ叿鐨勫苟琛岀矑搴︿笉闇€瑕?LangGraph 绠＄悊锛孲QLite 杩炴帴姹犳湰韬氨澶勭悊浜嗗苟鍙戙€?

---

## 鍏€佹枃浠剁粨鏋勶紙鏂板鏂囦欢锛?
```
backend/
鈹溾攢鈹€ langgraph/                          鈫?鏂板锛歀angGraph 鐩稿叧浠ｇ爜
鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹溾攢鈹€ builder.py                      鈫?build_schema_recovery_graph()
鈹?  鈹溾攢鈹€ state.py                        鈫?AgentState TypedDict
鈹?  鈹溾攢鈹€ nodes/
鈹?  鈹?  鈹溾攢鈹€ __init__.py
鈹?  鈹?  鈹溾攢鈹€ survey_node.py
鈹?  鈹?  鈹溾攢鈹€ column_node.py
鈹?  鈹?  鈹溾攢鈹€ name_node.py
鈹?  鈹?  鈹溾攢鈹€ code_node.py
鈹?  鈹?  鈹溾攢鈹€ orm_node.py
鈹?  鈹?  鈹溾攢鈹€ merge_node.py
鈹?  鈹?  鈹斺攢鈹€ sync_point.py
鈹?  鈹斺攢鈹€ edges/
鈹?      鈹溾攢鈹€ __init__.py
鈹?      鈹斺攢鈹€ conditions.py               鈫?should_run_orm 绛夋潯浠跺嚱鏁?鈹溾攢鈹€ agent/
鈹?  鈹溾攢鈹€ orchestrator.py                 鈫?淇濈暀锛堟墜鍐欑増浣滀负 fallback锛?鈹?  鈹溾攢鈹€ router.py                       鈫?淇濈暀
鈹?  鈹斺攢鈹€ workers/                        鈫?鍏ㄩ儴淇濈暀锛圠angGraph node 澶嶇敤杩欎簺 Worker锛?鈹溾攢鈹€ mcp/                                鈫?涓嶅彉
鈹斺攢鈹€ ...
```

---

## 涓冦€佹敼鍔ㄩ噺璇勪及

| 妯″潡 | 鏀瑰姩鏂瑰紡 | 琛屾暟浼拌 |
|------|---------|---------|
| 鏂板 `backend/langgraph/` 鍏ㄥ | 鏂板 | ~300 琛?|
| `backend/agent/orchestrator.py` | 鍔犱竴琛?`import`锛堟柊澧?`run_langgraph()` 鏂规硶锛?| +10 琛?|
| `backend/agent/workers/base.py` | 涓嶅姩 | 0 琛?|
| `backend/agent/workers/*.py` | 涓嶅姩 | 0 琛?|
| `backend/mcp/*.py` | 涓嶅姩 | 0 琛?|
| `backend/monitor/recorder.py` | 鍦ㄦ柊鐗?Node 涓姞鑷姩璁板綍閫昏緫 | +30 琛?|
| `requirements.txt` | 鍔?`langgraph` 渚濊禆 | +1 琛?|

**鎬绘柊澧炵害 340 琛岋紝闆舵敼鍔ㄥ凡鏈?Worker 浠ｇ爜銆?* 杩欐槸鏈€閲嶈鐨勮璁℃寚鏍団€斺€擫angGraph 鐗堢殑 Worker 鍜屾墜鍐欑増鐨?Worker 鏄?*鍚屼竴浠戒唬鐮?*銆?
---

## 鍏€佷笌鍓嶇閰嶅悎

LangGraph 鐨?`stream()` 杈撳嚭鍙互鐩存帴鐢ㄦ潵椹卞姩鍓嶇鐨勫垎鏋愯繘搴﹀姩鐢汇€?
```python
# 鍚庣 API
@app.post("/api/analyze/stream")
async def analyze_stream():
    """娴佸紡鍒嗘瀽 鈥?瀹炴椂鎺ㄩ€佹瘡涓?Node 鐨勫畬鎴愮姸鎬佸埌鍓嶇"""
    graph = build_schema_recovery_graph(app.state.tool_registry)
    initial_state = {...}
    async for event in graph.astream(initial_state):
        yield {
            "type": "node_complete",
            "node": list(event.keys())[0],
            "data": list(event.values())[0],
        }
    yield {"type": "complete"}
```

鍓嶇鏀跺埌 `node_complete` 浜嬩欢鍚庯紝鏇存柊杩涘害鏉＄殑瀵瑰簲 Step 涓?鉁呫€傝繖灏辨槸闈㈣瘯瀹樻兂鐪嬪埌鐨?瀹炴椂鍒嗘瀽杩涘害"浣撻獙銆?
---

## 涔濄€佹€荤粨

| 缁村害 | 鎵嬪啓鐗?| LangGraph 鐗?|
|------|-------|-------------|
| 渚濊禆 | 鏃?| `langgraph` (8MB) |
| 骞惰 | 鎵嬪姩 threading | `Send` API 鍘熺敓 |
| 鍙娴嬫€?| 鎵嬪姩鏃ュ織 | `stream()` + `get_graph()` |
| 鍙墿灞?| 鏀?Orchestrator 鏂规硶 | 鍔?Node + 鍔?Edge |
| Worker 浠ｇ爜 | 瀹炵幇 | **澶嶇敤** 鈫?鍏抽敭 |
| 闈㈣瘯灞曠ず | 鏋舵瀯璁捐娣卞害 | 宸ョ▼鍖栧箍搴?|
| 鏈€浣崇瓥鐣?| **涓ょ増鍏卞瓨**锛岄潰璇曟椂鍚勮鍚勭殑浼樺娍 |

