import type { ReactNode } from "react";
import { permissionStore } from "../../app/stores/permissionStore";
export function Authorized({ capability, children, fallback = null }: { capability: string; children: ReactNode; fallback?: ReactNode }) { return permissionStore.can(capability) ? children : fallback; }
