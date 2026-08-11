import { CheckCircle2, Clock3, Database, FileCode2, GitBranch, Network, Workflow } from "lucide-react";
import { useState } from "react";
import { ERCanvas } from "../components/ERDiagram/ERCanvas";
import { EvidenceSidebar } from "../components/EvidencePanel/EvidenceSidebar";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { StatCard } from "../components/Dashboard/StatCard";
import { useI18n } from "../i18n/LanguageContext";
import type { AnalysisProgress, AnalysisResult, AnalysisStep, ConfidenceLevel, RelationDetail, SurveyOutput } from "../types/api";

interface AnalysisPageProps {
  data?: AnalysisResult;
  loading: boolean;
  error?: string;
  progress?: AnalysisProgress;
  relations: RelationDetail[];
  filter: ConfidenceLevel;
  onFilterChange: (filter: ConfidenceLevel) => void;
  onRunAnalysis: () => void;
}

export function AnalysisPage({
  data,
  loading,
  error,
  progress,
  relations,
  filter,
  onFilterChange,
  onRunAnalysis
}: AnalysisPageProps) {
  const { t } = useI18n();
  const [selectedRelation, setSelectedRelation] = useState<RelationDetail>();
  const displayError = translateKnownError(error, "analysisRequestFailed", t("analysisRequestFailed"));
  const survey = data?.survey_result ?? (
    data?.steps?.find((step) => step.worker === "survey")?.output as SurveyOutput | undefined
  );
  const summary = survey?.summary;
  const mergeSummary = data?.merge_result?.summary;

  if (loading) return <LoadingSpinner progress={progress} />;

  if (!data) {
    return (
      <div className="page-stack">
        {displayError ? <div className="error-banner">{displayError}</div> : null}
        <EmptyState
          title={t("noDiagramTitle")}
          description={t("noDiagramDescription")}
          actionLabel={t("analyze")}
          onAction={onRunAnalysis}
        />
      </div>
    );
  }

  return (
    <div className="analysis-page">
      {displayError ? <div className="error-banner">{displayError}</div> : null}
      <section className="overview-grid">
        <StatCard title={t("table")} value={summary?.total_tables ?? "-"} subtitle={t("businessTables")} icon={Database} color="blue" />
        <StatCard title={t("storedProcedure")} value={summary?.total_procedures ?? "-"} subtitle={t("sqlEvidenceSource")} icon={Workflow} color="green" />
        <StatCard title={t("view")} value={summary?.total_views ?? "-"} subtitle={t("joinClues")} icon={Network} color="yellow" />
        <StatCard title={t("orm")} value={summary?.total_orm_files ?? "-"} subtitle={t("mybatisXml")} icon={FileCode2} color="slate" />
        <StatCard
          title={t("relations")}
          value={mergeSummary?.total_relations ?? 0}
          subtitle={t("highMediumLow", {
            high: mergeSummary?.high_confidence ?? 0,
            medium: mergeSummary?.medium_confidence ?? 0,
            low: mergeSummary?.low_confidence ?? 0
          })}
          icon={GitBranch}
          color="green"
        />
      </section>

      <PipelineTimeline steps={data.steps} engine={data.graph?.engine} fallbackReason={data.graph?.fallback_reason} />

      <ERCanvas
        diagram={data.er_diagram}
        relations={relations}
        filter={filter}
        selectedRelation={selectedRelation}
        onFilterChange={onFilterChange}
        onRelationSelect={setSelectedRelation}
      />
      <EvidenceSidebar relation={selectedRelation} onClose={() => setSelectedRelation(undefined)} />
    </div>
  );
}

function translateKnownError(error: string | undefined, source: string, target: string): string | undefined {
  return error?.replace(source, target);
}

function PipelineTimeline({ steps, engine, fallbackReason }: { steps: AnalysisStep[]; engine?: string; fallbackReason?: string }) {
  const { t } = useI18n();
  return (
    <section className="panel pipeline-panel">
      <div className="section-toolbar">
        <div>
          <h2>{t("executePipeline")}</h2>
          <p>{engine ? `engine: ${engine}` : t("workerTimeline")}</p>
        </div>
        {fallbackReason ? <span className="pipeline-warning">{t("fallback")}: {fallbackReason}</span> : null}
      </div>
      <div className="pipeline-timeline">
        {steps.map((step) => (
          <div className={`pipeline-step pipeline-step-${step.status}`} key={`${step.worker}-${step.step}`}>
            {["success", "completed"].includes(step.status) ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}
            <strong>{step.worker}</strong>
            <span>{step.status}</span>
            <small>{step.duration_ms} ms</small>
            <small>{step.tool_calls?.length ?? 0} {t("tools")}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

