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

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function parseSuccessfulResponse<T>(response: Response, allowEmpty: boolean): Promise<T> {
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  if (!text.trim()) {
    if (allowEmpty) return undefined as T;
    throw new Error("ClipKaro received an empty response from the server.");
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("ClipKaro received an invalid response from the server.");
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const method = (init?.method || "GET").toUpperCase();
  const isRead = method === "GET" || method === "HEAD";

  if (typeof document !== "undefined" && !isRead) {
    const csrf = document.cookie.split("; ").find(x => x.startsWith("csrf_token="))?.split("=")[1];
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }

  const attempts = isRead ? 2 : 1;
  let lastError: Error | null = null;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    let response: Response;
    try {
      response = await fetch(`${API_URL}${path}`, { credentials: "include", ...init, headers });
    } catch (cause) {
      lastError = new Error(
        "ClipKaro could not reach the processing server. Please try again in a moment.",
        { cause },
      );
      if (attempt + 1 < attempts) {
        await wait(250);
        continue;
      }
      throw lastError;
    }

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      let body: { detail?: unknown } = { detail: "Something went wrong" };
      if (text.trim()) {
        try { body = JSON.parse(text) as { detail?: unknown }; }
        catch { body = { detail: text }; }
      }
      throw new Error(readableError(body.detail));
    }

    if (response.status === 204) return undefined as T;

    try {
      return await parseSuccessfulResponse<T>(response, !isRead);
    } catch (cause) {
      lastError = cause instanceof Error ? cause : new Error("ClipKaro received an invalid response from the server.");
      if (attempt + 1 < attempts) {
        await wait(250);
        continue;
      }
      throw lastError;
    }
  }

  throw lastError || new Error("Something went wrong");
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
