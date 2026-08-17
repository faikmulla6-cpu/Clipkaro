import { API_URL, api, postJSON } from "@/lib/api";

export type ClipBehaviorType = "impression" | "preview_started" | "selected" | "edited";

export function newBehaviorSession(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function trackClipBehavior(
  clipId: string,
  eventType: ClipBehaviorType,
  options: {
    sessionId: string;
    eventId?: string;
    surface?: "project" | "editor" | "export";
    changedFields?: string[];
  },
): void {
  const eventId = options.eventId || newBehaviorSession();
  void postJSON(`/clips/${clipId}/behavior`, {
    event_type: eventType,
    client_event_id: eventId,
    client_session_id: options.sessionId,
    surface: options.surface || "project",
    changed_fields: options.changedFields || [],
  }).catch(() => {
    // Behavioral telemetry must never block creator actions. Strong export labels
    // are independently captured at the backend/database boundary.
  });
}

export async function recordDownload(exportId: string): Promise<void> {
  try {
    await api<void>(`/exports/${exportId}/download-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      keepalive: true,
    });
  } catch {
    // A telemetry receipt cannot make a paid creator lose access to the MP4.
  }
}

export function downloadExport(exportId: string): void {
  // Fire-and-forget with keepalive: navigation/download must never wait for an
  // analytics receipt, while the request still gets a chance to finish.
  void recordDownload(exportId);
  window.location.assign(`${API_URL}/exports/${exportId}/download`);
}
