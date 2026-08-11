import { Database, RefreshCw, X } from "lucide-react";
import { useMemoryInspector } from "../hooks/useMemoryInspector";
import { useI18n } from "../i18n/LanguageContext";

export function MemoryInspectorPage() {
  const { language } = useI18n();
  const memory = useMemoryInspector(true);
  const zh = language === "zh";
  return (
    <section className="memory-inspector">
      <div className="page-heading">
        <div>
          <h2>{zh ? "记忆检查器" : "Memory Inspector"}</h2>
          <p>{zh ? "追溯 L2/L3 记忆版本、证据引用、校准概率与生命周期。" : "Inspect L2/L3 versions, evidence lineage, calibrated confidence, and lifecycle."}</p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void memory.refresh()} disabled={memory.loading}>
          <RefreshCw className={memory.loading ? "spin" : ""} size={16} />
          {zh ? "刷新" : "Refresh"}
        </button>
      </div>
      {memory.error ? <div className="error-banner">{memory.error}</div> : null}
      <div className="memory-grid">
        {memory.items.map((item) => (
          <button className="memory-card" key={item.memory_id} type="button" onClick={() => void memory.select(item.memory_id)}>
            <Database size={18} />
            <span className="memory-card-main">
              <strong>{item.memory_id}</strong>
              <small>{item.layer.toUpperCase()} · v{item.current_version} · {item.status}</small>
            </span>
          </button>
        ))}
        {!memory.loading && memory.items.length === 0 && !memory.error ? (
          <div className="empty-panel">{zh ? "当前命名空间暂无可见记忆。" : "No memory is visible in the active namespace."}</div>
        ) : null}
      </div>
      {memory.selected ? (
        <aside className="memory-drawer" aria-label={zh ? "记忆详情" : "Memory detail"}>
          <button className="icon-button" type="button" onClick={memory.close} aria-label={zh ? "关闭" : "Close"}><X size={18} /></button>
          <h3>{memory.selected.memory_id}</h3>
          <div className="memory-meta">
            <span>v{memory.selected.version}</span>
            <span>{String(memory.selected.status ?? memory.selected.lifecycle ?? "unknown")}</span>
            {typeof memory.selected.calibrated_probability === "number" ? <span>{(memory.selected.calibrated_probability * 100).toFixed(1)}%</span> : null}
          </div>
          <p>{String(memory.selected.summary ?? memory.selected.rule_summary ?? "")}</p>
          <h4>{zh ? "证据引用" : "Evidence references"}</h4>
          <ul>{(memory.selected.evidence_ids ?? []).map((id) => <li key={id}>{id}</li>)}</ul>
          <h4>{zh ? "根事实" : "Root facts"}</h4>
          <ul>{(memory.selected.root_fact_ids ?? []).map((id) => <li key={id}>{id}</li>)}</ul>
          {memory.selected.calibration_version ? <p><small>Calibration: {memory.selected.calibration_version}</small></p> : null}
        </aside>
      ) : null}
    </section>
  );
}
