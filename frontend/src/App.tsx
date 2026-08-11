import { useCallback, useEffect, useMemo, useState } from "react";
import { Header } from "./components/Layout/Header";
import { Sidebar } from "./components/Layout/Sidebar";
import { useAnalysis } from "./hooks/useAnalysis";
import { I18nContext, type Language, type TranslationKey, translate } from "./i18n/LanguageContext";
import { AnalysisPage } from "./pages/AnalysisPage";
import { ChatPage } from "./pages/ChatPage";
import { MonitorPage } from "./pages/MonitorPage";
import { MemoryInspectorPage } from "./pages/MemoryInspectorPage";
import { ApprovalCenterPage } from "./features/approvals/ApprovalCenterPage";
import { RunInspectorPage } from "./features/runs/RunInspectorPage";
import { EvidenceWorkbenchPage } from "./features/evidence/EvidenceWorkbenchPage";
import { EvalConsolePage } from "./features/quality/EvalConsolePage";
import { ERExplorerPage } from "./features/er/ERExplorerPage";
import { useAppRouter, type PageKey } from "./app/router";
import { loadFeatures, useFeatureStore } from "./app/stores/featureStore";
import type { SurveyOutput } from "./types/api";

function getInitialLanguage(): Language {
  const stored = localStorage.getItem("schema-agent-language");
  return stored === "en" || stored === "zh" ? stored : "zh";
}

export default function App() {
  const { route, navigate } = useAppRouter();
  const features = useFeatureStore();
  const [language, setLanguage] = useState<Language>(getInitialLanguage);
  const analysis = useAnalysis();
  useEffect(() => { void loadFeatures(); }, []);
  const enabledPages = useMemo(() => {
    const pages = new Set<PageKey>(["analysis", "chat", "monitor", "eval"]);
    const flags = features.flags;
    if (flags.memory_inspector) pages.add("memory");
    if (flags.approval_center) pages.add("approvals");
    if (flags.run_inspector) pages.add("runs");
    if (flags.evidence_workbench) pages.add("evidence");
    if (flags.er_explorer_v2) pages.add("er");
    if (flags.eval_v2) pages.add("quality");
    return pages;
  }, [features.flags]);
  const activePage = enabledPages.has(route.page) ? route.page : "analysis";
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
          onPageChange={(page) => navigate(page)}
          onAnalyze={analysis.runAnalysis}
          analyzing={analysis.loading}
          enabledPages={enabledPages}
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
            {activePage === "eval" ? <EvalConsolePage /> : null}
            {activePage === "memory" ? <MemoryInspectorPage /> : null}
            {activePage === "approvals" ? <ApprovalCenterPage /> : null}
            {activePage === "runs" ? <RunInspectorPage initialRunId={route.resourceId} onSelectRun={(runId) => navigate("runs", runId)} /> : null}
            {activePage === "evidence" ? <EvidenceWorkbenchPage /> : null}
            {activePage === "quality" ? <EvalConsolePage /> : null}
            {activePage === "er" ? <ERExplorerPage /> : null}
          </main>
        </div>
      </div>
    </I18nContext.Provider>
  );
}
