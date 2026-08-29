"use client";

import { AppShell } from "@/components/AppShell";
import { ErrorState } from "@/components/ErrorState";
import { useAuth } from "@/components/AuthProvider";
import { API_URL, api, patchJSON, postJSON } from "@/lib/api";
import { downloadExport, newBehaviorSession, trackClipBehavior } from "@/lib/behavior";
import {
  AlertTriangle, AlignCenter, Captions, Check, Download, Film, Loader2, MoveHorizontal,
  Palette, Pause, Play, Save, Smartphone, Sparkles, Square, Type,
} from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Clip = {
  id: string; title: string; hook: string; transcript_text: string;
  start_time: number; end_time: number; score: number;
};
type Project = { id: string; title: string; duration: number; clips: Clip[] };
type ExportResponse = { id: string; job_id: string; status: string; expires_at: string };
type ExportStatus = { id: string; status: string; progress: number; download_url?: string | null; expires_at: string };
type Job = { id?: string; status: string; progress: number; message: string; error?: string; export_id?: string };
type TimedWord = { start: number; end: number; text: string; confidence?: number };
type CaptionCard = { start: number; end: number; lines: string[]; words: TimedWord[] };
type CaptionTrack = {
  language: string; clip_start: number; clip_end: number; words: TimedWord[]; cards: CaptionCard[];
  source_has_burned_captions?: boolean; source_caption_band?: number | null;
  review_suggested?: boolean; review_reasons?: string[];
  india_quality?: { india_quality_suitable?: boolean; likely_language_style?: string; code_switch_score?: number };
};
type CaptionStyle = { id: string; name: string; font_family: string; font_weight: number; font_size_width_ratio: number; text_transform: string; text_color: string; highlight_color: string; highlight_background: string; shadow: string; line_height: number; horizontal_inset_ratio: number; bottom_safe_ratio: number; above_safe_ratio: number; active_word_scale: number; corner_radius_px: number; background: string };
type BrandKit = { id: string; name: string; primary_color: string; logo_text?: string | null; caption_preset: string; is_default: boolean };
type Tab = "style" | "transcript" | "export";
type CaptionLanguageStyle = "auto" | "roman_hinglish" | "original";

const styles = [
  ["kinetic", "Kinetic", "Punchy highlighted words"],
  ["clean", "Clean", "Readable creator standard"],
  ["bold", "Bold", "Large high-contrast impact"],
  ["minimal", "Minimal", "Quiet and professional"],
  ["hindi-pop", "India Pop", "Hindi and Hinglish energy"],
] as const;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export default function Editor() {
  const { clipId } = useParams<{ clipId: string }>();
  const projectId = useSearchParams().get("project");
  const { user } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
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
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(30);
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [captionStyle, setCaptionStyle] = useState("kinetic");
  const [captionPosition, setCaptionPosition] = useState<"bottom" | "above" | "center">("bottom");
  const [ratio, setRatio] = useState("9:16");
  const [focusX, setFocusX] = useState(50);
  const [resolution, setResolution] = useState("720p");
  const [watermark, setWatermark] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("style");
  const [saving, setSaving] = useState(false);
  const [startingRender, setStartingRender] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [exportId, setExportId] = useState("");
  const [error, setError] = useState("");
  const [timedCaptionWords, setTimedCaptionWords] = useState<TimedWord[]>([]);
  const [captionCards, setCaptionCards] = useState<CaptionCard[]>([]);
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
        setTimedCaptionWords(track.words); setCaptionCards(track.cards || []);
        setSourceHasCaptions(hasSourceCaptions); setSourceCaptionBand(track.source_caption_band ?? null);
        setReviewSuggested(!!track.review_suggested); setReviewReasons(track.review_reasons || []);
        setIndiaQualityHint(track.india_quality?.india_quality_suitable ? `${track.india_quality.likely_language_style || "Indian speech"} detected` : "");
        if (hasSourceCaptions) setPreserveSourceCaptions(true);
      }).catch(() => { setTimedCaptionWords([]); setCaptionCards([]); setSourceHasCaptions(false); setSourceCaptionBand(null); setPreserveSourceCaptions(false); setReviewSuggested(false); setReviewReasons([]); setIndiaQualityHint(""); });
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
    // Free is always watermarked. Paid plans start watermark-free, while still
    // allowing a creator to opt into the ClipKaro mark if they want it.
    setWatermark(user.plan === "free");
    lastPlanRef.current = user.plan;
  }, [user]);
  useEffect(() => {
    if (indiaQualityMode && preserveSourceCaptions && captionPosition === "bottom") {
      setCaptionPosition("above");
    }
  }, [indiaQualityMode, preserveSourceCaptions, captionPosition]);
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
  const captionState = useMemo(() => {
    if (!captionWords.length) return { words: ["Add", "your", "caption", "text"], active: 0, uncertain: [] as boolean[], breakAfter: -1 };
    const duration = Math.max(end - start, 1);
    const relative = playhead - start;
    const liveCard = captionCards.find(card => relative >= card.start && relative <= card.end);
    if (liveCard) {
      const flat = liveCard.lines.join(" ").split(/\s+/).filter(Boolean);
      let active = liveCard.words.findIndex(word => relative >= word.start && relative < word.end);
      if (active < 0) liveCard.words.forEach((word, index) => { if (word.start <= relative) active = index; });
      return { words: flat, active: clamp(active, 0, Math.max(flat.length - 1, 0)),
               uncertain: liveCard.words.map(word => (word.confidence ?? 1) < .6),
               breakAfter: liveCard.lines.length === 2 ? liveCard.lines[0].split(/\s+/).length : -1 };
    }
    const chunkSize = 4;
    let wordIndex: number;
    if (timedCaptionWords.length) {
      const sourceIndex = timedCaptionWords.findIndex(word => relative >= word.start && relative < word.end);
      let settledIndex = sourceIndex;
      if (settledIndex < 0) {
        settledIndex = 0;
        timedCaptionWords.forEach((word, index) => { if (word.start <= relative) settledIndex = index; });
      }
      wordIndex = Math.round(Math.max(0, settledIndex) * Math.max(0, captionWords.length - 1) /
                             Math.max(1, timedCaptionWords.length - 1));
    } else {
      wordIndex = Math.floor(clamp((playhead - start) / duration, 0, .999) * captionWords.length);
    }
    wordIndex = clamp(wordIndex, 0, captionWords.length - 1);
    const chunkStart = Math.floor(wordIndex / chunkSize) * chunkSize;
    const chunk = captionWords.slice(chunkStart, chunkStart + chunkSize);
    const uncertain = chunk.map((_, offset) => {
      if (!timedCaptionWords.length) return false;
      const sourceIndex = Math.round((chunkStart + offset) * Math.max(0, timedCaptionWords.length - 1) /
                                     Math.max(1, captionWords.length - 1));
      return (timedCaptionWords[sourceIndex]?.confidence ?? 1) < .6;
    });
    return { words: chunk, active: wordIndex - chunkStart, uncertain, breakAfter: -1 };
  }, [captionWords, timedCaptionWords, captionCards, playhead, start, end]);

  function seekToClipStart() {
    if (!videoRef.current) return;
    videoRef.current.currentTime = start;
    setPlayhead(start);
  }

  function onLoaded() { seekToClipStart(); }
  function onTimeUpdate() {
    const video = videoRef.current; if (!video) return;
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
        hook, title, transcript_text: transcript, start_time: start, end_time: end,
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
    setError("");
    try {
      await save(false);
      const output = await postJSON<ExportResponse>(`/clips/${clip.id}/export`, {
        resolution, aspect_ratio: ratio, caption_style: captionStyle,
        caption_position: captionPosition, focus_x: focusX,
        hook_text: hook, watermark, brand_kit_id: brandKitId || null,
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

  if (loadError) return <AppShell title="Creator studio"><ErrorState message={loadError} retry={load} /></AppShell>;
  if (!clip || !project) return <AppShell title="Creator studio"><div className="screen-loader inline"><div className="loader-mark">✦</div><p>Loading the real video preview…</p></div></AppShell>;

  const selectedBrandKit = brandKits.find(kit => kit.id === brandKitId);
  const positionClass = `position-${captionPosition}`;
  const selectedCaptionStyle = captionStyles.find(style => style.id === captionStyle);
  const previewStyle = selectedCaptionStyle ? {
    "--caption-font-family": `${selectedCaptionStyle.font_family}, sans-serif`,
    "--caption-font-weight": selectedCaptionStyle.font_weight,
    "--caption-font-size-ratio": selectedCaptionStyle.font_size_width_ratio,
    "--caption-line-height": selectedCaptionStyle.line_height,
    "--caption-text-transform": selectedCaptionStyle.text_transform,
    "--caption-text-color": selectedCaptionStyle.text_color,
    "--caption-highlight-color": selectedCaptionStyle.highlight_color,
    "--caption-highlight-background": selectedCaptionStyle.highlight_background,
    "--caption-shadow": selectedCaptionStyle.shadow,
    "--caption-horizontal-inset": `${selectedCaptionStyle.horizontal_inset_ratio * 100}%`,
    "--caption-bottom": `${selectedCaptionStyle.bottom_safe_ratio * 100}%`,
    "--caption-above": `${selectedCaptionStyle.above_safe_ratio * 100}%`,
    "--caption-active-scale": selectedCaptionStyle.active_word_scale,
    "--caption-corner-radius": `${selectedCaptionStyle.corner_radius_px}px`,
    "--caption-background": selectedCaptionStyle.background,
  } as CSSProperties : undefined;
  const visibleHook = hook.trim().split(/\s+/).slice(0, 8).join(" ");
  const showHook = playhead - start < 4.5;
  return (
    <AppShell title="Creator studio" subtitle={project.title} action={<>
      <button className="secondary-btn small" onClick={() => save()} disabled={saving || renderBusy}>{saving ? <Loader2 className="spin" size={14} /> : <Save size={14} />}Save</button>
      <button className="primary-btn small" onClick={render} disabled={renderBusy}>{renderBusy ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}{startingRender ? "Starting…" : renderBusy ? "Rendering…" : "Export Short"}</button>
    </>}>
      <div className="editor-shell">
        <aside className="editor-tools">
          <button className={activeTab === "style" ? "active" : ""} onClick={() => setActiveTab("style")}><Captions /><span>Style</span></button>
          <button className={activeTab === "transcript" ? "active" : ""} onClick={() => setActiveTab("transcript")}><Type /><span>Words</span></button>
          <button className={activeTab === "export" ? "active" : ""} onClick={() => setActiveTab("export")}><Film /><span>Export</span></button>
        </aside>

        <section className="canvas-area">
          <div className={`video-canvas ratio-${ratio.replace(":", "-")}`}>
            <video
              ref={videoRef}
              src={`${API_URL}/projects/${project.id}/media`}
              preload="metadata"
              playsInline
              onLoadedMetadata={onLoaded}
              onTimeUpdate={onTimeUpdate}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              style={{ objectFit: preserveSourceCaptions ? "contain" : "cover", objectPosition: `${focusX}% 50%` }}
            />
            <button className="canvas-play" onClick={togglePlayback}>{playing ? <Pause fill="currentColor" /> : <Play fill="currentColor" />}</button>
            {showHook && visibleHook && <div className="canvas-hook">{visibleHook}</div>}
            <div className={`caption-preview style-${captionStyle} ${positionClass}`} style={previewStyle}>
              {captionState.words.map((word, index) => <span className={`${index === captionState.active ? "active-word" : ""} ${captionState.uncertain[index] ? "low-confidence" : ""}`} key={`${word}-${index}`}>{word} {captionState.breakAfter === index + 1 && <br/>}</span>)}
            </div>
            {selectedBrandKit?.logo_text && <div className="canvas-brandmark" style={{ color: selectedBrandKit.primary_color }}>{selectedBrandKit.logo_text}</div>}
            {watermark && <div className="canvas-watermark">✦ ClipKaro AI</div>}
            <div className="safe-zone" />
          </div>

          <div className="timeline">
            <div className="timeline-head"><button onClick={togglePlayback}>{playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Pause clip" : "Play selected clip"}</button><b>{Math.round(end - start)} sec</b></div>
            <div className="waveform">{Array.from({ length: 64 }).map((_, i) => <i key={i} style={{ height: `${18 + Math.abs(Math.sin(i * .7)) * 35}px` }} />)}<div className="trim-region" style={{ "--playhead": `${clamp((playhead - start) / Math.max(end - start, 1), 0, 1) * 100}%` } as React.CSSProperties} /></div>
            <div className="time-ruler"><span>{start.toFixed(1)}s</span><span>{playhead.toFixed(1)}s live</span><span>{end.toFixed(1)}s</span></div>
          </div>
        </section>

        <aside className="editor-panel">
          <div className="editor-tabs">
            {(["style", "transcript", "export"] as Tab[]).map(tab => <button key={tab} className={activeTab === tab ? "active" : ""} onClick={() => setActiveTab(tab)}>{tab}</button>)}
          </div>

          {activeTab === "style" && <>
            {sourceHasCaptions && <div className="editor-section"><p className="field-note"><b>Existing subtitles detected.</b> Preserve source captions keeps the full video frame inside the export so original subtitle pixels are not cropped.</p></div>}
            {reviewSuggested && <div className="editor-section"><p className="field-note review-note"><AlertTriangle size={13}/><span><b>Review suggested.</b> {reviewReasons.slice(0, 2).join(", ") || "Some words look uncertain."}</span></p></div>}
            <div className="editor-section"><label>Hook text</label><textarea value={hook} onChange={event => setHook(event.target.value)} maxLength={120} /><div className="input-count">{hook.length}/120</div></div>
            {brandKits.length > 0 && <div className="editor-section"><label><Palette size={13}/> Brand kit</label><select value={brandKitId} onChange={event => { const id = event.target.value; setBrandKitId(id); const kit = brandKits.find(item => item.id === id); if (kit && styles.some(style => style[0] === kit.caption_preset)) setCaptionStyle(kit.caption_preset); }}><option value="">No brand kit</option>{brandKits.map(kit => <option key={kit.id} value={kit.id}>{kit.name}{kit.is_default ? " · Default" : ""}</option>)}</select><p className="field-note">Applies your saved wordmark, brand color and preferred caption personality to this export.</p></div>}
            <div className="toggle-row"><div><b>India Quality Mode</b><span>{indiaQualityHint || "Better defaults for Hindi, Hinglish and Indian English"}</span></div><button className={indiaQualityMode ? "on" : ""} aria-pressed={indiaQualityMode} onClick={() => setIndiaQualityMode(value => !value)}><i /></button></div>
            {indiaQualityMode && <div className="editor-section"><label>Caption language style</label><select value={captionLanguageStyle} onChange={event => setCaptionLanguageStyle(event.target.value as CaptionLanguageStyle)}><option value="auto">Auto</option><option value="roman_hinglish">Roman Hinglish</option><option value="original">Original transcript</option></select><p className="field-note">Roman Hinglish keeps suitable Hindi/Hinglish captions readable in Latin script without translating the clip.</p></div>}
            <div className="editor-section"><label>Caption personality — preview changes instantly</label><div className="style-options">{styles.map(style => <button type="button" className={captionStyle === style[0] ? "active" : ""} onClick={() => setCaptionStyle(style[0])} key={style[0]}><span className={`style-swatch ${style[0]}`}>Aa</span><div><b>{style[1]}</b><small>{style[2]}</small></div>{captionStyle === style[0] && <Check size={14} />}</button>)}</div></div>
            <div className="editor-section"><label>Canvas ratio</label><div className="ratio-options">{[["9:16", Smartphone, "Shorts"], ["4:5", AlignCenter, "Feed"], ["1:1", Square, "Square"]].map(([value, Icon, name]) => <button type="button" key={value as string} className={ratio === value ? "active" : ""} onClick={() => setRatio(value as string)}><Icon size={17} /><b>{value as string}</b><small>{name as string}</small></button>)}</div></div>
            <div className="editor-section"><label><MoveHorizontal size={13} /> Manual reframe: {focusX}%</label><input className="focus-slider" type="range" min="0" max="100" value={focusX} onChange={event => setFocusX(Number(event.target.value))} /><div className="focus-labels"><span>Left</span><span>Centre</span><span>Right</span></div></div>
            <div className="editor-section"><label>Caption position</label><div className="segmented three"><button className={captionPosition === "bottom" ? "active" : ""} onClick={() => setCaptionPosition("bottom")}>Lower</button><button className={captionPosition === "above" ? "active" : ""} onClick={() => setCaptionPosition("above")}>Above</button><button className={captionPosition === "center" ? "active" : ""} onClick={() => setCaptionPosition("center")}>Centre</button></div></div>
            <div className="toggle-row"><div><b>Preserve source captions</b><span>{sourceHasCaptions ? `Detected near ${Math.round((sourceCaptionBand ?? .82) * 100)}% height` : "Use when the source already has subtitles"}</span></div><button className={preserveSourceCaptions ? "on" : ""} aria-pressed={preserveSourceCaptions} onClick={() => setPreserveSourceCaptions(value => !value)}><i /></button></div>
          </>}

          {activeTab === "transcript" && <>
            <div className="editor-section"><label>Editable transcript</label><textarea className="transcript-editor" value={transcript} onChange={event => setTranscript(event.target.value)} /><p className="field-note">Changes appear in the live caption preview and are saved with this clip.</p></div>
            <div className="editor-section"><label>Clip title</label><input value={title} onChange={event => setTitle(event.target.value)} /></div>
            <div className="editor-section"><label>Precise trim</label><div className="trim-inputs"><div><span>Start</span><input type="number" step=".1" min="0" max={end - 1} value={start} onChange={event => { const value = Number(event.target.value); setStart(value); if (videoRef.current) videoRef.current.currentTime = value; }} /></div><div><span>End</span><input type="number" step=".1" min={start + 1} max={project.duration} value={end} onChange={event => setEnd(Number(event.target.value))} /></div></div></div>
          </>}

          {activeTab === "export" && <>
            <div className="editor-section"><label>Export quality</label><select value={resolution} onChange={event => setResolution(event.target.value)}><option value="720p">720p · Fast and efficient</option><option value="1080p">1080p · Any paid plan</option></select></div>
            <div className="export-summary"><span>Format <b>{ratio}</b></span><span>Duration <b>{Math.round(end - start)}s</b></span><span>Captions <b>{styles.find(style => style[0] === captionStyle)?.[1]}</b></span><span>Frame <b>{preserveSourceCaptions ? "Full" : `${focusX}%`}</b></span><span>India <b>{indiaQualityMode ? captionLanguageStyle.replace("_", " ") : "Off"}</b></span><span>Brand <b>{selectedBrandKit?.name || "None"}</b></span></div>
            <div className="toggle-row"><div><b>ClipKaro watermark</b><span>{freePlan ? "Required on Free" : "Optional on your paid plan"}</span></div><button className={watermark ? "on" : ""} aria-pressed={watermark} disabled={freePlan} onClick={() => { if (!freePlan) setWatermark(value => !value); }}><i /></button></div>
            <button className="primary-btn render-panel-button" onClick={render} disabled={renderBusy}>{renderBusy ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />} {startingRender ? "Starting securely…" : renderBusy ? "Rendering Short…" : "Render verified Short"}</button>
          </>}
        </aside>
      </div>

      {error && <div className={`floating-error ${error === "Saved" ? "success" : ""}`}>{error}</div>}
      {job && <div className="export-drawer"><div className="export-icon">{job.status === "completed" ? <Check /> : job.status === "failed" ? <span>!</span> : <Loader2 className="spin" />}</div><div><b>{job.status === "completed" ? "Your Short is ready" : job.status === "failed" ? job.error || job.message : job.message}</b><span>{job.status === "completed" ? "The downloaded MP4 matches this crop and caption style" : `${job.progress}% complete`}</span><div className="progress"><i style={{ width: `${job.progress}%` }} /></div></div>{job.status === "completed" && <button className="primary-btn" type="button" onClick={downloadReadyExport} disabled={downloading}>{downloading ? <Loader2 className="spin" size={15} /> : <Download size={15} />}{downloading ? "Preparing…" : "Download MP4"}</button>}</div>}
    </AppShell>
  );
}
