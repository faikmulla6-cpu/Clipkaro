"use client";

import { AppShell } from "@/components/AppShell";
import { ErrorState } from "@/components/ErrorState";
import { API_URL, api, deleteJSON, patchJSON, postJSON } from "@/lib/api";
import { newBehaviorSession, trackClipBehavior } from "@/lib/behavior";
import { AlertCircle, ArrowLeft, ChevronRight, Clock3, Copy, LayoutGrid, List, PackageCheck, Pause, Play, RefreshCw, RotateCcw, Save, Sparkles, Target, Upload, WandSparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

type Clip = {
  id: string; title: string; hook: string; reason: string;
  start_time: number; end_time: number; score: number;
  score_breakdown: Record<string, number>; platform: string; transcript_text: string;
};
type TranscriptState = { current: boolean; export_safe: boolean; reason: string };
type TranscriptReviewSummary = { flagged: number; corrected: number; reviewed: number; remaining: number };
type TranscriptReviewSegment = {
  index: number; start: number; end: number; original_text: string; text: string;
  state: "needs_review" | "reviewed" | "corrected" | "clean"; flagged: boolean; reasons: string[];
};
type TranscriptReviewResponse = { language: string; summary: TranscriptReviewSummary; segments: TranscriptReviewSegment[] };
type Project = { id: string; title: string; status: string; stage?: string; progress?: number; duration: number; language: string; detected_language?: string; clips: Clip[]; transcript_state?: TranscriptState; transcript_review?: TranscriptReviewSummary; source_available?: boolean; upgrade_blocked?: string; error?: string | null; updated_at?: string | null };
type ReprocessResponse = { job_id: string };
type ClipPack = {
  clip_id: string; clip_title: string;
  youtube_shorts: { titles: string[]; description: string; hashtags: string[] };
  instagram_reels: { caption: string; hashtags: string[] };
  x: { post: string };
  linkedin: { post: string; recommended: boolean };
  thumbnail_text: string[];
};
type ContentPack = {
  content_summary: string; content_angles: string[];
  best_clips_order: { clip_id: string; rank: number; reason: string }[];
  clips: ClipPack[];
};
type ContentPackResponse = { status: string; content_pack: ContentPack | null; updated_at?: string };
const languageNames: Record<string,string> = { en: "English", hi: "Hindi", mr: "Marathi", ur: "Urdu", auto: "Auto", hinglish: "Hinglish" };
const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;

function minutesSince(value?: string | null) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 60000));
}

function processingMessage(project: Project, staleMinutes: number | null) {
  if (staleMinutes !== null && staleMinutes >= 10) {
    return "This is taking longer than normal. Your upload is still saved; refresh once, and if it has not moved, use Retry after ClipKaro marks it failed or upload the source again.";
  }
  if (project.stage === "queued" || project.stage === "recovery") {
    return "Your video is waiting for the media worker. You can leave this page and come back from Projects.";
  }
  if (project.stage === "transcribing") {
    return "ClipKaro is creating timestamped captions. Long videos and mixed-language audio can take a few minutes.";
  }
  return "ClipKaro is analysing the source and preparing verified clips.";
}

function MomentPreview({ projectId, clip, rank, behaviorSessionId, sourceAvailable }: { projectId: string; clip: Clip; rank: number; behaviorSessionId: string; sourceAvailable: boolean }) {
  const ref = useRef<HTMLVideoElement>(null);
  const previewLogged = useRef(false);
  const [playing, setPlaying] = useState(false);
  function loaded() { if (ref.current) ref.current.currentTime = clip.start_time; }
  function timeUpdate() {
    if (ref.current && ref.current.currentTime >= clip.end_time) {
      ref.current.pause(); ref.current.currentTime = clip.start_time; setPlaying(false);
    }
  }
  async function toggle() {
    if (!ref.current) return;
    if (ref.current.paused) {
      if (ref.current.currentTime < clip.start_time || ref.current.currentTime >= clip.end_time) ref.current.currentTime = clip.start_time;
      await ref.current.play();
      if (!previewLogged.current) {
        previewLogged.current = true;
        trackClipBehavior(clip.id, "preview_started", {
          sessionId: behaviorSessionId,
          eventId: `${behaviorSessionId}:preview:${clip.id}`,
          surface: "project",
        });
      }
      setPlaying(true);
    }
    else { ref.current.pause(); setPlaying(false); }
  }
  return <div className="moment-preview"><div className="preview-scene real-preview">{sourceAvailable ? <><video ref={ref} src={`${API_URL}/projects/${projectId}/media`} muted playsInline preload="metadata" onLoadedMetadata={loaded} onTimeUpdate={timeUpdate} /><button onClick={toggle}>{playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}</button></> : <div className="expired-media-note"><b>Source expired</b><span>Moment metadata is kept, but the private source file has left the retention window.</span></div>}<span className="moment-rank">#{rank} pick</span><span className="time-pill">{formatTime(clip.start_time)} – {formatTime(clip.end_time)}</span></div><div className="score-ring" style={{ "--score": `${clip.score * 3.6}deg` } as React.CSSProperties}><b>{clip.score}</b><small>score</small></div></div>;
}

function MomentCard({ projectId, clip, rank, behaviorSessionId, sourceAvailable }: { projectId: string; clip: Clip; rank: number; behaviorSessionId: string; sourceAvailable: boolean }) {
  const articleRef = useRef<HTMLElement | null>(null);
  const impressionLogged = useRef(false);
  useEffect(() => {
    const node = articleRef.current;
    if (!node || impressionLogged.current) return;
    const record = () => {
      if (impressionLogged.current) return;
      impressionLogged.current = true;
      trackClipBehavior(clip.id, "impression", {
        sessionId: behaviorSessionId,
        eventId: `${behaviorSessionId}:impression:${clip.id}`,
        surface: "project",
      });
    };
    if (!("IntersectionObserver" in window)) {
      record();
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      const entry = entries[0];
      if (entry?.isIntersecting && entry.intersectionRatio >= 0.5) {
        record();
        observer.disconnect();
      }
    }, { threshold: [0.5] });
    observer.observe(node);
    return () => observer.disconnect();
  }, [behaviorSessionId, clip.id]);

  return <article className="moment-card" ref={articleRef}>
    <MomentPreview projectId={projectId} clip={clip} rank={rank} behaviorSessionId={behaviorSessionId} sourceAvailable={sourceAvailable} />
    <div className="moment-body"><div className="platform-pill"><Target size={12} />{clip.platform}</div><h3>{clip.title}</h3><blockquote>“{clip.hook}”</blockquote><div className="why"><WandSparkles size={14} /><span>{clip.reason}</span></div><div className="score-bars">{Object.entries(clip.score_breakdown).slice(0, 5).map(([key, value]) => <div key={key}><span>{key}</span><i><b style={{ width: `${value}%` }} /></i><strong>{value}</strong></div>)}</div>{sourceAvailable ? <Link href={`/editor/${clip.id}?project=${projectId}`} className="primary-btn">Crop, caption and export <ChevronRight size={15} /></Link> : <Link href="/upload" className="secondary-btn">Upload source again <ChevronRight size={15}/></Link>}</div>
  </article>;
}

function CopyButton({ value, onCopied }: { value: string; onCopied: () => void }) {
  return <button className="icon-btn copy-action" type="button" onClick={async () => { await navigator.clipboard.writeText(value); onCopied(); }} aria-label="Copy"><Copy size={14}/></button>;
}

function TranscriptReviewPanel({ projectId, sourceAvailable, summary, onChanged }: { projectId: string; sourceAvailable: boolean; summary?: TranscriptReviewSummary; onChanged: () => Promise<void> }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<TranscriptReviewResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [open, setOpen] = useState(Boolean(summary?.remaining));
  const [notice, setNotice] = useState("");
  const loadReview = useCallback(async () => {
    const result = await api<TranscriptReviewResponse>(`/projects/${projectId}/transcript-review`);
    setState(result);
    setDrafts(Object.fromEntries(result.segments.map(item => [item.index, item.text])));
    setSelected(current => current ?? result.segments[0]?.index ?? null);
  }, [projectId]);
  useEffect(() => { loadReview().catch(() => undefined); }, [loadReview]);
  const current = state?.segments.find(item => item.index === selected) || state?.segments[0];
  async function jump(segment: TranscriptReviewSegment) {
    setSelected(segment.index);
    if (!videoRef.current || !sourceAvailable) return;
    videoRef.current.currentTime = segment.start;
    await videoRef.current.play().catch(() => undefined);
  }
  async function save(segment: TranscriptReviewSegment) {
    const text = drafts[segment.index] ?? segment.text;
    await patchJSON(`/projects/${projectId}/transcript-review/${segment.index}`, { text });
    setNotice("Correction saved");
    await loadReview();
    await onChanged();
  }
  async function reset(segment: TranscriptReviewSegment) {
    await deleteJSON(`/projects/${projectId}/transcript-review/${segment.index}`);
    setNotice("Reset to original");
    await loadReview();
    await onChanged();
  }
  const counts = state?.summary || summary || { flagged: 0, corrected: 0, reviewed: 0, remaining: 0 };
  const prominent = counts.remaining > 0;
  return <section className={`transcript-review-panel ${prominent ? "needs-review" : ""}`}>
    <div className="transcript-review-head">
      <div><span className="eyebrow"><AlertCircle size={12}/> REVIEW TRANSCRIPT</span><h2>{prominent ? `${counts.remaining} transcript segments may need review` : "No transcript issues detected"}</h2><p>{counts.flagged} flagged · {counts.corrected} corrected · {counts.remaining} remaining</p></div>
      <button className="secondary-btn small" type="button" onClick={() => setOpen(value => !value)}>{open ? "Hide review" : "Open review"}</button>
    </div>
    {notice && <div className="success-banner">{notice}</div>}
    {open && <div className="transcript-review-body">
      <div className="review-video">{sourceAvailable ? <video ref={videoRef} src={`${API_URL}/projects/${projectId}/media`} controls preload="metadata" /> : <div className="expired-media-note"><b>Source expired</b><span>Corrections can still be reviewed from saved transcript text.</span></div>}</div>
      <div className="review-list">{state?.segments.length ? state.segments.map(segment => <button type="button" key={segment.index} className={current?.index === segment.index ? "active" : ""} onClick={() => void jump(segment)}><b>{formatTime(segment.start)} - {formatTime(segment.end)}</b><span>{segment.state === "corrected" ? "Corrected" : segment.reasons.join(", ") || "Reviewed"}</span></button>) : <p>No suspicious segments are currently flagged.</p>}</div>
      {current && <div className="review-editor">
        <div><b>{formatTime(current.start)} - {formatTime(current.end)}</b><small>{current.reasons.join(", ") || (current.state === "corrected" ? "Corrected" : "Review optional")}</small></div>
        <label>Detected<textarea value={current.original_text} readOnly /></label>
        <label>Edit transcript<textarea value={drafts[current.index] ?? current.text} onChange={event => setDrafts(values => ({ ...values, [current.index]: event.target.value }))} /></label>
        <div className="review-actions"><button className="secondary-btn small" type="button" onClick={() => void jump(current)}><Play size={14}/>Jump</button><button className="secondary-btn small" type="button" onClick={() => void reset(current)}><RotateCcw size={14}/>Reset</button><button className="primary-btn small" type="button" onClick={() => void save(current)}><Save size={14}/>Save correction</button></div>
      </div>}
    </div>}
  </section>;
}

function ContentPackPanel({ projectId, clips }: { projectId: string; clips: Clip[] }) {
  const [state, setState] = useState<ContentPackResponse>({ status: "missing", content_pack: null });
  const [selectedClipId, setSelectedClipId] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [noticeKind, setNoticeKind] = useState<"info" | "error">("info");
  const loadPack = useCallback(async () => {
    try {
      const result = await api<ContentPackResponse>(`/projects/${projectId}/content-pack`);
      setState(result);
      setNotice("");
      setSelectedClipId(current => current || result.content_pack?.clips[0]?.clip_id || clips[0]?.id || "");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "";
      if (/not found/i.test(message)) {
        setState({ status: "missing", content_pack: null });
        setNotice("");
      } else {
        setState({ status: "failed", content_pack: null });
        setNoticeKind("error");
        setNotice("Content Pack could not be loaded. Your clips are safe — refresh once or try again in a moment.");
      }
    }
  }, [projectId, clips]);
  useEffect(() => { loadPack(); }, [loadPack]);
  async function generate() {
    setBusy(true); setNotice("");
    try {
      const result = await postJSON<ContentPackResponse>(`/projects/${projectId}/content-pack`, {});
      setState(result);
      setSelectedClipId(result.content_pack?.clips[0]?.clip_id || clips[0]?.id || "");
      setNoticeKind("info");
      setNotice("Content Pack ready — publishing copy is grounded in your current transcript and clips.");
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "";
      setNoticeKind("error");
      setNotice(/not found/i.test(message)
        ? "Content Pack could not start on this deployment. Refresh after the latest ClipKaro backend is live, then try again."
        : message || "Content Pack couldn't be generated. Try again.");
    } finally { setBusy(false); }
  }
  function copied() {
    setNoticeKind("info");
    setNotice("Copied");
    window.setTimeout(() => setNotice(""), 1200);
  }
  const pack = state.content_pack;
  const stale = state.status === "stale";
  const selected = pack?.clips.find(item => item.clip_id === selectedClipId) || pack?.clips[0];
  const selectedText = selected ? [
    ...selected.youtube_shorts.titles,
    selected.youtube_shorts.description,
    selected.youtube_shorts.hashtags.join(" "),
    selected.instagram_reels.caption,
    selected.instagram_reels.hashtags.join(" "),
    selected.x.post,
    selected.linkedin.post,
    ...selected.thumbnail_text,
  ].join("\n\n") : "";
  return <section className="content-pack-panel">
    <div className="content-pack-head">
      <div><span className="eyebrow"><PackageCheck size={12}/> CONTENT PACK</span><h2>Publish copy for these clips</h2><p>Grounded in this transcript, clip hooks and ClipKaro scores.</p></div>
      <div className="content-pack-actions">
        {selected && <button className="secondary-btn small" type="button" onClick={() => navigator.clipboard.writeText(selectedText).then(copied)}><Copy size={14}/>Copy all</button>}
        <button className="primary-btn small" type="button" disabled={busy} onClick={generate}>{busy ? <RefreshCw className="spin" size={14}/> : <Sparkles size={14}/>}{stale ? "Regenerate pack" : pack ? "Refresh pack" : "Generate Content Pack"}</button>
      </div>
    </div>
    {notice && <div className={`content-pack-status ${noticeKind}`}>{notice}</div>}
    {stale && <div className="error-banner"><span>Transcript changed - regenerate Content Pack before publishing this copy.</span></div>}
    {!pack ? <div className="empty-state compact"><h3>No Content Pack yet</h3><p>Generate ready-to-use YouTube Shorts titles and descriptions, Instagram captions and hashtags, X posts, LinkedIn copy when relevant, cover text, content angles and a recommended publishing order from the clips ClipKaro already found.</p></div> : <>
      <div className="content-pack-overview"><div><b>Summary</b><p>{pack.content_summary}</p></div><div><b>Angles</b><p>{pack.content_angles.join(" · ")}</p></div></div>
      <div className="content-pack-layout">
        <div className="pack-clip-list">{pack.best_clips_order.map(item => {
          const clip = clips.find(row => row.id === item.clip_id);
          return <button type="button" key={item.clip_id} className={selected?.clip_id === item.clip_id ? "active" : ""} onClick={() => setSelectedClipId(item.clip_id)}><b>#{item.rank} {clip?.title || "Clip"}</b><span>{item.reason}</span></button>;
        })}</div>
        {selected && <div className="pack-copy-grid">
          <article><h3>YouTube Shorts titles</h3>{selected.youtube_shorts.titles.map(title => <div className="copy-row" key={title}><span>{title}</span><CopyButton value={title} onCopied={copied}/></div>)}</article>
          <article><h3>YouTube description</h3><p>{selected.youtube_shorts.description}</p><CopyButton value={selected.youtube_shorts.description} onCopied={copied}/></article>
          <article><h3>Instagram Reels</h3><p>{selected.instagram_reels.caption}</p><small>{selected.instagram_reels.hashtags.join(" ")}</small><CopyButton value={`${selected.instagram_reels.caption}\n\n${selected.instagram_reels.hashtags.join(" ")}`} onCopied={copied}/></article>
          <article><h3>X / Twitter</h3><p>{selected.x.post}</p><CopyButton value={selected.x.post} onCopied={copied}/></article>
          <article><h3>LinkedIn</h3><p>{selected.linkedin.post}</p><CopyButton value={selected.linkedin.post} onCopied={copied}/></article>
          <article><h3>Cover text</h3>{selected.thumbnail_text.map(item => <div className="copy-row" key={item}><span>{item}</span><CopyButton value={item} onCopied={copied}/></div>)}</article>
        </div>}
      </div>
    </>}
  </section>;
}

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const behaviorSessionRef = useRef("");
  if (!behaviorSessionRef.current) behaviorSessionRef.current = newBehaviorSession();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [filter, setFilter] = useState("Best match");
  const [languageChoice, setLanguageChoice] = useState("hi");
  const [reprocessing, setReprocessing] = useState(false);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const data=await api<Project>(`/projects/${id}`); setProject(data); setLanguageChoice(data.detected_language === "ur" ? "hi" : data.detected_language || data.language || "hi"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "The project could not be loaded."); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!project || !["queued", "processing"].includes(project.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const data = await api<Project>(`/projects/${id}`);
        setProject(data);
        if (!["queued", "processing"].includes(data.status)) window.clearInterval(timer);
      } catch { /* keep the last valid state and retry */ }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [id, project?.status]);

  async function startReprocess(language = languageChoice){
    setReprocessing(true); setError("");
    try{
      await postJSON<ReprocessResponse>(`/projects/${id}/reprocess`,{language});
      const refreshed = await api<Project>(`/projects/${id}`);
      setProject(refreshed);
      const timer=window.setInterval(async()=>{try{const data=await api<Project>(`/projects/${id}`);setProject(data);if(data.status==="ready"||data.status==="failed"){clearInterval(timer);setReprocessing(false);}}catch{/* retry */}},1200);
    }catch(cause){setReprocessing(false);setError(cause instanceof Error?cause.message:"Could not re-analyse this video.")}
  }

  async function reprocessLanguage(){
    await startReprocess(languageChoice);
  }

  if (error) return <AppShell title="Project"><ErrorState message={error} retry={load} /></AppShell>;
  if (loading || !project) return <AppShell title="Opening project"><div className="screen-loader inline"><div className="loader-mark">✦</div><p>Loading moments and source video…</p></div></AppShell>;
  if (project.status === "failed") return <AppShell title={project.title} subtitle="This project needs attention" action={<Link href="/projects" className="secondary-btn small"><ArrowLeft size={14} />All projects</Link>}>
    <div className="empty-state">
      <div className="empty-icon"><AlertCircle size={24}/></div>
      <h3>Processing did not finish</h3>
      <p>{project.error || "ClipKaro could not finish analysing this video. Retry once; if it fails again, upload a shorter or cleaner source."}</p>
      <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
        <button className="primary-btn" type="button" disabled={reprocessing || project.source_available === false} onClick={() => void startReprocess(project.detected_language || project.language || "auto")}>
          {reprocessing ? <RefreshCw className="spin" size={15}/> : <RefreshCw size={15}/>}
          {reprocessing ? "Retrying…" : "Retry processing"}
        </button>
        <Link href="/upload" className="secondary-btn"><Upload size={15}/>Upload again</Link>
      </div>
      {project.source_available === false && <small style={{ color: "var(--muted)" }}>The retained source file has expired, so retry is unavailable for this project.</small>}
    </div>
  </AppShell>;
  if (["queued", "processing"].includes(project.status)) {
    const staleMinutes = minutesSince(project.updated_at);
    const stale = staleMinutes !== null && staleMinutes >= 10;
    return <AppShell title={project.title} subtitle="Processing your source video" action={<Link href="/projects" className="secondary-btn small"><ArrowLeft size={14} />All projects</Link>}>
      <div className="screen-loader inline">
        <div className="loader-mark">✦</div>
        <h2>{project.stage === "upgrading" ? "Rebuilding captions with the latest accuracy model" : stale ? "Still working, but taking longer than usual" : "Analysing audio and video"}</h2>
        <p>{processingMessage(project, staleMinutes)}</p>
        <div className="progress-track"><i style={{width:`${Math.max(3, project.progress || 0)}%`}} /></div>
        <small>{project.progress || 0}% complete{staleMinutes !== null ? ` · last update ${staleMinutes} min ago` : ""}</small>
        {stale && <div className="processing-actions">
          <button className="secondary-btn small" type="button" onClick={() => void load()}><RefreshCw size={14}/>Refresh status</button>
          <Link href="/contact" className="secondary-btn small"><Clock3 size={14}/>Contact support</Link>
        </div>}
      </div>
    </AppShell>;
  }
  const clips = project.clips.filter(clip => filter === "Best match" || filter === "Under 30 sec" && clip.end_time - clip.start_time <= 30 || filter === "High hook" && (clip.score_breakdown.hook || 0) >= 75 || filter === "High emotion" && (clip.score_breakdown.emotion || 0) >= 65);

  return <AppShell title={project.title} subtitle={`${project.clips.length} AI-ranked moments · ${formatTime(project.duration || 0)} source · ${languageNames[project.detected_language || project.language] || "Language pending"}`} action={<Link href="/projects" className="secondary-btn small"><ArrowLeft size={14} />All projects</Link>}>
    <div className="project-summary"><div><span className="eyebrow"><Sparkles size={12} /> ANALYSIS COMPLETE</span><h2>Your strongest moments, ranked</h2><p>Play the actual source moment, inspect every score, then open the real cropped preview in Creator Studio.</p></div><div className="summary-score"><small>Top potential</small><b>{project.clips[0]?.score || 0}</b><span>/100</span></div></div>
    {!project.source_available && <div className="error-banner"><span>This source video has expired from private media storage. Your project history is preserved, but preview, re-analysis and new exports require uploading the source again.</span></div>}
    {project.upgrade_blocked === "active_export" && <div className="error-banner"><span>This project needs a pipeline upgrade, but an export is still rendering. ClipKaro is preserving that export first; refresh after it finishes to upgrade the project safely.</span></div>}
    <div className="language-correction"><div><b>Spoken language</b><span>Detected: {languageNames[project.detected_language || project.language] || "Unknown"}. Wrong script or words? Re-analyse without uploading again. A completed source is not charged Karo Minutes twice; up to 3 correction runs are allowed per video in 24 hours.</span></div><select value={languageChoice} onChange={event=>setLanguageChoice(event.target.value)} disabled={reprocessing || project.source_available === false || project.upgrade_blocked === "active_export"}><option value="hi">Hindi</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option><option value="auto">Auto detect</option></select><button className="secondary-btn small" onClick={reprocessLanguage} disabled={reprocessing || project.source_available === false || project.upgrade_blocked === "active_export"}>{reprocessing?"Re-analysing audio…":"Re-analyse language"}</button></div>
    <TranscriptReviewPanel projectId={project.id} sourceAvailable={project.source_available !== false} summary={project.transcript_review} onChanged={load} />
    <ContentPackPanel projectId={project.id} clips={project.clips} />
    <div className="moments-toolbar"><div className="filter-tabs">{["Best match", "Under 30 sec", "High hook", "High emotion"].map(item => <button key={item} onClick={() => setFilter(item)} className={filter === item ? "active" : ""}>{item}</button>)}</div><div className="view-toggle"><button className={view === "grid" ? "active" : ""} onClick={() => setView("grid")}><LayoutGrid size={15} /></button><button className={view === "list" ? "active" : ""} onClick={() => setView("list")}><List size={15} /></button></div></div>
    {!clips.length ? <div className="empty-state compact"><h3>No clips match this filter</h3><button className="secondary-btn" onClick={() => setFilter("Best match")}>Show all moments</button></div> : <div className={`moment-grid ${view}`}>{clips.map((clip) => <MomentCard key={clip.id} projectId={project.id} clip={clip} rank={project.clips.findIndex(item => item.id === clip.id) + 1} behaviorSessionId={behaviorSessionRef.current} sourceAvailable={project.source_available !== false} />)}</div>}
  </AppShell>;
}
