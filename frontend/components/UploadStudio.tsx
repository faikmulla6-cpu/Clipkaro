"use client";

import { AlertCircle, Check, ChevronRight, CloudUpload, FileVideo, Loader2, LockKeyhole, Sparkles, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountSettings, API_URL, api } from "@/lib/api";

const UPLOAD_URL = `${API_URL}/projects/upload`;
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

const stages = [
  ["validating", "Check video"],
  ["audio", "Prepare audio"],
  ["transcribing", "Transcribe"],
  ["ranking", "Find moments"],
  ["finishing", "Build previews"],
];

export function UploadStudio() {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [language, setLanguage] = useState<AccountSettings["default_language"]>("auto");
  const [category, setCategory] = useState<AccountSettings["creator_category"]>("auto");
  const input = useRef<HTMLInputElement>(null);
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
  }, []);

  function choose(next?: File) {
    if (!next) return;
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

  function watch(jobId: string, projectId: string) {
    const source = new EventSource(`${API_URL}/jobs/${jobId}/events`, { withCredentials: true });
    source.addEventListener("progress", (event) => setJob(JSON.parse((event as MessageEvent).data)));
    source.addEventListener("done", (event) => {
      const data = JSON.parse((event as MessageEvent).data);
      setJob(data);
      source.close();
      if (data.status === "completed") setTimeout(() => router.push(`/projects/${projectId}`), 700);
    });
    source.onerror = () => {
      source.close();
      setError("Live connection paused. Your video is still processing—open Projects to check it.");
      setBusy(false);
    };
  }

  function upload() {
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    form.append("title", (document.getElementById("project-title") as HTMLInputElement)?.value || file.name.replace(/\.[^.]+$/, ""));
    form.append("language", language);
    form.append("category", category);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", UPLOAD_URL);
    xhr.withCredentials = true;
    const csrf = document.cookie.split("; ").find((item) => item.startsWith("csrf_token="))?.split("=")[1];
    if (csrf) xhr.setRequestHeader("X-CSRF-Token", decodeURIComponent(csrf));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) setUploadProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const project = JSON.parse(xhr.responseText);
        setJob({ status: "queued", progress: 0, stage: "queued", message: "Your video is in the processing queue", project_id: project.id });
        watch(project.job_id, project.id);
      } else {
        try { setError(JSON.parse(xhr.responseText).detail); }
        catch { setError("Upload failed. Please try again."); }
        setBusy(false);
      }
    };
    xhr.onerror = () => {
      setError("Could not reach the processing server.");
      setBusy(false);
    };
    xhr.send(form);
  }

  const activeIndex = job ? stages.findIndex((stage) => stage[0] === job.stage) : -1;
  const waitingForAsr = Boolean(job?.asr_state === "queued" && job.queue_position && job.queue_position > 0);

  if (job) {
    const diagnostic = job.error || job.message || "Processing failed without a diagnostic. Restart the backend and try again.";
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
    <div className="upload-studio">
      {preflight && !preflight.ready && <div className="preflight-warning"><AlertCircle size={20}/><div><b>Processing engine is not ready</b>{preflight.problems.map((problem) => <p key={problem}>{problem}</p>)}<small>{preflight.recommendation}</small></div></div>}
      <div className={`drop-zone ${file ? "has-file" : ""}`} onClick={() => !file && input.current?.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0]); }}>
        <input ref={input} type="file" accept=".mp4,.mov,.webm,.mkv,video/mp4,video/quicktime,video/webm,video/x-matroska,video/matroska,application/x-matroska,application/matroska" hidden onChange={(event) => choose(event.target.files?.[0])}/>
        {file ? <div className="selected-file"><div className="file-icon"><FileVideo size={27}/></div><div className="file-copy"><b>{file.name}</b><span>{(file.size / 1024 / 1024).toFixed(1)} MB · Ready for AI analysis</span></div><span className="ready-pill"><Check size={14}/> Ready</span><button className="icon-btn" onClick={(event) => { event.stopPropagation(); setFile(null); }}><X size={18}/></button></div> : <><div className="upload-orb"><CloudUpload size={30}/></div><h2>Drop your long video here</h2><p>We&apos;ll find the strongest hooks, lessons and stories.</p><button className="secondary-btn"><Upload size={16}/> Choose video</button><span className="file-help">MP4, MOV, WebM or MKV · Up to 500 MB · Private by default</span></>}
      </div>

      {file && <div className="upload-options">
        <div className="field"><label>Project title</label><input id="project-title" defaultValue={file.name.replace(/\.[^.]+$/, "")}/></div>
        <div className="field"><label>Spoken language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value as AccountSettings["default_language"])}><option value="hi">Hindi · Recommended</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option><option value="auto">Auto detect · India-first</option></select></div>
        <div className="field"><label>Content type</label><select id="category" value={category} onChange={(event) => setCategory(event.target.value as AccountSettings["creator_category"])}><option value="auto">Let AI decide</option><option value="education">Education</option><option value="podcast">Podcast</option><option value="business">Business</option><option value="motivation">Motivation</option><option value="spiritual">Spiritual</option><option value="local-business">Local business</option></select></div>
      </div>}

      {busy && uploadProgress < 100 && <div className="processing-box"><div><Loader2 className="spin" size={20}/><div><b>Uploading securely</b><span>{uploadProgress}% transferred</span></div><strong>{uploadProgress}%</strong></div><div className="progress large"><span style={{ width: `${uploadProgress}%` }}/></div></div>}
      {error && <div className="error-banner"><AlertCircle size={18}/><span>{error}</span></div>}
      <div className="studio-actions"><span><Check size={15}/> I own or have permission to use this video.</span><button className="primary-btn" disabled={!file || busy || preflight?.ready === false} onClick={upload}><Sparkles size={17}/> {preflight?.ready === false ? "Fix processing engine first" : "Find my best moments"} <ChevronRight size={17}/></button></div>
      <div className="how-grid">{[["01", "Upload privately", "Your original stays yours."], ["02", "Watch AI work", "Live stages, no mystery spinner."], ["03", "Choose & polish", "Edit only the moments you want."]].map((item) => <div key={item[0]}><span>{item[0]}</span><div><b>{item[1]}</b><p>{item[2]}</p></div></div>)}</div>
    </div>
  );
}
