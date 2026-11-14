import { ApiError, errorFromBody } from "@/lib/errors";
import { currentAccessToken, getSupabase } from "@/lib/supabase";

export { ApiError, errorFromBody };

function apiOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim().replace(/\/$/, "");
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    throw new Error("NEXT_PUBLIC_API_URL is not set.");
  }
  return "http://localhost:8000";
}

const API_URL = apiOrigin();
const WAKING_MESSAGE = "The API is waking up. Wait about a minute and try again.";

type ApiOptions = RequestInit & { orgId?: string | null; token?: string | null };

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function failure(body: unknown, status: number): ApiError {
  if (body == null) return new ApiError("api_waking", WAKING_MESSAGE, status || 503);
  return errorFromBody(body, status);
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const { token: explicitToken, orgId: explicitOrgId, ...request } = options;
  let token = explicitToken ?? currentAccessToken();
  if (!token) {
    const { data } = await getSupabase().auth.getSession();
    token = data.session?.access_token ?? null;
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const orgId =
    explicitOrgId === undefined ? window.localStorage.getItem("vansora.orgId") : explicitOrgId;
  if (orgId) {
    headers.set("X-Organization-Id", orgId);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, {
      ...request,
      headers,
    });
  } catch {
    throw new ApiError("api_waking", WAKING_MESSAGE, 503);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const body = await readJson(response);
  if (!response.ok || body == null) {
    throw failure(body, response.status);
  }
  return body as T;
}

export async function downloadApi(path: string, filename: string, orgId?: string) {
  const headers = new Headers();
  let token = currentAccessToken();
  if (!token) {
    const { data } = await getSupabase().auth.getSession();
    token = data.session?.access_token ?? null;
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const organizationId = orgId ?? window.localStorage.getItem("vansora.orgId");
  if (organizationId) headers.set("X-Organization-Id", organizationId);
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, { headers });
  } catch {
    throw new ApiError("api_waking", WAKING_MESSAGE, 503);
  }
  if (!response.ok) {
    throw failure(await readJson(response), response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
