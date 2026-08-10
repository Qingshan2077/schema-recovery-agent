import { useI18n, type TranslationKey } from "../../i18n/LanguageContext";

interface SourceContributionChartProps {
  data: Record<string, { avg_percentage?: number; percentage?: number; appearances?: number; count?: number }>;
}

const labelKeys: Record<string, TranslationKey> = {
  column_name_suffix: "columnNameSuffix",
  primary_key_name_match: "primaryKeyMatch",
  naming_convention_match: "namingConvention",
  index_exists: "indexEvidence",
  naming_cross_table: "crossTableNaming"
};

const staticLabels: Record<string, string> = {
  sql_join: "SQL JOIN",
  orm_association: "ORM Association",
  orm_collection: "ORM Collection"
};

export function SourceContributionChart({ data }: SourceContributionChartProps) {
  const { t } = useI18n();
  const entries = Object.entries(data).map(([source, item]) => {
    const labelKey = labelKeys[source];
    return {
      source,
      label: labelKey ? t(labelKey) : staticLabels[source] ?? source,
      value: item.avg_percentage ?? item.percentage ?? 0,
      count: item.appearances ?? item.count ?? 0
    };
  });

  if (!entries.length) {
    return <div className="table-empty">{t("noContributionData")}</div>;
  }

  return (
    <div className="source-chart">
      {entries.map((entry) => (
        <div className="source-row" key={entry.source}>
          <div className="source-label">
            <span>{entry.label}</span>
            <small>{t("occurrenceCount", { count: entry.count })}</small>
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
