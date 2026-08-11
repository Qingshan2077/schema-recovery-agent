import { useSyncExternalStore } from "react";
import type { DomainEvent, EventState } from "../../types/events";

interface RunEventState extends EventState { runId: string | null; }
const STORAGE_PREFIX = "schema-agent-run-events-v2:";
let state: RunEventState = { runId: null, cursor: 0, gap: null, events: [] };
const listeners = new Set<() => void>();

export function reduceEvents(incoming: DomainEvent[]) {
  const known = new Set(state.events.map((event) => event.sequence));
  let gap = state.gap;
  const ordered = [...incoming].sort((a, b) => a.sequence - b.sequence);
  for (const event of ordered) {
    if (known.has(event.sequence)) continue;
    if (event.sequence > state.cursor + 1) gap = { expected: state.cursor + 1, received: event.sequence };
    state = { ...state, cursor: Math.max(state.cursor, event.sequence), events: [...state.events, event], gap };
    known.add(event.sequence);
  }
  persistRunEvents();
  listeners.forEach((listener) => listener());
}

export function selectRun(runId: string) {
  if (state.runId === runId) return;
  try {
    const restored = JSON.parse(sessionStorage.getItem(STORAGE_PREFIX + runId) ?? "null");
    state = restored ? { runId, cursor: restored.cursor ?? 0, gap: restored.gap ?? null, events: restored.events ?? [] } : { runId, cursor: 0, gap: null, events: [] };
  } catch { state = { runId, cursor: 0, gap: null, events: [] }; }
  listeners.forEach((listener) => listener());
}

export function persistRunEvents() {
  if (state.runId) sessionStorage.setItem(STORAGE_PREFIX + state.runId, JSON.stringify(state));
}

export function useRunStore() { return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, () => state); }
