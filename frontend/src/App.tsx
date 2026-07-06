import { useCallback, useMemo, useState } from "react";
import { Header } from "./components/Layout/Header";
import { Sidebar } from "./components/Layout/Sidebar";
import { useAnalysis } from "./hooks/useAnalysis";
import { I18nContext, type Language, translate } from "./i18n/LanguageContext";
import { AnalysisPage } from "./pages/AnalysisPage";
import { EvalPage } from "./pages/EvalPage";
import { MonitorPage } from "./pages/MonitorPage";
import type { SurveyOutput } from "./types/api";

type PageKey = "analysis" | "monitor" | "eval";

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("analysis");
  const [language, setLanguage] = useState<Language>(() => (localStorage.getItem("schema-agent-language") as Language) || "zh");
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
      t: (key: Parameters<typeof translate>[1], values?: Record<string, string | number>) => translate(language, key, values)
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
            {activePage === "monitor" ? <MonitorPage /> : null}
            {activePage === "eval" ? <EvalPage /> : null}
          </main>
        </div>
      </div>
    </I18nContext.Provider>
  );
}
