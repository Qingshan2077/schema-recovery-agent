import { useEffect, useState } from "react";
import { api } from "../../app/api/client";
import { reduceEvents, selectRun, useRunStore } from "../../app/stores/runStore";
import type { DomainEvent } from "../../types/events";

interface Props { initialRunId?: string; onSelectRun?: (runId: string) => void; }

export function RunInspectorPage({ initialRunId, onSelectRun }: Props) {
  const [runId, setRunId] = useState(initialRunId ?? "");
  const [following, setFollowing] = useState(false);
  const [error, setError] = useState("");
  const state = useRunStore();

  const load = async (target = runId) => {
    if (!target) return;
    if (state.runId !== target) selectRun(target);
    try {
      const cursor = state.runId === target ? state.cursor : 0;
      const value = await api<{ events: DomainEvent[] }>(`/api/runs/${encodeURIComponent(target)}/events?after_sequence=${cursor}`);
      reduceEvents(value.events);
      setError("");
      onSelectRun?.(target);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "run events unavailable"); }
  };

  useEffect(() => { if (initialRunId) { setRunId(initialRunId); selectRun(initialRunId); void load(initialRunId); } }, [initialRunId]);
  useEffect(() => {
    if (!following || !runId) return;
    const timer = window.setInterval(() => { void load(runId); }, 1500);
    return () => window.clearInterval(timer);
  }, [following, runId, state.cursor]);

  return <section><div className="page-heading"><div><h2>Live Run Inspector</h2><p>按 run_id + sequence 续流；刷新和断线不会创建新分析。</p></div></div><div className="inline-form"><input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="run_id"/><button onClick={() => void load()}>Load</button><button onClick={() => setFollowing((value) => !value)}>{following ? "Stop following" : "Follow"}</button></div>{error && <div className="error-banner">{error}</div>}{state.gap && <div className="error-banner">Sequence gap: expected {state.gap.expected}, received {state.gap.received}. Cursor retained for safe reconnect.</div>}<div className="timeline">{state.events.map((event) => <article key={event.sequence}><strong>#{event.sequence} {event.type}</strong><span>{String(event.status ?? "")}</span><code>{String(event.trace_id ?? "")}</code><details><summary>Span / payload</summary><pre>{JSON.stringify(event, null, 2)}</pre></details></article>)}</div></section>;
}
