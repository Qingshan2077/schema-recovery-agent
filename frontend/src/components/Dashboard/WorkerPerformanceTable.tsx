import type { MonitorStats } from "../../types/api";

interface WorkerPerformanceTableProps {
  workers: NonNullable<MonitorStats["worker_stats"]>;
}

export function WorkerPerformanceTable({ workers }: WorkerPerformanceTableProps) {
  if (!workers.length) {
    return <div className="table-empty">暂无 Worker 运行数据</div>;
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Worker</th>
            <th>次数</th>
            <th>平均耗时</th>
            <th>成功率</th>
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
