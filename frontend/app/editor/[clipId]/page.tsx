"use client";

import { ErrorState } from "@/components/ErrorState";
import { useAuth } from "@/components/AuthProvider";
import { API_URL, api, patchJSON, postJSON } from "@/lib/api";
import { dualStackCoverageSeconds, findScene, paintSmartLayoutFrame, parseSmartLayoutPlan, type SmartLayoutPlan } from "@/lib/smart-layout-timeline";
import { downloadExport, newBehaviorSession, trackClipBehavior } from "@/lib/behavior";
import {
  AlertTriangle, AlignCenter, AlignLeft, AlignRight, ArrowLeft, ArrowRight, Captions, Check, Download, Film, GripVertical, Loader2, LockKeyhole, MoveHorizontal,
  Palette, Pause, Play, Redo2, Save, Scissors, Send, Smartphone, Sparkles, Square, Trash2, Type, Undo2, WandSparkles, X, ZoomIn, ZoomOut,
} from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Clip = {
  id: string; title: string; hook: string; transcript_text: string;
  start_time: number; end_time: number; score: number;
};
type Project = { id: string; title: string; duration: number; clips: Clip[] };
type ExportResponse = { id: string; job_id: string; status: string; expires_at: string };
type ExportStatus = { id: string; status: string; progress: number; download_url?: string | null; expires_at: string };
type Job = { id?: string; status: string; progress: number; message: string; error?: string; export_id?: string };
type TimedWord = { start: number; end: number; text: string; confidence?: number; source_start?: number; source_end?: number };
type RemovedRange = { start: number; end: number; reason: string };
type EditPlan = { version: number; removed_ranges: RemovedRange[]; split_points: number[]; segment_order?: number[]; layout_mode?: "classic" | SmartPlanModes };
type SpeechRegion = { id: number; start: number; end: number };
type CaptionCard = { start: number; end: number; lines: string[]; words: TimedWord[] };
type CaptionTrack = {
  language: string; clip_start: number; clip_end: number; words: TimedWord[]; cards: CaptionCard[]; speech_regions?: SpeechRegion[];
  source_words?: TimedWord[]; edit_plan?: EditPlan; clean_speech_ranges?: RemovedRange[];
  source_has_burned_captions?: boolean; source_caption_band?: number | null;
  review_suggested?: boolean; review_reasons?: string[];
  india_quality?: { india_quality_suitable?: boolean; likely_language_style?: string; code_switch_score?: number };
};
type CaptionStyle = { id: string; name: string; font_family: string; font_weight: number; font_size_width_ratio: number; text_transform: string; text_color: string; highlight_color: string; highlight_background: string; shadow: string; line_height: number; horizontal_inset_ratio: number; bottom_safe_ratio: number; above_safe_ratio: number; active_word_scale: number; corner_radius_px: number; background: string };
type BrandKit = { id: string; name: string; primary_color: string; logo_text?: string | null; caption_preset: string; is_default: boolean };
type WorkspaceTool = "edit" | "captions" | "frame" | "brand" | "export";
type CaptionLanguageStyle = "auto" | "roman_hinglish" | "original";
type CaptionAlignment = "left" | "center" | "right";
type PostKaroStatus = { plan_eligible: boolean; ready: boolean };

// Preview capability is discovered from the authenticated production backend.
 // No fragile Hostinger build-time NEXT_PUBLIC switch is required.
type SmartPlanModes = "auto" | "dual_stack" | "speaker_focus";
type SmartLayoutBillingAction = "new_charge" | "cached_reuse" | "free_refresh" | "existing_job" | "unknown";
type LayoutAnalysisResponse = { status: string; job_id?: string; plans?: Record<SmartPlanModes, unknown>; reanalysis_free?: boolean; billing_action?: SmartLayoutBillingAction };
type SmartQuotaStatus = { available: boolean; reason?: "rollout" | "ready" | "upgrade" | "pass_exhausted"; plan?: string;
  allowance?: number; used?: number; remaining?: number; daily_cap?: number;
  daily_used?: number; daily_remaining?: number; period_end?: string | null; };
const styles = [
  ["kinetic", "Kinetic", "Punchy highlighted words"],
  ["clean", "Clean", "Readable creator standard"],
  ["bold", "Bold", "Large high-contrast impact"],
  ["minimal", "Minimal", "Quiet and professional"],
  ["hindi-pop", "India Pop", "Hindi and Hinglish energy"],
] as const;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);
const emptyEditPlan = (): EditPlan => ({ version: 2, removed_ranges: [], split_points: [], segment_order: [0] });
const rangeContains = (range: RemovedRange, time: number) => time >= range.start && time < range.end;
const MIN_SEGMENT_KEEP = .25;

function mergeRemovedRanges(ranges: RemovedRange[]): RemovedRange[] {
  const sorted = ranges.map(range => ({ ...range })).sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: RemovedRange[] = [];
  sorted.forEach(range => {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end + .001) {
      previous.end = Math.max(previous.end, range.end);
      if (previous.reason !== range.reason) previous.reason = "mixed";
    } else {
      merged.push(range);
    }
  });
  return merged;
}

function segmentTrimReason(edge: "left" | "right", segment: { start: number; end: number }) {
  return `trim-${edge === "left" ? "l" : "r"}-${(edge === "left" ? segment.start : segment.end).toFixed(3)}`;
}

function findSegmentTrimRange(segment: { start: number; end: number }, edge: "left" | "right", ranges: RemovedRange[]) {
  const exactReason = segmentTrimReason(edge, segment);
  const exact = ranges.find(range => range.reason === exactReason);
  if (exact) return exact;
  return ranges.find(range => {
    if (!(range.reason === "mixed" || range.reason.startsWith("trim-"))) return false;
    if (edge === "left") {
      return Math.abs(range.start - segment.start) < .02 && range.end < segment.end - MIN_SEGMENT_KEEP;
    }
    return Math.abs(range.end - segment.end) < .02 && range.start > segment.start + MIN_SEGMENT_KEEP;
  });
}

function segmentTrimBounds(segment: { start: number; end: number }, ranges: RemovedRange[]) {
  const left = findSegmentTrimRange(segment, "left", ranges);
  const right = findSegmentTrimRange(segment, "right", ranges);
  const visibleStart = clamp(left?.end ?? segment.start, segment.start, segment.end - MIN_SEGMENT_KEEP);
  const visibleEnd = clamp(right?.start ?? segment.end, segment.start + MIN_SEGMENT_KEEP, segment.end);
  return {
    visibleStart,
    visibleEnd: Math.max(visibleEnd, visibleStart + MIN_SEGMENT_KEEP),
    left,
    right,
  };
}

function keptPiecesForSegment(segment: { start: number; end: number }, ranges: RemovedRange[]) {
  let cursor = segment.start;
  const pieces: Array<{ start: number; end: number }> = [];
  for (const range of ranges) {
    const cutStart = Math.max(segment.start, range.start);
    const cutEnd = Math.min(segment.end, range.end);
    if (cutEnd <= segment.start || cutStart >= segment.end) continue;
    if (cutStart > cursor + .001) pieces.push({ start: cursor, end: cutStart });
    cursor = Math.max(cursor, cutEnd);
    if (cursor >= segment.end) break;
  }
  if (segment.end > cursor + .001) pieces.push({ start: cursor, end: segment.end });
  return pieces;
}

function validSegmentOrder(plan: EditPlan, count: number) {
  const natural = Array.from({ length: count }, (_, index) => index);
  const order = plan.segment_order || [];
  if (order.length !== count) return natural;
  const sorted = [...order].sort((a, b) => a - b);
  return sorted.every((value, index) => value === natural[index]) ? [...order] : natural;
}

export default function Editor() {
  const { clipId } = useParams<{ clipId: string }>();
  const projectId = useSearchParams().get("project");
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const secondaryVideoRef = useRef<HTMLVideoElement>(null);
  const smartCanvasRef = useRef<HTMLCanvasElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const captionContentRef = useRef<HTMLSpanElement>(null);
  const captionDragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const timelineScrubRef = useRef<{ pointerId: number; element: HTMLDivElement } | null>(null);
  const videoTrackRef = useRef<HTMLDivElement>(null);
  const playbackPieceIndexRef = useRef<number | null>(null);
  const trimDragRef = useRef<{
    pointerId: number;
    segmentIndex: number;
    edge: "left" | "right";
    element: HTMLButtonElement;
    track: HTMLDivElement;
    segment: { start: number; end: number };
    basePlan: EditPlan;
    draftPlan: EditPlan;
    visualStart: number;
    visualEnd: number;
    visualSourceStart: number;
    visualSourceEnd: number;
    visualTimelineDuration: number;
  } | null>(null);
  const behaviorSessionRef = useRef("");
  const previewLogged = useRef(false);
  const renderStartRef = useRef(false);
  const activeJobRef = useRef("");
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const lastPlanRef = useRef<string | null>(null);
  if (!behaviorSessionRef.current) behaviorSessionRef.current = newBehaviorSession();
  const [project, setProject] = useState<Project | null>(null);
  const [clip, setClip] = useState<Clip | null>(null);
  const [loadError, setLoadError] = useState("");
  const [hook, setHook] = useState("");
  const [hookEnabled, setHookEnabled] = useState(true);
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(30);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [captionStyle, setCaptionStyle] = useState("kinetic");
  const [captionPosition, setCaptionPosition] = useState<"bottom" | "above" | "center">("bottom");
  const [captionX, setCaptionX] = useState(50);
  const [captionY, setCaptionY] = useState<number | null>(null);
  const [captionScale, setCaptionScale] = useState(1);
  const [captionAlignment, setCaptionAlignment] = useState<CaptionAlignment>("center");
  const [captionDragging, setCaptionDragging] = useState(false);
  const [ratio, setRatio] = useState("9:16");
  const [layoutMode, setLayoutMode] = useState<"auto" | "dual_stack" | "speaker_focus" | "classic">("classic");
  const [layoutPlans, setLayoutPlans] = useState<Record<SmartPlanModes, SmartLayoutPlan> | null>(null);
  const [layoutPlansClipKey, setLayoutPlansClipKey] = useState<string | null>(null);
  const [layoutAnalysis, setLayoutAnalysis] = useState<"idle" | "analyzing" | "ready" | "error">("idle");
  const [layoutAnalysisError, setLayoutAnalysisError] = useState("");
  const [analysisConfirmedFor, setAnalysisConfirmedFor] = useState<string | null>(null);
  const clipAnalysisKey = clip ? `${clip.id}:${clip.start_time}:${clip.end_time}` : "";
  const analysisConfirmed = !!clipAnalysisKey && analysisConfirmedFor === clipAnalysisKey;
  const [freeReanalysis, setFreeReanalysis] = useState(false);
  const [layoutBilling, setLayoutBilling] = useState<{ clipKey: string; action: SmartLayoutBillingAction } | null>(null);
  const layoutBillingRef = useRef<{ clipKey: string; action: SmartLayoutBillingAction } | null>(null);
  const currentBillingAction = layoutBilling?.clipKey === clipAnalysisKey ? layoutBilling.action : null;
  const recordLayoutBilling = useCallback((clipKey: string, action: SmartLayoutBillingAction) => {
    const value = { clipKey, action };
    layoutBillingRef.current = value;
    setLayoutBilling(value);
  }, []);
  const [smartQuota, setSmartQuota] = useState<SmartQuotaStatus | null>(null);
  const smartClipCost = clip ? Math.max(1, Math.ceil(((clip.end_time - clip.start_time) - .00000001) / 60)) : 1;
  const smartClipCostText = smartClipCost + (smartClipCost === 1 ? " credit" : " credits");
  const [smartCapability, setSmartCapability] = useState<"checking" | "ready" | "unavailable">("checking");
  const SMART_LAYOUT_V2_ENABLED = smartCapability === "ready";
  const [focusX, setFocusX] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [resolution, setResolution] = useState("720p");
  const [watermark, setWatermark] = useState(true);
  const [activeTool, setActiveTool] = useState<WorkspaceTool>("edit");
  const [saving, setSaving] = useState(false);
  const [startingRender, setStartingRender] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [exportId, setExportId] = useState("");
  const [exportLayoutMode, setExportLayoutMode] = useState<"classic" | SmartPlanModes | null>(null);
  const [error, setError] = useState("");
  const [drawerDismissed, setDrawerDismissed] = useState(false);
  const [timedCaptionWords, setTimedCaptionWords] = useState<TimedWord[]>([]);
  const [sourceWords, setSourceWords] = useState<TimedWord[]>([]);
  const [editPlan, setEditPlan] = useState<EditPlan>(emptyEditPlan);
  const [cleanSpeechRanges, setCleanSpeechRanges] = useState<RemovedRange[]>([]);
  const [undoPlans, setUndoPlans] = useState<EditPlan[]>([]);
  const [redoPlans, setRedoPlans] = useState<EditPlan[]>([]);
  const [captionCards, setCaptionCards] = useState<CaptionCard[]>([]);
  const [speechRegions, setSpeechRegions] = useState<SpeechRegion[]>([]);
  const [sourceHasCaptions, setSourceHasCaptions] = useState(false);
  const [sourceCaptionBand, setSourceCaptionBand] = useState<number | null>(null);
  const [preserveSourceCaptions, setPreserveSourceCaptions] = useState(false);
  const [indiaQualityMode, setIndiaQualityMode] = useState(false);
  const [captionLanguageStyle, setCaptionLanguageStyle] = useState<CaptionLanguageStyle>("auto");
  const [indiaQualityHint, setIndiaQualityHint] = useState("");
  const [reviewSuggested, setReviewSuggested] = useState(false);
  const [reviewReasons, setReviewReasons] = useState<string[]>([]);
  const [captionStyles, setCaptionStyles] = useState<CaptionStyle[]>([]);
  const [brandKits, setBrandKits] = useState<BrandKit[]>([]);
  const [brandKitId, setBrandKitId] = useState("");
  const [postKaro, setPostKaro] = useState<PostKaroStatus | null>(null);
  const [showPostKaroPrompt, setShowPostKaroPrompt] = useState(false);
  const [selectedSegmentIndex, setSelectedSegmentIndex] = useState<number | null>(null);
  const [timelineScrubbing, setTimelineScrubbing] = useState(false);
  const [trimmingSegment, setTrimmingSegment] = useState(false);
  const [draggedSegmentIndex, setDraggedSegmentIndex] = useState<number | null>(null);
  const [dragOverSegmentIndex, setDragOverSegmentIndex] = useState<number | null>(null);

  // V2 ONLY: show actual crop analysis, not duplicated placeholder speakers.
  // Until the authenticated backend accepts this user, the canvas stays a
  // single honest source frame and never simulates multiple detected faces.
  const smartRequested = SMART_LAYOUT_V2_ENABLED && ratio === "9:16" && layoutMode !== "classic" && !preserveSourceCaptions;
  const verifiedLayoutPlans = layoutPlans && clip && layoutPlansClipKey === clipAnalysisKey
    && Math.abs(layoutPlans.auto.source_start - clip.start_time) <= .02
    && Math.abs(layoutPlans.auto.duration - (clip.end_time - clip.start_time)) <= .02 ? layoutPlans : null;
  const realPlan = smartRequested && verifiedLayoutPlans && layoutAnalysis !== "error" ? verifiedLayoutPlans[layoutMode] : null;
  const smartClipBillingLabel = (() => {
    if (realPlan) {
      if (currentBillingAction === "new_charge") return smartClipCostText + " used";
      if (currentBillingAction === "free_refresh") return "Free refresh · 0 new credits";
      if (currentBillingAction === "existing_job") return "Existing result · no additional charge";
      if (currentBillingAction === "cached_reuse") return "Saved result · 0 new credits";
      return "Result ready · billing status unavailable";
    }
    if (layoutAnalysis === "analyzing") {
      if (currentBillingAction === "existing_job") return "Existing analysis · no additional charge";
      if (currentBillingAction === "free_refresh" || freeReanalysis) return "Free refresh in progress";
      if (currentBillingAction === "new_charge") return smartClipCostText + " reserved";
      return smartClipCostText + " · pending";
    }
    return freeReanalysis ? "Free refresh" : smartClipCostText;
  })();
  const actualScene = realPlan ? findScene(realPlan, playhead) : null;
  const dualStackCoverage = realPlan && layoutMode === "dual_stack" ? dualStackCoverageSeconds(realPlan) : null;
  const currentExportLayoutMode = ratio === "9:16" ? layoutMode : "classic";
  const exportedLayoutIsStale = exportLayoutMode !== null && exportLayoutMode !== currentExportLayoutMode;
  const previewDual = false;
  const previewFocus = false;

  useEffect(() => {
    let active = true;
    api<SmartQuotaStatus>("/smart-layout-v2/capabilities")
      .then(value => { if (active) { setSmartQuota(value); setSmartCapability(value.available ? "ready" : "unavailable"); } })
      .catch(() => { if (active) setSmartCapability("unavailable"); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!previewDual) return;
    const source = videoRef.current;
    const mirror = secondaryVideoRef.current;
    if (!source || !mirror) return;
    const sync = () => {
      if (Number.isFinite(source.currentTime) && mirror.readyState >= 1
          && Math.abs(mirror.currentTime - source.currentTime) > .12) {
        mirror.currentTime = source.currentTime;
      }
      if (mirror.playbackRate !== source.playbackRate) mirror.playbackRate = source.playbackRate;
      if (source.paused || source.ended) mirror.pause();
      else if (mirror.paused) void mirror.play().catch(() => {});
    };
    for (const name of ["timeupdate", "seeked", "play", "pause", "ratechange", "loadedmetadata"]) {
      source.addEventListener(name, sync);
    }
    mirror.addEventListener("loadedmetadata", sync);
    sync();
    return () => {
      for (const name of ["timeupdate", "seeked", "play", "pause", "ratechange", "loadedmetadata"]) {
        source.removeEventListener(name, sync);
      }
      mirror.removeEventListener("loadedmetadata", sync);
      mirror.pause();
    };
  }, [previewDual, project?.id]);

  useEffect(() => {
    // Consent, plans and billing outcome are scoped to this exact clip/range.
    // The render-time key check below prevents stale plans being used before this effect runs.
    setAnalysisConfirmedFor(null);
    setFreeReanalysis(false);
    setLayoutPlans(null);
    setLayoutPlansClipKey(null);
    setLayoutAnalysis("idle");
    setLayoutAnalysisError("");
    layoutBillingRef.current = null;
    setLayoutBilling(null);
  }, [clip?.id, clip?.start_time, clip?.end_time]);

  useEffect(() => {
    if (!SMART_LAYOUT_V2_ENABLED || !clip?.id || !smartRequested || verifiedLayoutPlans || layoutAnalysis === "error") return;
    let disposed = false;
    let poll: number | null = null;
    let requested = false;
    let attempts = 0;
    const check = async (): Promise<void> => {
      try {
        let status = await api<LayoutAnalysisResponse>(`/clips/${clip.id}/smart-layout-v2`);
        if (status.status === "not_started" && !requested) {
          // An earlier paid analysis is free to refresh even when the cache
          // expired. The server owns this flag; frontend never invents it.
          if (!disposed) setFreeReanalysis(!!status.reanalysis_free);
          if (!analysisConfirmed || disposed) return;
          requested = true;
          status = await postJSON<LayoutAnalysisResponse>(`/clips/${clip.id}/smart-layout-v2`, {});
          if (disposed) return;
          recordLayoutBilling(clipAnalysisKey, status.billing_action ?? "unknown");
          if (status.billing_action === "free_refresh") setFreeReanalysis(true);
        }
        if (disposed) return;
        if (status.status === "ready" && status.plans) {
          const currentBilling = layoutBillingRef.current;
          if (!currentBilling || currentBilling.clipKey !== clipAnalysisKey || currentBilling.action === "unknown") {
            recordLayoutBilling(clipAnalysisKey, status.billing_action ?? "unknown");
          }
          const next = {} as Record<SmartPlanModes, SmartLayoutPlan>;
          for (const mode of ["auto", "dual_stack", "speaker_focus"] as const) {
            const item = parseSmartLayoutPlan(status.plans[mode]);
            if (!item || item.requested_mode !== mode
                || Math.abs(item.source_start - clip.start_time) > .02
                || Math.abs(item.duration - (clip.end_time - clip.start_time)) > .02) {
              throw new Error("Private framing analysis does not match this clip.");
            }
            next[mode] = item;
          }
          setLayoutPlans(next);
          setLayoutPlansClipKey(clipAnalysisKey);
          setLayoutAnalysis("ready");
          void api<SmartQuotaStatus>("/smart-layout-v2/capabilities")
            .then(balance => { if (!disposed) setSmartQuota(balance); })
            .catch(() => {});
          return;
        }
        if ((status.status === "queued" || status.status === "processing") && ++attempts <= 120) {
          setLayoutAnalysis("analyzing");
          const currentBilling = layoutBillingRef.current;
          if (status.billing_action && (!currentBilling || currentBilling.clipKey !== clipAnalysisKey)) {
            recordLayoutBilling(clipAnalysisKey, status.billing_action);
          }
          poll = window.setTimeout(() => { void check(); }, 2000);
          return;
        }
        throw new Error("Preview analysis was not completed. Try again later.");
      } catch (reason) {
        if (!disposed) {
          setLayoutAnalysis("error");
          setLayoutAnalysisError(reason instanceof Error ? reason.message : "Preview analysis is unavailable.");
          layoutBillingRef.current = null;
          setLayoutBilling(null);
          setFreeReanalysis(false);
          void api<SmartQuotaStatus>("/smart-layout-v2/capabilities")
            .then(balance => { if (!disposed) setSmartQuota(balance); })
            .catch(() => {});
        }
      }
    };
    void check();
    return () => { disposed = true; if (poll !== null) window.clearTimeout(poll); };
  }, [clipAnalysisKey, smartRequested, verifiedLayoutPlans, layoutAnalysis, analysisConfirmed, recordLayoutBilling]);

  useEffect(() => {
    if (!realPlan) return;
    const video = videoRef.current;
    const canvas = smartCanvasRef.current;
    if (!video || !canvas) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    let cancelled = false;
    let frameHandle = 0;
    let timerHandle = 0;
    const draw = () => {
      if (cancelled) return;
      try {
        paintSmartLayoutFrame(ctx, video, realPlan, video.currentTime);
      } catch {
        setLayoutPlans(null);
        setLayoutAnalysis("error");
        setLayoutAnalysisError("The private media preview cannot be drawn securely. Retry later.");
      }
    };
    const tick = () => {
      draw();
      if (cancelled) return;
      if (typeof video.requestVideoFrameCallback === "function") {
        frameHandle = video.requestVideoFrameCallback(() => tick());
      } else {
        timerHandle = window.requestAnimationFrame(tick);
      }
    };
    video.addEventListener("seeked", draw);
    video.addEventListener("loadeddata", draw);
    tick();
    return () => {
      cancelled = true;
      video.removeEventListener("seeked", draw);
      video.removeEventListener("loadeddata", draw);
      if (frameHandle && typeof video.cancelVideoFrameCallback === "function") video.cancelVideoFrameCallback(frameHandle);
      if (timerHandle) window.cancelAnimationFrame(timerHandle);
    };
  }, [realPlan, clip?.id]);

  const freePlan = user?.plan === "free";
  const renderBusy = startingRender || (!!job && !["completed", "failed"].includes(job.status));

  const stopJobWatch = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const load = useCallback(async () => {
    if (!projectId) { setLoadError("The project reference is missing from this editor link."); return; }
    setLoadError("");
    try {
      const data = await api<Project>(`/projects/${projectId}`);
      const selected = data.clips.find(item => item.id === clipId);
      if (!selected) throw new Error("This clip no longer exists in the project.");
      setLayoutPlans(null); setLayoutAnalysis("idle"); setLayoutAnalysisError("");
      setProject(data); setClip(selected); setHook(selected.hook); setTitle(selected.title);
      setTranscript(selected.transcript_text || selected.hook);
      setStart(selected.start_time); setEnd(selected.end_time); setPlayhead(selected.start_time);
      api<CaptionTrack>(`/clips/${clipId}/captions`).then(track => {
        const hasSourceCaptions = !!track.source_has_burned_captions;
        const source = track.source_words || track.words;
        setSourceWords(source); setTimedCaptionWords(source); setCaptionCards(track.source_words ? [] : (track.cards || [])); setSpeechRegions(track.speech_regions || []);
        if (track.edit_plan?.layout_mode) setLayoutMode(track.edit_plan.layout_mode);
        setEditPlan(track.edit_plan || emptyEditPlan()); setCleanSpeechRanges(track.clean_speech_ranges || []); setUndoPlans([]); setRedoPlans([]);
        setSourceHasCaptions(hasSourceCaptions); setSourceCaptionBand(track.source_caption_band ?? null);
        setReviewSuggested(!!track.review_suggested); setReviewReasons(track.review_reasons || []);
        setIndiaQualityHint(track.india_quality?.india_quality_suitable ? `${track.india_quality.likely_language_style || "Indian speech"} detected` : "");
        // A previously saved Smart Layout must not be silently disabled just
        // because the original upload contained burned-in subtitles.
        if (hasSourceCaptions) {
          setPreserveSourceCaptions(!track.edit_plan?.layout_mode || track.edit_plan.layout_mode === "classic");
        }
      }).catch(() => { setTimedCaptionWords([]); setSourceWords([]); setEditPlan(emptyEditPlan()); setCleanSpeechRanges([]); setCaptionCards([]); setSpeechRegions([]); setSourceHasCaptions(false); setSourceCaptionBand(null); setPreserveSourceCaptions(false); setReviewSuggested(false); setReviewReasons([]); setIndiaQualityHint(""); });
    } catch (cause) {
      setLoadError(cause instanceof Error ? cause.message : "The project could not be loaded.");
    }
  }, [projectId, clipId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api<CaptionStyle[]>("/caption-styles").then(setCaptionStyles).catch(() => setCaptionStyles([])); }, []);
  useEffect(() => {
    api<BrandKit[]>("/brand-kits").then(kits => {
      setBrandKits(kits);
      const preferred = kits.find(kit => kit.is_default);
      if (preferred) { setBrandKitId(preferred.id); if (styles.some(style => style[0] === preferred.caption_preset)) setCaptionStyle(preferred.caption_preset); }
    }).catch(() => setBrandKits([]));
  }, []);
  useEffect(() => {
    if (!user || lastPlanRef.current === user.plan) return;
    setWatermark(user.plan === "free");
    setResolution(user.plan === "free" ? "720p" : "1080p");
    lastPlanRef.current = user.plan;
  }, [user]);
  useEffect(() => {
    if (!user) return;
    api<PostKaroStatus>("/post-karo/status").then(setPostKaro).catch(() => setPostKaro(null));
  }, [user?.plan]);
  useEffect(() => {
    if (indiaQualityMode && preserveSourceCaptions && captionY === null && captionPosition === "bottom") {
      setCaptionPosition("above");
    }
    if (preserveSourceCaptions && zoom !== 1) setZoom(1);
  }, [indiaQualityMode, preserveSourceCaptions, captionPosition, captionY, zoom]);
  useEffect(() => {
    if (!clip) return;
    trackClipBehavior(clip.id, "selected", {
      sessionId: behaviorSessionRef.current,
      eventId: `${behaviorSessionRef.current}:selected:${clip.id}`,
      surface: "editor",
    });
  }, [clip?.id]);
  useEffect(() => () => stopJobWatch(), [stopJobWatch]);

  const captionWords = useMemo(() => transcript.trim().split(/\s+/).filter(Boolean), [transcript]);
  const wordRemoved = useCallback((word: TimedWord, plan = editPlan) => plan.removed_ranges.some(range => word.start < range.end && word.end > range.start), [editPlan]);
  const timelineSpan = Math.max(end - start, 1);
  const mergedRemovedRanges = useMemo(() => mergeRemovedRanges(editPlan.removed_ranges), [editPlan.removed_ranges]);
  const pauseBlocks = useMemo(() => sourceWords.slice(1).map((word, index) => ({ start: sourceWords[index].end, end: word.start, reason: "silence" })).filter(item => item.end - item.start >= .25), [sourceWords]);
  const timelineSegments = useMemo(() => {
    const duration = Math.max(end - start, .1);
    const points = editPlan.split_points.filter(point => point > .05 && point < duration - .05).sort((a, b) => a - b);
    const boundaries = [0, ...points, duration];
    return boundaries.slice(0, -1).map((segmentStart, index) => ({
      start: segmentStart,
      end: boundaries[index + 1],
    }));
  }, [editPlan.split_points, start, end]);
  const segmentOrder = useMemo(() => validSegmentOrder(editPlan, timelineSegments.length), [editPlan.segment_order, timelineSegments.length]);
  const displayTimelineSegments = useMemo(() => timelineSegments.map(segment => {
    const bounds = segmentTrimBounds(segment, editPlan.removed_ranges);
    const fullyRemoved = mergedRemovedRanges.some(range => range.start <= segment.start + .01 && range.end >= segment.end - .01);
    return { ...segment, ...bounds, fullyRemoved };
  }), [timelineSegments, editPlan.removed_ranges, mergedRemovedRanges]);
  const timelineLayout = useMemo(() => {
    let outputCursor = 0;
    const pieces: Array<{ sourceStart: number; sourceEnd: number; outputStart: number; outputEnd: number; segmentIndex: number }> = [];
    const segments = segmentOrder.map(sourceIndex => {
      const sourceSegment = displayTimelineSegments[sourceIndex];
      const kept = sourceSegment ? keptPiecesForSegment(sourceSegment, mergedRemovedRanges) : [];
      const outputStart = outputCursor;
      kept.forEach(piece => {
        const length = piece.end - piece.start;
        pieces.push({
          sourceStart: piece.start,
          sourceEnd: piece.end,
          outputStart: outputCursor,
          outputEnd: outputCursor + length,
          segmentIndex: sourceIndex,
        });
        outputCursor += length;
      });
      return sourceSegment ? {
        ...sourceSegment,
        sourceIndex,
        outputStart,
        outputEnd: outputCursor,
        outputDuration: outputCursor - outputStart,
      } : null;
    }).filter((segment): segment is NonNullable<typeof segment> => !!segment);
    return { pieces, segments, duration: outputCursor };
  }, [segmentOrder, displayTimelineSegments, mergedRemovedRanges]);
  const visualTimelineLayout = useMemo(() => {
    let visualCursor = 0;
    const segments = segmentOrder.map(sourceIndex => {
      const sourceSegment = displayTimelineSegments[sourceIndex];
      if (!sourceSegment) return null;
      const visualStart = visualCursor;
      const sourceDuration = sourceSegment.end - sourceSegment.start;
      visualCursor += sourceDuration;
      return {
        ...sourceSegment,
        sourceIndex,
        visualStart,
        visualEnd: visualCursor,
        visualDuration: sourceDuration,
      };
    }).filter((segment): segment is NonNullable<typeof segment> => !!segment);
    return { segments, duration: Math.max(visualCursor, .1) };
  }, [segmentOrder, displayTimelineSegments]);
  const visualRemovedRanges = useMemo(() => visualTimelineLayout.segments.flatMap(segment =>
    mergedRemovedRanges.flatMap(range => {
      const startInSegment = Math.max(segment.start, range.start);
      const endInSegment = Math.min(segment.end, range.end);
      if (endInSegment <= startInSegment + .001) return [];
      return [{
        start: segment.visualStart + (startInSegment - segment.start),
        end: segment.visualStart + (endInSegment - segment.start),
      }];
    }),
  ), [visualTimelineLayout.segments, mergedRemovedRanges]);
  const editedDuration = Math.max(MIN_SEGMENT_KEEP, timelineLayout.duration);
  const selectedSegment = selectedSegmentIndex === null ? null : timelineSegments[selectedSegmentIndex] || null;
  const selectedDisplaySegment = selectedSegmentIndex === null ? null : displayTimelineSegments[selectedSegmentIndex] || null;
  const selectedOrderPosition = selectedSegmentIndex === null ? -1 : segmentOrder.indexOf(selectedSegmentIndex);
  const selectedSegmentRemoved = !!selectedDisplaySegment?.fullyRemoved;
  const selectedSegmentHasTrim = !!selectedDisplaySegment && (
    selectedDisplaySegment.visibleStart > selectedDisplaySegment.start + .01 ||
    selectedDisplaySegment.visibleEnd < selectedDisplaySegment.end - .01
  );
  const orderedAllSourceWords = useMemo(() => segmentOrder.flatMap(segmentIndex => {
    const segment = timelineSegments[segmentIndex];
    if (!segment) return [];
    return sourceWords.filter(word =>
      word.start >= segment.start - .001 &&
      word.start < segment.end - .001
    );
  }), [segmentOrder, timelineSegments, sourceWords]);
  const orderedSourceWords = useMemo(
    () => orderedAllSourceWords.filter(word => !wordRemoved(word)),
    [orderedAllSourceWords, editPlan, wordRemoved],
  );
  useEffect(() => {
    if (!sourceWords.length) return;
    setTranscript(orderedSourceWords.map(word => word.text).join(" "));
  }, [sourceWords, editPlan, orderedSourceWords]);

  const sourceRelativeToOutput = useCallback((relative: number) => {
    for (let index = 0; index < timelineLayout.pieces.length; index += 1) {
      const piece = timelineLayout.pieces[index];
      if (relative >= piece.sourceStart - .001 && relative <= piece.sourceEnd + .001) {
        return piece.outputStart + clamp(relative - piece.sourceStart, 0, piece.sourceEnd - piece.sourceStart);
      }
    }
    return null;
  }, [timelineLayout.pieces]);

  const outputToSourceRelative = useCallback((outputTime: number) => {
    const safe = clamp(outputTime, 0, editedDuration);
    const pieces = timelineLayout.pieces;
    for (let index = 0; index < pieces.length; index += 1) {
      const piece = pieces[index];
      const isLast = index === pieces.length - 1;
      if (safe < piece.outputEnd - .001 || (isLast && safe <= piece.outputEnd + .001)) {
        return {
          source: piece.sourceStart + clamp(safe - piece.outputStart, 0, piece.sourceEnd - piece.sourceStart),
          pieceIndex: index,
          segmentIndex: piece.segmentIndex,
        };
      }
    }
    const last = pieces.at(-1);
    return last ? { source: last.sourceEnd, pieceIndex: pieces.length - 1, segmentIndex: last.segmentIndex } : null;
  }, [timelineLayout.pieces, editedDuration]);

  const sourceRelativeToVisual = useCallback((relative: number) => {
    const sourceIndex = timelineSegments.findIndex((segment, index) =>
      relative >= segment.start - .001 &&
      (relative < segment.end - .001 || (index === timelineSegments.length - 1 && relative <= segment.end + .001)),
    );
    if (sourceIndex < 0) return null;
    const visual = visualTimelineLayout.segments.find(segment => segment.sourceIndex === sourceIndex);
    const source = timelineSegments[sourceIndex];
    if (!visual || !source) return null;
    return visual.visualStart + clamp(relative - source.start, 0, source.end - source.start);
  }, [timelineSegments, visualTimelineLayout.segments]);

  const visualToSourceRelative = useCallback((visualTime: number) => {
    const safe = clamp(visualTime, 0, visualTimelineLayout.duration);
    const segments = visualTimelineLayout.segments;
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      const isLast = index === segments.length - 1;
      if (safe < segment.visualEnd - .001 || (isLast && safe <= segment.visualEnd + .001)) {
        return {
          source: segment.start + clamp(safe - segment.visualStart, 0, segment.end - segment.start),
          segmentIndex: segment.sourceIndex,
        };
      }
    }
    const last = segments.at(-1);
    return last ? { source: last.end, segmentIndex: last.sourceIndex } : null;
  }, [visualTimelineLayout]);

  const timelineCaptionBlocks = useMemo(() => {
    const blocks: Array<{ start: number; end: number; text: string }> = [];
    segmentOrder.forEach(segmentIndex => {
      const segment = timelineSegments[segmentIndex];
      if (!segment) return;
      const mapped = orderedSourceWords
        .filter(word => word.start >= segment.start - .001 && word.start < segment.end - .001)
        .map(word => ({
          word,
          start: sourceRelativeToVisual(word.start),
          end: sourceRelativeToVisual(word.end),
        }))
        .filter(item => item.start !== null && item.end !== null && (item.end as number) > (item.start as number));
      for (let index = 0; index < mapped.length; index += 4) {
        const chunk = mapped.slice(index, index + 4);
        if (!chunk.length) continue;
        blocks.push({
          start: chunk[0].start as number,
          end: chunk[chunk.length - 1].end as number,
          text: chunk.map(item => item.word.text).join(" "),
        });
      }
    });
    return blocks;
  }, [orderedSourceWords, segmentOrder, timelineSegments, sourceRelativeToVisual]);

  const captionState = useMemo(() => {
    if (!captionWords.length) return { words: ["Add", "your", "caption", "text"], active: 0, uncertain: [] as boolean[], breakAfter: -1, visible: true };
    const sourceRelative = playhead - start;
    const outputRelative = sourceRelativeToOutput(sourceRelative) ?? 0;
    const reordered = segmentOrder.some((value, index) => value !== index);
    // Once real timing exists, silence must be visually silent too — even after segment reorder.
    const speechActive = !speechRegions.length || speechRegions.some(region => sourceRelative >= region.start && sourceRelative < region.end);
    if (!speechActive) {
      return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
    }
    if (sourceWords.length && (editPlan.removed_ranges.length > 0 || reordered)) {
      const visible = orderedSourceWords;
      const active = visible.findIndex(word => sourceRelative >= word.start && sourceRelative < word.end);
      if (active < 0) return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
      const chunkStart = Math.floor(active / 4) * 4;
      const chunk = visible.slice(chunkStart, chunkStart + 4);
      return { words: chunk.map(word => word.text), active: active - chunkStart,
        uncertain: chunk.map(word => (word.confidence ?? 1) < .6), breakAfter: -1, visible: true };
    }
    const liveCard = captionCards.find(card => outputRelative >= card.start && outputRelative < card.end);
    if (liveCard) {
      const flat = liveCard.lines.join(" ").split(/\s+/).filter(Boolean);
      let active = liveCard.words.findIndex(word => outputRelative >= word.start && outputRelative < word.end);
      if (active < 0) liveCard.words.forEach((word, index) => { if (word.start <= outputRelative) active = index; });
      return { words: flat, active: clamp(active, 0, Math.max(flat.length - 1, 0)),
               uncertain: liveCard.words.map(word => (word.confidence ?? 1) < .6),
               breakAfter: liveCard.lines.length === 2 ? liveCard.lines[0].split(/\s+/).length : -1,
               visible: true };
    }
    if (sourceWords.length) {
      const visible = sourceWords.filter(word => !wordRemoved(word));
      const active = visible.findIndex(word => sourceRelative >= word.start && sourceRelative < word.end);
      if (active < 0) return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
      const chunkStart = Math.floor(active / 4) * 4;
      const chunk = visible.slice(chunkStart, chunkStart + 4);
      return { words: chunk.map(word => word.text), active: active - chunkStart,
        uncertain: chunk.map(word => (word.confidence ?? 1) < .6), breakAfter: -1, visible: true };
    }
    if (timedCaptionWords.length || captionCards.length) {
      return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
    }
    const chunkSize = 4;
    const wordIndex = clamp(
      Math.floor(clamp(outputRelative / editedDuration, 0, .999) * captionWords.length),
      0,
      captionWords.length - 1,
    );
    const chunkStart = Math.floor(wordIndex / chunkSize) * chunkSize;
    const chunk = captionWords.slice(chunkStart, chunkStart + chunkSize);
    return { words: chunk, active: wordIndex - chunkStart, uncertain: chunk.map(() => false), breakAfter: -1, visible: true };
  }, [captionWords, timedCaptionWords, captionCards, sourceWords, orderedSourceWords, wordRemoved, speechRegions, playhead, start, sourceRelativeToOutput, segmentOrder, editPlan.removed_ranges, editedDuration]);

  function commitEditPlan(next: EditPlan) {
    setUndoPlans(history => [...history.slice(-49), editPlan]);
    setRedoPlans([]);
    setEditPlan(next);
  }

  function removeRange(range: RemovedRange) {
    if (editPlan.removed_ranges.some(item => Math.abs(item.start - range.start) < .01 && Math.abs(item.end - range.end) < .01)) return;
    commitEditPlan({ ...editPlan, removed_ranges: [...editPlan.removed_ranges, range].sort((a, b) => a.start - b.start) });
  }

  function restoreRange(range: RemovedRange) {
    commitEditPlan({ ...editPlan, removed_ranges: editPlan.removed_ranges.filter(item => item !== range) });
  }

  function undoEdit() {
    const previous = undoPlans.at(-1); if (!previous) return;
    setUndoPlans(history => history.slice(0, -1)); setRedoPlans(history => [...history, editPlan]); setEditPlan(previous);
  }

  function redoEdit() {
    const next = redoPlans.at(-1); if (!next) return;
    setRedoPlans(history => history.slice(0, -1)); setUndoPlans(history => [...history, editPlan]); setEditPlan(next);
  }

  function splitAtPlayhead() {
    const point = Number(clamp(playhead - start, .05, end - start - .05).toFixed(3));
    if (editPlan.removed_ranges.some(range => rangeContains(range, point))) { setError("Move the playhead onto a kept section before splitting."); return; }
    if (editPlan.split_points.some(item => Math.abs(item - point) < .05)) return;
    const sourceSegmentIndex = timelineSegments.findIndex((segment, index) =>
      point >= segment.start && (point < segment.end || (index === timelineSegments.length - 1 && point <= segment.end)),
    );
    const splitPoints = [...editPlan.split_points, point].sort((a, b) => a - b);
    const currentOrder = segmentOrder;
    const nextOrder = sourceSegmentIndex < 0 ? Array.from({ length: splitPoints.length + 1 }, (_, index) => index) :
      currentOrder.flatMap(index => {
        if (index === sourceSegmentIndex) return [index, index + 1];
        return [index > sourceSegmentIndex ? index + 1 : index];
      });
    commitEditPlan({ ...editPlan, version: 2, split_points: splitPoints, segment_order: nextOrder });
    setSelectedSegmentIndex(sourceSegmentIndex < 0 ? splitPoints.filter(item => item <= point + .001).length : sourceSegmentIndex + 1);
  }

  function selectSegmentForRelative(relative: number) {
    const safe = clamp(relative, 0, timelineSpan);
    const index = timelineSegments.findIndex((segment, segmentIndex) =>
      safe >= segment.start && (safe < segment.end || (segmentIndex === timelineSegments.length - 1 && safe <= segment.end)),
    );
    if (index >= 0) setSelectedSegmentIndex(index);
  }

  function seekTimelineRelative(visualTime: number, select = true) {
    const mapped = visualToSourceRelative(visualTime);
    if (!mapped) return;
    if (select) setSelectedSegmentIndex(mapped.segmentIndex);
    let source = mapped.source;
    let pieceIndex = timelineLayout.pieces.findIndex(piece =>
      piece.segmentIndex === mapped.segmentIndex &&
      source >= piece.sourceStart - .001 &&
      source <= piece.sourceEnd + .001,
    );
    if (pieceIndex < 0) {
      const candidates = timelineLayout.pieces
        .map((piece, index) => ({ piece, index }))
        .filter(item => item.piece.segmentIndex === mapped.segmentIndex);
      if (!candidates.length) return;
      let closest = { ...candidates[0], distance: Number.POSITIVE_INFINITY };
      candidates.forEach(item => {
        const distance = source < item.piece.sourceStart
          ? item.piece.sourceStart - source
          : source > item.piece.sourceEnd ? source - item.piece.sourceEnd : 0;
        if (distance < closest.distance) closest = { ...item, distance };
      });
      pieceIndex = closest.index;
      source = clamp(source, closest.piece.sourceStart, closest.piece.sourceEnd);
    }
    const sourceTime = start + source;
    playbackPieceIndexRef.current = pieceIndex;
    setPlayhead(sourceTime);
    if (videoRef.current) videoRef.current.currentTime = sourceTime;
  }

  function timelineRelativeFromPointer(clientX: number, element: HTMLDivElement) {
    const rect = element.getBoundingClientRect();
    if (!rect.width) return 0;
    return clamp((clientX - rect.left) / rect.width * visualTimelineLayout.duration, 0, visualTimelineLayout.duration);
  }

  function beginTimelineScrub(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    timelineScrubRef.current = { pointerId: event.pointerId, element: event.currentTarget };
    setTimelineScrubbing(true);
    seekTimelineRelative(timelineRelativeFromPointer(event.clientX, event.currentTarget));
  }

  function moveTimelineScrub(event: React.PointerEvent<HTMLDivElement>) {
    const scrub = timelineScrubRef.current;
    if (!scrub || scrub.pointerId !== event.pointerId) return;
    seekTimelineRelative(timelineRelativeFromPointer(event.clientX, scrub.element));
  }

  function endTimelineScrub(event: React.PointerEvent<HTMLDivElement>) {
    const scrub = timelineScrubRef.current;
    if (!scrub || scrub.pointerId !== event.pointerId) return;
    seekTimelineRelative(timelineRelativeFromPointer(event.clientX, scrub.element));
    timelineScrubRef.current = null;
    setTimelineScrubbing(false);
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch {}
  }

  function deleteSelectedSegment() {
    if (!selectedSegment || selectedSegmentRemoved) return;
    const candidate = mergeRemovedRanges([...editPlan.removed_ranges, { ...selectedSegment, reason: "segment" as const }]);
    const removedDuration = candidate.reduce((total, range) => total + range.end - range.start, 0);
    if (timelineSpan - removedDuration < MIN_SEGMENT_KEEP) {
      setError("Keep at least 0.25 seconds of the clip.");
      return;
    }
    removeRange({ ...selectedSegment, reason: "segment" });
  }

  function reorderSegment(sourceIndex: number, targetSourceIndex: number) {
    if (sourceIndex === targetSourceIndex) return;
    const nextOrder = [...segmentOrder];
    const from = nextOrder.indexOf(sourceIndex);
    const to = nextOrder.indexOf(targetSourceIndex);
    if (from < 0 || to < 0) return;
    const [moved] = nextOrder.splice(from, 1);
    nextOrder.splice(to, 0, moved);
    commitEditPlan({ ...editPlan, version: 2, segment_order: nextOrder });
    setSelectedSegmentIndex(sourceIndex);
    setDraggedSegmentIndex(null);
    setDragOverSegmentIndex(null);
    playbackPieceIndexRef.current = null;
  }

  function moveSelectedSegment(direction: -1 | 1) {
    if (selectedSegmentIndex === null || selectedSegmentRemoved) return;
    const position = segmentOrder.indexOf(selectedSegmentIndex);
    const targetPosition = position + direction;
    if (position < 0 || targetPosition < 0 || targetPosition >= segmentOrder.length) return;
    reorderSegment(selectedSegmentIndex, segmentOrder[targetPosition]);
  }

  function beginSegmentReorder(event: React.DragEvent<HTMLElement>, sourceIndex: number) {
    const display = displayTimelineSegments[sourceIndex];
    if (!display || display.fullyRemoved || trimmingSegment) {
      event.preventDefault();
      return;
    }
    videoRef.current?.pause();
    setPlaying(false);
    setSelectedSegmentIndex(sourceIndex);
    setDraggedSegmentIndex(sourceIndex);
    setDragOverSegmentIndex(sourceIndex);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(sourceIndex));
  }

  function overSegmentReorder(event: React.DragEvent<HTMLDivElement>, targetSourceIndex: number) {
    if (draggedSegmentIndex === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setDragOverSegmentIndex(targetSourceIndex);
  }

  function finishSegmentReorder(event: React.DragEvent<HTMLDivElement>, targetSourceIndex: number) {
    event.preventDefault();
    const sourceIndex = draggedSegmentIndex ?? Number(event.dataTransfer.getData("text/plain"));
    if (Number.isInteger(sourceIndex)) reorderSegment(sourceIndex, targetSourceIndex);
    else {
      setDraggedSegmentIndex(null);
      setDragOverSegmentIndex(null);
    }
  }

  function cancelSegmentReorder() {
    setDraggedSegmentIndex(null);
    setDragOverSegmentIndex(null);
  }

  function planWithSegmentTrim(basePlan: EditPlan, segment: { start: number; end: number }, edge: "left" | "right", relative: number) {
    const currentTrim = findSegmentTrimRange(segment, edge, basePlan.removed_ranges);
    const ranges = basePlan.removed_ranges.filter(range => range !== currentTrim);
    const reason = segmentTrimReason(edge, segment);
    if (edge === "left" && relative - segment.start >= .04) {
      ranges.push({ start: segment.start, end: relative, reason });
    }
    if (edge === "right" && segment.end - relative >= .04) {
      ranges.push({ start: relative, end: segment.end, reason });
    }
    return { ...basePlan, removed_ranges: ranges.sort((a, b) => a.start - b.start) };
  }

  function updateSegmentTrimFromPointer(clientX: number) {
    const drag = trimDragRef.current;
    if (!drag) return;
    const rect = drag.track.getBoundingClientRect();
    if (!rect.width) return;
    const pointerVisual = clamp(
      (clientX - rect.left) / rect.width * drag.visualTimelineDuration,
      drag.visualStart,
      drag.visualEnd,
    );
    const rawRelative = drag.visualSourceStart + clamp(
      pointerVisual - drag.visualStart,
      0,
      drag.visualEnd - drag.visualStart,
    );
    const baseBounds = segmentTrimBounds(drag.segment, drag.basePlan.removed_ranges);
    const relative = drag.edge === "left"
      ? clamp(rawRelative, drag.segment.start, baseBounds.visibleEnd - MIN_SEGMENT_KEEP)
      : clamp(rawRelative, baseBounds.visibleStart + MIN_SEGMENT_KEEP, drag.segment.end);
    const next = planWithSegmentTrim(drag.basePlan, drag.segment, drag.edge, Number(relative.toFixed(3)));
    const removedDuration = mergeRemovedRanges(next.removed_ranges).reduce((total, range) => total + range.end - range.start, 0);
    if (timelineSpan - removedDuration < MIN_SEGMENT_KEEP) return;
    drag.draftPlan = next;
    setEditPlan(next);
    playbackPieceIndexRef.current = null;
    const sourceTime = start + relative + (drag.edge === "left" ? .002 : -.002);
    setPlayhead(sourceTime);
    if (videoRef.current) videoRef.current.currentTime = sourceTime;
  }

  function beginSegmentTrim(event: React.PointerEvent<HTMLButtonElement>, segmentIndex: number, edge: "left" | "right") {
    if (event.button !== 0) return;
    const segment = timelineSegments[segmentIndex];
    const layout = visualTimelineLayout.segments.find(item => item.sourceIndex === segmentIndex);
    const track = videoTrackRef.current;
    if (!segment || !layout || !track) return;
    const fullyRemoved = mergedRemovedRanges.some(range => range.start <= segment.start + .01 && range.end >= segment.end - .01);
    if (fullyRemoved) return;
    event.preventDefault();
    event.stopPropagation();
    videoRef.current?.pause();
    setPlaying(false);
    setSelectedSegmentIndex(segmentIndex);
    setError("");
    event.currentTarget.setPointerCapture(event.pointerId);
    trimDragRef.current = {
      pointerId: event.pointerId,
      segmentIndex,
      edge,
      element: event.currentTarget,
      track,
      segment,
      basePlan: editPlan,
      draftPlan: editPlan,
      visualStart: layout.visualStart,
      visualEnd: layout.visualEnd,
      visualSourceStart: segment.start,
      visualSourceEnd: segment.end,
      visualTimelineDuration: visualTimelineLayout.duration,
    };
    setTrimmingSegment(true);
    updateSegmentTrimFromPointer(event.clientX);
  }

  function moveSegmentTrim(event: React.PointerEvent<HTMLButtonElement>) {
    const drag = trimDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    event.stopPropagation();
    updateSegmentTrimFromPointer(event.clientX);
  }

  function finishSegmentTrim(event: React.PointerEvent<HTMLButtonElement>, cancel = false) {
    const drag = trimDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    event.stopPropagation();
    if (!cancel) updateSegmentTrimFromPointer(event.clientX);
    const finalPlan = cancel ? drag.basePlan : drag.draftPlan;
    if (cancel) {
      setEditPlan(drag.basePlan);
    } else if (JSON.stringify(finalPlan) !== JSON.stringify(drag.basePlan)) {
      setUndoPlans(history => [...history.slice(-49), drag.basePlan]);
      setRedoPlans([]);
    }
    try { drag.element.releasePointerCapture(event.pointerId); } catch {}
    trimDragRef.current = null;
    setTrimmingSegment(false);
  }

  function resetSelectedSegmentTrim() {
    if (!selectedSegment) return;
    const left = findSegmentTrimRange(selectedSegment, "left", editPlan.removed_ranges);
    const right = findSegmentTrimRange(selectedSegment, "right", editPlan.removed_ranges);
    if (!left && !right) return;
    const trimRanges = new Set<RemovedRange>([left, right].filter((range): range is RemovedRange => !!range));
    commitEditPlan({ ...editPlan, removed_ranges: editPlan.removed_ranges.filter(range => !trimRanges.has(range)) });
  }

  useEffect(() => {
    if (selectedSegmentIndex !== null && selectedSegmentIndex >= timelineSegments.length) {
      setSelectedSegmentIndex(timelineSegments.length ? timelineSegments.length - 1 : null);
    }
  }, [selectedSegmentIndex, timelineSegments.length]);

  useEffect(() => {
    function onEditorKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || target?.isContentEditable) return;
      if (trimDragRef.current) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === "z") {
        event.preventDefault();
        if (event.shiftKey) redoEdit(); else undoEdit();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && key === "y") {
        event.preventDefault();
        redoEdit();
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.code === "Space") {
        event.preventDefault();
        togglePlayback();
      } else if (key === "s") {
        event.preventDefault();
        splitAtPlayhead();
      } else if ((event.key === "Delete" || event.key === "Backspace") && selectedSegment) {
        event.preventDefault();
        deleteSelectedSegment();
      }
    }
    window.addEventListener("keydown", onEditorKeyDown);
    return () => window.removeEventListener("keydown", onEditorKeyDown);
  }, [selectedSegmentIndex, selectedSegment, selectedSegmentRemoved, editPlan, undoPlans, redoPlans, playhead, start, end, timelineSegments]);

  function cleanSpeech() {
    const additions = cleanSpeechRanges.filter(range => !editPlan.removed_ranges.some(item => range.start < item.end && range.end > item.start));
    if (additions.length) commitEditPlan({ ...editPlan, removed_ranges: [...editPlan.removed_ranges, ...additions].sort((a, b) => a.start - b.start) });
  }

  function captionPreset(position: "bottom" | "above" | "center") {
    setCaptionPosition(position);
    setCaptionX(50);
    setCaptionY(null);
  }

  function resetCaptionLayout() {
    setCaptionPosition("bottom");
    setCaptionX(50);
    setCaptionY(null);
    setCaptionScale(1);
    setCaptionAlignment("center");
  }

  function updateCaptionPlacement(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    const caption = captionRef.current;
    const captionContent = captionContentRef.current;
    const drag = captionDragRef.current;
    if (!canvas || !caption || !drag) return;
    const canvasRect = canvas.getBoundingClientRect();
    const captionRect = (captionContent || caption).getBoundingClientRect();
    if (!canvasRect.width || !canvasRect.height) return;

    const centerX = clientX - drag.offsetX;
    const centerY = clientY - drag.offsetY;
    const halfWidthPercent = Math.min(44, captionRect.width / canvasRect.width * 50);
    const halfHeightPercent = Math.min(44, captionRect.height / canvasRect.height * 50);
    const styleInset = captionStyles.find(style => style.id === captionStyle)?.horizontal_inset_ratio ?? .06;
    const horizontalSafe = clamp(styleInset * 100, 4, 20);
    const minX = Math.min(50, horizontalSafe + halfWidthPercent);
    const maxX = Math.max(50, 100 - horizontalSafe - halfWidthPercent);
    const minY = Math.min(50, 6 + halfHeightPercent);
    const maxY = Math.max(50, 94 - halfHeightPercent);
    const x = clamp((centerX - canvasRect.left) / canvasRect.width * 100, minX, maxX);
    const y = clamp((centerY - canvasRect.top) / canvasRect.height * 100, minY, maxY);
    setCaptionX(Number(x.toFixed(1)));
    setCaptionY(Number(y.toFixed(1)));
  }

  function beginCaptionDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || !canvasRef.current || !captionRef.current) return;
    const captionRect = captionRef.current.getBoundingClientRect();
    captionDragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - (captionRect.left + captionRect.width / 2),
      offsetY: event.clientY - (captionRect.top + captionRect.height / 2),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setCaptionDragging(true);
    event.preventDefault();
  }

  function moveCaptionDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!captionDragRef.current || captionDragRef.current.pointerId !== event.pointerId) return;
    updateCaptionPlacement(event.clientX, event.clientY);
    event.preventDefault();
  }

  function endCaptionDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!captionDragRef.current || captionDragRef.current.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    captionDragRef.current = null;
    setCaptionDragging(false);
  }

  function nudgeCaption(event: React.KeyboardEvent<HTMLDivElement>) {
    const direction = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
    if (!direction) return;
    event.preventDefault();
    const step = event.shiftKey ? 5 : 1;
    const style = captionStyles.find(item => item.id === captionStyle);
    const inset = clamp((style?.horizontal_inset_ratio ?? .06) * 100, 4, 20);
    const baseY = captionY ?? (captionPosition === "center" ? 50 : captionPosition === "above"
      ? (style?.above_safe_ratio ?? .34) * 100
      : (1 - (style?.bottom_safe_ratio ?? .18)) * 100);
    setCaptionX(value => Number(clamp(value + direction[0] * step, inset, 100 - inset).toFixed(1)));
    setCaptionY(Number(clamp(baseY + direction[1] * step, 6, 94).toFixed(1)));
  }

  function seekToClipStart() {
    const video = videoRef.current;
    const first = timelineLayout.pieces[0];
    if (!video || !first) return;
    playbackPieceIndexRef.current = 0;
    video.currentTime = start + first.sourceStart;
    setPlayhead(video.currentTime);
  }

  function onLoaded() {
    const video = videoRef.current;
    if (realPlan && video && Number.isFinite(playhead) && playhead >= start && playhead <= end) {
      // Switching the existing player to the protected byte-range source
      // MUST NOT unexpectedly jump from the user's current scene to 0.
      video.currentTime = playhead;
      return;
    }
    seekToClipStart();
  }
  function onTimeUpdate() {
    const video = videoRef.current;
    const pieces = timelineLayout.pieces;
    if (!video || !pieces.length) return;
    const relative = video.currentTime - start;
    let pieceIndex = playbackPieceIndexRef.current;
    const trackedIndex = pieceIndex;
    const trackedPiece = trackedIndex === null ? null : pieces[trackedIndex];

    // While preview playback is active, edited timeline order is authoritative.
    // timeupdate can arrive after the browser has already crossed a source split;
    // advance from the tracked piece before source-time recovery can select the
    // naturally adjacent source segment and accidentally undo a reorder.
    if (!video.paused && trackedIndex !== null && trackedPiece && relative >= trackedPiece.sourceEnd - .015) {
      const next = pieces[trackedIndex + 1];
      if (next) {
        playbackPieceIndexRef.current = trackedIndex + 1;
        video.currentTime = start + next.sourceStart + .002;
        setPlayhead(video.currentTime);
        return;
      }
      video.pause();
      setPlaying(false);
      video.currentTime = start + trackedPiece.sourceEnd;
      setPlayhead(video.currentTime);
      return;
    }

    if (
      pieceIndex === null ||
      !pieces[pieceIndex] ||
      relative < pieces[pieceIndex].sourceStart - .03 ||
      relative > pieces[pieceIndex].sourceEnd + .03
    ) {
      pieceIndex = pieces.findIndex(piece => relative >= piece.sourceStart - .02 && relative <= piece.sourceEnd + .02);
      if (pieceIndex < 0) {
        const first = pieces[0];
        playbackPieceIndexRef.current = 0;
        video.currentTime = start + first.sourceStart;
        setPlayhead(video.currentTime);
        return;
      }
      playbackPieceIndexRef.current = pieceIndex;
    }
    const piece = pieces[pieceIndex];
    if (!video.paused && relative >= piece.sourceEnd - .015) {
      const next = pieces[pieceIndex + 1];
      if (next) {
        playbackPieceIndexRef.current = pieceIndex + 1;
        video.currentTime = start + next.sourceStart + .002;
        setPlayhead(video.currentTime);
        return;
      }
      video.pause();
      setPlaying(false);
      video.currentTime = start + piece.sourceEnd;
      setPlayhead(video.currentTime);
      return;
    }
    setPlayhead(video.currentTime);
  }
  async function togglePlayback() {
    const video = videoRef.current;
    const pieces = timelineLayout.pieces;
    if (!video || !pieces.length) return;
    if (video.paused) {
      const relative = video.currentTime - start;
      let pieceIndex = pieces.findIndex(piece => relative >= piece.sourceStart - .02 && relative < piece.sourceEnd - .015);
      if (pieceIndex < 0) {
        pieceIndex = 0;
        video.currentTime = start + pieces[0].sourceStart;
      }
      playbackPieceIndexRef.current = pieceIndex;
      await video.play();
      if (clip && !previewLogged.current) {
        previewLogged.current = true;
        trackClipBehavior(clip.id, "preview_started", {
          sessionId: behaviorSessionRef.current,
          eventId: `${behaviorSessionRef.current}:preview:${clip.id}`,
          surface: "editor",
        });
      }
      setPlaying(true);
    } else { video.pause(); setPlaying(false); }
  }

  async function save(showConfirmation = true) {
    if (!clip) return;
    const changedFields = [
      hook !== clip.hook ? "hook" : "",
      title !== clip.title ? "title" : "",
      transcript !== clip.transcript_text ? "transcript_text" : "",
      start !== clip.start_time ? "start_time" : "",
      end !== clip.end_time ? "end_time" : "",
    ].filter(Boolean);
    setSaving(true); setError("");
    try {
      const updated = await patchJSON<Clip>(`/clips/${clip.id}`, {
        hook, title, transcript_text: transcript, start_time: start, end_time: end,
        edit_plan: { ...editPlan, layout_mode: layoutMode },
      });
      setClip(updated);
      if (changedFields.length) {
        trackClipBehavior(clip.id, "edited", {
          sessionId: behaviorSessionRef.current,
          surface: "editor",
          changedFields,
        });
      }
      if (showConfirmation) setError("Saved");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not save this clip.";
      setError(message); throw cause;
    } finally { setSaving(false); }
  }

  function pollJob(jobId: string) {
    const timer = window.setInterval(async () => {
      if (activeJobRef.current !== jobId) {
        window.clearInterval(timer);
        return;
      }
      try {
        const state = await api<Job>(`/jobs/${jobId}`);
        if (activeJobRef.current !== jobId) return;
        setJob(state);
        if (["completed", "failed"].includes(state.status)) {
          window.clearInterval(timer);
          if (pollTimerRef.current === timer) pollTimerRef.current = null;
        }
      } catch { /* The next poll handles transient API/container restarts. */ }
    }, 1000);
    pollTimerRef.current = timer;
    return timer;
  }

  function watchJob(jobId: string) {
    stopJobWatch();
    activeJobRef.current = jobId;
    const source = new EventSource(`${API_URL}/jobs/${jobId}/events`, { withCredentials: true });
    eventSourceRef.current = source;
    source.addEventListener("progress", event => {
      if (activeJobRef.current !== jobId) return;
      setJob(JSON.parse((event as MessageEvent).data));
    });
    source.addEventListener("done", event => {
      if (activeJobRef.current !== jobId) return;
      setJob(JSON.parse((event as MessageEvent).data));
      source.close();
      if (eventSourceRef.current === source) eventSourceRef.current = null;
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    });
    source.onerror = () => {
      source.close();
      if (eventSourceRef.current === source) eventSourceRef.current = null;
      if (activeJobRef.current === jobId && pollTimerRef.current === null) pollJob(jobId);
    };
  }

  async function render() {
    if (!clip || renderStartRef.current || renderBusy) return;
    // Never charge an export for a Dual Stack selection that cannot split.
    // Auto Director and Speaker Focus retain their existing fallback behavior.
    if (ratio === "9:16" && layoutMode === "dual_stack") {
      if (!realPlan) {
        setError("Wait for private two-speaker analysis before exporting Dual Stack. No export was started.");
        return;
      }
      if (dualStackCoverageSeconds(realPlan) <= 0) {
        setError("Dual Stack has no verified two-speaker shots in this clip. No new export was started or charged.");
        return;
      }
    }
    renderStartRef.current = true;
    setStartingRender(true);
    setDrawerDismissed(false);
    setError("");
    try {
      await save(false);
      const output = await postJSON<ExportResponse>(`/clips/${clip.id}/export`, {
        resolution, aspect_ratio: ratio, caption_style: captionStyle, layout_mode: ratio === "9:16" ? layoutMode : "classic",
        caption_position: captionPosition, caption_x: captionX, caption_y: captionY, caption_scale: captionScale,
        caption_alignment: captionAlignment,
        focus_x: focusX, zoom, hook_text: hook, hook_enabled: hookEnabled, watermark, brand_kit_id: brandKitId || null,
        preserve_source_captions: preserveSourceCaptions,
        india_quality_mode: indiaQualityMode,
        caption_language_style: captionLanguageStyle,
      });
      setExportId(output.id);
      setExportLayoutMode(ratio === "9:16" ? layoutMode : "classic");
      setJob({ id: output.job_id, status: "queued", progress: 0, message: "Waiting for the render worker", export_id: output.id });
      watchJob(output.job_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The export could not start.");
    } finally {
      renderStartRef.current = false;
      setStartingRender(false);
    }
  }

  async function downloadReadyExport() {
    if (!exportId || downloading) return;
    setDownloading(true);
    setError("");
    try {
      const state = await api<ExportStatus>(`/exports/${exportId}`);
      if (state.status !== "ready" || !state.download_url) {
        setError("Your Short is still finishing securely. Try Download again in a moment.");
        return;
      }
      downloadExport(exportId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The download could not be prepared yet.");
    } finally {
      setDownloading(false);
    }
  }

  function openPostKaro() {
    if (!exportId) return;
    if (postKaro?.ready) {
      router.push("/post-karo?export=" + encodeURIComponent(exportId));
      return;
    }
    setShowPostKaroPrompt(true);
  }

  if (authLoading || !user) return (
    <div className="pro-editor-state">
      <div className="screen-loader inline"><div className="loader-mark">✦</div><p>Opening your editor…</p></div>
    </div>
  );
  if (loadError) return <div className="pro-editor-state"><ErrorState message={loadError} retry={load} /></div>;
  if (!clip || !project) return (
    <div className="pro-editor-state">
      <div className="screen-loader inline"><div className="loader-mark">✦</div><p>Loading the real video preview…</p></div>
    </div>
  );

  const selectedBrandKit = brandKits.find(kit => kit.id === brandKitId);
  const positionClass = (realPlan && actualScene?.layout === "dual_stack") || previewDual ? "position-center smart-stack-captions" : captionY === null ? "position-" + captionPosition : "caption-custom-position";
  const selectedCaptionStyle = captionStyles.find(style => style.id === captionStyle);
  const baseCaptionRatio = selectedCaptionStyle?.font_size_width_ratio ?? .065;
  const captionInsetRatio = selectedCaptionStyle?.horizontal_inset_ratio ?? .06;
  const previewStyle = {
    ...(selectedCaptionStyle ? {
      "--caption-font-family": selectedCaptionStyle.font_family + ", sans-serif",
      "--caption-font-weight": selectedCaptionStyle.font_weight,
      "--caption-line-height": selectedCaptionStyle.line_height,
      "--caption-text-transform": selectedCaptionStyle.text_transform,
      "--caption-text-color": selectedCaptionStyle.text_color,
      "--caption-highlight-color": selectedCaptionStyle.highlight_color,
      "--caption-highlight-background": selectedCaptionStyle.highlight_background,
      "--caption-shadow": selectedCaptionStyle.shadow,
      "--caption-horizontal-inset": String(selectedCaptionStyle.horizontal_inset_ratio * 100) + "%",
      "--caption-bottom": String(selectedCaptionStyle.bottom_safe_ratio * 100) + "%",
      "--caption-above": String(selectedCaptionStyle.above_safe_ratio * 100) + "%",
      "--caption-active-scale": selectedCaptionStyle.active_word_scale,
      "--caption-corner-radius": String(selectedCaptionStyle.corner_radius_px) + "px",
      "--caption-background": selectedCaptionStyle.background,
    } : {}),
    "--caption-font-size-ratio-effective": baseCaptionRatio * captionScale,
    "--caption-safe-width": String(Math.max(60, (1 - captionInsetRatio * 2) * 100)) + "%",
    "--caption-x": String(captionX) + "%",
    "--caption-y": String(captionY ?? 50) + "%",
    textAlign: captionAlignment,
  } as CSSProperties;
  const visibleHook = hook.trim().split(/\s+/).slice(0, 8).join(" ");
  const outputPlayhead = sourceRelativeToOutput(playhead - start) ?? 0;
  const visualPlayhead = sourceRelativeToVisual(playhead - start) ?? 0;
  const showHook = outputPlayhead < 4.5;
  const playheadOffset = clamp(outputPlayhead, 0, editedDuration);
  const playheadPercent = visualTimelineLayout.duration > 0 ? clamp(visualPlayhead / visualTimelineLayout.duration * 100, 0, 100) : 0;
  const timelineTicks = Array.from({ length: 7 }, (_, index) => visualTimelineLayout.duration * index / 6);

  return (
    <div className="pro-editor-root">
      <header className="pro-editor-topbar">
        <div className="pro-editor-topbar-start">
          <button type="button" className="pro-editor-back" onClick={() => router.back()} aria-label="Back to project"><ArrowLeft size={18}/></button>
          <div className="pro-editor-title">
            <span>CLIPKARO SMART EDITOR</span>
            <strong>{title || project.title}</strong>
          </div>
        </div>
        <div className="pro-editor-topbar-actions">
          <button type="button" className="pro-editor-icon-button" title="Undo" aria-label="Undo Smart Edit" disabled={!undoPlans.length} onClick={undoEdit}><Undo2 size={16}/></button>
          <button type="button" className="pro-editor-icon-button" title="Redo" aria-label="Redo Smart Edit" disabled={!redoPlans.length} onClick={redoEdit}><Redo2 size={16}/></button>
          <span className="pro-editor-topbar-divider"/>
          <button className="secondary-btn small" onClick={() => save()} disabled={saving || renderBusy}>{saving ? <Loader2 className="spin" size={14}/> : <Save size={14}/>} Save</button>
          <button className="primary-btn small" onClick={render} disabled={renderBusy}>{renderBusy ? <Loader2 className="spin" size={14}/> : <Sparkles size={14}/>} {startingRender ? "Starting…" : renderBusy ? "Rendering…" : "Export Short"}</button>
        </div>
      </header>
      <div className="pro-editor-body">
        <nav className="pro-editor-toolrail" aria-label="Editor tools">
          <button type="button" className={activeTool === "edit" ? "active" : ""} onClick={() => setActiveTool("edit")}><Type size={19}/><span>Edit</span></button>
          <button type="button" className={activeTool === "captions" ? "active" : ""} onClick={() => setActiveTool("captions")}><Captions size={19}/><span>Captions</span></button>
          <button type="button" className={activeTool === "frame" ? "active" : ""} onClick={() => setActiveTool("frame")}><MoveHorizontal size={19}/><span>Frame</span></button>
          <button type="button" className={activeTool === "brand" ? "active" : ""} onClick={() => setActiveTool("brand")}><Palette size={19}/><span>Brand</span></button>
          <button type="button" className={activeTool === "export" ? "active" : ""} onClick={() => setActiveTool("export")}><Film size={19}/><span>Export</span></button>
        </nav>

        <aside className="pro-editor-context">
          {activeTool === "edit" && <>
            <div className="pro-editor-panel-head">
              <span>Smart Edit V1</span>
              <h2>Edit video like text</h2>
              <p>Click words or pauses to remove them from video, audio and captions.</p>
            </div>
            <div className="pro-editor-context-scroll">
              <div className="pro-editor-field"><label>Clip title</label><input value={title} onChange={event => setTitle(event.target.value)} /></div>
              <div className="smart-edit-actions pro-editor-smart-actions">
                <button type="button" onClick={cleanSpeech} disabled={!cleanSpeechRanges.length}><WandSparkles size={13}/> Clean Speech</button>
                <button type="button" onClick={splitAtPlayhead}><Scissors size={13}/> Split at {Math.max(0, playhead-start).toFixed(1)}s</button>
              </div>
              <div className="smart-transcript pro-editor-transcript" aria-label="Text based video editor">
                {orderedAllSourceWords.map((word, index) => {
                  const removed = editPlan.removed_ranges.find(range => word.start < range.end && word.end > range.start);
                  const nextWord = orderedAllSourceWords[index + 1];
                  const sameLogicalSegment = !!nextWord && timelineSegments.some(segment =>
                    word.start >= segment.start - .001 &&
                    word.start < segment.end - .001 &&
                    nextWord.start >= segment.start - .001 &&
                    nextWord.start < segment.end - .001,
                  );
                  const pause = sameLogicalSegment ? pauseBlocks.find(item => Math.abs(item.start - word.end) < .01) : undefined;
                  return <span className="smart-token-group" key={word.start + "-" + index}>
                    <button type="button" className={"smart-word" + (removed ? " removed" : "")} title={removed ? "Restore word" : "Remove word from media"} onClick={() => removed ? restoreRange(removed) : removeRange({ start: word.start, end: word.end, reason: "word" })}>{word.text}</button>
                    {pause && <button type="button" className={"pause-block" + (editPlan.removed_ranges.some(range => rangeContains(range, (pause.start+pause.end)/2)) ? " removed" : "")} title={(pause.end-pause.start).toFixed(1) + "s pause — click to remove"} onClick={() => removeRange(pause)}><Pause size={9}/>{(pause.end-pause.start).toFixed(1)}s</button>}
                  </span>;
                })}
              </div>
              {!!editPlan.removed_ranges.length && <div className="removed-edit-list pro-editor-removals"><b>{editPlan.removed_ranges.length} removals</b>{editPlan.removed_ranges.map((range, index) => <button type="button" key={range.start + "-" + index} onClick={() => restoreRange(range)}><X size={10}/>{range.reason} {range.start.toFixed(1)}–{range.end.toFixed(1)}s</button>)}</div>}
              <p className="field-note pro-editor-note">Edits are non-destructive. Preview and export use the same edit plan.</p>
            </div>
          </>}

          {activeTool === "captions" && <>
            <div className="pro-editor-panel-head"><span>CAPTIONS</span><h2>Hook & caption style</h2><p>Keep the current caption engine, just organized for faster editing.</p></div>
            <div className="pro-editor-context-scroll">
              {sourceHasCaptions && <div className="pro-editor-alert"><b>Existing subtitles detected</b><p>Preserve source captions keeps the full source frame safe.</p></div>}
              {reviewSuggested && <div className="pro-editor-alert warning"><AlertTriangle size={14}/><div><b>Review suggested</b><p>{reviewReasons.slice(0, 2).join(", ") || "Some words look uncertain."}</p></div></div>}
              <div className="toggle-row pro-editor-toggle"><div><b>Hook text</b><span>{hookEnabled ? "Shown for the first 4.5 seconds" : "Opening hook is off"}</span></div><button type="button" className={hookEnabled ? "on" : ""} aria-pressed={hookEnabled} onClick={() => setHookEnabled(value => !value)}><i/></button></div>
              <div className="pro-editor-field"><label>Hook text</label><textarea value={hook} onChange={event => setHook(event.target.value)} maxLength={120} disabled={!hookEnabled}/><small>{hook.length}/120</small></div>
              <div className="pro-editor-field"><label>Caption personality</label>
                <div className="style-options pro-editor-style-list">{styles.map(style => <button type="button" className={captionStyle === style[0] ? "active" : ""} onClick={() => setCaptionStyle(style[0])} key={style[0]}><span className={"style-swatch " + style[0]}>Aa</span><div><b>{style[1]}</b><small>{style[2]}</small></div>{captionStyle === style[0] && <Check size={14}/>}</button>)}</div>
              </div>
            </div>
          </>}

          {activeTool === "frame" && <>
            <div className="pro-editor-panel-head"><span>FRAME</span><h2>Compose the Short</h2><p>Use the exact framing controls already supported by ClipKaro export.</p></div>
            <div className="pro-editor-context-scroll">
              <div className="pro-editor-field"><label>Canvas ratio</label><div className="ratio-options">{[["9:16", Smartphone, "Shorts"], ["4:5", AlignCenter, "Feed"], ["1:1", Square, "Square"]].map(([value, Icon, name]) => <button type="button" key={value as string} className={ratio === value ? "active" : ""} onClick={() => setRatio(value as string)}><Icon size={17}/><b>{value as string}</b><small>{name as string}</small></button>)}</div></div>
              <div className="pro-editor-field">
                <label>Karo Smart Layouts</label>
                <select aria-label="Karo Smart Layout" value={layoutMode} onChange={event => { const selected = event.target.value as typeof layoutMode; setLayoutMode(selected); if (selected !== "classic") setPreserveSourceCaptions(false); }} disabled={ratio !== "9:16"}>
                  <option value="auto">Auto Director · Detect two speakers</option>
                  <option value="dual_stack">Dual Stack · Top / bottom + middle captions</option>
                  <option value="speaker_focus">Speaker Focus · Follow the person speaking</option>
                  <option value="classic">Classic · Single-person crop</option>
                </select>
                <p className="field-note">{smartCapability === "ready"
                  ? "One secure analysis powers Auto Director, Dual Stack and Speaker Focus. Switching modes or re-exporting uses saved results for free."
                  : (smartQuota?.reason === "upgrade" || smartQuota?.reason === "pass_exhausted")
                    ? smartQuota?.reason === "pass_exhausted" ? "Mini Pass has reached its Short or processing-minute allowance. Classic framing remains available." : "Real Smart Layout requires a premium plan. Classic framing remains available."
                    : "Real Smart Layout is in controlled beta. No simulated split will be shown."}</p>
                {ratio === "9:16" && layoutMode !== "classic" && <section className="smart-quota-card" aria-label="Real Smart Layout credits">
                  <div className="smart-quota-head"><span><Sparkles size={15}/> REAL SMART LAYOUT</span><b>{smartQuota?.plan ? smartQuota.plan.replace("_", " ").toUpperCase() : "PRIVATE BETA"}</b></div>
                  {smartQuota?.available ? <>
                    <div className="smart-quota-numbers"><strong>{smartQuota.remaining ?? 0}<small> / {smartQuota.allowance ?? 0} credits left</small></strong><span>Renews with your paid plan</span></div>
                    <div className="smart-quota-track" role="progressbar" aria-label="Smart Layout plan credits remaining" aria-valuemin={0} aria-valuemax={smartQuota.allowance || 1} aria-valuenow={smartQuota.remaining || 0}>
                      <div style={{ width: String(Math.min(100, (smartQuota.remaining || 0) / Math.max(1, smartQuota.allowance || 1) * 100)) + "%" }}/>
                    </div>
                    <p className="smart-quota-meta">Last 24h: <b>{smartQuota.daily_remaining ?? 0} of {smartQuota.daily_cap ?? 0}</b> available · This clip: <b>{smartClipBillingLabel}</b></p>
                    {smartQuota.period_end && <small className="smart-quota-date">Plan period ends {new Date(smartQuota.period_end).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}.</small>}
                    {!realPlan && layoutAnalysis !== "analyzing" && !analysisConfirmed && <button className="smart-quota-action" type="button"
                      disabled={!freeReanalysis && ((smartQuota.remaining ?? 0) < smartClipCost || (smartQuota.daily_remaining ?? 0) < smartClipCost)}
                      onClick={() => {
                        layoutBillingRef.current = null;
                        setLayoutBilling(null);
                        setAnalysisConfirmedFor(clipAnalysisKey);
                        setLayoutAnalysis("analyzing");
                        setLayoutAnalysisError("");
                      }}>
                      <Sparkles size={14}/> {freeReanalysis ? "Refresh previous analysis · Free" : "Analyze securely · " + smartClipCost + (smartClipCost === 1 ? " credit" : " credits")}
                    </button>}
                    {!realPlan && !freeReanalysis && ((smartQuota.remaining ?? 0) < smartClipCost || (smartQuota.daily_remaining ?? 0) < smartClipCost) &&
                      <p className="smart-quota-warning" role="status">Not enough {((smartQuota.remaining ?? 0) < smartClipCost) ? "plan" : "daily"} credits for a new analysis. Previously analyzed clips stay reusable.</p>}
                    {realPlan && currentBillingAction === "new_charge" && <p className="smart-quota-reused"><Check size={13}/> Analysis complete · {smartClipCostText} used</p>}
                    {realPlan && currentBillingAction === "cached_reuse" && <p className="smart-quota-reused"><Check size={13}/> Saved analysis reused · no new charge</p>}
                    {realPlan && currentBillingAction === "free_refresh" && <p className="smart-quota-reused"><Check size={13}/> Saved analysis refreshed · no new charge</p>}
                    {realPlan && currentBillingAction === "existing_job" && <p className="smart-quota-reused"><Check size={13}/> Existing analysis reused · no additional charge</p>}
                    {realPlan && (!currentBillingAction || currentBillingAction === "unknown") && <p className="smart-quota-reused" role="status">Analysis ready · billing status unavailable</p>}
                  </> : <div className="smart-quota-locked"><b>{smartQuota?.reason === "pass_exhausted" ? "Mini Pass completed" : smartQuota?.reason === "upgrade" ? "Unlock with a paid plan" : "Controlled beta access"}</b>
                    <p>{smartQuota?.reason === "pass_exhausted" ? "Your existing Mini Pass Short or minute quota is exhausted. A new pass or subscription is required for further analysis." : smartQuota?.reason === "upgrade" ? "Premium plans include secure face-aware analysis credits." : "Real analysis will become available after your account joins the approved rollout."}</p>
                    {(smartQuota?.reason === "upgrade" || smartQuota?.reason === "pass_exhausted") && <a href="/pricing">Compare plans →</a>}
                  </div>}
                </section>}
                {layoutMode === "dual_stack" && dualStackCoverage !== null &&
                  <p className="field-note" role="status">
                    {dualStackCoverage > 0
                      ? `Verified two-person Dual Stack: ${dualStackCoverage.toFixed(1)} of ${realPlan!.duration.toFixed(1)} seconds. Other shots remain single-person; captions move to the middle only during verified split scenes.`
                      : "No simultaneous two-face shots detected. Dual Stack cannot produce two live panels from separate close-ups; the preview check does not use export credits."}
                  </p>}
              </div>
              <div className="pro-editor-stat-grid"><span><small>Ratio</small><b>{ratio}</b></span><span><small>Focus</small><b>{Math.round(focusX)}%</b></span><span><small>Zoom</small><b>{Math.round(zoom*100)}%</b></span></div>
              <p className="pro-editor-note">Framing changes are reflected in the exported MP4, not only in preview.</p>
            </div>
          </>}

          {activeTool === "brand" && <>
            <div className="pro-editor-panel-head"><span>BRAND</span><h2>Brand kit</h2><p>Apply your saved wordmark, color and preferred caption preset.</p></div>
            <div className="pro-editor-context-scroll">
              <div className="pro-editor-field"><label>Brand kit</label><select value={brandKitId} onChange={event => { const id = event.target.value; setBrandKitId(id); const kit = brandKits.find(item => item.id === id); if (kit && styles.some(style => style[0] === kit.caption_preset)) setCaptionStyle(kit.caption_preset); }}><option value="">No brand kit</option>{brandKits.map(kit => <option key={kit.id} value={kit.id}>{kit.name}{kit.is_default ? " · Default" : ""}</option>)}</select></div>
              {selectedBrandKit ? <div className="pro-editor-brand-card"><span style={{ background: selectedBrandKit.primary_color }}/><div><b>{selectedBrandKit.name}</b><small>{selectedBrandKit.logo_text || "No wordmark"} · {selectedBrandKit.caption_preset}</small></div></div> : <div className="pro-editor-empty-card">Choose a saved Brand Kit or keep this Short unbranded.</div>}
            </div>
          </>}

          {activeTool === "export" && <>
            <div className="pro-editor-panel-head"><span>EXPORT</span><h2>Ready to publish</h2><p>Everything below reflects the settings that will be sent to the renderer.</p></div>
            <div className="pro-editor-context-scroll">
              <div className="export-summary pro-editor-export-summary"><span>Format <b>{ratio}</b></span><span>Duration <b>{editedDuration.toFixed(1)}s</b></span><span>Captions <b>{styles.find(style => style[0] === captionStyle)?.[1]}</b></span><span>Caption size <b>{Math.round(captionScale*100)}%</b></span><span>Placement <b>{captionY === null ? (captionPosition === "bottom" ? "Lower" : captionPosition === "above" ? "Upper" : "Centre") : "Custom"}</b></span><span>Align <b>{captionAlignment}</b></span><span>Layout <b>{ratio === "9:16" ? layoutMode.replace("_", " ") : "Classic"}</b></span><span>Frame <b>{ratio === "9:16" && layoutMode !== "classic" ? "Face-aware" : preserveSourceCaptions ? "Full" : Math.round(focusX) + "%"}</b></span><span>Zoom <b>{ratio === "9:16" && layoutMode !== "classic" ? "Automatic" : preserveSourceCaptions ? "100% safe" : Math.round(zoom*100) + "%"}</b></span><span>India <b>{indiaQualityMode ? captionLanguageStyle.replace("_", " ") : "Off"}</b></span><span>Brand <b>{selectedBrandKit?.name || "None"}</b></span></div>
            </div>
          </>}
        </aside>
        <section className="pro-editor-stage">
          <div className="pro-editor-stage-meta">
            <span>{ratio} canvas</span>
            <span>{editedDuration.toFixed(1)}s edited</span>
          </div>
          <div ref={canvasRef} className={"video-canvas pro-video-canvas ratio-" + ratio.replace(":", "-")}>
            <div className={"smart-preview-primary" + (previewDual ? " smart-preview-top" : "") + (previewFocus ? " smart-preview-focus" : "")}>
              <video
              ref={videoRef}
              src={realPlan ? API_URL + "/clips/" + clip.id + "/smart-layout-v2/media" : API_URL + "/projects/" + project.id + "/media"}
              crossOrigin={realPlan ? "use-credentials" : undefined}
              preload="metadata"
              playsInline
              onLoadedMetadata={onLoaded}
              onTimeUpdate={onTimeUpdate}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              style={{
                objectFit: preserveSourceCaptions ? "contain" : "cover",
                objectPosition: previewDual ? "16% 50%" : previewFocus ? "50% 50%" : String(focusX) + "% 50%",
                transform: preserveSourceCaptions || previewDual || !!realPlan ? "scale(1)" : previewFocus ? "scale(1.08)" : "scale(" + String(zoom) + ")",
                opacity: realPlan ? 0 : 1,
              }}
            />
            </div>
            {realPlan && <canvas ref={smartCanvasRef} className="smart-layout-v2-canvas"
              width={360} height={640} aria-label="Analyzed Smart Layout preview"/>}
            {ratio === "9:16" && layoutMode !== "classic" && smartCapability !== "ready" &&
              <div className="smart-layout-v2-status" role="status">
                {smartCapability === "checking" ? "Checking secure Smart Layout availability…" : smartQuota?.reason === "pass_exhausted" ? "Mini Pass creation or minute allowance reached. Open Frame to compare plans." : smartQuota?.reason === "upgrade" ? "Real Smart Layout is premium. Open Frame to compare plans. Classic is still available." : "Real Smart Layout is currently limited to approved beta accounts. No simulated split is shown."}
              </div>}
            {smartRequested && SMART_LAYOUT_V2_ENABLED && !realPlan && <div className="smart-layout-v2-status" role="status">
              {layoutAnalysis === "error" ? <><span>Smart Layout preview unavailable: {layoutAnalysisError}</span><button type="button" onClick={() => { setLayoutPlans(null); setLayoutPlansClipKey(null); setAnalysisConfirmedFor(null); layoutBillingRef.current = null; setLayoutBilling(null); setLayoutAnalysis("idle"); setLayoutAnalysisError(""); }}>Review and retry</button></> : layoutAnalysis === "analyzing" ? (currentBillingAction === "existing_job" ? "An existing Smart Layout analysis is already running…" : "Analyzing real speaker positions…") : analysisConfirmed ? "Analyzing real speaker positions…" : (!freeReanalysis && ((smartQuota?.remaining ?? 0) < smartClipCost || (smartQuota?.daily_remaining ?? 0) < smartClipCost)) ? "Not enough credits for a new analysis. Open Frame for your balance." : "Review the credit cost in Frame, then choose Analyze securely."}
            </div>}
            {previewDual && <>
              <div className="smart-preview-band" aria-hidden="true" />
              <div className="smart-preview-secondary" aria-hidden="true">
                <video ref={secondaryVideoRef} src={API_URL + "/projects/" + project.id + "/media"}
                  muted playsInline preload="metadata" tabIndex={-1}
                  style={{ objectPosition: "84% 50%" }}/>
              </div>
            </>}
            {ratio === "9:16" && layoutMode !== "classic" && <div className="smart-preview-label">
              <Sparkles size={11}/> {layoutMode === "auto" ? "AUTO DIRECTOR" : layoutMode === "dual_stack" ? "DUAL STACK" : "SPEAKER FOCUS"} · {realPlan ? "ANALYZED PREVIEW" : SMART_LAYOUT_V2_ENABLED ? "ANALYSIS PENDING" : "NOT ANALYZED"}
            </div>}
            <button className="canvas-play pro-canvas-play" onClick={togglePlayback}>{playing ? <Pause fill="currentColor"/> : <Play fill="currentColor"/>}</button>
            {hookEnabled && showHook && visibleHook && <div className="canvas-hook">{visibleHook}</div>}
            {captionState.visible && <div
              ref={captionRef}
              className={"caption-preview caption-draggable style-" + captionStyle + " " + positionClass + (captionDragging ? " caption-dragging" : "")}
              style={previewStyle}
              title="Drag caption to place it"
              tabIndex={0}
              aria-label="Caption preview. Drag to place it, or use arrow keys for precise movement."
              onKeyDown={nudgeCaption}
              onPointerDown={beginCaptionDrag}
              onPointerMove={moveCaptionDrag}
              onPointerUp={endCaptionDrag}
              onPointerCancel={endCaptionDrag}
            >
              <span ref={captionContentRef} className="caption-content">
                {captionState.words.map((word, index) => <span className={(index === captionState.active ? "active-word " : "") + (captionState.uncertain[index] ? "low-confidence" : "")} key={word + "-" + index}>{word} </span>)}
              </span>
            </div>}
            {selectedBrandKit?.logo_text && <div className="canvas-brandmark" style={{ color: selectedBrandKit.primary_color }}>{selectedBrandKit.logo_text}</div>}
            {watermark && <div className="canvas-watermark">✦ ClipKaro AI</div>}
            <div className="safe-zone"/>
          </div>
          <div className="pro-editor-player-controls">
            <button type="button" onClick={togglePlayback} aria-label={playing ? "Pause" : "Play"}>{playing ? <Pause size={16} fill="currentColor"/> : <Play size={16} fill="currentColor"/>}</button>
            <b>{playheadOffset.toFixed(1)}s</b>
            <span>/ {editedDuration.toFixed(1)}s</span>
            <div className="pro-editor-player-spacer"/>
            <span>{editPlan.removed_ranges.length} removals</span>
            <span>{editPlan.split_points.length} markers</span>
          </div>
        </section>
        <aside className="pro-editor-inspector">
          {activeTool === "edit" && <>
            <div className="pro-editor-inspector-head"><span>EDIT</span><h3>Clip controls</h3></div>
            <div className="pro-editor-inspector-scroll">
              <div className="pro-editor-quick-actions">
                <button type="button" disabled={!undoPlans.length} onClick={undoEdit}><Undo2 size={14}/> Undo</button>
                <button type="button" disabled={!redoPlans.length} onClick={redoEdit}><Redo2 size={14}/> Redo</button>
              </div>
              <div className={"pro-editor-segment-card" + (selectedSegment ? " active" : "")}>
                <div className="pro-editor-segment-card-copy">
                  <span>Selected segment</span>
                  <b>{selectedDisplaySegment ? selectedDisplaySegment.visibleStart.toFixed(1) + "s – " + selectedDisplaySegment.visibleEnd.toFixed(1) + "s" : "Click a timeline segment"}</b>
                  {selectedSegment && <small>Order {selectedOrderPosition + 1} of {segmentOrder.length}{selectedSegmentHasTrim ? " · source " + selectedSegment.start.toFixed(1) + "s – " + selectedSegment.end.toFixed(1) + "s" : ""}</small>}
                </div>
                <div className="pro-editor-segment-card-actions">
                  <button type="button" className="reorder-step" onClick={() => moveSelectedSegment(-1)} disabled={!selectedSegment || selectedSegmentRemoved || selectedOrderPosition <= 0} title="Move segment earlier"><ArrowLeft size={13}/> Earlier</button>
                  <button type="button" className="reorder-step" onClick={() => moveSelectedSegment(1)} disabled={!selectedSegment || selectedSegmentRemoved || selectedOrderPosition < 0 || selectedOrderPosition >= segmentOrder.length - 1} title="Move segment later">Later <ArrowRight size={13}/></button>
                  {selectedSegmentHasTrim && <button type="button" className="reset-trim" onClick={resetSelectedSegmentTrim} title="Restore this segment to its split boundaries">Reset trim</button>}
                  <button type="button" onClick={deleteSelectedSegment} disabled={!selectedSegment || selectedSegmentRemoved} title="Delete selected segment from video, audio and captions"><Trash2 size={14}/>{selectedSegmentRemoved ? "Removed" : "Delete"}</button>
                </div>
              </div>
              <div className="pro-editor-field">
                <label>Precise trim</label>
                <div className="trim-inputs">
                  <div><span>Start</span><input type="number" step=".1" min="0" max={end-1} value={start} onChange={event => { const value=Number(event.target.value); setStart(value); if(videoRef.current) videoRef.current.currentTime=value; }}/></div>
                  <div><span>End</span><input type="number" step=".1" min={start+1} max={project.duration} value={end} onChange={event => setEnd(Number(event.target.value))}/></div>
                </div>
              </div>
              <div className="pro-editor-stat-grid"><span><small>Source</small><b>{Math.max(0,end-start).toFixed(1)}s</b></span><span><small>Edited</small><b>{editedDuration.toFixed(1)}s</b></span><span><small>Words</small><b>{sourceWords.length}</b></span></div>
              <div className="pro-editor-help-card"><Scissors size={15}/><div><b>Non-destructive edit plan</b><p>Word and pause removals stay reversible and are reused by export.</p></div></div>
            </div>
          </>}
          {activeTool === "captions" && <>
            <div className="pro-editor-inspector-head"><span>CAPTIONS</span><h3>Layout & language</h3></div>
            <div className="pro-editor-inspector-scroll">
              <div className="toggle-row pro-editor-toggle">
                <div><b>India Quality Mode</b><span>{indiaQualityHint || "Hindi, Hinglish and Indian English defaults"}</span></div>
                <button className={indiaQualityMode ? "on" : ""} aria-pressed={indiaQualityMode} onClick={() => setIndiaQualityMode(value => !value)}><i/></button>
              </div>
              {indiaQualityMode && <div className="pro-editor-field">
                <label>Caption language style</label>
                <select value={captionLanguageStyle} onChange={event => setCaptionLanguageStyle(event.target.value as CaptionLanguageStyle)}>
                  <option value="auto">Auto</option><option value="roman_hinglish">Roman Hinglish</option><option value="original">Original transcript</option>
                </select>
              </div>}
              <div className="pro-editor-field">
                <div className="caption-control-head"><label><MoveHorizontal size={13}/> Caption placement</label><button type="button" onClick={resetCaptionLayout} disabled={captionY===null && captionPosition==="bottom" && captionX===50 && captionScale===1 && captionAlignment==="center"}>Reset</button></div>
                <div className="segmented three caption-presets"><button type="button" className={captionY===null && captionPosition==="bottom" ? "active" : ""} onClick={() => captionPreset("bottom")}>Lower</button><button type="button" className={captionY===null && captionPosition==="center" ? "active" : ""} onClick={() => captionPreset("center")}>Centre</button><button type="button" className={captionY===null && captionPosition==="above" ? "active" : ""} onClick={() => captionPreset("above")}>Upper</button></div>
                <div className="caption-placement-status"><span>{captionY===null ? "Preset placement" : "Custom · X " + Math.round(captionX) + "% · Y " + Math.round(captionY) + "%"}</span><b>Drag caption on preview</b></div>
                <p className="field-note">Drag caption on preview. ClipKaro keeps it inside the safe zone and applies the placement to every caption in this Short.</p>
              </div>
              <div className="pro-editor-field">
                <div className="caption-size-heading"><label>Caption size</label><b>{Math.round(captionScale*100)}%</b></div>
                <div className="zoom-control caption-size-control">
                  <button type="button" aria-label="Make caption smaller" disabled={captionScale<=.65} onClick={() => setCaptionScale(value => clamp(Number((value-.05).toFixed(2)),.65,1.6))}><ZoomOut size={15}/></button>
                  <input aria-label="Caption size" type="range" min=".65" max="1.6" step=".05" value={captionScale} onChange={event => setCaptionScale(Number(event.target.value))}/>
                  <button type="button" aria-label="Make caption larger" disabled={captionScale>=1.6} onClick={() => setCaptionScale(value => clamp(Number((value+.05).toFixed(2)),.65,1.6))}><ZoomIn size={15}/></button>
                </div>
                <div className="caption-size-scale"><span>65%</span><span>100%</span><span>160%</span></div>
              </div>


              <div className="pro-editor-field">
                <div className="caption-size-heading caption-align-heading"><label>Text alignment</label><b>{captionAlignment}</b></div>
                <div className="segmented three caption-align-controls" role="group" aria-label="Caption text alignment">
                  <button type="button" className={captionAlignment==="left" ? "active" : ""} onClick={() => setCaptionAlignment("left")}><AlignLeft size={14}/> Left</button>
                  <button type="button" className={captionAlignment==="center" ? "active" : ""} onClick={() => setCaptionAlignment("center")}><AlignCenter size={14}/> Centre</button>
                  <button type="button" className={captionAlignment==="right" ? "active" : ""} onClick={() => setCaptionAlignment("right")}><AlignRight size={14}/> Right</button>
                </div>
                <p className="field-note caption-reflow-note"><Check size={12}/> Text wraps and reflows automatically as caption size changes.</p>
              </div>
              <div className="toggle-row pro-editor-toggle">
                <div><b>Preserve source captions</b><span>{ratio === "9:16" && layoutMode !== "classic" ? "Switch to Classic to keep burned-in subtitles. Smart Layout uses ClipKaro captions." : sourceHasCaptions ? "Detected near " + Math.round((sourceCaptionBand ?? .82)*100) + "% height" : "Use when source already contains subtitles"}</span></div>
                <button className={preserveSourceCaptions ? "on" : ""} aria-label="Preserve source captions" aria-pressed={preserveSourceCaptions} disabled={ratio === "9:16" && layoutMode !== "classic"} onClick={() => setPreserveSourceCaptions(value => !value)}><i/></button>
              </div>
            </div>
          </>}

          {activeTool === "frame" && <>
            <div className="pro-editor-inspector-head"><span>FRAME</span><h3>Reframe & zoom</h3></div>
            <div className="pro-editor-inspector-scroll">
              <div className="pro-editor-field">
                <label><MoveHorizontal size={13}/> Manual reframe: {focusX}%</label>
                <input className="focus-slider" type="range" min="0" max="100" value={focusX} disabled={ratio === "9:16" && layoutMode !== "classic"} onChange={event => setFocusX(Number(event.target.value))}/>
                <div className="focus-labels"><span>Left</span><span>Centre</span><span>Right</span></div>
              </div>
              <div className={"pro-editor-field zoom-section" + (preserveSourceCaptions || (ratio === "9:16" && layoutMode !== "classic") ? " disabled" : "")}>
                <div className="zoom-heading"><label><ZoomIn size={13}/> Video zoom: {Math.round(zoom*100)}%</label><button className="zoom-reset" type="button" disabled={preserveSourceCaptions || (ratio === "9:16" && layoutMode !== "classic") || zoom===1} onClick={() => setZoom(1)}>Reset</button></div>
                <div className="zoom-control">
                  <button type="button" aria-label="Zoom out" disabled={preserveSourceCaptions || (ratio === "9:16" && layoutMode !== "classic") || zoom<=1} onClick={() => setZoom(value => clamp(Number((value-.05).toFixed(2)),1,2))}><ZoomOut size={15}/></button>
                  <input aria-label="Video zoom" type="range" min="1" max="2" step=".05" value={zoom} disabled={preserveSourceCaptions || (ratio === "9:16" && layoutMode !== "classic")} onChange={event => setZoom(Number(event.target.value))}/>
                  <button type="button" aria-label="Zoom in" disabled={preserveSourceCaptions || (ratio === "9:16" && layoutMode !== "classic") || zoom>=2} onClick={() => setZoom(value => clamp(Number((value+.05).toFixed(2)),1,2))}><ZoomIn size={15}/></button>
                </div>
                <div className="zoom-scale"><span>100%</span><span>150%</span><span>200%</span></div>
                {preserveSourceCaptions && <p className="zoom-safe-note"><AlertTriangle size={12}/><span>Zoom stays at 100% while original captions are preserved.</span></p>}
              </div>
              <div className="pro-editor-help-card"><MoveHorizontal size={15}/><div><b>Export-safe framing</b><p>Classic uses manual focus and zoom. Smart Layouts use automatic per-shot face framing; manual sliders do not override them. Your layout choice is previewed immediately above.</p></div></div>
            </div>
          </
>}

          {activeTool === "brand" && <>
            <div className="pro-editor-inspector-head"><span>BRAND</span><h3>Current brand</h3></div>
            <div className="pro-editor-inspector-scroll">
              {selectedBrandKit ? <>
                <div className="pro-editor-brand-preview" style={{ borderColor: selectedBrandKit.primary_color }}><span style={{ background: selectedBrandKit.primary_color }}/><b>{selectedBrandKit.logo_text || selectedBrandKit.name}</b></div>
                <div className="pro-editor-stat-grid"><span><small>Preset</small><b>{selectedBrandKit.caption_preset}</b></span><span><small>Default</small><b>{selectedBrandKit.is_default ? "Yes" : "No"}</b></span></div>
              </> : <div className="pro-editor-empty-card">No Brand Kit is applied. Export stays clean and uses the current caption style.</div>}
            </div>
          </>}

          {activeTool === "export" && <>
            <div className="pro-editor-inspector-head"><span>EXPORT</span><h3>Render settings</h3></div>
            <div className="pro-editor-inspector-scroll">
              <div className="pro-editor-field"><label>Export quality</label><select value={resolution} onChange={event => setResolution(event.target.value)}><option value="720p">720p · Fast and efficient</option><option value="1080p">1080p · Any paid plan</option></select></div>
              <div className="toggle-row pro-editor-toggle"><div><b>ClipKaro watermark</b><span>{freePlan ? "Required on Free" : "Optional on your paid plan"}</span></div><button className={watermark ? "on" : ""} aria-pressed={watermark} disabled={freePlan} onClick={() => { if(!freePlan) setWatermark(value => !value); }}><i/></button></div>
              <button className="primary-btn pro-editor-render-button" onClick={render} disabled={renderBusy}>{renderBusy ? <Loader2 className="spin" size={15}/> : <Sparkles size={15}/>} {startingRender ? "Starting securely…" : renderBusy ? "Rendering Short…" : "Render verified Short"}</button>
              <p className="pro-editor-note">Your export keeps the same crop, captions, edit plan, brand and quality settings shown in this workspace.</p>
            </div>
          </>}
        </aside>
      </div>

      <section className={"pro-editor-timeline" + (timelineScrubbing ? " scrubbing" : "") + (trimmingSegment ? " trimming" : "") + (draggedSegmentIndex !== null ? " reordering" : "")}>
        <div className="pro-editor-timeline-toolbar">
          <div className="pro-editor-timeline-play">
            <button type="button" onClick={togglePlayback}>{playing ? <Pause size={14} fill="currentColor"/> : <Play size={14} fill="currentColor"/>}</button>
            <b>{playheadOffset.toFixed(1)}s</b><span>/ {editedDuration.toFixed(1)}s</span>
          </div>
          <div className="pro-editor-timeline-actions">
            <button type="button" onClick={splitAtPlayhead} title="Split at playhead (S)"><Scissors size={13}/> Split</button>
            <button type="button" className="danger" onClick={deleteSelectedSegment} disabled={!selectedSegment || selectedSegmentRemoved} title="Delete selected segment (Delete)"><Trash2 size={13}/> Delete segment</button>
            <span>Space Play · S Split · Delete Remove · Drag yellow edges Trim · Grip & drag Reorder · Ctrl+Z Undo</span>
          </div>
          <div className="pro-editor-timeline-status"><span>{editedDuration.toFixed(1)} sec edited</span><span className="timeline-removal-summary">{editPlan.removed_ranges.length} removals</span><span>{editPlan.split_points.length} split markers</span></div>
        </div>
        <div className="pro-editor-ruler">
          <span className="pro-editor-track-label"/>
          <div>{timelineTicks.map((tick, index) => <span key={index} style={{ left: String(index/6*100) + "%" }}>{tick.toFixed(1)}s</span>)}</div>
        </div>
        <div className="pro-editor-track-row">
          <span className="pro-editor-track-label">Video</span>
          <div
            ref={videoTrackRef}
            className="pro-editor-video-track interactive"
            onPointerDown={beginTimelineScrub}
            onPointerMove={moveTimelineScrub}
            onPointerUp={endTimelineScrub}
            onPointerCancel={endTimelineScrub}
            title="Click or drag to seek. Use the grip on a segment to reorder it."
          >
            {visualTimelineLayout.segments.map(segment => {
              const index = segment.sourceIndex;
              const blockStart = segment.visualStart + (segment.visibleStart - segment.start);
              const blockEnd = segment.visualStart + (segment.visibleEnd - segment.start);
              return <div
                className={"pro-editor-video-segment" +
                  (selectedSegmentIndex === index ? " selected" : "") +
                  (segment.visibleStart > segment.start + .01 || segment.visibleEnd < segment.end - .01 ? " trimmed" : "") +
                  (segment.fullyRemoved ? " removed" : "") +
                  (draggedSegmentIndex === index ? " dragging" : "") +
                  (dragOverSegmentIndex === index && draggedSegmentIndex !== index ? " drop-target" : "")}
                key={"segment-"+index}
                style={{
                  left:String(blockStart/visualTimelineLayout.duration*100)+"%",
                  width:String(Math.max((blockEnd-blockStart)/visualTimelineLayout.duration*100,.6))+"%",
                }}
                onDragOver={event => overSegmentReorder(event,index)}
                onDragEnter={event => overSegmentReorder(event,index)}
                onDrop={event => finishSegmentReorder(event,index)}
              >
                <span>{index+1}</span>
                {!segment.fullyRemoved && <button
                  type="button"
                  className="segment-reorder-grip"
                  draggable
                  aria-label={"Drag segment " + String(index+1) + " to reorder"}
                  title="Drag to reorder segment"
                  onPointerDown={event => event.stopPropagation()}
                  onDragStart={event => beginSegmentReorder(event,index)}
                  onDragEnd={cancelSegmentReorder}
                ><GripVertical size={12}/></button>}
                {selectedSegmentIndex === index && !segment.fullyRemoved && <>
                  <button
                    type="button"
                    draggable={false}
                    className="segment-trim-handle left"
                    aria-label={"Trim start of segment " + String(index+1)}
                    title="Drag to trim segment start"
                    onPointerDown={event => beginSegmentTrim(event,index,"left")}
                    onPointerMove={moveSegmentTrim}
                    onPointerUp={event => finishSegmentTrim(event)}
                    onPointerCancel={event => finishSegmentTrim(event,true)}
                    onClick={event => event.stopPropagation()}
                  ><i/></button>
                  <button
                    type="button"
                    draggable={false}
                    className="segment-trim-handle right"
                    aria-label={"Trim end of segment " + String(index+1)}
                    title="Drag to trim segment end"
                    onPointerDown={event => beginSegmentTrim(event,index,"right")}
                    onPointerMove={moveSegmentTrim}
                    onPointerUp={event => finishSegmentTrim(event)}
                    onPointerCancel={event => finishSegmentTrim(event,true)}
                    onClick={event => event.stopPropagation()}
                  ><i/></button>
                </>}
              </div>;
            })}
            {visualRemovedRanges.map((range,index) => <span className="timeline-removal" key={"video-removal-"+index} style={{ left:String(range.start/visualTimelineLayout.duration*100)+"%", width:String((range.end-range.start)/visualTimelineLayout.duration*100)+"%" }}/>)}
            {visualTimelineLayout.segments.slice(0,-1).map((segment,index) => <span className="timeline-split" key={"video-output-split-"+index} style={{ left:String(segment.visualEnd/visualTimelineLayout.duration*100)+"%" }}/>)}
            <span className="pro-editor-playhead" style={{ left:String(playheadPercent)+"%" }}/>
          </div>
        </div>
        <div className="pro-editor-track-row">
          <span className="pro-editor-track-label">Audio</span>
          <div
            className="waveform smart-waveform pro-editor-audio-track interactive"
            onPointerDown={beginTimelineScrub}
            onPointerMove={moveTimelineScrub}
            onPointerUp={endTimelineScrub}
            onPointerCancel={endTimelineScrub}
            title="Click or drag to seek"
          >
            {Array.from({length:96}).map((_,i)=><i key={i} style={{height:String(10+Math.abs(Math.sin(i*.63))*28)+"px"}}/>)}
            {visualRemovedRanges.map((range,index) => <span className="timeline-removal" key={"audio-removal-"+index} style={{ left:String(range.start/visualTimelineLayout.duration*100)+"%", width:String((range.end-range.start)/visualTimelineLayout.duration*100)+"%" }}/>)}
            {visualTimelineLayout.segments.slice(0,-1).map((segment,index) => <span className="timeline-split" key={"audio-output-split-"+index} style={{ left:String(segment.visualEnd/visualTimelineLayout.duration*100)+"%" }}/>)}
            <span className="pro-editor-playhead" style={{ left:String(playheadPercent)+"%" }}/>
          </div>
        </div>
        <div className="pro-editor-track-row">
          <span className="pro-editor-track-label">Captions</span>
          <div
            className="pro-editor-caption-track interactive"
            onPointerDown={beginTimelineScrub}
            onPointerMove={moveTimelineScrub}
            onPointerUp={endTimelineScrub}
            onPointerCancel={endTimelineScrub}
            title="Click or drag to seek"
          >
            {timelineCaptionBlocks.map((block,index) => <span key={"caption-"+index} style={{ left:String(block.start/visualTimelineLayout.duration*100)+"%", width:String(Math.max((block.end-block.start)/visualTimelineLayout.duration*100,.4))+"%" }} title={block.text} />)}
            <span className="pro-editor-playhead" style={{ left:String(playheadPercent)+"%" }}/>
          </div>
        </div>
      </section>

      {error && <div className={`floating-error ${error === "Saved" ? "success" : ""}`}>{error}</div>}
      {job && !drawerDismissed && <div className="export-drawer"><div className="export-icon">{job.status === "completed" ? <Check /> : job.status === "failed" ? <span>!</span> : <Loader2 className="spin" />}</div><div><b>{job.status === "completed" ? (exportedLayoutIsStale ? "Your previous Short is ready" : "Your Short is ready") : job.status === "failed" ? job.error || job.message : job.message}</b><span>{job.status === "completed" ? (exportedLayoutIsStale ? "This MP4 uses the previously exported layout. Export Short again to apply your newly selected layout." : "This MP4 uses the settings selected when export started.") : `${job.progress}% complete`}</span><div className="progress"><i style={{ width: `${job.progress}%` }} /></div></div>{job.status === "completed" && <div className="post-karo-drawer-actions">
        <button className="secondary-btn" type="button" onClick={downloadReadyExport} disabled={downloading}>{downloading ? <Loader2 className="spin" size={15}/> : <Download size={15}/>} {downloading ? "Preparing…" : "Download MP4"}</button>
        <button className={postKaro?.ready ? "primary-btn" : "post-karo-locked-btn"} type="button" onClick={openPostKaro}>{postKaro?.ready ? <Send size={15}/> : <LockKeyhole size={14}/>} Post Now</button>
        {showPostKaroPrompt && <div className="post-karo-gate-backdrop" onMouseDown={() => setShowPostKaroPrompt(false)}>
          <div className="post-karo-gate-card" onMouseDown={event => event.stopPropagation()}>
            <div className="post-karo-gate-icon"><Send/></div>
            <span>POST KARO</span>
            <h3>Set up Post Karo first</h3>
            <p>Post Karo is free on every ClipKaro plan. Connect Instagram or YouTube once, then publish finished Shorts directly from ClipKaro.</p>
            <div><button className="secondary-btn" type="button" onClick={() => setShowPostKaroPrompt(false)}>Not now</button><button className="primary-btn" type="button" onClick={() => router.push("/post-karo?export=" + encodeURIComponent(exportId))}>Set up Post Karo <ArrowRight size={14}/></button></div>
          </div>
        </div>}
      </div>}<button className="export-drawer-close" type="button" aria-label="Dismiss export status" onClick={() => setDrawerDismissed(true)}><X size={15}/></button></div>}
    </div>
  );
}
