import { useCallback, useState } from "react";
import type { EvalReport } from "../types/api";

export function useEval() {
  const [report, setReport] = useState<EvalReport>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const runEval = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch("/api/eval/report");
      if (!response.ok) throw new Error(`评测请求失败: ${response.status}`);
      setReport((await response.json()) as EvalReport);
    } catch (error) {
      setError(error instanceof Error ? error.message : "评测请求失败");
    } finally {
      setLoading(false);
    }
  }, []);

  return { report, loading, error, runEval };
}
