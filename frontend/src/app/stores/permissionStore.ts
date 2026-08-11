let capabilities = new Set<string>();
export const permissionStore = { replace: (values: string[]) => { capabilities = new Set(values); }, can: (value: string) => capabilities.has(value) };
