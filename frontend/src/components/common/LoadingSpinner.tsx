import { Check, Clock, LoaderCircle, MinusCircle } from "lucide-react";
import { useI18n, type TranslationKey } from "../../i18n/LanguageContext";
import type { AnalysisProgress, AnalysisStep } from "../../types/api";

const pipeline: Array<{ worker: string; node: string; labelKey: TranslationKey }> = [
  { worker: "survey", node: "survey_node", labelKey: "scanDatabase" },
  { worker: "router", node: "router_node", labelKey: "buildPlan" },
  { worker: "column", node: "column_node", labelKey: "columnAnalysis" },
  { worker: "name", node: "name_node", labelKey: "nameAnalysis" },
  { worker: "code", node: "code_node", labelKey: "sqlCodeAnalysis" },
  { worker: "orm", node: "orm_node", labelKey: "ormAnalysis" },
  { worker: "merge", node: "merge_node", labelKey: "evidenceFusion" }
];

interface LoadingSpinnerProps {
  progress?: AnalysisProgress;
}

export function LoadingSpinner({ progress }: LoadingSpinnerProps) {
  const { t } = useI18n();
  const completed = progress?.completedSteps ?? 0;
  const total = progress?.totalSteps ?? pipeline.length;
  const percent = Math.min(100, Math.round((completed / Math.max(total, 1)) * 100));

  return (
    <div className="loading-panel">
      <LoaderCircle className="spin" size={30} />
      <h2>{t("scanningSchema")}</h2>
      <p>{progress?.sessionId ? t("session", { id: progress.sessionId }) : t("langGraphRunning")}</p>
      <div className="loading-steps">
        {pipeline.map((item) => {
          const step = progress?.steps.find((entry) => entry.worker === item.worker);
          const started = Boolean(progress?.startedNodes.includes(item.node));
          return <ProgressStep item={item} step={step} started={started} key={item.worker} />;
        })}
      </div>
      <div className="progress-track" aria-label={t("analysisProgress")}>
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
      <span className="progress-caption">{t("progressDone", { done: completed, total })}</span>
    </div>
  );
}

function ProgressStep({ item, step, started }: { item: { worker: string; labelKey: TranslationKey }; step?: AnalysisStep; started: boolean }) {
  const { t } = useI18n();
  const isSkipped = step?.status === "skipped";
  const isDone = Boolean(step) && !isSkipped;
  const statusClass = step ? `loading-step-${step.status}` : started ? "loading-step-running" : "";
  const toolCallCount = step?.tool_calls?.length ?? 0;
  return (
    <div className={`loading-step ${statusClass}`}>
      {isSkipped ? <MinusCircle size={16} /> : isDone ? <Check size={16} /> : started ? <LoaderCircle className="spin" size={16} /> : <Clock size={16} />}
      <span>{t(item.labelKey)}</span>
      {step ? <small>{step.status === "success" ? `${step.duration_ms} ms / ${toolCallCount} ${t("tools")}` : step.status}</small> : started ? <small>{t("running")}</small> : null}
    </div>
  );
}
