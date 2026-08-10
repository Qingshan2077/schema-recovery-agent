import { Bot, DatabaseZap, Send, ShieldAlert, User, X } from "lucide-react";
import { FormEvent, useState } from "react";
import { useChat } from "../hooks/useChat";
import { useI18n } from "../i18n/LanguageContext";
import type { ChatMessage } from "../types/api";
import type { QAOutput } from "../types/api";
import { ArtifactRenderer, CitationList } from "../components/Chat/QAArtifacts";

export function ChatPage() {
  const { t } = useI18n();
  const { messages, loading, error, activeRunId, activity, sendMessage, cancelRun } = useChat();
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
            messages.map((message, index) => <ChatBubble message={message} onSelectEntity={(name, intent) => void sendMessage(buildClarificationReply(name, intent))} key={message.messageId ?? `${message.role}-${index}`} />)
          )}
        </div>

        {activeRunId ? <div className="chat-confirmation-bar"><div><strong>{activity ?? "Agent 正在处理"}</strong><span>{activeRunId}</span></div><button className="secondary-button" type="button" onClick={() => void cancelRun()}><X size={16} />{t("cancel")}</button></div> : null}

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

function ChatBubble({ message, onSelectEntity }: { message: ChatMessage; onSelectEntity: (name: string, intent: string) => void }) {
  const { t } = useI18n();
  const isUser = message.role === "user";
  const structured = message.structured as QAOutput | undefined;
  return (
    <article className={`chat-bubble ${isUser ? "chat-bubble-user" : "chat-bubble-assistant"}`}>
      <div className="chat-avatar">{isUser ? <User size={16} /> : message.type === "confirmation" ? <ShieldAlert size={16} /> : <Bot size={16} />}</div>
      <div className="chat-content">
        <pre>{message.content}</pre>
        {structured?.clarification_question ? <div className="qa-clarification"><ShieldAlert size={16} /><span>{structured.clarification_question}</span></div> : null}
        {structured?.entities?.flatMap((entity) => entity.candidates ?? []).length ? <div className="qa-entity-options">{structured.entities.flatMap((entity) => entity.candidates ?? []).map((candidate) => <button className="secondary-button" type="button" key={candidate.entity_id} onClick={() => onSelectEntity(candidate.name, structured.intent)}>{candidate.name}</button>)}</div> : null}
        {structured?.artifacts?.map((artifact) => <ArtifactRenderer artifact={artifact} key={artifact.artifact_id} />)}
        {structured?.citations ? <CitationList citations={structured.citations} /> : null}
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

function buildClarificationReply(table: string, intent: string): string {
  if (intent === "table_metadata") return `${table} 表的元数据是什么？`;
  if (intent === "indexes") return `${table} 表有哪些索引？`;
  if (intent === "relations" || intent === "evidence_explain") return `${table} 表有哪些关系证据？`;
  return `${table} 表有哪些字段？`;
}
