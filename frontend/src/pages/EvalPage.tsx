import { BarChart3, CheckCircle2, Gauge, RefreshCw, Target } from "lucide-react";
import { SourceContributionChart } from "../components/Dashboard/SourceContributionChart";
import { StatCard } from "../components/Dashboard/StatCard";
import { EmptyState } from "../components/common/EmptyState";
import { useEval } from "../hooks/useEval";
import { useI18n } from "../i18n/LanguageContext";

export function EvalPage() {
  const { t } = useI18n();
  const { report, loading, error, runEval } = useEval();
  const quantitative = report?.quantitative;
  const displayError = translateKnownError(error, "evalRequestFailed", t("evalRequestFailed"));

  return (
    <div className="page-stack">
      <div className="page-header-row">
        <div>
          <h2>{t("evalTitle")}</h2>
          <p>{t("evalDescription")}</p>
        </div>
        <button className="primary-button" type="button" onClick={runEval} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
          {loading ? t("evaluating") : t("runEval")}
        </button>
      </div>

      {displayError ? <div className="error-banner">{displayError}</div> : null}

      {!report ? (
        <EmptyState
          title={t("noEvalTitle")}
          description={t("noEvalDescription")}
          actionLabel={t("runEval")}
          onAction={runEval}
        />
      ) : (
        <>
          <section className="overview-grid">
            <StatCard title="Precision" value={formatScore(quantitative?.precision)} subtitle={t("exactPrecision")} icon={Target} color="green" />
            <StatCard title="Recall" value={formatScore(quantitative?.recall)} subtitle={t("exactRecall")} icon={Gauge} color="blue" />
            <StatCard title="F1" value={formatScore(quantitative?.f1_score)} subtitle={t("f1Description")} icon={BarChart3} color="yellow" />
            <StatCard title="High-P" value={formatScore(quantitative?.high_confidence_precision)} subtitle={t("highConfidenceCalibration")} icon={CheckCircle2} color="slate" />
            <StatCard title="FK Recall" value={formatScore(quantitative?.partial_fk_recall)} subtitle={t("partialFkHit")} icon={Gauge} color="blue" />
          </section>

          <section className="dashboard-grid">
            <div className="panel">
              <h3>{t("quantitativeDetails")}</h3>
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
              <h3>{t("monitorSummary")}</h3>
              <SourceContributionChart data={report.monitor?.worker_stats ? {} : {}} />
              <div className="metric-list">
                <div className="metric-row">
                  <span>{t("analysisCount")}</span>
                  <strong>{report.monitor?.total_analyses ?? 0}</strong>
                </div>
                <div className="metric-row">
                  <span>{t("avgDuration")}</span>
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

function translateKnownError(error: string | undefined, source: string, target: string): string | undefined {
  return error?.replace(source, target);
}
