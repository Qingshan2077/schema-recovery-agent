import { useCallback, useMemo, useState } from "react";
import { Header } from "./components/Layout/Header";
import { Sidebar } from "./components/Layout/Sidebar";
import { useAnalysis } from "./hooks/useAnalysis";
import { I18nContext, type Language, type TranslationKey, translate } from "./i18n/LanguageContext";
import { AnalysisPage } from "./pages/AnalysisPage";
import { ChatPage } from "./pages/ChatPage";
import { EvalPage } from "./pages/EvalPage";
import { MonitorPage } from "./pages/MonitorPage";
import { MemoryInspectorPage } from "./pages/MemoryInspectorPage";
import type { SurveyOutput } from "./types/api";

export type PageKey = "analysis" | "chat" | "monitor" | "eval" | "memory";

function getInitialLanguage(): Language {
  const stored = localStorage.getItem("schema-agent-language");
  return stored === "en" || stored === "zh" ? stored : "zh";
}

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("analysis");
  const [language, setLanguage] = useState<Language>(getInitialLanguage);
  const analysis = useAnalysis();
  const survey = useMemo(
    () => analysis.data?.steps?.find((step) => step.worker === "survey")?.output as SurveyOutput | undefined,
    [analysis.data]
  );

  const handleLanguageChange = useCallback((nextLanguage: Language) => {
    setLanguage(nextLanguage);
    localStorage.setItem("schema-agent-language", nextLanguage);
  }, []);

  const i18n = useMemo(
    () => ({
      language,
      setLanguage: handleLanguageChange,
      toggleLanguage: () => handleLanguageChange(language === "zh" ? "en" : "zh"),
      t: (key: TranslationKey, values?: Record<string, string | number>) => translate(language, key, values)
    }),
    [handleLanguageChange, language]
  );

  return (
    <I18nContext.Provider value={i18n}>
      <div className="app-shell">
        <Header
          activePage={activePage}
          onPageChange={setActivePage}
          onAnalyze={analysis.runAnalysis}
          analyzing={analysis.loading}
        />
        <div className="app-body">
          <Sidebar survey={survey} />
          <main className="main-content">
            {activePage === "analysis" ? (
              <AnalysisPage
                data={analysis.data}
                loading={analysis.loading}
                error={analysis.error}
                progress={analysis.progress}
                relations={analysis.relations}
                filter={analysis.filter}
                onFilterChange={analysis.setFilter}
                onRunAnalysis={analysis.runAnalysis}
              />
            ) : null}
            {activePage === "chat" ? <ChatPage /> : null}
            {activePage === "monitor" ? <MonitorPage /> : null}
            {activePage === "eval" ? <EvalPage /> : null}
            {activePage === "memory" ? <MemoryInspectorPage /> : null}
          </main>
        </div>
      </div>
    </I18nContext.Provider>
  );
}
