import { Database, FileCode2, GitMerge, Network, Workflow } from "lucide-react";
import type { SurveyOutput } from "../../types/api";

interface SidebarProps {
  survey?: SurveyOutput;
}

export function Sidebar({ survey }: SidebarProps) {
  const summary = survey?.summary;
  const items = [
    { label: "表", value: summary?.total_tables ?? "-", icon: Database },
    { label: "存储过程", value: summary?.total_procedures ?? "-", icon: Workflow },
    { label: "视图", value: summary?.total_views ?? "-", icon: Network },
    { label: "ORM", value: summary?.total_orm_files ?? "-", icon: FileCode2 }
  ];

  return (
    <aside className="sidebar">
      <section className="sidebar-section">
        <h2>数据库概况</h2>
        <p>{survey?.server_info?.database ?? "等待分析结果"}</p>
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
        <h2>分析链路</h2>
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

