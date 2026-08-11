import { useEffect, useState } from "react";
import { api } from "../../app/api/client";

export function EvidenceWorkbenchPage() {
  const [relations, setRelations] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [error, setError] = useState("");
  const load = async () => { try { const value = await api<{ items: any[] }>("/api/evidence-ledger/relations?limit=200"); setRelations(value.items); if (selected) setSelected(value.items.find((item) => item.relation_id === selected.relation_id) ?? null); } catch (reason) { setError(String(reason)); } };
  useEffect(() => { void load(); }, []);
  const decide = async (action: "accept" | "reject" | "mark_stale") => {
    if (!selected) return;
    const requestId = crypto.randomUUID().replace(/-/g, "");
    try {
      const value = await api<any>(`/api/evidence-ledger/relations/${encodeURIComponent(selected.relation_id)}/feedback`, { method: "POST", body: JSON.stringify({ previous_version: selected.version, action, actor_id: "local-reviewer", actor_role: "schema_reviewer", reason: `Reviewed in Evidence Workbench: ${action}`, correction: {}, run_id: `run_${requestId}`, trace_id: `trc_${requestId}` }) });
      setSelected(value.relation); await load(); setError("");
    } catch (reason) { setError(String(reason)); await load(); }
  };
  return <section><div className="page-heading"><div><h2>Evidence Workbench</h2><p>关系版本、独立根事实、冲突和可校准融合贡献。</p></div></div>{error && <div className="error-banner">{error}</div>}<div className="workbench-split"><div className="entity-list">{relations.map((relation) => <button key={relation.relation_id} onClick={() => setSelected(relation)}><strong>{relation.source_table_id} → {relation.target_table_id}</strong><small>{relation.status} · {relation.confidence_band} · {(relation.calibrated_probability * 100).toFixed(1)}% · v{relation.version}</small></button>)}</div>{selected && <article className="detail-panel"><h3>{selected.claim_key}</h3><p>Raw {selected.raw_probability?.toFixed(3)} / calibrated {selected.calibrated_probability?.toFixed(3)}</p><p>Fusion {selected.fusion_version} · calibration {selected.calibration_version}</p><h4>Contribution waterfall</h4>{selected.contribution_breakdown?.map((item: any) => <div className="contribution-row" key={item.feature}><span>{item.feature}</span><meter min="-3" max="3" value={item.log_odds_delta}/><code>{item.log_odds_delta.toFixed(3)}</code></div>)}<h4>Validation flags</h4><ul>{selected.validation_flags?.map((flag: string) => <li key={flag}>{flag}</li>)}</ul><div className="decision-actions"><button onClick={() => void decide("accept")}>Accept</button><button onClick={() => void decide("reject")}>Reject</button><button onClick={() => void decide("mark_stale")}>Mark stale</button></div></article>}</div></section>;
}
