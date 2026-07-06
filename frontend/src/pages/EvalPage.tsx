import { BarChart3, CheckCircle2, Gauge, RefreshCw, Target } from "lucide-react";
import { SourceContributionChart } from "../components/Dashboard/SourceContributionChart";
import { StatCard } from "../components/Dashboard/StatCard";
import { EmptyState } from "../components/common/EmptyState";
import { useEval } from "../hooks/useEval";

export function EvalPage() {
  const { report, loading, error, runEval } = useEval();
  const quantitative = report?.quantitative;

  return (
    <div className="page-stack">
      <div className="page-header-row">
        <div>
          <h2>评测报告</h2>
          <p>基于预标注关系集计算精确匹配、部分 FK 命中、目标表错误和置信度校准。</p>
        </div>
        <button className="primary-button" type="button" onClick={runEval} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
          {loading ? "评测中" : "运行评测"}
        </button>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      {!report ? (
        <EmptyState
          title="尚未运行评测"
          description="运行评测会触发一次端到端分析，并对照预期关系生成质量指标。"
          actionLabel="运行评测"
          onAction={runEval}
        />
      ) : (
        <>
          <section className="overview-grid">
            <StatCard title="Precision" value={formatScore(quantitative?.precision)} subtitle="精确关系查准率" icon={Target} color="green" />
            <StatCard title="Recall" value={formatScore(quantitative?.recall)} subtitle="精确关系查全率" icon={Gauge} color="blue" />
            <StatCard title="F1" value={formatScore(quantitative?.f1_score)} subtitle="综合指标" icon={BarChart3} color="yellow" />
            <StatCard title="High-P" value={formatScore(quantitative?.high_confidence_precision)} subtitle="高置信度校准" icon={CheckCircle2} color="slate" />
            <StatCard title="FK Recall" value={formatScore(quantitative?.partial_fk_recall)} subtitle="FK 部分命中" icon={Gauge} color="blue" />
          </section>

          <section className="dashboard-grid">
            <div className="panel">
              <h3>定量细节</h3>
              <div className="metric-list">
                {Object.entries(quantitative?.details ?? {}).map(([key, value]) => (
                  <div className="metric-row" key={key}>
                    <span>{formatMetricName(key)}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel">
              <h3>Monitor 摘要</h3>
              <SourceContributionChart data={report.monitor?.worker_stats ? {} : {}} />
              <div className="metric-list">
                <div className="metric-row">
                  <span>分析次数</span>
                  <strong>{report.monitor?.total_analyses ?? 0}</strong>
                </div>
                <div className="metric-row">
                  <span>平均耗时</span>
                  <strong>{report.monitor?.avg_duration_ms ?? 0} ms</strong>
                </div>
              </div>
            </div>
          </section>

          <section className="panel">
            <h3>LLM Judge</h3>
            <pre className="json-preview">{JSON.stringify(report.qualitative, null, 2)}</pre>
          </section>
        </>
      )}
    </div>
  );
}

function formatScore(value?: number): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-";
}

function formatMetricName(key: string): string {
  return key.replaceAll("_", " ");
}
