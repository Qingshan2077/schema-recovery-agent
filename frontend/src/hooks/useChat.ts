import { useCallback, useState } from "react";
import type { ChatMessage, ChatResponse } from "../types/api";

const CHAT_ERROR_KEY = "chatRequestFailed";

export function useChat() {
  const [threadId, setThreadId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingOperation, setPendingOperation] = useState<Record<string, unknown>>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const sendMessage = useCallback(
    async (content: string, options?: { confirmed?: boolean; pending?: Record<string, unknown> }) => {
      const trimmed = content.trim();
      if (!trimmed && !options?.confirmed) return;

      const userMessage: ChatMessage = { role: "user", content: trimmed || "confirm" };
      const history = messages.map(({ role, content }) => ({ role, content }));
      setMessages((current) => [...current, userMessage]);
      setLoading(true);
      setError(undefined);

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: trimmed || "confirm",
            thread_id: threadId,
            session_id: threadId,
            history,
            confirmed: Boolean(options?.confirmed),
            pending_operation: options?.pending
          })
        });
        if (!response.ok) throw new Error(`${CHAT_ERROR_KEY}: ${response.status}`);
        const data = (await response.json()) as ChatResponse;
        setThreadId(data.thread_id ?? data.session_id);
        const assistantMessage = toAssistantMessage(data);
        setMessages((current) => [...current, assistantMessage]);
        setPendingOperation(data.type === "confirmation" ? data.pending : undefined);
        return data;
      } catch (error) {
        const message = error instanceof Error ? error.message : CHAT_ERROR_KEY;
        setError(message);
        setMessages((current) => [...current, { role: "assistant", content: message, type: "error" }]);
      } finally {
        setLoading(false);
      }
    },
    [messages, threadId]
  );

  const confirmPending = useCallback(() => {
    if (!pendingOperation) return;
    return sendMessage("confirm", { confirmed: true, pending: pendingOperation });
  }, [pendingOperation, sendMessage]);

  const cancelPending = useCallback(() => {
    setPendingOperation(undefined);
  }, []);

  return { messages, pendingOperation, loading, error, sendMessage, confirmPending, cancelPending };
}

function toAssistantMessage(response: ChatResponse): ChatMessage {
  if (response.type === "answer") {
    return { role: "assistant", content: response.content, type: response.type };
  }
  if (response.type === "confirmation") {
    return {
      role: "assistant",
      content: response.message,
      type: response.type,
      pending: response.pending,
      safetyLevel: response.safety_level
    };
  }
  return {
    role: "assistant",
    content: response.message,
    type: response.type,
    ddlExecuted: response.ddl_executed,
    newAnalysis: response.new_analysis
  };
}
