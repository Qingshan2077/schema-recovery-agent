import { Bot, CheckCircle2, DatabaseZap, Send, ShieldAlert, User, X } from "lucide-react";
import { FormEvent, useState } from "react";
import { useChat } from "../hooks/useChat";
import { useI18n } from "../i18n/LanguageContext";
import type { ChatMessage } from "../types/api";

export function ChatPage() {
  const { t } = useI18n();
  const { messages, pendingOperation, loading, error, sendMessage, confirmPending, cancelPending } = useChat();
  const [draft, setDraft] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const next = draft.trim();
    if (!next || loading) return;
    setDraft("");
    void sendMessage(next);
  };

  return (
    <div className="page-stack chat-page">
      <div className="page-header-row">
        <div>
          <h2>{t("chatTitle")}</h2>
          <p>{t("chatDescription")}</p>
        </div>
      </div>

      {error ? <div className="error-banner">{translateKnownError(error, "chatRequestFailed", t("chatRequestFailed"))}</div> : null}

      <section className="chat-panel">
        <div className="chat-messages">
          {!messages.length ? (
            <div className="chat-empty">
              <Bot size={28} />
              <p>{t("assistantReady")}</p>
            </div>
          ) : (
            messages.map((message, index) => <ChatBubble message={message} key={`${message.role}-${index}`} />)
          )}
        </div>

        {pendingOperation ? (
          <div className="chat-confirmation-bar">
            <div>
              <strong>{t("confirmationRequired")}</strong>
              <span>{String(pendingOperation.sql_type ?? "").toUpperCase() === "DROP" ? t("safetyDangerous") : t("safetyConfirm")}</span>
            </div>
            <button className="primary-button" type="button" onClick={() => void confirmPending()} disabled={loading}>
              <CheckCircle2 size={16} />
              {t("confirmExecution")}
            </button>
            <button className="secondary-button" type="button" onClick={cancelPending} disabled={loading}>
              <X size={16} />
              {t("cancel")}
            </button>
          </div>
        ) : null}

        <form className="chat-input-row" onSubmit={handleSubmit}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t("chatPlaceholder")}
            rows={3}
          />
          <button className="primary-button" type="submit" disabled={loading || !draft.trim()}>
            <Send size={16} />
            {loading ? t("sending") : t("send")}
          </button>
        </form>
      </section>
    </div>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const { t } = useI18n();
  const isUser = message.role === "user";
  return (
    <article className={`chat-bubble ${isUser ? "chat-bubble-user" : "chat-bubble-assistant"}`}>
      <div className="chat-avatar">{isUser ? <User size={16} /> : message.type === "confirmation" ? <ShieldAlert size={16} /> : <Bot size={16} />}</div>
      <div className="chat-content">
        <pre>{message.content}</pre>
        {message.ddlExecuted ? (
          <div className="chat-ddl-result">
            <DatabaseZap size={16} />
            <span>{t("ddlExecuted")}: {message.ddlExecuted}</span>
          </div>
        ) : null}
        {message.newAnalysis ? <small>{t("newAnalysisReady")}</small> : null}
      </div>
    </article>
  );
}

function translateKnownError(error: string | undefined, source: string, target: string): string | undefined {
  return error?.replace(source, target);
}
