import { Database, FileCode2, GitMerge, Network, Workflow } from "lucide-react";
import { useI18n } from "../../i18n/LanguageContext";
import type { SurveyOutput } from "../../types/api";

interface SidebarProps {
  survey?: SurveyOutput;
}

export function Sidebar({ survey }: SidebarProps) {
  const { t } = useI18n();
  const summary = survey?.summary;
  const items = [
    { label: t("table"), value: summary?.total_tables ?? "-", icon: Database },
    { label: t("storedProcedure"), value: summary?.total_procedures ?? "-", icon: Workflow },
    { label: t("view"), value: summary?.total_views ?? "-", icon: Network },
    { label: t("orm"), value: summary?.total_orm_files ?? "-", icon: FileCode2 }
  ];

  return (
    <aside className="sidebar">
      <section className="sidebar-section">
        <h2>{t("databaseOverview")}</h2>
        <p>{survey?.server_info?.database ?? t("waitingAnalysis")}</p>
        <div className="sidebar-metrics">
          {items.map((item) => (
            <div className="sidebar-metric" key={item.label}>
              <item.icon size={16} />
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="sidebar-section">
        <h2>{t("analysisPipeline")}</h2>
        <ol className="pipeline-list">
          {["Survey", "Router", "Column", "Name", "Code", "ORM", "Merge"].map((step) => (
            <li key={step}>
              <GitMerge size={14} />
              {step}
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
