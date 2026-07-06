import { Check, Clock, LoaderCircle, MinusCircle } from "lucide-react";
import type { AnalysisProgress, AnalysisStep } from "../../types/api";

const pipeline = [
  { worker: "survey", node: "survey_node", label: "扫描数据库对象" },
  { worker: "router", node: "router_node", label: "生成执行计划" },
  { worker: "column", node: "column_node", label: "列级关系分析" },
  { worker: "name", node: "name_node", label: "命名规则分析" },
  { worker: "code", node: "code_node", label: "SQL 代码分析" },
  { worker: "orm", node: "orm_node", label: "ORM 配置分析" },
  { worker: "merge", node: "merge_node", label: "证据融合" }
];

interface LoadingSpinnerProps {
  progress?: AnalysisProgress;
}

export function LoadingSpinner({ progress }: LoadingSpinnerProps) {
  const completed = progress?.completedSteps ?? 0;
  const total = progress?.totalSteps ?? pipeline.length;
  const percent = Math.min(100, Math.round((completed / Math.max(total, 1)) * 100));

  return (
    <div className="loading-panel">
      <LoaderCircle className="spin" size={30} />
      <h2>正在分析数据库 Schema</h2>
      <p>{progress?.sessionId ? `会话 ${progress.sessionId}` : "LangGraph 正在编排 Worker 节点"}</p>
      <div className="loading-steps">
        {pipeline.map((item) => {
          const step = progress?.steps.find((entry) => entry.worker === item.worker);
          const started = Boolean(progress?.startedNodes.includes(item.node));
          return <ProgressStep item={item} step={step} started={started} key={item.worker} />;
        })}
      </div>
      <div className="progress-track" aria-label="分析进度">
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
      <span className="progress-caption">{completed}/{total} 个节点完成</span>
    </div>
  );
}

function ProgressStep({ item, step, started }: { item: { worker: string; label: string }; step?: AnalysisStep; started: boolean }) {
  const isSkipped = step?.status === "skipped";
  const isDone = Boolean(step) && !isSkipped;
  const statusClass = step ? `loading-step-${step.status}` : started ? "loading-step-running" : "";
  const toolCallCount = step?.tool_calls?.length ?? 0;
  return (
    <div className={`loading-step ${statusClass}`}>
      {isSkipped ? <MinusCircle size={16} /> : isDone ? <Check size={16} /> : started ? <LoaderCircle className="spin" size={16} /> : <Clock size={16} />}
      <span>{item.label}</span>
      {step ? <small>{step.status === "success" ? `${step.duration_ms} ms / ${toolCallCount} tools` : step.status}</small> : started ? <small>running</small> : null}
    </div>
  );
}
