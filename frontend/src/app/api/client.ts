export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init.headers ?? {}) } });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, String(payload.detail ?? "request_failed"), String(payload.detail ?? `HTTP ${response.status}`));
  }
  return response.json() as Promise<T>;
}
