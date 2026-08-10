import { Activity, BarChart3, Clock, Database, RefreshCw } from "lucide-react";
import { SourceContributionChart } from "../components/Dashboard/SourceContributionChart";
import { StatCard } from "../components/Dashboard/StatCard";
import { WorkerPerformanceTable } from "../components/Dashboard/WorkerPerformanceTable";
import { EmptyState } from "../components/common/EmptyState";
import { useMonitor } from "../hooks/useMonitor";
import { useI18n } from "../i18n/LanguageContext";

export function MonitorPage() {
  const { t } = useI18n();
  const { stats, contributions, history, loading, error, refresh } = useMonitor();
  const displayError = translateKnownError(error, "monitorRequestFailed", t("monitorRequestFailed"));
  const workerStats = stats?.worker_stats ?? [];
  const avgSuccess = workerStats.length
    ? workerStats.reduce((sum, item) => sum + item.success_rate, 0) / workerStats.length
    : 0;

  return (
    <div className="page-stack">
      <div className="page-header-row">
        <div>
          <h2>{t("monitorTitle")}</h2>
          <p>{t("monitorDescription")}</p>
        </div>
        <button className="secondary-button" type="button" onClick={refresh} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
          {t("refresh")}
        </button>
      </div>

      {displayError ? <div className="error-banner">{displayError}</div> : null}
      {stats?.total_analyses === 0 ? (
        <EmptyState title={t("noMonitorTitle")} description={t("noMonitorDescription")} />
      ) : (
        <>
          <section className="overview-grid">
            <StatCard title={t("analysisCount")} value={stats?.total_analyses ?? 0} subtitle={t("historyRecords")} icon={Activity} color="blue" />
            <StatCard title={t("avgDuration")} value={`${stats?.avg_duration_ms ?? 0} ms`} subtitle={t("endToEndDuration")} icon={Clock} color="green" />
            <StatCard title={t("avgTables")} value={stats?.avg_tables_per_analysis ?? 0} subtitle={t("perAnalysis")} icon={Database} color="slate" />
            <StatCard title={t("avgSuccessRate")} value={`${avgSuccess.toFixed(1)}%`} subtitle={t("workerAverage")} icon={BarChart3} color="yellow" />
          </section>

          <section className="dashboard-grid">
            <div className="panel">
              <h3>{t("workerPerformance")}</h3>
              <WorkerPerformanceTable workers={workerStats} />
            </div>
            <div className="panel">
              <h3>{t("sourceContribution")}</h3>
              <SourceContributionChart data={contributions} />
            </div>
          </section>

          <section className="panel">
            <h3>{t("recentAnalyses")}</h3>
            <div className="history-list">
              {history.length ? (
                history.map((item) => (
                  <div className="history-item" key={`${item.session_id}-${item.id}`}>
                    <strong>{item.session_id}</strong>
                    <span>{item.date}</span>
                    <small>{t("relationSummary", { relations: item.relations, high: item.high_confidence })}</small>
                  </div>
                ))
              ) : (
                <div className="table-empty">{t("noHistory")}</div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function translateKnownError(error: string | undefined, source: string, target: string): string | undefined {
  return error?.replace(source, target);
}
