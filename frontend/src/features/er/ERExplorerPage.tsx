import { useEffect, useMemo, useState } from "react";
import { api } from "../../app/api/client";

interface RelationVersion { relation_id: string; version: number; source_table_id: string; target_table_id: string; source_column_ids: string[]; target_column_ids: string[]; status: string; confidence_band: string; calibrated_probability: number; evidence_ids: string[]; }
const LAYOUT_KEY = "schema-agent-er-layout-v2";

export function ERExplorerPage() {
  const [relations, setRelations] = useState<RelationVersion[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<RelationVersion | null>(null);
  const [versions, setVersions] = useState<RelationVersion[]>([]);
  const [compact, setCompact] = useState(() => localStorage.getItem(LAYOUT_KEY) === "compact");
  useEffect(() => { void api<{ items: RelationVersion[] }>("/api/evidence-ledger/relations?limit=500").then((value) => setRelations(value.items)); }, []);
  const visible = useMemo(() => relations.filter((item) => `${item.source_table_id} ${item.target_table_id} ${item.source_column_ids.join(" ")} ${item.target_column_ids.join(" ")}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())), [query, relations]);
  const tables = useMemo(() => Array.from(new Set(visible.flatMap((item) => [item.source_table_id, item.target_table_id]))).sort(), [visible]);
  const positions = useMemo(() => new Map<string, { x: number; y: number }>(tables.map((table, index): [string, { x: number; y: number }] => {
    const angle = (index / Math.max(1, tables.length)) * Math.PI * 2 - Math.PI / 2;
    return [table, { x: 400 + Math.cos(angle) * 300, y: 260 + Math.sin(angle) * 190 }];
  })), [tables]);
  const choose = async (item: RelationVersion) => {
    setSelected(item);
    try {
      const value = await api<{ items: RelationVersion[] }>(`/api/evidence-ledger/relations/${encodeURIComponent(item.relation_id)}/versions`);
      setVersions(value.items);
    } catch { setVersions([item]); }
  };
  const toggleLayout = () => { const next = !compact; setCompact(next); localStorage.setItem(LAYOUT_KEY, next ? "compact" : "comfortable"); };
  return <section><div className="page-heading"><div><h2>ER Explorer v2</h2><p>推断关系、人工状态、证据与版本差异使用稳定 relation_id 串联。</p></div><button onClick={toggleLayout}>{compact ? "Comfortable" : "Compact"}</button></div><div className="inline-form"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索表、字段或关系"/></div><div className="er-workspace"><svg className="er-canvas" viewBox="0 0 800 520" role="img" aria-label="Schema relation graph"><defs><marker id="er-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z"/></marker></defs>{visible.map((item) => { const source = positions.get(item.source_table_id); const target = positions.get(item.target_table_id); if (!source || !target) return null; return <g key={item.relation_id} className={`er-edge ${item.confidence_band}`} onClick={() => void choose(item)}><line x1={source.x} y1={source.y} x2={target.x} y2={target.y} markerEnd="url(#er-arrow)"/><title>{item.source_column_ids.join(", ")} → {item.target_column_ids.join(", ")} · {(item.calibrated_probability * 100).toFixed(1)}%</title></g>; })}{tables.map((table) => { const point = positions.get(table)!; return <g className="er-node" key={table} transform={`translate(${point.x - 70} ${point.y - 22})`}><rect width="140" height="44" rx="8"/><text x="70" y="27" textAnchor="middle">{table}</text></g>; })}</svg>{selected && <article className="detail-panel"><h3>{selected.source_table_id} → {selected.target_table_id}</h3><code>{selected.relation_id}</code><p>{selected.source_column_ids.join(", ")} → {selected.target_column_ids.join(", ")}</p><p>Evidence: {selected.evidence_ids.join(", ") || "none"}</p><h4>Version diff</h4>{versions.map((item) => <pre key={item.version}>v{item.version} · {item.status} · {item.calibrated_probability.toFixed(4)} · {item.evidence_ids.length} evidence</pre>)}</article>}</div><div className={compact ? "entity-list compact" : "entity-list"}>{visible.map((item) => <button key={`${item.relation_id}:${item.version}`} onClick={() => void choose(item)}><strong>{item.source_table_id} → {item.target_table_id}</strong><span>{item.source_column_ids.join(", ")} → {item.target_column_ids.join(", ")}</span><small>{item.status} · {item.confidence_band} · {(item.calibrated_probability * 100).toFixed(1)}% · v{item.version}</small></button>)}</div></section>;
}
