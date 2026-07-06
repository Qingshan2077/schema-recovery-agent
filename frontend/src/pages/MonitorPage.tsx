import { Activity, BarChart3, Clock, Database, RefreshCw } from "lucide-react";
import { SourceContributionChart } from "../components/Dashboard/SourceContributionChart";
import { StatCard } from "../components/Dashboard/StatCard";
import { WorkerPerformanceTable } from "../components/Dashboard/WorkerPerformanceTable";
import { EmptyState } from "../components/common/EmptyState";
import { useMonitor } from "../hooks/useMonitor";

export function MonitorPage() {
  const { stats, contributions, history, loading, error, refresh } = useMonitor();
  const workerStats = stats?.worker_stats ?? [];
  const avgSuccess = workerStats.length
    ? workerStats.reduce((sum, item) => sum + item.success_rate, 0) / workerStats.length
    : 0;

  return (
    <div className="page-stack">
      <div className="page-header-row">
        <div>
          <h2>监控面板</h2>
          <p>分析链路耗时、Worker 成功率和证据来源贡献。</p>
        </div>
        <button className="secondary-button" type="button" onClick={refresh} disabled={loading}>
          <RefreshCw className={loading ? "spin" : ""} size={16} />
          刷新
        </button>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}
      {stats?.total_analyses === 0 ? (
        <EmptyState title="暂无监控记录" description="完成一次分析后，监控数据会自动写入并展示在这里。" />
      ) : (
        <>
          <section className="overview-grid">
            <StatCard title="分析次数" value={stats?.total_analyses ?? 0} subtitle="历史记录" icon={Activity} color="blue" />
            <StatCard title="平均耗时" value={`${stats?.avg_duration_ms ?? 0} ms`} subtitle="端到端耗时" icon={Clock} color="green" />
            <StatCard title="平均表数" value={stats?.avg_tables_per_analysis ?? 0} subtitle="每次分析" icon={Database} color="slate" />
            <StatCard title="平均成功率" value={`${avgSuccess.toFixed(1)}%`} subtitle="Worker 均值" icon={BarChart3} color="yellow" />
          </section>

          <section className="dashboard-grid">
            <div className="panel">
              <h3>Worker 性能</h3>
              <WorkerPerformanceTable workers={workerStats} />
            </div>
            <div className="panel">
              <h3>证据源贡献率</h3>
              <SourceContributionChart data={contributions} />
            </div>
          </section>

          <section className="panel">
            <h3>最近分析记录</h3>
            <div className="history-list">
              {history.length ? (
                history.map((item) => (
                  <div className="history-item" key={`${item.session_id}-${item.id}`}>
                    <strong>{item.session_id}</strong>
                    <span>{item.date}</span>
                    <small>{item.relations} 条关系，{item.high_confidence} 条高置信度</small>
                  </div>
                ))
              ) : (
                <div className="table-empty">暂无历史记录</div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
