import type { ChatEventPage, ChatMessage, ChatThreadResponse, QAOutput, StartedQARun } from "../types/api";

const THREAD_KEY = "schema-recovery.qa-thread-id";
const TERMINAL_EVENTS = new Set(["run.completed", "run.failed", "run.cancelled"]);

interface ChatState {
  threadId?: string;
  messages: ChatMessage[];
  loading: boolean;
  error?: string;
  activeRunId?: string;
  activity?: string;
  cursor: number;
  initialized: boolean;
}

let state: ChatState = {
  threadId: window.localStorage.getItem(THREAD_KEY) ?? undefined,
  messages: [],
  loading: false,
  initialized: false,
  cursor: 0
};
const listeners = new Set<() => void>();

function publish(patch: Partial<ChatState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener());
}

async function json<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) throw new Error(`chatRequestFailed: ${response.status}`);
  return (await response.json()) as T;
}

function mapThread(thread: ChatThreadResponse): ChatMessage[] {
  return thread.messages.map((message) => ({
    messageId: message.message_id,
    role: message.role,
    content: message.content,
    structured: message.structured,
    createdAt: message.created_at,
    type: message.role === "assistant" && (message.structured as QAOutput | undefined)?.clarification_question
      ? "clarification"
      : message.role === "assistant" ? "answer" : undefined
  }));
}

export const chatStore = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  snapshot() {
    return state;
  },
  async initialize() {
    if (state.initialized) return;
    publish({ initialized: true, loading: true, error: undefined });
    try {
      let threadId = state.threadId;
      if (threadId) {
        const response = await fetch(`/api/v2/threads/${threadId}`);
        if (response.ok) {
          const thread = (await response.json()) as ChatThreadResponse;
          publish({ messages: mapThread(thread), cursor: thread.last_sequence, loading: false });
          return;
        }
        window.localStorage.removeItem(THREAD_KEY);
        threadId = undefined;
      }
      const created = await json<ChatThreadResponse>("/api/v2/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "Schema Q&A" })
      });
      window.localStorage.setItem(THREAD_KEY, created.thread_id);
      publish({ threadId: created.thread_id, messages: [], loading: false });
    } catch (error) {
      publish({ initialized: false, loading: false, error: error instanceof Error ? error.message : "chatRequestFailed" });
    }
  },
  async send(content: string) {
    const trimmed = content.trim();
    if (!trimmed || state.loading) return;
    if (!state.threadId) await this.initialize();
    const threadId = state.threadId;
    if (!threadId) return;
    publish({
      loading: true,
      error: undefined,
      messages: [...state.messages, { role: "user", content: trimmed }]
    });
    try {
      const started = await json<StartedQARun>(`/api/v2/threads/${threadId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: trimmed, idempotency_key: crypto.randomUUID() })
      });
      publish({ activeRunId: started.run_id });
      await this.poll(threadId, started.run_id);
    } catch (error) {
      publish({ loading: false, activeRunId: undefined, error: error instanceof Error ? error.message : "chatRequestFailed" });
    }
  },
  async poll(threadId: string, runId: string) {
    let terminal = false;
    while (!terminal && state.activeRunId === runId) {
      const page = await json<ChatEventPage>(`/api/v2/threads/${threadId}/events?after_sequence=${state.cursor}`);
      const latest = [...page.events].reverse().find((event) => event.run_id === runId);
      publish({ cursor: page.next_sequence, activity: latest ? activityLabel(latest.event_type) : state.activity });
      terminal = page.events.some((event) => event.run_id === runId && TERMINAL_EVENTS.has(event.event_type));
      if (!terminal) await new Promise((resolve) => window.setTimeout(resolve, 500));
    }
    const thread = await json<ChatThreadResponse>(`/api/v2/threads/${threadId}`);
    publish({ messages: mapThread(thread), loading: false, activeRunId: undefined, activity: undefined });
  },
  async cancel() {
    if (!state.activeRunId) return;
    await json(`/api/v2/runs/${state.activeRunId}/cancel`, { method: "POST" });
  }
};

function activityLabel(eventType: string): string {
  if (eventType === "qa.plan.completed") return "正在规划查询";
  if (eventType === "qa.entity.resolved") return "正在解析实体";
  if (eventType.startsWith("tool.")) return "正在读取 Schema";
  if (eventType === "qa.facts.verified") return "正在验证事实";
  if (eventType === "qa.answer.verified") return "正在验证引用";
  return "Agent 正在处理";
}
