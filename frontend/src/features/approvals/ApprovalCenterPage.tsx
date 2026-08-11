import { useEffect, useState } from "react";
import { api, ApiError } from "../../app/api/client";
import type { ApprovalOperation } from "../../types/approvals";

export function ApprovalCenterPage() {
  const [items, setItems] = useState<ApprovalOperation[]>([]); const [selected, setSelected] = useState<ApprovalOperation | null>(null); const [error, setError] = useState("");
  const load = async () => { try { const value = await api<{ items: ApprovalOperation[] }>("/api/v2/approvals"); setItems(value.items); } catch (reason) { setError(reason instanceof Error ? reason.message : "request failed"); } };
  useEffect(() => { void load(); }, []);
  const decide = async (decision: "approve" | "reject") => {
    if (!selected) return;
    try {
      const updated = await api<ApprovalOperation>(`/api/v2/approvals/${selected.operation_id}/resolve`, { method: "POST", body: JSON.stringify({ expected_version: selected.version, decision, reason: "Reviewed in Approval Center", acknowledged_hash: selected.normalized_sql_hash, request_id: crypto.randomUUID() }) });
      setSelected(updated); await load();
    } catch (reason) { setError(reason instanceof ApiError && reason.status === 409 ? "Operation changed. Refresh before deciding again." : String(reason)); await load(); }
  };
  return <section><div className="page-heading"><div><h2>Approval Center</h2><p>Server-owned immutable DDL plans and approval audit.</p></div></div>{error && <div className="error-banner">{error}</div>}<div className="workbench-split"><div className="entity-list">{items.map((item) => <button type="button" key={item.operation_id} onClick={() => setSelected(item)}><strong>{item.risk_level.toUpperCase()}</strong><span>{item.operation_id}</span><small>{item.environment} · {item.status} · expires {new Date(item.expires_at).toLocaleString()}</small></button>)}</div>{selected && <article className="detail-panel"><h3>{selected.operation_id}</h3><p>v{selected.version} · {selected.status} · {selected.risk_level}</p><code>{selected.normalized_sql_hash}</code><h4>Schema diff</h4><pre>{JSON.stringify(selected.diff, null, 2)}</pre><h4>Impact / dry-run</h4><pre>{JSON.stringify(selected.impact, null, 2)}</pre><h4>Normalized SQL</h4>{selected.normalized_sql.length ? selected.normalized_sql.map((sql) => <pre key={sql}>{sql}</pre>) : <p>Not authorized to view SQL.</p>}<div className="decision-actions"><button disabled={!selected.capabilities?.approve || selected.status !== "awaiting_approval"} onClick={() => void decide("approve")}>Approve</button><button disabled={!selected.capabilities?.approve || selected.status !== "awaiting_approval"} onClick={() => void decide("reject")}>Reject</button></div></article>}</div></section>;
}
