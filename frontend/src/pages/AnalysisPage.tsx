import { CheckCircle2, Clock3, Database, FileCode2, GitBranch, Network, Workflow } from "lucide-react";
import { useState } from "react";
import { ERCanvas } from "../components/ERDiagram/ERCanvas";
import { EvidenceSidebar } from "../components/EvidencePanel/EvidenceSidebar";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSpinner } from "../components/common/LoadingSpinner";
import { StatCard } from "../components/Dashboard/StatCard";
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
  const [selectedRelation, setSelectedRelation] = useState<RelationDetail>();
  const survey = data?.steps?.find((step) => step.worker === "survey")?.output as SurveyOutput | undefined;
  const summary = survey?.summary;
  const mergeSummary = data?.merge_result?.summary;

  if (loading) return <LoadingSpinner progress={progress} />;

  if (!data) {
    return (
      <div className="page-stack">
        {error ? <div className="error-banner">{error}</div> : null}
        <EmptyState
          title="尚未生成 ER 图"
          description="触发一次 Schema 分析后，这里会展示表关系图、置信度分布和证据链。"
          actionLabel="开始分析"
          onAction={onRunAnalysis}
        />
      </div>
    );
  }

  return (
    <div className="analysis-page">
      {error ? <div className="error-banner">{error}</div> : null}
      <section className="overview-grid">
        <StatCard title="表" value={summary?.total_tables ?? "-"} subtitle="业务表数量" icon={Database} color="blue" />
        <StatCard title="存储过程" value={summary?.total_procedures ?? "-"} subtitle="SQL 证据来源" icon={Workflow} color="green" />
        <StatCard title="视图" value={summary?.total_views ?? "-"} subtitle="JOIN 线索" icon={Network} color="yellow" />
        <StatCard title="ORM" value={summary?.total_orm_files ?? "-"} subtitle="MyBatis XML" icon={FileCode2} color="slate" />
        <StatCard
          title="关系"
          value={mergeSummary?.total_relations ?? 0}
          subtitle={`高 ${mergeSummary?.high_confidence ?? 0} / 中 ${mergeSummary?.medium_confidence ?? 0} / 低 ${mergeSummary?.low_confidence ?? 0}`}
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

function PipelineTimeline({ steps, engine, fallbackReason }: { steps: AnalysisStep[]; engine?: string; fallbackReason?: string }) {
  return (
    <section className="panel pipeline-panel">
      <div className="section-toolbar">
        <div>
          <h2>执行链路</h2>
          <p>{engine ? `engine: ${engine}` : "worker execution timeline"}</p>
        </div>
        {fallbackReason ? <span className="pipeline-warning">fallback: {fallbackReason}</span> : null}
      </div>
      <div className="pipeline-timeline">
        {steps.map((step) => (
          <div className={`pipeline-step pipeline-step-${step.status}`} key={`${step.worker}-${step.step}`}>
            {step.status === "success" ? <CheckCircle2 size={16} /> : <Clock3 size={16} />}
            <strong>{step.worker}</strong>
            <span>{step.status}</span>
            <small>{step.duration_ms} ms</small>
            <small>{step.tool_calls?.length ?? 0} tools</small>
          </div>
        ))}
      </div>
    </section>
  );
}


