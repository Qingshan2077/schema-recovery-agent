import type { MonitorStats } from "../../types/api";
import { useI18n } from "../../i18n/LanguageContext";

interface WorkerPerformanceTableProps {
  workers: NonNullable<MonitorStats["worker_stats"]>;
}

export function WorkerPerformanceTable({ workers }: WorkerPerformanceTableProps) {
  const { t } = useI18n();
  if (!workers.length) {
    return <div className="table-empty">{t("noWorkerData")}</div>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Worker</th>
            <th>{t("runs")}</th>
            <th>{t("avgDuration")}</th>
            <th>{t("successRate")}</th>
          </tr>
        </thead>
        <tbody>
          {workers.map((worker) => (
            <tr key={worker.worker_id}>
              <td>{worker.worker_id}</td>
              <td>{worker.runs}</td>
              <td>{worker.avg_duration_ms} ms</td>
              <td>{worker.success_rate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
