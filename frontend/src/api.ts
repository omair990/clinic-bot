// Thin fetch wrapper for the FastAPI JSON API. Same-origin cookie session, so we just
// include credentials. Throws ApiError (status carries 401/403 for the UI to react to).
const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle(r: Response) {
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const body = await r.json();
      msg = body.detail || msg;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

export function apiGet<T = any>(path: string): Promise<T> {
  return fetch(BASE + path, { credentials: "include" }).then(handle);
}

export function apiPost<T = any>(path: string, body?: unknown): Promise<T> {
  return fetch(BASE + path, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }).then(handle);
}
