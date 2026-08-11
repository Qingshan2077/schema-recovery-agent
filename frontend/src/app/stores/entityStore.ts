const entities = new Map<string, unknown>();
export const entityStore = { put: (id: string, value: unknown) => entities.set(id, value), get: <T>(id: string) => entities.get(id) as T | undefined };
