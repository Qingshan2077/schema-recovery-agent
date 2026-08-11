import { useCallback, useEffect, useState } from "react";
import type { MemoryDetail, MemoryListResponse, MemorySummary } from "../types/memory";

export function useMemoryInspector(enabled: boolean) {
  const [items, setItems] = useState<MemorySummary[]>([]);
  const [selected, setSelected] = useState<MemoryDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/memory?limit=200", {
        headers: { "X-Trace-ID": `ui-${crypto.randomUUID()}` }
      });
      if (!response.ok) throw new Error(response.status === 404 ? "Memory Inspector is disabled" : `HTTP ${response.status}`);
      const payload = (await response.json()) as MemoryListResponse;
      setItems(payload.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Memory request failed");
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  const select = useCallback(async (memoryId: string) => {
    setError(null);
    try {
      const response = await fetch(`/api/memory/${encodeURIComponent(memoryId)}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setSelected((await response.json()) as MemoryDetail);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Memory detail request failed");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { items, selected, loading, error, refresh, select, close: () => setSelected(null) };
}
