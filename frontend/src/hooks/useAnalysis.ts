import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import type { AnalysisProgress, AnalysisResult, ConfidenceLevel, RelationDetail, StreamProgressEvent } from "../types/api";

interface UseAnalysisState {
  data?: AnalysisResult;
  loading: boolean;
  error?: string;
  progress?: AnalysisProgress;
}

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
      if (!response.ok) throw new Error(`分析请求失败: ${response.status}`);
      if (!response.body) {
        await runAnalysisFallback(setState);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalData: AnalysisResult | undefined;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line) as StreamProgressEvent;
          if (event.type === "error") throw new Error(event.error ?? "分析请求失败");
          finalData = applyStreamEvent(event, setState) ?? finalData;
        }
      }

      if (buffer.trim()) {
        const event = JSON.parse(buffer) as StreamProgressEvent;
        if (event.type === "error") throw new Error(event.error ?? "分析请求失败");
        finalData = applyStreamEvent(event, setState) ?? finalData;
      }

      if (!finalData) await runAnalysisFallback(setState);
    } catch (error) {
      setState({
        loading: false,
        error: error instanceof Error ? error.message : "分析请求失败"
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
      const nextSteps = [...previous.steps.filter((step) => step.worker !== event.step!.worker), event.step!].sort((a, b) => a.step - b.step);
      return {
        ...current,
        loading: true,
        progress: {
          sessionId: event.session_id ?? previous.sessionId,
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
    setState({ data: event.data, loading: false, progress: undefined });
    return event.data;
  }

  return undefined;
}

async function runAnalysisFallback(setState: Dispatch<SetStateAction<UseAnalysisState>>) {
  const response = await fetch("/api/analyze", { method: "POST" });
  if (!response.ok) throw new Error(`分析请求失败: ${response.status}`);
  const data = (await response.json()) as AnalysisResult;
  setState({ data, loading: false, progress: undefined });
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
