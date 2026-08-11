import { useSyncExternalStore } from "react";
import { api } from "../api/client";

export interface FeatureSnapshot { loaded: boolean; flags: Record<string, boolean>; error?: string; }
let state: FeatureSnapshot = { loaded: false, flags: {} };
const listeners = new Set<() => void>();
const publish = (next: FeatureSnapshot) => { state = next; listeners.forEach((listener) => listener()); };

export async function loadFeatures() {
  try {
    const health = await api<{ feature_flags?: Record<string, boolean> }>("/health");
    publish({ loaded: true, flags: health.feature_flags ?? {} });
  } catch (reason) {
    publish({ loaded: true, flags: {}, error: reason instanceof Error ? reason.message : "feature discovery failed" });
  }
}

export function useFeatureStore() {
  return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, () => state);
}
