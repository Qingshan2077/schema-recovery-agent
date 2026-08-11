import { Activity, BarChart3, BrainCircuit, GitBranch, Languages, MessageSquareText, Play, RefreshCw, ShieldCheck, Route, FlaskConical } from "lucide-react";
import { useI18n } from "../../i18n/LanguageContext";

type PageKey = "analysis" | "chat" | "monitor" | "eval" | "memory" | "approvals" | "runs" | "evidence" | "quality";

interface HeaderProps {
  activePage: PageKey;
  onPageChange: (page: PageKey) => void;
  onAnalyze: () => void;
  analyzing: boolean;
}

export function Header({ activePage, onPageChange, onAnalyze, analyzing }: HeaderProps) {
  const { t, toggleLanguage, language } = useI18n();
  return (
    <header className="app-header">
      <div className="brand">
        <GitBranch size={24} />
        <div>
          <h1>Schema Recovery Agent</h1>
          <span>{t("appSubtitle")}</span>
        </div>
      </div>
      <nav className="top-nav" aria-label={t("mainNav")}>
        <button className={activePage === "analysis" ? "active" : ""} type="button" onClick={() => onPageChange("analysis")}>
          <GitBranch size={16} />
          {t("navAnalysis")}
        </button>
        <button className={activePage === "chat" ? "active" : ""} type="button" onClick={() => onPageChange("chat")}>
          <MessageSquareText size={16} />
          {t("navChat")}
        </button>
        <button className={activePage === "monitor" ? "active" : ""} type="button" onClick={() => onPageChange("monitor")}>
          <Activity size={16} />
          {t("navMonitor")}
        </button>
        <button className={activePage === "eval" ? "active" : ""} type="button" onClick={() => onPageChange("eval")}>
          <BarChart3 size={16} />
          {t("navEval")}
        </button>
        <button className={activePage === "memory" ? "active" : ""} type="button" onClick={() => onPageChange("memory")}>
          <BrainCircuit size={16} />
          {language === "zh" ? "\u8bb0\u5fc6" : "Memory"}
        </button>
        <button className={activePage === "approvals" ? "active" : ""} type="button" onClick={() => onPageChange("approvals")}><ShieldCheck size={16}/>{language === "zh" ? "\u5ba1\u6279" : "Approvals"}</button>
        <button className={activePage === "runs" ? "active" : ""} type="button" onClick={() => onPageChange("runs")}><Route size={16}/>{language === "zh" ? "\u8fd0\u884c" : "Runs"}</button>
        <button className={activePage === "evidence" ? "active" : ""} type="button" onClick={() => onPageChange("evidence")}><FlaskConical size={16}/>{language === "zh" ? "\u8bc1\u636e" : "Evidence"}</button>
        <button className={activePage === "quality" ? "active" : ""} type="button" onClick={() => onPageChange("quality")}><BarChart3 size={16}/>{language === "zh" ? "\u8d28\u91cf" : "Quality"}</button>
      </nav>
      <div className="header-actions">
        <button className="secondary-button" type="button" onClick={toggleLanguage}>
          <Languages size={16} />
          {t("languageToggle")}
        </button>
        <button className="primary-button" type="button" onClick={onAnalyze} disabled={analyzing}>
          {analyzing ? <RefreshCw className="spin" size={16} /> : <Play size={16} />}
          {analyzing ? t("analyzing") : t("analyze")}
        </button>
      </div>
    </header>
  );
}
