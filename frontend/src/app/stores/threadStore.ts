import { useSyncExternalStore } from "react";

export interface ThreadSnapshot { threadId: string | null; runId: string | null; artifacts: string[]; cursor: number; }
const STORAGE_KEY = "schema-agent-thread-store-v2";
function restore(): ThreadSnapshot {
  try { return { threadId: null, runId: null, artifacts: [], cursor: 0, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") }; }
  catch { return { threadId: null, runId: null, artifacts: [], cursor: 0 }; }
}
let snapshot = restore();
const listeners = new Set<() => void>();
export const threadStore = {
  get: () => snapshot,
  update: (patch: Partial<ThreadSnapshot>) => {
    snapshot = { ...snapshot, ...patch };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    listeners.forEach((listener) => listener());
  },
  clear: () => { snapshot = { threadId: null, runId: null, artifacts: [], cursor: 0 }; localStorage.removeItem(STORAGE_KEY); listeners.forEach((listener) => listener()); }
};
export function useThreadStore() { return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, threadStore.get); }
