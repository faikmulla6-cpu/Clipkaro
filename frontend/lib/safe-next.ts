const SAFE_ORIGIN = "https://clipkaro.local";
const POST_AUTH_NEXT_STORAGE_KEY = "clipkaro:post-auth-next";
const POST_AUTH_NEXT_TTL_MS = 30 * 60 * 1000;

const blockedDestinations = new Set([
  "/login",
  "/signup",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
]);

/**
 * Accept only same-origin relative destinations. This prevents auth `next`
 * parameters from becoming open redirects and also avoids auth-page loops.
 */
export function safeInternalNext(raw: string | null | undefined, fallback = "/dashboard"): string {
  if (!raw) return fallback;
  const candidate = raw.trim();
  if (
    !candidate.startsWith("/") ||
    candidate.startsWith("//") ||
    candidate.includes("\\") ||
    /[\u0000-\u001f\u007f]/.test(candidate)
  ) {
    return fallback;
  }

  try {
    const resolved = new URL(candidate, SAFE_ORIGIN);
    if (resolved.origin !== SAFE_ORIGIN || blockedDestinations.has(resolved.pathname)) return fallback;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}

export function authHref(path: "/login" | "/signup" | "/verify-email", rawNext?: string | null): string {
  const next = safeInternalNext(rawNext, "");
  return next ? `${path}?next=${encodeURIComponent(next)}` : path;
}

/**
 * Email verification often opens in a different browser tab. Keep only a
 * short-lived, validated internal continuation so that flow can return to the
 * feature the creator intentionally opened. The value is never trusted without
 * re-validation when read.
 */
export function rememberPostAuthNext(rawNext: string | null | undefined): void {
  if (typeof window === "undefined") return;
  const next = safeInternalNext(rawNext, "");
  if (!next) return;
  try {
    window.localStorage.setItem(
      POST_AUTH_NEXT_STORAGE_KEY,
      JSON.stringify({ path: next, expiresAt: Date.now() + POST_AUTH_NEXT_TTL_MS }),
    );
  } catch {
    // Storage can be blocked by browser privacy settings; query-string routing
    // still works in the current tab.
  }
}

export function readPostAuthNext(fallback = "/dashboard"): string {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(POST_AUTH_NEXT_STORAGE_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as { path?: unknown; expiresAt?: unknown };
    if (typeof parsed.expiresAt !== "number" || parsed.expiresAt < Date.now()) {
      window.localStorage.removeItem(POST_AUTH_NEXT_STORAGE_KEY);
      return fallback;
    }
    return safeInternalNext(typeof parsed.path === "string" ? parsed.path : null, fallback);
  } catch {
    try { window.localStorage.removeItem(POST_AUTH_NEXT_STORAGE_KEY); } catch {}
    return fallback;
  }
}

export function clearPostAuthNext(): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(POST_AUTH_NEXT_STORAGE_KEY); } catch {}
}
