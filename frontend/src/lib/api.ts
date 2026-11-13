import { ApiError, errorFromBody } from "@/lib/errors";
import { getSupabase } from "@/lib/supabase";

export { ApiError, errorFromBody };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiOptions = RequestInit & { orgId?: string | null };

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) {
    headers.set("Content-Type", "application/json");
  }
  const { data } = await getSupabase().auth.getSession();
  const token = data.session?.access_token;
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const orgId =
    options.orgId === undefined ? window.localStorage.getItem("vansora.orgId") : options.orgId;
  if (orgId) {
    headers.set("X-Organization-Id", orgId);
  }

  const response = await fetch(`${API_URL}/api/v1${path}`, {
    ...options,
    headers,
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw errorFromBody(body, response.status);
  }
  return body as T;
}
