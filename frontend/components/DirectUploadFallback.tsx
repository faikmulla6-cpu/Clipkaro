"use client";

import { AlertCircle, Check, ChevronRight, CloudUpload, FileVideo, Loader2, LockKeyhole, Sparkles, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountSettings, API_URL, api } from "@/lib/api";

const UPLOAD_URL = `${API_URL}/projects/upload`;
const DIRECT_GCS_UPLOAD = process.env.NEXT_PUBLIC_UPLOAD_MODE === "direct_gcs";
const SUPPORTED_VIDEO_EXTENSIONS = new Set(["mp4", "mov", "webm", "mkv"]);
const GENERIC_VIDEO_MIME_TYPES = new Set(["", "application/octet-stream", "application/x-matroska", "application/matroska"]);

type Job = {
  status: string;
  progress: number;
  stage: string;
  message: string;
  error?: string;
  project_id?: string;
  asr_state?: "queued" | "running";
  queue_position?: number;
  queue_size?: number;
  asr_active?: number;
  asr_limit?: number;
};

type Preflight = {
  ready: boolean;
  checks: { ffmpeg: boolean; whisper: boolean; storage: boolean; model: string };
  problems: string[];
  recommendation: string;
};

type UploadSession = { upload_session_id: string; method: "PUT"; upload_url: string; headers: Record<string, string>; expires_at: string };
type UploadCompletion = { project_id: string; job_id: string; status: string };

const stages = [
  ["validating", "Check video"],
  ["audio", "Prepare audio"],
  ["transcribing", "Transcribe"],
  ["ranking", "Find moments"],
  ["finishing", "Build previews"],
];

export function DirectUploadFallback({ embedded = false, disabled = false, onActivityChange }: { embedded?: boolean; disabled?: boolean; onActivityChange?: (active: boolean) => void } = {}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [language, setLanguage] = useState<AccountSettings["default_language"]>("auto");
  const [category, setCategory] = useState<AccountSettings["creator_category"]>("auto");
  const input = useRef<HTMLInputElement>(null);
  const activeUpload = useRef<XMLHttpRequest | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const activeJobRef = useRef<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    api<Preflight>("/system/preflight").then(setPreflight).catch(() => setPreflight(null));
    api<AccountSettings>("/settings")
      .then((saved) => {
        setLanguage(saved.default_language);
        setCategory(saved.creator_category);
      })
      .catch(() => {
        setLanguage("auto");
        setCategory("auto");
      });
    return () => {
      eventSourceRef.current?.close();
      if (pollTimerRef.current !== null) window.clearInterval(pollTimerRef.current);
    };
  }, []);

  function choose(next?: File) {
    if (!next || disabled) return;
    const extension = next.name.split(".").pop()?.toLowerCase() || "";
    const knownExtension = SUPPORTED_VIDEO_EXTENSIONS.has(extension);
    const browserSaysVideo = next.type.startsWith("video/");
    const browserHasGenericMime = GENERIC_VIDEO_MIME_TYPES.has(next.type.toLowerCase());
    if (!knownExtension || (!browserSaysVideo && !browserHasGenericMime)) {
      setError("Choose an MP4, MOV, WebM or MKV video.");
      return;
    }
    if (next.size > 500 * 1024 * 1024) {
      setError("This file is above the 500 MB upload limit.");
      return;
    }
    setFile(next);
    setError("");
    setJob(null);
  }

  function stopWatch() {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }

  function watch(jobId: string, projectId: string) {
    stopWatch();
    activeJobRef.current = jobId;

    const apply = (data: Job) => {
      if (activeJobRef.current !== jobId) return;
      setJob(data);
      if (!["completed", "failed"].includes(data.status)) return;
      activeJobRef.current = null;
      stopWatch();
      setBusy(false);
      onActivityChange?.(false);
      if (data.status === "completed") setTimeout(() => router.push(`/projects/${projectId}`), 500);
    };

    pollTimerRef.current = window.setInterval(async () => {
      try { apply(await api<Job>(`/jobs/${jobId}`)); }
      catch { /* keep retrying while the durable job exists */ }
    }, 4000);

    const source = new EventSource(`${API_URL}/jobs/${jobId}/events`, { withCredentials: true });
    eventSourceRef.current = source;
    source.addEventListener("progress", (event) => apply(JSON.parse((event as MessageEvent).data) as Job));
    source.addEventListener("done", (event) => apply(JSON.parse((event as MessageEvent).data) as Job));
    source.onerror = () => {
      source.close();
      if (eventSourceRef.current === source) eventSourceRef.current = null;
    };
  }

  function send(xhr: XMLHttpRequest, body: XMLHttpRequestBodyInit): Promise<XMLHttpRequest> {
    activeUpload.current = xhr;
    return new Promise<XMLHttpRequest>((resolve, reject) => {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) setUploadProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve(xhr) : reject(new Error(xhr.responseText || "Upload failed."));
      xhr.onerror = () => reject(new Error("Could not reach private media storage."));
      xhr.onabort = () => reject(new Error("Upload cancelled."));
      xhr.send(body);
    }).finally(() => { activeUpload.current = null; });
  }

  async function upload() {
    if (!file || disabled) return;
    setBusy(true);
    onActivityChange?.(true);
    setError("");
    setUploadProgress(0);
    const title = (document.getElementById("project-title") as HTMLInputElement)?.value || file.name.replace(/\.[^.]+$/, "");
    try {
      if (DIRECT_GCS_UPLOAD) {
        const contentType = file.type || "application/octet-stream";
        const session = await api<UploadSession>("/uploads/init", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, content_type: contentType, size: file.size, title, language, category }),
        });
        const xhr = new XMLHttpRequest();
        xhr.open(session.method, session.upload_url);
        Object.entries(session.headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
        await send(xhr, file);
        const completed = await api<UploadCompletion>(`/uploads/${session.upload_session_id}/complete`, { method: "POST" });
        setJob({ status: "queued", progress: 0, stage: "queued", message: "Your video is in the processing queue", project_id: completed.project_id });
        watch(completed.job_id, completed.project_id);
      } else {
        const form = new FormData();
        form.append("file", file); form.append("title", title); form.append("language", language); form.append("category", category);
        const xhr = new XMLHttpRequest();
        xhr.open("POST", UPLOAD_URL); xhr.withCredentials = true;
        const csrf = document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1];
        if (csrf) xhr.setRequestHeader("X-CSRF-Token", decodeURIComponent(csrf));
        const response = await send(xhr, form);
        const project = JSON.parse(response.responseText);
        setJob({ status: "queued", progress: 0, stage: "queued", message: "Your video is in the processing queue", project_id: project.id });
        watch(project.job_id, project.id);
      }
    } catch (cause) {
      let message = cause instanceof Error ? cause.message : "Upload failed. Please try again.";
      try { message = JSON.parse(message).detail || message; } catch { /* plain network diagnostic */ }
      setError(message);
      setBusy(false);
      onActivityChange?.(false);
    }
  }

  const activeIndex = job ? stages.findIndex((stage) => stage[0] === job.stage) : -1;
  const waitingForAsr = Boolean(job?.asr_state === "queued" && job.queue_position && job.queue_position > 0);

  if (job) {
    const diagnostic = job.message || job.error || "Processing failed without a diagnostic. Please try again.";
    return (
      <div className="processing-experience">
        <div className="processing-hero">
          <div className="ai-orbit"><span>✦</span><i/><i/><i/></div>
          <span className="eyebrow">LIVE AI PIPELINE</span>
          <h2>{job.status === "failed" ? "This video needs attention" : waitingForAsr ? "Your video is safely queued for transcription" : "Finding the moments people will remember"}</h2>
          <p>{diagnostic}</p>
          <div className="processing-percent">{job.progress}<small>%</small></div>
          <div className="progress processing-progress"><span style={{ width: `${job.progress}%` }}/></div>
        </div>
        <div className="stage-track">
          {stages.map((stage, index) => <div className={`${index < activeIndex ? "done" : index === activeIndex ? "active" : ""}`} key={stage[0]}><span>{index < activeIndex ? <Check size={14}/> : index + 1}</span><b>{stage[1]}</b></div>)}
        </div>
        {waitingForAsr && <div className="processing-note"><Loader2 className="spin" size={15}/> Transcription queue position <b>#{job.queue_position}</b> · {job.asr_active || 0}/{job.asr_limit || 1} ASR slot active · your upload stays queued instead of overloading the server.</div>}
        {job.status === "failed" && <div className="error-banner diagnostic"><AlertCircle size={18}/><span>{diagnostic}</span><button onClick={() => { setJob(null); setBusy(false); }}>Try another video</button></div>}
        <div className="processing-note"><LockKeyhole size={15}/> Your upload is private and automatically expires.</div>
      </div>
    );
  }

  return (
    <div className={`upload-studio ${embedded ? "upload-studio--embedded" : ""}`}>
      {preflight && !preflight.ready && !embedded && <div className="preflight-warning"><AlertCircle size={20}/><div><b>Processing engine is not ready</b>{preflight.problems.map((problem) => <p key={problem}>{problem}</p>)}<small>{preflight.recommendation}</small></div></div>}
      <div className={`drop-zone ${file ? "has-file" : ""} ${disabled ? "is-disabled" : ""}`} onClick={() => !disabled && !file && input.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0]); }}>
        <input ref={input} type="file" disabled={disabled} accept=".mp4,.mov,.webm,.mkv,video/mp4,video/quicktime,video/webm,video/x-matroska,video/matroska,application/x-matroska,application/matroska" hidden onChange={(event) => choose(event.target.files?.[0])}/>
        {file ? <div className="selected-file"><div className="file-icon"><FileVideo size={27}/></div><div className="file-copy"><b>{file.name}</b><span>{(file.size / 1024 / 1024).toFixed(1)} MB · Ready for AI analysis</span></div><span className="ready-pill"><Check size={14}/> Ready</span><button className="icon-btn" onClick={(event) => { event.stopPropagation(); setFile(null); }}><X size={18}/></button></div> : <><div className="upload-orb"><CloudUpload size={30}/></div><h2>Drop your long video here</h2><p>We&apos;ll find the strongest hooks, lessons and stories.</p><button className="secondary-btn"><Upload size={16}/> Choose video</button><span className="file-help">MP4, MOV, WebM or MKV · Up to 500 MB · Private by default</span></>}
      </div>

      {file && <div className="upload-options">
        <div className="field"><label>Project title</label><input id="project-title" defaultValue={file.name.replace(/\.[^.]+$/, "")}/></div>
        <div className="field"><label>Spoken language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value as AccountSettings["default_language"])}><option value="hi">Hindi · Recommended</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option><option value="auto">Auto detect · India-first</option></select></div>
        <div className="field"><label>Content type</label><select id="category" value={category} onChange={(event) => setCategory(event.target.value as AccountSettings["creator_category"])}><option value="auto">Let AI decide</option><option value="education">Education</option><option value="podcast">Podcast</option><option value="business">Business</option><option value="motivation">Motivation</option><option value="spiritual">Spiritual</option><option value="local-business">Local business</option></select></div>
      </div>}

      {busy && uploadProgress < 100 && <div className="processing-box"><div><Loader2 className="spin" size={20}/><div><b>Uploading securely</b><span>{uploadProgress}% transferred</span></div><strong>{uploadProgress}%</strong><button type="button" className="secondary-btn" onClick={() => activeUpload.current?.abort()}>Cancel</button></div><div className="progress large"><span style={{ width: `${uploadProgress}%` }}/></div></div>}
      {error && <div className="error-banner"><AlertCircle size={18}/><span>{error}</span></div>}
      <div className="studio-actions"><span><Check size={15}/> I own or have permission to use this video.</span><button className="primary-btn" disabled={!file || busy || disabled || preflight?.ready === false} onClick={upload}><Sparkles size={17}/> {preflight?.ready === false ? "Fix processing engine first" : "Find my best moments"} <ChevronRight size={17}/></button></div>
      {!embedded && <div className="how-grid">{[["01", "Upload privately", "Your original stays yours."], ["02", "Watch AI work", "Live stages, no mystery spinner."], ["03", "Choose & polish", "Edit only the moments you want."]].map((item) => <div key={item[0]}><span>{item[0]}</span><div><b>{item[1]}</b><p>{item[2]}</p></div></div>)}</div>}
    </div>
  );
}
