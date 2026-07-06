interface SourceContributionChartProps {
  data: Record<string, { avg_percentage?: number; percentage?: number; appearances?: number; count?: number }>;
}

const labels: Record<string, string> = {
  sql_join: "SQL JOIN",
  orm_association: "ORM Association",
  orm_collection: "ORM Collection",
  column_name_suffix: "列名后缀",
  primary_key_name_match: "主键匹配",
  naming_convention_match: "命名约定",
  index_exists: "索引证据",
  naming_cross_table: "跨表命名"
};

export function SourceContributionChart({ data }: SourceContributionChartProps) {
  const entries = Object.entries(data).map(([source, item]) => ({
    source,
    label: labels[source] ?? source,
    value: item.avg_percentage ?? item.percentage ?? 0,
    count: item.appearances ?? item.count ?? 0
  }));

  if (!entries.length) {
    return <div className="table-empty">暂无证据贡献数据</div>;
  }

  return (
    <div className="source-chart">
      {entries.map((entry) => (
        <div className="source-row" key={entry.source}>
          <div className="source-label">
            <span>{entry.label}</span>
            <small>{entry.count} 次</small>
          </div>
          <div className="source-bar-track">
            <div className={`source-bar source-${entry.source}`} style={{ width: `${Math.max(4, entry.value)}%` }} />
          </div>
          <strong>{entry.value.toFixed(1)}%</strong>
        </div>
      ))}
    </div>
  );
}
