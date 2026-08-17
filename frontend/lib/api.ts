export const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

function readableError(detail: unknown): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item && typeof item === "object" && "msg" in item && typeof item.msg === "string" ? item.msg : "")
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  return "Something went wrong";
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof document !== "undefined" && init?.method && !["GET","HEAD"].includes(init.method.toUpperCase())) {
    const csrf = document.cookie.split("; ").find(x => x.startsWith("csrf_token="))?.split("=")[1];
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { credentials: "include", ...init, headers });
  } catch (cause) {
    throw new Error(
      "ClipKaro could not reach the processing server. Start the backend on port 8000, then refresh this page.",
      { cause },
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Something went wrong" }));
    throw new Error(readableError(body.detail));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type User = { id: string; name: string; email: string; plan: string; role: string; onboarding_complete: boolean };
export type VerificationStatus = {
  verified: boolean;
  required: boolean;
  can_process: boolean;
  email: string;
};
export type AccountSettings = {
  name: string;
  email: string;
  default_language: "auto" | "en" | "hi" | "hinglish" | "mr";
  timezone: string;
  creator_category: "auto" | "education" | "podcast" | "business" | "motivation" | "spiritual" | "local-business";
};
export type Usage = { plan: string; exports_used: number; exports_limit: number; exports_remaining: number; source_minutes: number; processing_minutes_limit: number; processing_minutes_remaining: number; period_key: string };

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function patchJSON<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

export function deleteJSON<T = void>(path: string): Promise<T> {
  return api<T>(path, { method: "DELETE" });
}
