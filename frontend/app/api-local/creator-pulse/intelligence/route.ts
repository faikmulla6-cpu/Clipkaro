import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

type PulseVideoInput = {
  id: string;
  title: string;
  thumbnail_url?: string | null;
  views: number;
  likes?: number | null;
  comments?: number | null;
  age_days: number;
  views_per_day: number;
  engagement_rate?: number | null;
  vs_recent_average_pct: number;
};

type PulseReportInput = {
  id: string;
  captured_at: string;
  channel: {
    id: string;
    handle: string;
    title: string;
    description?: string | null;
    subscribers?: number | null;
    hidden_subscriber_count: boolean;
    total_views: number;
    video_count: number;
  };
  recent: {
    average_views: number;
    average_engagement_rate?: number | null;
    upload_cadence_days?: number | null;
    videos: PulseVideoInput[];
  };
  delta?: {
    available?: boolean;
    previous_captured_at?: string | null;
    subscriber_change?: number | null;
    view_change?: number | null;
    video_count_change?: number | null;
  };
};

type Recommendation = {
  title: string;
  why: string;
  angle: string;
  hook: string;
  confidence: "Strong" | "Moderate" | "Limited";
  thumbnail_text: string;
  thumbnail_direction: string;
};

type IntelligenceResponse = Recommendation & {
  generated_at: string;
  text_model: string;
  thumbnail_model: string | null;
  thumbnail_data_url: string | null;
  thumbnail_status: "generated" | "unavailable";
};

type CacheEntry = { expiresAt: number; value: IntelligenceResponse };
type GlobalCache = typeof globalThis & { __clipkaroPulseIntelligence?: Map<string, CacheEntry> };

const globalCache = globalThis as GlobalCache;
const intelligenceCache = globalCache.__clipkaroPulseIntelligence ?? new Map<string, CacheEntry>();
globalCache.__clipkaroPulseIntelligence = intelligenceCache;

const TEXT_MODEL = "gemini-2.5-flash";
const IMAGE_MODEL = "gemini-2.5-flash-image";
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const ALLOWED_THUMBNAIL_HOSTS = new Set(["i.ytimg.com", "img.youtube.com"]);

function cleanText(value: unknown, maxLength: number): string {
  return String(value ?? "").replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function safeNumber(value: unknown, max = Number.MAX_SAFE_INTEGER): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(parsed, max));
}

function geminiKeys(): string[] {
  const names = [
    "GEMINI_API_KEY_PRIMARY",
    "GEMINI_API_KEY_BACKUP_1",
    "GEMINI_API_KEY_BACKUP_2",
    "GEMINI_API_KEY_BACKUP_3",
    "GEMINI_API_KEY_BACKUP_4",
    "GEMINI_API_KEY_BACKUP_5",
  ];
  return Array.from(new Set(names.map((name) => cleanText(process.env[name], 500)).filter(Boolean)));
}

function pruneCache() {
  const now = Date.now();
  for (const [key, entry] of intelligenceCache.entries()) {
    if (entry.expiresAt <= now) intelligenceCache.delete(key);
  }
  while (intelligenceCache.size > 100) {
    const oldest = intelligenceCache.keys().next().value as string | undefined;
    if (!oldest) break;
    intelligenceCache.delete(oldest);
  }
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal, cache: "no-store" });
  } finally {
    clearTimeout(timeout);
  }
}

function sanitizeReport(raw: unknown): PulseReportInput | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  const channelRaw = value.channel;
  const recentRaw = value.recent;
  if (!channelRaw || typeof channelRaw !== "object" || !recentRaw || typeof recentRaw !== "object") return null;
  const channel = channelRaw as Record<string, unknown>;
  const recent = recentRaw as Record<string, unknown>;
  const rawVideos = Array.isArray(recent.videos) ? recent.videos.slice(0, 10) : [];
  const videos = rawVideos
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((video) => ({
      id: cleanText(video.id, 80),
      title: cleanText(video.title, 240),
      thumbnail_url: cleanText(video.thumbnail_url, 600) || null,
      views: safeNumber(video.views, 10_000_000_000),
      likes: video.likes == null ? null : safeNumber(video.likes, 10_000_000_000),
      comments: video.comments == null ? null : safeNumber(video.comments, 10_000_000_000),
      age_days: Math.max(0.01, safeNumber(video.age_days, 100_000)),
      views_per_day: safeNumber(video.views_per_day, 10_000_000_000),
      engagement_rate: video.engagement_rate == null ? null : safeNumber(video.engagement_rate, 100_000),
      vs_recent_average_pct: Number.isFinite(Number(video.vs_recent_average_pct)) ? Number(video.vs_recent_average_pct) : 0,
    }))
    .filter((video) => video.id && video.title);

  if (!videos.length) return null;

  const deltaRaw = value.delta && typeof value.delta === "object" ? value.delta as Record<string, unknown> : {};
  return {
    id: cleanText(value.id, 80),
    captured_at: cleanText(value.captured_at, 80),
    channel: {
      id: cleanText(channel.id, 100),
      handle: cleanText(channel.handle, 120),
      title: cleanText(channel.title, 180),
      description: cleanText(channel.description, 900) || null,
      subscribers: channel.subscribers == null ? null : safeNumber(channel.subscribers, 10_000_000_000),
      hidden_subscriber_count: Boolean(channel.hidden_subscriber_count),
      total_views: safeNumber(channel.total_views, 10_000_000_000_000),
      video_count: safeNumber(channel.video_count, 100_000_000),
    },
    recent: {
      average_views: safeNumber(recent.average_views, 10_000_000_000),
      average_engagement_rate: recent.average_engagement_rate == null ? null : safeNumber(recent.average_engagement_rate, 100_000),
      upload_cadence_days: recent.upload_cadence_days == null ? null : safeNumber(recent.upload_cadence_days, 100_000),
      videos,
    },
    delta: {
      available: Boolean(deltaRaw.available),
      previous_captured_at: cleanText(deltaRaw.previous_captured_at, 80) || null,
      subscriber_change: deltaRaw.subscriber_change == null ? null : Number(deltaRaw.subscriber_change),
      view_change: deltaRaw.view_change == null ? null : Number(deltaRaw.view_change),
      video_count_change: deltaRaw.video_count_change == null ? null : Number(deltaRaw.video_count_change),
    },
  };
}

async function verifyPaidScan(request: Request, scanId: string, report: PulseReportInput): Promise<void> {
  const backendUrl = cleanText(process.env.BACKEND_URL, 1000).replace(/\/$/, "");
  if (!backendUrl) throw new Error("Creator Pulse intelligence is not connected to the processing server.");

  const cookie = request.headers.get("cookie") || "";
  if (!cookie) throw new Error("Sign in again before generating Creator Pulse intelligence.");

  const response = await fetchWithTimeout(
    `${backendUrl}/api/v1/creator-pulse/status`,
    { method: "GET", headers: { accept: "application/json", cookie } },
    12_000,
  );
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error("Sign in again before generating Creator Pulse intelligence.");
    throw new Error("Creator Pulse could not verify this paid scan right now.");
  }

  const status = await response.json() as { recent_scans?: Array<Record<string, unknown>> };
  const scan = (status.recent_scans || []).find((item) => cleanText(item.id, 80) === scanId);
  if (!scan) throw new Error("This Pulse could not be verified as a recent successful scan.");

  const sameHandle = cleanText(scan.handle, 120).toLowerCase() === report.channel.handle.toLowerCase();
  const sameViews = safeNumber(scan.total_views, 10_000_000_000_000) === report.channel.total_views;
  const sameCapture = cleanText(scan.captured_at, 80) === report.captured_at;
  if (!sameHandle || !sameViews || !sameCapture || report.id !== scanId) {
    throw new Error("Creator Pulse evidence did not match the verified scan.");
  }
}

function buildRecommendationPrompt(report: PulseReportInput): string {
  const ranked = [...report.recent.videos].sort((a, b) => b.views_per_day - a.views_per_day);
  const videos = ranked.map((video, index) => ({
    rank_by_views_per_day: index + 1,
    title: video.title,
    views: video.views,
    age_days: Number(video.age_days.toFixed(2)),
    views_per_day: Number(video.views_per_day.toFixed(2)),
    engagement_rate_percent: video.engagement_rate == null ? null : Number(video.engagement_rate.toFixed(2)),
    vs_recent_average_percent: Number(video.vs_recent_average_pct.toFixed(2)),
  }));

  const evidence = {
    channel: {
      title: report.channel.title,
      handle: report.channel.handle,
      description: report.channel.description,
      subscribers: report.channel.hidden_subscriber_count ? null : report.channel.subscribers,
      total_views: report.channel.total_views,
      video_count: report.channel.video_count,
    },
    recent_summary: {
      average_views: report.recent.average_views,
      average_engagement_rate_percent: report.recent.average_engagement_rate,
      median_upload_cadence_days: report.recent.upload_cadence_days,
    },
    recent_videos_ranked_by_current_views_per_day: videos,
    previous_pulse_delta: report.delta,
  };

  return `You are the decision layer inside ClipKaro Creator Pulse. Produce ONE specific next YouTube video recommendation for this creator using ONLY the verified public YouTube evidence below.

Rules:
- Stay close to the creator's recent subjects, vocabulary, audience and content style. Do not jump to a random niche.
- Prefer a fresh continuation, experiment, comparison, challenge, update or deeper angle related to patterns that currently show stronger momentum.
- Do not claim causation, CTR, impressions, watch time, retention, revenue, audience demographics or any metric not provided.
- Do not invent percentages, benchmarks, trend data, search volume or competitor data.
- The title must be publishable, specific and natural, not clickbait spam.
- The explanation must tell the creator what to do next and why the supplied evidence supports it.
- The hook should be one short opening line the creator can actually say in the video.
- The thumbnail text must be 2 to 4 words, easy to read, and complement the title rather than repeat it.
- thumbnail_direction should describe one professional 16:9 YouTube thumbnail composition. It may borrow visual language from the creator's recent thumbnails, but must be an original composition.
- confidence must be Strong, Moderate or Limited. Use Strong only when multiple recent items support a consistent direction.
- Never promise that the recommendation will go viral or guarantee performance.

Verified evidence:\n${JSON.stringify(evidence)}`;
}

function normalizeRecommendation(raw: unknown): Recommendation | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const confidenceRaw = cleanText(item.confidence, 20);
  const confidence: Recommendation["confidence"] = confidenceRaw === "Strong" || confidenceRaw === "Limited" ? confidenceRaw : "Moderate";
  const title = cleanText(item.title, 120);
  const why = cleanText(item.why, 620);
  const angle = cleanText(item.angle, 180);
  const hook = cleanText(item.hook, 220);
  const thumbnailWords = cleanText(item.thumbnail_text, 60).split(/\s+/).filter(Boolean).slice(0, 4).join(" ");
  const thumbnail_direction = cleanText(item.thumbnail_direction, 700);
  if (!title || !why || !angle || !hook || !thumbnailWords || !thumbnail_direction) return null;
  return { title, why, angle, hook, confidence, thumbnail_text: thumbnailWords, thumbnail_direction };
}

async function generateRecommendation(report: PulseReportInput, keys: string[]): Promise<{ value: Recommendation; key: string }> {
  const body = {
    contents: [{ role: "user", parts: [{ text: buildRecommendationPrompt(report) }] }],
    generationConfig: {
      temperature: 0.35,
      maxOutputTokens: 1200,
      responseMimeType: "application/json",
      responseSchema: {
        type: "OBJECT",
        properties: {
          title: { type: "STRING" },
          why: { type: "STRING" },
          angle: { type: "STRING" },
          hook: { type: "STRING" },
          confidence: { type: "STRING", enum: ["Strong", "Moderate", "Limited"] },
          thumbnail_text: { type: "STRING" },
          thumbnail_direction: { type: "STRING" },
        },
        required: ["title", "why", "angle", "hook", "confidence", "thumbnail_text", "thumbnail_direction"],
      },
    },
  };

  let lastError = "Gemini could not create the recommendation.";
  for (const key of keys) {
    try {
      const response = await fetchWithTimeout(
        `https://generativelanguage.googleapis.com/v1beta/models/${TEXT_MODEL}:generateContent`,
        {
          method: "POST",
          headers: { "content-type": "application/json", "x-goog-api-key": key },
          body: JSON.stringify(body),
        },
        24_000,
      );
      if (!response.ok) {
        const detail = cleanText(await response.text().catch(() => ""), 500);
        lastError = `Gemini recommendation failed (${response.status})${detail ? `: ${detail}` : ""}`;
        if ([400, 401, 403, 429, 500, 502, 503, 504].includes(response.status)) continue;
        break;
      }
      const payload = await response.json() as Record<string, any>;
      const text = payload?.candidates?.[0]?.content?.parts?.find((part: any) => typeof part?.text === "string")?.text;
      if (!text) {
        lastError = "Gemini returned no recommendation text.";
        continue;
      }
      const parsed = normalizeRecommendation(JSON.parse(text));
      if (!parsed) {
        lastError = "Gemini returned an incomplete recommendation.";
        continue;
      }
      return { value: parsed, key };
    } catch (error) {
      lastError = error instanceof Error ? cleanText(error.message, 500) : lastError;
    }
  }
  throw new Error(lastError);
}

async function fetchReferenceImage(urlValue: string | null | undefined): Promise<{ type: "image"; mime_type: string; data: string } | null> {
  if (!urlValue) return null;
  let url: URL;
  try { url = new URL(urlValue); } catch { return null; }
  if (url.protocol !== "https:" || !ALLOWED_THUMBNAIL_HOSTS.has(url.hostname)) return null;

  try {
    const response = await fetchWithTimeout(url.toString(), { method: "GET", headers: { accept: "image/jpeg,image/png,image/webp" } }, 8_000);
    if (!response.ok) return null;
    const contentType = (response.headers.get("content-type") || "image/jpeg").split(";")[0].trim().toLowerCase();
    if (!new Set(["image/jpeg", "image/png", "image/webp"]).has(contentType)) return null;
    const buffer = Buffer.from(await response.arrayBuffer());
    if (!buffer.length || buffer.length > 3_000_000) return null;
    return { type: "image", mime_type: contentType, data: buffer.toString("base64") };
  } catch {
    return null;
  }
}

function buildThumbnailPrompt(report: PulseReportInput, recommendation: Recommendation): string {
  return `Create exactly ONE original professional YouTube thumbnail for the creator ${report.channel.title} (${report.channel.handle}).

Recommended video title: ${recommendation.title}
Video angle: ${recommendation.angle}
Thumbnail text: ${recommendation.thumbnail_text}
Creative direction: ${recommendation.thumbnail_direction}

The supplied images, when present, are recent thumbnails from this same creator. Use them only to understand the creator's current visual language, subject matter and presentation style. Do not copy an existing thumbnail pixel-for-pixel.

Production requirements:
- 16:9 YouTube thumbnail, premium 2026 creator quality, instantly readable at small size.
- One dominant focal idea, deliberate visual hierarchy, strong separation between subject and background.
- Render ONLY the exact short thumbnail text: "${recommendation.thumbnail_text}". No other words.
- Keep text large, clean and legible. Avoid tiny labels, fake UI text and clutter.
- Match the creator's recent niche and the recommended title; do not introduce unrelated products or topics.
- If a clear recurring creator/person is visible in the reference thumbnails, keep the person naturally recognizable without changing age or body type. If identity is not clear enough, build the thumbnail around the topic/product/interface instead of inventing a face.
- No Gemini logo, no Google logo, no ClipKaro logo, no visible AI branding, no decorative watermark, no signature.
- Do not promise results or include fake views, CTR, subscriber counts or analytics.
- Photorealistic/clean commercial finish where appropriate to the source style; realistic hands and screens; no obvious AI artifacts.`;
}

function extractGeneratedImage(payload: Record<string, any>): { data: string; mimeType: string } | null {
  const direct = payload.output_image || payload.outputImage;
  if (direct?.data) return { data: String(direct.data), mimeType: cleanText(direct.mime_type || direct.mimeType || "image/jpeg", 80) };
  for (const step of Array.isArray(payload.steps) ? payload.steps : []) {
    if (step?.type !== "model_output") continue;
    for (const block of Array.isArray(step.content) ? step.content : []) {
      if (block?.type === "image" && block?.data) {
        return { data: String(block.data), mimeType: cleanText(block.mime_type || block.mimeType || "image/jpeg", 80) };
      }
    }
  }
  return null;
}

async function generateThumbnail(report: PulseReportInput, recommendation: Recommendation, keys: string[], preferredKey: string): Promise<{ dataUrl: string; model: string } | null> {
  const ranked = [...report.recent.videos].sort((a, b) => b.views_per_day - a.views_per_day).slice(0, 3);
  const references = (await Promise.all(ranked.map((video) => fetchReferenceImage(video.thumbnail_url)))).filter(Boolean) as Array<{ type: "image"; mime_type: string; data: string }>;
  const input: Array<Record<string, string>> = [
    ...references,
    { type: "text", text: buildThumbnailPrompt(report, recommendation) },
  ];
  const orderedKeys = [preferredKey, ...keys.filter((key) => key !== preferredKey)];

  for (const key of orderedKeys) {
    try {
      const response = await fetchWithTimeout(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        {
          method: "POST",
          headers: { "content-type": "application/json", "x-goog-api-key": key },
          body: JSON.stringify({
            model: IMAGE_MODEL,
            input,
            response_format: { type: "image", mime_type: "image/jpeg", aspect_ratio: "16:9", image_size: "1K" },
          }),
        },
        45_000,
      );
      if (!response.ok) {
        if ([400, 401, 403, 429, 500, 502, 503, 504].includes(response.status)) continue;
        return null;
      }
      const payload = await response.json() as Record<string, any>;
      const image = extractGeneratedImage(payload);
      if (!image?.data || image.data.length > 8_000_000) continue;
      const mime = new Set(["image/jpeg", "image/png", "image/webp"]).has(image.mimeType) ? image.mimeType : "image/jpeg";
      return { dataUrl: `data:${mime};base64,${image.data}`, model: IMAGE_MODEL };
    } catch {
      continue;
    }
  }
  return null;
}

export async function POST(request: Request) {
  pruneCache();
  try {
    const keys = geminiKeys();
    if (!keys.length) {
      return NextResponse.json({ detail: "Creator Pulse AI is not configured yet." }, { status: 503, headers: { "Cache-Control": "no-store" } });
    }

    const body = await request.json().catch(() => null) as { scan_id?: unknown; report?: unknown } | null;
    const scanId = cleanText(body?.scan_id, 80);
    const report = sanitizeReport(body?.report);
    if (!scanId || !report || report.id !== scanId) {
      return NextResponse.json({ detail: "Creator Pulse intelligence request is incomplete." }, { status: 422, headers: { "Cache-Control": "no-store" } });
    }

    const cached = intelligenceCache.get(scanId);
    if (cached && cached.expiresAt > Date.now()) {
      return NextResponse.json(cached.value, { headers: { "Cache-Control": "private, no-store" } });
    }

    await verifyPaidScan(request, scanId, report);
    const generated = await generateRecommendation(report, keys);
    const thumbnail = await generateThumbnail(report, generated.value, keys, generated.key);

    const value: IntelligenceResponse = {
      ...generated.value,
      generated_at: new Date().toISOString(),
      text_model: TEXT_MODEL,
      thumbnail_model: thumbnail?.model || null,
      thumbnail_data_url: thumbnail?.dataUrl || null,
      thumbnail_status: thumbnail ? "generated" : "unavailable",
    };

    intelligenceCache.set(scanId, { expiresAt: Date.now() + CACHE_TTL_MS, value });
    return NextResponse.json(value, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    const message = error instanceof Error ? cleanText(error.message, 500) : "Creator Pulse intelligence is temporarily unavailable.";
    const status = /sign in/i.test(message) ? 401 : /verified scan|evidence did not match/i.test(message) ? 409 : 502;
    return NextResponse.json({ detail: message || "Creator Pulse intelligence is temporarily unavailable." }, { status, headers: { "Cache-Control": "no-store" } });
  }
}
