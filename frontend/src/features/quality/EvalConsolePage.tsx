import { useEffect, useState } from "react";
import { api } from "../../app/api/client";

interface Dataset { dataset_id: string; version: string; status?: string; }

export function EvalConsolePage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState("schema-agent-qa-core");
  const [version, setVersion] = useState("1.0.0");
  const [split, setSplit] = useState("dev");
  const [id, setId] = useState("");
  const [record, setRecord] = useState<any>();
  const [report, setReport] = useState<any>();
  const [error, setError] = useState("");
  useEffect(() => { void api<{ items: Dataset[] }>("/api/v2/evals/datasets").then((value) => setDatasets(value.items)).catch((reason) => setError(String(reason))); }, []);
  const start = async () => { try { const value = await api<any>("/api/v2/evals/runs", { method: "POST", body: JSON.stringify({ dataset_id: dataset, dataset_version: version, split, mode: "diagnostic", engine: "manual", gate_policy: "diagnostic-v1", case_ids: [] }) }); setId(value.eval_run_id); setRecord(value); setReport(undefined); setError(""); } catch (reason) { setError(String(reason)); } };
  const refresh = async () => { if (!id) return; try { const value = await api<any>(`/api/v2/evals/runs/${encodeURIComponent(id)}`); setRecord(value); if (["completed", "failed"].includes(value.status)) setReport(await api(`/api/v2/evals/runs/${encodeURIComponent(id)}/report`)); setError(""); } catch (reason) { setError(String(reason)); } };
  const metrics = report?.["metrics.json"] ?? {};
  const gate = report?.["gate-result.json"];
  return <section><div className="page-heading"><div><h2>Eval & Quality Console</h2><p>隔离 Fixture 执行、不可变报告和缺失门禁均显式展示。</p></div></div><div className="inline-form"><select value={`${dataset}:${version}`} onChange={(event) => { const [nextDataset, nextVersion] = event.target.value.split(":"); setDataset(nextDataset); setVersion(nextVersion); }}>{datasets.map((item) => <option key={`${item.dataset_id}:${item.version}`} value={`${item.dataset_id}:${item.version}`}>{item.dataset_id} · {item.version}</option>)}</select><select value={split} onChange={(event) => setSplit(event.target.value)}><option value="dev">dev</option><option value="public_test">public_test</option><option value="adversarial">adversarial</option></select><button onClick={() => void start()}>Start isolated eval</button></div><div className="inline-form"><input value={id} onChange={(event) => setId(event.target.value)} placeholder="eval_run_id"/><button onClick={() => void refresh()}>Refresh</button></div>{error && <div className="error-banner">{error}</div>}{record && <article className="detail-panel"><h3>{record.eval_run_id}</h3><p>{record.status} · {record.completed_cases}/{record.total_cases} · failed {record.failed_cases}</p></article>}{gate && <article className="detail-panel"><h3>Gate: {gate.status}</h3><p>未覆盖的 Schema/DBA 指标保持 missing，不会被 QA 结果伪装为通过。</p><ul>{gate.blocking_reasons?.map((reason: string) => <li key={reason}>{reason}</li>)}</ul><div className="metric-grid">{Object.entries(metrics).map(([name, value]) => <div key={name}><strong>{name}</strong><span>{String(value)}</span></div>)}</div></article>}</section>;
}
