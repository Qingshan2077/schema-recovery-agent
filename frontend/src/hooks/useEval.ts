import { useCallback, useState } from "react";
import type { EvalReport } from "../types/api";

const EVAL_ERROR_KEY = "evalRequestFailed";

export function useEval() {
  const [report, setReport] = useState<EvalReport>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const runEval = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch("/api/v2/evals/runs", { method: "POST" });
      if (!response.ok) throw new Error(`${EVAL_ERROR_KEY}: ${response.status}`);
      setReport((await response.json()) as EvalReport);
    } catch (error) {
      setError(error instanceof Error ? error.message : EVAL_ERROR_KEY);
    } finally {
      setLoading(false);
    }
  }, []);

  return { report, loading, error, runEval };
}
