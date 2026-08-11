import { Activity, BarChart3, BrainCircuit, GitBranch, Languages, MessageSquareText, Play, RefreshCw } from "lucide-react";
import { useI18n } from "../../i18n/LanguageContext";

type PageKey = "analysis" | "chat" | "monitor" | "eval" | "memory";

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
