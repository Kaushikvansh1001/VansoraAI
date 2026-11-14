import { ApiError, errorFromBody } from "@/lib/errors";
import { currentAccessToken, getSupabase } from "@/lib/supabase";

export { ApiError, errorFromBody };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiOptions = RequestInit & { orgId?: string | null; token?: string | null };

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

  const response = await fetch(`${API_URL}/api/v1${path}`, {
    ...request,
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
