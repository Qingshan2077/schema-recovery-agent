import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { AnalysisProgress, AnalysisResult, ConfidenceLevel, RelationDetail, StreamProgressEvent } from "../types/api";

interface UseAnalysisState {
  data?: AnalysisResult;
  loading: boolean;
  error?: string;
  progress?: AnalysisProgress;
}

interface RunRecordResponse {
  status: string;
  run_id?: string;
  run_status?: string;
  result?: AnalysisResult;
}

const ANALYSIS_ERROR_KEY = "analysisRequestFailed";

const initialProgress: AnalysisProgress = {
  totalSteps: 7,
  completedSteps: 0,
  startedNodes: [],
  steps: []
};

export function useAnalysis() {
  const [state, setState] = useState<UseAnalysisState>({ loading: false });
  const [filter, setFilter] = useState<ConfidenceLevel>("all");

  const runAnalysis = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: undefined, progress: initialProgress }));
    try {
      const response = await fetch("/api/analyze/stream", { method: "POST" });
      if (!response.ok) throw new Error(`${ANALYSIS_ERROR_KEY}: ${response.status}`);
      const headerRunId = response.headers.get("X-Run-ID") ?? undefined;
      if (!response.body) {
        if (!headerRunId) throw new Error(`${ANALYSIS_ERROR_KEY}: missing response stream`);
        const recovered = await fetchExistingRun(headerRunId);
        setState({ data: recovered, loading: false, progress: undefined });
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const seenSequences = new Set<number>();
      let buffer = "";
      let finalData: AnalysisResult | undefined;
      let runId = headerRunId;

      const consume = (line: string) => {
        if (!line.trim()) return;
        const event = JSON.parse(line) as StreamProgressEvent;
        runId = event.run_id ?? event.session_id ?? runId;
        if (event.sequence !== undefined) {
          if (seenSequences.has(event.sequence)) return;
          seenSequences.add(event.sequence);
        }
        if (event.type === "error") {
          throw new Error(`${event.error ?? ANALYSIS_ERROR_KEY}${runId ? ` [run_id=${runId}]` : ""}`);
        }
        finalData = applyStreamEvent(event, setState) ?? finalData;
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) consume(line);
      }
      if (buffer.trim()) consume(buffer);

      if (!finalData) {
        if (!runId) throw new Error(`${ANALYSIS_ERROR_KEY}: stream ended without run identity`);
        finalData = await fetchExistingRun(runId);
        setState({ data: finalData, loading: false, progress: undefined });
      }
    } catch (error) {
      setState({
        loading: false,
        error: error instanceof Error ? error.message : ANALYSIS_ERROR_KEY
      });
    }
  }, []);

  const relations = useMemo(() => flattenRelations(state.data), [state.data]);

  return {
    ...state,
    relations,
    filter,
    setFilter,
    runAnalysis
  };
}

function applyStreamEvent(
  event: StreamProgressEvent,
  setState: Dispatch<SetStateAction<UseAnalysisState>>
): AnalysisResult | undefined {
  if (event.type === "started") {
    setState((current) => ({
      ...current,
      loading: true,
      progress: {
        totalSteps: event.total_steps ?? 7,
        completedSteps: 0,
        sessionId: event.session_id,
        runId: event.run_id,
        traceId: event.trace_id,
        lastSequence: event.sequence,
        startedNodes: [],
        steps: []
      }
    }));
    return undefined;
  }

  if (event.type === "node_started" && event.node) {
    setState((current) => {
      const previous = current.progress ?? initialProgress;
      const started = new Set(previous.startedNodes);
      for (const node of event.node!.split(",")) started.add(node);
      return {
        ...current,
        loading: true,
        progress: {
          ...previous,
          sessionId: event.session_id ?? previous.sessionId,
          runId: event.run_id ?? previous.runId,
          traceId: event.trace_id ?? previous.traceId,
          lastSequence: event.sequence ?? previous.lastSequence,
          currentNode: event.node,
          startedNodes: Array.from(started)
        }
      };
    });
    return undefined;
  }

  if (event.type === "node_complete" && event.step) {
    setState((current) => {
      const previous = current.progress ?? initialProgress;
      const nextSteps = [...previous.steps.filter((step) => step.worker !== event.step!.worker), event.step!]
        .sort((left, right) => left.step - right.step);
      return {
        ...current,
        loading: true,
        progress: {
          sessionId: event.session_id ?? previous.sessionId,
          runId: event.run_id ?? previous.runId,
          traceId: event.trace_id ?? previous.traceId,
          lastSequence: event.sequence ?? previous.lastSequence,
          totalSteps: event.progress?.total ?? previous.totalSteps,
          completedSteps: event.progress?.completed ?? nextSteps.length,
          currentNode: event.node,
          startedNodes: previous.startedNodes,
          steps: nextSteps
        }
      };
    });
    return undefined;
  }

  if (event.type === "complete" && event.data) {
    const terminalError = ["failed", "blocked", "canceled", "expired"].includes(event.data.run_status)
      ? `${event.data.error ?? `analysis ${event.data.run_status}`} [run_id=${event.data.run_id}]`
      : undefined;
    setState({ data: event.data, loading: false, progress: undefined, error: terminalError });
    return event.data;
  }
  return undefined;
}

async function fetchExistingRun(runId: string): Promise<AnalysisResult> {
  const response = await fetch(`/api/v2/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new Error(`${ANALYSIS_ERROR_KEY}: unable to recover run ${runId}`);
  const record = (await response.json()) as RunRecordResponse;
  const result = record.result ?? (
    record.run_id && record.run_status
      ? record as unknown as AnalysisResult
      : undefined
  );
  if (result) {
    if (["failed", "blocked", "canceled", "expired"].includes(result.run_status)) {
      throw new Error(`${result.error ?? `analysis ${result.run_status}`} [run_id=${runId}]`);
    }
    return result;
  }
  throw new Error(`${ANALYSIS_ERROR_KEY}: run ${runId} is ${record.status}`);
}

function flattenRelations(data?: AnalysisResult): RelationDetail[] {
  const merge = data?.merge_result;
  if (!merge) return [];
  return [
    ...merge.high_confidence_relations,
    ...merge.medium_confidence_relations,
    ...merge.low_confidence_relations
  ];
}
