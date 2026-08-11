export interface ThreadSnapshot { threadId: string | null; runId: string | null; artifacts: string[]; }
let snapshot: ThreadSnapshot = { threadId: null, runId: null, artifacts: [] };
export const threadStore = { get: () => snapshot, update: (patch: Partial<ThreadSnapshot>) => { snapshot = { ...snapshot, ...patch }; } };
