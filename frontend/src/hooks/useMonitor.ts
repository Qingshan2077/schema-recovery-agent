import { useCallback, useEffect, useState } from "react";
import type { MemoryQueryResult, MonitorStats } from "../types/api";

export function useMonitor() {
  const [stats, setStats] = useState<MonitorStats>();
  const [contributions, setContributions] = useState<Record<string, { avg_percentage: number; appearances: number }>>({});
  const [history, setHistory] = useState<MemoryQueryResult["history"]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [statsResponse, contributionsResponse, memoryResponse] = await Promise.all([
        fetch("/api/monitor/stats"),
        fetch("/api/monitor/contributions"),
        fetch("/api/memory/query")
      ]);
      if (!statsResponse.ok || !contributionsResponse.ok || !memoryResponse.ok) {
        throw new Error("监控数据请求失败");
      }
      setStats((await statsResponse.json()) as MonitorStats);
      setContributions(await contributionsResponse.json());
      const memory = (await memoryResponse.json()) as MemoryQueryResult;
      setHistory(memory.history ?? []);
    } catch (error) {
      setError(error instanceof Error ? error.message : "监控数据请求失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { stats, contributions, history, loading, error, refresh };
}
