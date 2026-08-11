import { useCallback, useEffect, useMemo, useState } from "react";

export type PageKey = "analysis" | "chat" | "monitor" | "eval" | "memory" | "approvals" | "runs" | "evidence" | "quality" | "er";

export interface AppRoute { page: PageKey; resourceId?: string; }

function readRoute(): AppRoute {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const page = (parts[0] || "analysis") as PageKey;
  const allowed: PageKey[] = ["analysis", "chat", "monitor", "eval", "memory", "approvals", "runs", "evidence", "quality", "er"];
  return { page: allowed.includes(page) ? page : "analysis", resourceId: parts[1] ? decodeURIComponent(parts[1]) : undefined };
}

export function useAppRouter() {
  const [route, setRoute] = useState<AppRoute>(readRoute);
  useEffect(() => {
    const listener = () => setRoute(readRoute());
    window.addEventListener("hashchange", listener);
    if (!window.location.hash) window.history.replaceState(null, "", "#/analysis");
    return () => window.removeEventListener("hashchange", listener);
  }, []);
  const navigate = useCallback((page: PageKey, resourceId?: string) => {
    window.location.hash = `/${page}${resourceId ? `/${encodeURIComponent(resourceId)}` : ""}`;
  }, []);
  return useMemo(() => ({ route, navigate }), [navigate, route]);
}
