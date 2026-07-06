import { Activity, BarChart3, GitBranch, Languages, Play, RefreshCw } from "lucide-react";
import { useI18n } from "../../i18n/LanguageContext";

type PageKey = "analysis" | "monitor" | "eval";

interface HeaderProps {
  activePage: PageKey;
  onPageChange: (page: PageKey) => void;
  onAnalyze: () => void;
  analyzing: boolean;
}

export function Header({ activePage, onPageChange, onAnalyze, analyzing }: HeaderProps) {
  const { t, toggleLanguage } = useI18n();
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
        <button className={activePage === "monitor" ? "active" : ""} type="button" onClick={() => onPageChange("monitor")}>
          <Activity size={16} />
          {t("navMonitor")}
        </button>
        <button className={activePage === "eval" ? "active" : ""} type="button" onClick={() => onPageChange("eval")}>
          <BarChart3 size={16} />
          {t("navEval")}
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
