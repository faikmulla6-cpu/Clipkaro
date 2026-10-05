"use client";

import { ErrorState } from "@/components/ErrorState";
import { useAuth } from "@/components/AuthProvider";
import { API_URL, api, patchJSON, postJSON } from "@/lib/api";
import { downloadExport, newBehaviorSession, trackClipBehavior } from "@/lib/behavior";
import {
  AlertTriangle, AlignCenter, AlignLeft, AlignRight, ArrowLeft, ArrowRight, Captions, Check, Download, Film, Loader2, LockKeyhole, MoveHorizontal,
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
type EditPlan = { version: 1; removed_ranges: RemovedRange[]; split_points: number[] };
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

const styles = [
  ["kinetic", "Kinetic", "Punchy highlighted words"],
  ["clean", "Clean", "Readable creator standard"],
  ["bold", "Bold", "Large high-contrast impact"],
  ["minimal", "Minimal", "Quiet and professional"],
  ["hindi-pop", "India Pop", "Hindi and Hinglish energy"],
] as const;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);
const emptyEditPlan = (): EditPlan => ({ version: 1, removed_ranges: [], split_points: [] });
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

export default function Editor() {
  const { clipId } = useParams<{ clipId: string }>();
  const projectId = useSearchParams().get("project");
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const captionContentRef = useRef<HTMLSpanElement>(null);
  const captionDragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);
  const timelineScrubRef = useRef<{ pointerId: number; element: HTMLDivElement } | null>(null);
  const videoTrackRef = useRef<HTMLDivElement>(null);
  const trimDragRef = useRef<{
    pointerId: number;
    segmentIndex: number;
    edge: "left" | "right";
    element: HTMLButtonElement;
    track: HTMLDivElement;
    segment: { start: number; end: number };
    basePlan: EditPlan;
    draftPlan: EditPlan;
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
      setProject(data); setClip(selected); setHook(selected.hook); setTitle(selected.title);
      setTranscript(selected.transcript_text || selected.hook);
      setStart(selected.start_time); setEnd(selected.end_time); setPlayhead(selected.start_time);
      api<CaptionTrack>(`/clips/${clipId}/captions`).then(track => {
        const hasSourceCaptions = !!track.source_has_burned_captions;
        const source = track.source_words || track.words;
        setSourceWords(source); setTimedCaptionWords(source); setCaptionCards(track.source_words ? [] : (track.cards || [])); setSpeechRegions(track.speech_regions || []);
        setEditPlan(track.edit_plan || emptyEditPlan()); setCleanSpeechRanges(track.clean_speech_ranges || []); setUndoPlans([]); setRedoPlans([]);
        setSourceHasCaptions(hasSourceCaptions); setSourceCaptionBand(track.source_caption_band ?? null);
        setReviewSuggested(!!track.review_suggested); setReviewReasons(track.review_reasons || []);
        setIndiaQualityHint(track.india_quality?.india_quality_suitable ? `${track.india_quality.likely_language_style || "Indian speech"} detected` : "");
        if (hasSourceCaptions) setPreserveSourceCaptions(true);
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
  const editedDuration = useMemo(() => Math.max(.25, end - start - mergedRemovedRanges.reduce((total, range) => total + range.end - range.start, 0)), [mergedRemovedRanges, start, end]);
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
  const displayTimelineSegments = useMemo(() => timelineSegments.map(segment => {
    const bounds = segmentTrimBounds(segment, editPlan.removed_ranges);
    const fullyRemoved = mergedRemovedRanges.some(range => range.start <= segment.start + .01 && range.end >= segment.end - .01);
    return { ...segment, ...bounds, fullyRemoved };
  }), [timelineSegments, editPlan.removed_ranges, mergedRemovedRanges]);
  const selectedSegment = selectedSegmentIndex === null ? null : timelineSegments[selectedSegmentIndex] || null;
  const selectedDisplaySegment = selectedSegmentIndex === null ? null : displayTimelineSegments[selectedSegmentIndex] || null;
  const selectedSegmentRemoved = !!selectedDisplaySegment?.fullyRemoved;
  const selectedSegmentHasTrim = !!selectedDisplaySegment && (
    selectedDisplaySegment.visibleStart > selectedDisplaySegment.start + .01 ||
    selectedDisplaySegment.visibleEnd < selectedDisplaySegment.end - .01
  );
  useEffect(() => {
    if (!sourceWords.length) return;
    setTranscript(sourceWords.filter(word => !wordRemoved(word)).map(word => word.text).join(" "));
  }, [sourceWords, editPlan, wordRemoved]);
  const captionState = useMemo(() => {
    if (!captionWords.length) return { words: ["Add", "your", "caption", "text"], active: 0, uncertain: [] as boolean[], breakAfter: -1, visible: true };
    const duration = Math.max(end - start, 1);
    const relative = playhead - start;
    const speechActive = !speechRegions.length || speechRegions.some(region => relative >= region.start && relative < region.end);
    if (!speechActive) {
      return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
    }
    const liveCard = captionCards.find(card => relative >= card.start && relative < card.end);
    if (liveCard) {
      const flat = liveCard.lines.join(" ").split(/\s+/).filter(Boolean);
      let active = liveCard.words.findIndex(word => relative >= word.start && relative < word.end);
      if (active < 0) liveCard.words.forEach((word, index) => { if (word.start <= relative) active = index; });
      return { words: flat, active: clamp(active, 0, Math.max(flat.length - 1, 0)),
               uncertain: liveCard.words.map(word => (word.confidence ?? 1) < .6),
               breakAfter: liveCard.lines.length === 2 ? liveCard.lines[0].split(/\s+/).length : -1,
               visible: true };
    }
    if (sourceWords.length) {
      const visible = sourceWords.filter(word => !wordRemoved(word));
      let active = visible.findIndex(word => relative >= word.start && relative < word.end);
      if (active < 0) return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
      const chunkStart = Math.floor(active / 4) * 4;
      const chunk = visible.slice(chunkStart, chunkStart + 4);
      return { words: chunk.map(word => word.text), active: active - chunkStart,
        uncertain: chunk.map(word => (word.confidence ?? 1) < .6), breakAfter: -1, visible: true };
    }
    // Once real word/card timing exists, silence must be visually silent too.
    // Do not keep the previous phrase pinned on screen between speech regions.
    if (timedCaptionWords.length || captionCards.length) {
      return { words: [] as string[], active: -1, uncertain: [] as boolean[], breakAfter: -1, visible: false };
    }
    const chunkSize = 4;
    const wordIndex = clamp(
      Math.floor(clamp((playhead - start) / duration, 0, .999) * captionWords.length),
      0,
      captionWords.length - 1,
    );
    const chunkStart = Math.floor(wordIndex / chunkSize) * chunkSize;
    const chunk = captionWords.slice(chunkStart, chunkStart + chunkSize);
    return { words: chunk, active: wordIndex - chunkStart, uncertain: chunk.map(() => false), breakAfter: -1, visible: true };
  }, [captionWords, timedCaptionWords, captionCards, sourceWords, wordRemoved, speechRegions, playhead, start, end]);

  function commitEditPlan(next: EditPlan) {
    setUndoPlans(history => [...history.slice(-49), editPlan]);
    setRedoPlans([]);
    setEditPlan(next);
    const kept = sourceWords.filter(word => !wordRemoved(word, next)).map(word => word.text).join(" ");
    if (kept) setTranscript(kept);
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
    const splitPoints = [...editPlan.split_points, point].sort((a, b) => a - b);
    commitEditPlan({ ...editPlan, split_points: splitPoints });
    setSelectedSegmentIndex(splitPoints.filter(item => item <= point + .001).length);
  }

  function selectSegmentForRelative(relative: number) {
    const safe = clamp(relative, 0, timelineSpan);
    const index = timelineSegments.findIndex((segment, segmentIndex) =>
      safe >= segment.start && (safe < segment.end || (segmentIndex === timelineSegments.length - 1 && safe <= segment.end)),
    );
    if (index >= 0) setSelectedSegmentIndex(index);
  }

  function seekTimelineRelative(relative: number, select = true) {
    const safe = clamp(relative, 0, timelineSpan);
    const sourceTime = start + safe;
    setPlayhead(sourceTime);
    if (videoRef.current) videoRef.current.currentTime = sourceTime;
    if (select) selectSegmentForRelative(safe);
  }

  function timelineRelativeFromPointer(clientX: number, element: HTMLDivElement) {
    const rect = element.getBoundingClientRect();
    if (!rect.width) return 0;
    return clamp((clientX - rect.left) / rect.width * timelineSpan, 0, timelineSpan);
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
    const candidate = [...editPlan.removed_ranges, { ...selectedSegment, reason: "segment" as const }].sort((a, b) => a.start - b.start);
    const merged: Array<{ start: number; end: number }> = [];
    candidate.forEach(range => {
      const previous = merged.at(-1);
      if (previous && range.start <= previous.end + .001) previous.end = Math.max(previous.end, range.end);
      else merged.push({ start: range.start, end: range.end });
    });
    const removedDuration = merged.reduce((total, range) => total + range.end - range.start, 0);
    if (timelineSpan - removedDuration < .25) {
      setError("Keep at least 0.25 seconds of the clip.");
      return;
    }
    removeRange({ ...selectedSegment, reason: "segment" });
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
    if (!videoRef.current) return;
    videoRef.current.currentTime = start;
    setPlayhead(start);
  }

  function onLoaded() { seekToClipStart(); }
  function onTimeUpdate() {
    const video = videoRef.current; if (!video) return;
    const relative = video.currentTime - start;
    const removed = editPlan.removed_ranges.find(range => rangeContains(range, relative));
    if (removed) { video.currentTime = Math.min(end, start + removed.end + .002); setPlayhead(video.currentTime); return; }
    if (video.currentTime < start - .2 || video.currentTime >= end) {
      video.currentTime = start;
      if (!video.paused) void video.play();
    }
    setPlayhead(video.currentTime);
  }
  async function togglePlayback() {
    const video = videoRef.current; if (!video) return;
    if (video.paused) {
      if (video.currentTime < start || video.currentTime >= end) video.currentTime = start;
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
        hook, title, transcript_text: transcript, start_time: start, end_time: end, edit_plan: editPlan,
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
    renderStartRef.current = true;
    setStartingRender(true);
    setDrawerDismissed(false);
    setError("");
    try {
      await save(false);
      const output = await postJSON<ExportResponse>(`/clips/${clip.id}/export`, {
        resolution, aspect_ratio: ratio, caption_style: captionStyle,
        caption_position: captionPosition, caption_x: captionX, caption_y: captionY, caption_scale: captionScale,
        caption_alignment: captionAlignment,
        focus_x: focusX, zoom, hook_text: hook, hook_enabled: hookEnabled, watermark, brand_kit_id: brandKitId || null,
        preserve_source_captions: preserveSourceCaptions,
        india_quality_mode: indiaQualityMode,
        caption_language_style: captionLanguageStyle,
      });
      setExportId(output.id);
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
  const positionClass = captionY === null ? "position-" + captionPosition : "caption-custom-position";
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
  const showHook = playhead - start < 4.5;
  const playheadOffset = clamp(playhead - start, 0, timelineSpan);
  const playheadPercent = playheadOffset / timelineSpan * 100;
  const timelineTicks = Array.from({ length: 7 }, (_, index) => timelineSpan * index / 6);

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
                {sourceWords.map((word, index) => {
                  const removed = editPlan.removed_ranges.find(range => word.start < range.end && word.end > range.start);
                  const pause = index < sourceWords.length - 1 ? pauseBlocks.find(item => Math.abs(item.start - word.end) < .01) : undefined;
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
              <div className="export-summary pro-editor-export-summary"><span>Format <b>{ratio}</b></span><span>Duration <b>{editedDuration.toFixed(1)}s</b></span><span>Captions <b>{styles.find(style => style[0] === captionStyle)?.[1]}</b></span><span>Caption size <b>{Math.round(captionScale*100)}%</b></span><span>Placement <b>{captionY === null ? (captionPosition === "bottom" ? "Lower" : captionPosition === "above" ? "Upper" : "Centre") : "Custom"}</b></span><span>Align <b>{captionAlignment}</b></span><span>Frame <b>{preserveSourceCaptions ? "Full" : Math.round(focusX) + "%"}</b></span><span>Zoom <b>{preserveSourceCaptions ? "100% safe" : Math.round(zoom*100) + "%"}</b></span><span>India <b>{indiaQualityMode ? captionLanguageStyle.replace("_", " ") : "Off"}</b></span><span>Brand <b>{selectedBrandKit?.name || "None"}</b></span></div>
            </div>
          </>}
        </aside>
        <section className="pro-editor-stage">
          <div className="pro-editor-stage-meta">
            <span>{ratio} canvas</span>
            <span>{editedDuration.toFixed(1)}s edited</span>
          </div>
          <div ref={canvasRef} className={"video-canvas pro-video-canvas ratio-" + ratio.replace(":", "-")}>
            <video
              ref={videoRef}
              src={API_URL + "/projects/" + project.id + "/media"}
              preload="metadata"
              playsInline
              onLoadedMetadata={onLoaded}
              onTimeUpdate={onTimeUpdate}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              style={{
                objectFit: preserveSourceCaptions ? "contain" : "cover",
                objectPosition: String(focusX) + "% 50%",
                transform: preserveSourceCaptions ? "scale(1)" : "scale(" + String(zoom) + ")",
              }}
            />
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
            <span>/ {timelineSpan.toFixed(1)}s</span>
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
                <div>
                  <span>Selected segment</span>
                  <b>{selectedSegment ? selectedSegment.start.toFixed(1) + "s – " + selectedSegment.end.toFixed(1) + "s" : "Click a timeline segment"}</b>
                </div>
                <button type="button" onClick={deleteSelectedSegment} disabled={!selectedSegment || selectedSegmentRemoved} title="Delete selected segment from video, audio and captions"><Trash2 size={14}/>{selectedSegmentRemoved ? "Removed" : "Delete"}</button>
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
                <div><b>Preserve source captions</b><span>{sourceHasCaptions ? "Detected near " + Math.round((sourceCaptionBand ?? .82)*100) + "% height" : "Use when source already contains subtitles"}</span></div>
                <button className={preserveSourceCaptions ? "on" : ""} aria-pressed={preserveSourceCaptions} onClick={() => setPreserveSourceCaptions(value => !value)}><i/></button>
              </div>
            </div>
          </>}

          {activeTool === "frame" && <>
            <div className="pro-editor-inspector-head"><span>FRAME</span><h3>Reframe & zoom</h3></div>
            <div className="pro-editor-inspector-scroll">
              <div className="pro-editor-field">
                <label><MoveHorizontal size={13}/> Manual reframe: {focusX}%</label>
                <input className="focus-slider" type="range" min="0" max="100" value={focusX} onChange={event => setFocusX(Number(event.target.value))}/>
                <div className="focus-labels"><span>Left</span><span>Centre</span><span>Right</span></div>
              </div>
              <div className={"pro-editor-field zoom-section" + (preserveSourceCaptions ? " disabled" : "")}>
                <div className="zoom-heading"><label><ZoomIn size={13}/> Video zoom: {Math.round(zoom*100)}%</label><button className="zoom-reset" type="button" disabled={preserveSourceCaptions || zoom===1} onClick={() => setZoom(1)}>Reset</button></div>
                <div className="zoom-control">
                  <button type="button" aria-label="Zoom out" disabled={preserveSourceCaptions || zoom<=1} onClick={() => setZoom(value => clamp(Number((value-.05).toFixed(2)),1,2))}><ZoomOut size={15}/></button>
                  <input aria-label="Video zoom" type="range" min="1" max="2" step=".05" value={zoom} disabled={preserveSourceCaptions} onChange={event => setZoom(Number(event.target.value))}/>
                  <button type="button" aria-label="Zoom in" disabled={preserveSourceCaptions || zoom>=2} onClick={() => setZoom(value => clamp(Number((value+.05).toFixed(2)),1,2))}><ZoomIn size={15}/></button>
                </div>
                <div className="zoom-scale"><span>100%</span><span>150%</span><span>200%</span></div>
                {preserveSourceCaptions && <p className="zoom-safe-note"><AlertTriangle size={12}/><span>Zoom stays at 100% while original captions are preserved.</span></p>}
              </div>
              <div className="pro-editor-help-card"><MoveHorizontal size={15}/><div><b>Export-safe framing</b><p>Ratio, horizontal focus and zoom use the current renderer contract.</p></div></div>
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

      <section className={"pro-editor-timeline" + (timelineScrubbing ? " scrubbing" : "")}>
        <div className="pro-editor-timeline-toolbar">
          <div className="pro-editor-timeline-play">
            <button type="button" onClick={togglePlayback}>{playing ? <Pause size={14} fill="currentColor"/> : <Play size={14} fill="currentColor"/>}</button>
            <b>{playheadOffset.toFixed(1)}s</b><span>/ {timelineSpan.toFixed(1)}s</span>
          </div>
          <div className="pro-editor-timeline-actions">
            <button type="button" onClick={splitAtPlayhead} title="Split at playhead (S)"><Scissors size={13}/> Split</button>
            <button type="button" className="danger" onClick={deleteSelectedSegment} disabled={!selectedSegment || selectedSegmentRemoved} title="Delete selected segment (Delete)"><Trash2 size={13}/> Delete segment</button>
            <span>Space Play · S Split · Delete Remove · Ctrl+Z Undo</span>
          </div>
          <div className="pro-editor-timeline-status"><span>{editedDuration.toFixed(1)} sec edited</span><span>{editPlan.removed_ranges.length} removals</span><span>{editPlan.split_points.length} split markers</span></div>
        </div>
        <div className="pro-editor-ruler">
          <span className="pro-editor-track-label"/>
          <div>{timelineTicks.map((tick, index) => <span key={index} style={{ left: String(index/6*100) + "%" }}>{tick.toFixed(1)}s</span>)}</div>
        </div>
        <div className="pro-editor-track-row">
          <span className="pro-editor-track-label">Video</span>
          <div
            className="pro-editor-video-track interactive"
            onPointerDown={beginTimelineScrub}
            onPointerMove={moveTimelineScrub}
            onPointerUp={endTimelineScrub}
            onPointerCancel={endTimelineScrub}
            title="Click or drag to seek. Click a segment to select it."
          >
            {timelineSegments.map((segment,index) => <div
              className={"pro-editor-video-segment" + (selectedSegmentIndex === index ? " selected" : "")}
              key={"segment-"+index}
              style={{ left:String(segment.start/timelineSpan*100)+"%", width:String((segment.end-segment.start)/timelineSpan*100)+"%" }}
            ><span>{index+1}</span></div>)}
            {editPlan.removed_ranges.map((range,index) => <span className="timeline-removal" key={"video-removal-"+index} style={{ left:String(range.start/timelineSpan*100)+"%", width:String((range.end-range.start)/timelineSpan*100)+"%" }}/>)}
            {editPlan.split_points.map((point,index) => <span className="timeline-split" key={"video-split-"+index} style={{ left:String(point/timelineSpan*100)+"%" }}/>)}
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
            {editPlan.removed_ranges.map((range,index) => <span className="timeline-removal" key={"audio-removal-"+index} style={{ left:String(range.start/timelineSpan*100)+"%", width:String((range.end-range.start)/timelineSpan*100)+"%" }}/>)}
            {editPlan.split_points.map((point,index) => <span className="timeline-split" key={"audio-split-"+index} style={{ left:String(point/timelineSpan*100)+"%" }}/>)}
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
            {captionCards.map((card,index) => <span key={"caption-"+index} style={{ left:String(card.start/timelineSpan*100)+"%", width:String(Math.max((card.end-card.start)/timelineSpan*100,.4))+"%" }} title={card.lines.join(" ")} />)}
            <span className="pro-editor-playhead" style={{ left:String(playheadPercent)+"%" }}/>
          </div>
        </div>
      </section>

      {error && <div className={`floating-error ${error === "Saved" ? "success" : ""}`}>{error}</div>}
      {job && !drawerDismissed && <div className="export-drawer"><div className="export-icon">{job.status === "completed" ? <Check /> : job.status === "failed" ? <span>!</span> : <Loader2 className="spin" />}</div><div><b>{job.status === "completed" ? "Your Short is ready" : job.status === "failed" ? job.error || job.message : job.message}</b><span>{job.status === "completed" ? "The downloaded MP4 matches this crop, zoom and caption style" : `${job.progress}% complete`}</span><div className="progress"><i style={{ width: `${job.progress}%` }} /></div></div>{job.status === "completed" && <div className="post-karo-drawer-actions">
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
