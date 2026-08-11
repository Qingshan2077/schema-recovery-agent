import { useSyncExternalStore } from "react";

let snapshot = { capabilities: new Set<string>() };
const listeners = new Set<() => void>();
export const permissionStore = {
  replace: (values: string[]) => { snapshot = { capabilities: new Set(values) }; listeners.forEach((listener) => listener()); },
  can: (value: string) => snapshot.capabilities.has(value),
  get: () => snapshot
};
export function usePermissionStore() { return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, permissionStore.get); }
