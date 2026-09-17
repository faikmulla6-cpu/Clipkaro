"use client";

import {
  AlertCircle,
  Check,
  ChevronRight,
  Clipboard,
  Clock3,
  Link2,
  Loader2,
  LockKeyhole,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  WandSparkles,
  Youtube,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountSettings, API_URL, Usage, api } from "@/lib/api";

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

type YouTubeImport = {
  project_id: string;
  job_id: string;
  status: string;
  youtube_video_id: string;
};

const stages = [
  ["importing", "Import video"],
  ["validating", "Check quality"],
  ["audio", "Prepare audio"],
  ["transcribing", "Transcribe"],
  ["ranking", "Find moments"],
  ["finishing", "Build previews"],
];

function youtubeVideoId(value: string): string {
  try {
    const url = new URL(value.trim());
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    const allowed = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);
    if (!allowed.has(host) || !["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port) return "";
    const parts = url.pathname.split("/").filter(Boolean);
    let id = "";
    if (host === "youtu.be") id = parts[0] || "";
    else if (url.pathname.replace(/\/$/, "") === "/watch") id = url.searchParams.get("v") || "";
    else if (parts.length >= 2 && ["shorts", "embed", "live"].includes(parts[0].toLowerCase())) id = parts[1];
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : "";
  } catch {
    return "";
  }
}

export function UploadStudio() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [title, setTitle] = useState("");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [language, setLanguage] = useState<AccountSettings["default_language"]>("auto");
  const [category, setCategory] = useState<AccountSettings["creator_category"]>("auto");
  const router = useRouter();
  const videoId = useMemo(() => youtubeVideoId(youtubeUrl), [youtubeUrl]);

  useEffect(() => {
    api<Preflight>("/system/preflight").then(setPreflight).catch(() => setPreflight(null));
    api<Usage>("/usage").then(setUsage).catch(() => setUsage(null));
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

  function watch(jobId: string, projectId: string) {
    const source = new EventSource(`${API_URL}/jobs/${jobId}/events`, { withCredentials: true });
    source.addEventListener("progress", (event) => setJob(JSON.parse((event as MessageEvent).data)));
    source.addEventListener("done", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as Job;
      setJob(data);
      source.close();
      setBusy(false);
      if (data.status === "completed") setTimeout(() => router.push(`/projects/${projectId}`), 700);
    });
    source.onerror = () => {
      source.close();
      setError("Live connection paused. Your video is still processing — open Projects to check it.");
      setBusy(false);
    };
  }

  async function pasteFromClipboard() {
    setError("");
    try {
      const text = await navigator.clipboard.readText();
      setYoutubeUrl(text.trim());
    } catch {
      setError("Clipboard access was blocked. Paste the YouTube link into the field.");
    }
  }

  async function startImport() {
    if (!videoId || !rightsConfirmed || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<YouTubeImport>("/imports/youtube", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: youtubeUrl.trim(),
          title: title.trim(),
          language,
          category,
          rights_confirmed: rightsConfirmed,
        }),
      });
      setJob({
        status: "queued",
        progress: 0,
        stage: "queued",
        message: "Your YouTube video is in ClipKaro's secure processing queue",
        project_id: result.project_id,
      });
      watch(result.job_id, result.project_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ClipKaro could not start this import. Please try again.");
      setBusy(false);
    }
  }

  const activeIndex = job ? stages.findIndex((stage) => stage[0] === job.stage) : -1;
  const waitingForAsr = Boolean(job?.asr_state === "queued" && job.queue_position && job.queue_position > 0);

  if (job) {
    const diagnostic = job.message || job.error || "Processing this video now.";
    return (
      <div className="mx-auto w-full max-w-5xl overflow-hidden rounded-[32px] border border-white/10 bg-[#07110d] text-white shadow-[0_28px_90px_rgba(3,18,12,0.28)]">
        <div className="relative overflow-hidden px-5 py-10 sm:px-10 sm:py-14">
          <div className="pointer-events-none absolute -left-24 -top-28 h-72 w-72 rounded-full bg-[#dfff57]/10 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-32 right-0 h-80 w-80 rounded-full bg-emerald-400/10 blur-3xl" />
          <div className="relative mx-auto max-w-3xl text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-[#dfff57]/25 bg-[#dfff57]/10 shadow-[inset_0_1px_rgba(255,255,255,.08)]">
              {job.status === "failed" ? <AlertCircle size={29} className="text-rose-300" /> : <Loader2 size={29} className="animate-spin text-[#dfff57]" />}
            </div>
            <span className="text-[11px] font-extrabold tracking-[0.22em] text-[#dfff57]">CLIPKARO AI PIPELINE</span>
            <h2 className="mx-auto mt-3 max-w-2xl text-3xl font-extrabold tracking-[-0.04em] sm:text-4xl">
              {job.status === "failed" ? "This video needs attention" : waitingForAsr ? "Safely waiting for transcription" : "Turning your video into strong Shorts"}
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-white/65 sm:text-base">{diagnostic}</p>
            <div className="mt-8 flex items-end justify-center gap-1 text-5xl font-black tracking-[-0.05em]">
              {job.progress}<span className="pb-1 text-xl text-[#dfff57]">%</span>
            </div>
            <div className="mx-auto mt-4 h-2 max-w-xl overflow-hidden rounded-full bg-white/10">
              <div className="h-full rounded-full bg-[#dfff57] transition-[width] duration-500" style={{ width: `${job.progress}%` }} />
            </div>
          </div>
        </div>

        <div className="grid gap-2 border-t border-white/10 bg-black/20 p-4 sm:grid-cols-3 sm:p-6 lg:grid-cols-6">
          {stages.map((stage, index) => {
            const done = index < activeIndex;
            const active = index === activeIndex;
            return (
              <div key={stage[0]} className={`rounded-2xl border px-3 py-3 text-left transition ${active ? "border-[#dfff57]/40 bg-[#dfff57]/10" : done ? "border-emerald-400/20 bg-emerald-400/5" : "border-white/8 bg-white/[0.03]"}`}>
                <span className={`mb-2 flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-black ${active || done ? "bg-[#dfff57] text-[#07110d]" : "bg-white/10 text-white/45"}`}>{done ? <Check size={13} /> : index + 1}</span>
                <b className="text-xs text-white/85">{stage[1]}</b>
              </div>
            );
          })}
        </div>

        {waitingForAsr && <div className="mx-5 mb-5 rounded-2xl border border-[#dfff57]/20 bg-[#dfff57]/5 px-4 py-3 text-sm text-white/70 sm:mx-6"><Loader2 className="mr-2 inline animate-spin" size={15}/> Queue position <b className="text-white">#{job.queue_position}</b> · your job waits safely instead of overloading the service.</div>}
        {job.status === "failed" && <div className="m-5 flex flex-col gap-3 rounded-2xl border border-rose-300/20 bg-rose-400/10 p-4 sm:m-6 sm:flex-row sm:items-center"><AlertCircle size={18} className="shrink-0 text-rose-300"/><span className="flex-1 text-sm text-rose-50">{diagnostic}</span><button className="rounded-xl border border-white/15 px-4 py-2 text-sm font-bold hover:bg-white/10" onClick={() => { setJob(null); setBusy(false); }}>Try another link</button></div>}
        <div className="flex items-center gap-2 border-t border-white/10 px-5 py-4 text-xs text-white/45 sm:px-6"><LockKeyhole size={14}/> Source media is private and follows ClipKaro&apos;s automatic retention policy.</div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      {preflight && !preflight.ready && (
        <div className="mb-5 flex gap-3 rounded-2xl border border-amber-300/30 bg-amber-50 p-4 text-sm text-amber-950">
          <AlertCircle size={20} className="mt-0.5 shrink-0"/><div><b>Processing engine needs attention</b>{preflight.problems.map((problem) => <p className="mt-1" key={problem}>{problem}</p>)}<small className="mt-2 block opacity-70">{preflight.recommendation}</small></div>
        </div>
      )}

      <div className="relative overflow-hidden rounded-[34px] border border-[#143c2d]/15 bg-[#07110d] text-white shadow-[0_30px_100px_rgba(7,40,28,.18)]">
        <div className="pointer-events-none absolute inset-0 opacity-60" style={{ backgroundImage: "radial-gradient(circle at 15% 15%, rgba(223,255,87,.14), transparent 28%), radial-gradient(circle at 90% 80%, rgba(30,190,120,.12), transparent 34%)" }} />
        <div className="pointer-events-none absolute left-[8%] top-12 rotate-[-12deg] text-white/[0.035]"><Scissors size={150}/></div>
        <div className="pointer-events-none absolute bottom-4 right-[5%] rotate-12 text-[#dfff57]/[0.04]"><WandSparkles size={170}/></div>

        <div className="relative grid gap-8 p-5 sm:p-8 lg:grid-cols-[1.05fr_.95fr] lg:p-10">
          <div className="flex flex-col justify-center py-2 lg:py-8">
            <div className="mb-5 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[#dfff57]/25 bg-[#dfff57]/10 px-3 py-1.5 text-[11px] font-extrabold tracking-[0.12em] text-[#dfff57]"><Sparkles size={13}/> NEW LINK-FIRST WORKFLOW</span>
              {usage && <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.05] px-3 py-1.5 text-xs font-semibold text-white/65"><Clock3 size={13}/>{usage.processing_minutes_remaining:g} Karo Minutes left</span>}
            </div>
            <h2 className="max-w-xl text-[clamp(2.3rem,5vw,4.5rem)] font-black leading-[0.95] tracking-[-0.055em]">Paste a video.<br/><span className="text-[#dfff57]">Get the moments.</span></h2>
            <p className="mt-5 max-w-lg text-sm leading-6 text-white/58 sm:text-base">Drop in a YouTube link and ClipKaro handles the import, transcription and moment discovery inside the same private creator workflow.</p>
            <div className="mt-7 grid max-w-lg grid-cols-3 gap-2">
              {[[Link2, "Paste"], [Sparkles, "Analyse"], [Scissors, "Clip"]].map(([Icon, label], index) => {
                const StepIcon = Icon as typeof Link2;
                return <div key={String(label)} className="rounded-2xl border border-white/8 bg-white/[0.035] p-3"><span className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl bg-white/[0.06] text-[#dfff57]"><StepIcon size={16}/></span><b className="text-xs text-white/78">0{index + 1} · {String(label)}</b></div>;
              })}
            </div>
          </div>

          <div className="rounded-[28px] border border-white/12 bg-white/[0.07] p-4 shadow-[inset_0_1px_rgba(255,255,255,.08),0_24px_60px_rgba(0,0,0,.18)] backdrop-blur-xl sm:p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#ff0033] shadow-lg shadow-red-950/30"><Youtube size={23}/></span><div><b className="block text-sm">YouTube source</b><span className="text-xs text-white/45">One video link at a time</span></div></div>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-bold text-emerald-200"><ShieldCheck size={12}/> PRIVATE</span>
            </div>

            <label className="mb-2 block text-xs font-bold text-white/65">Paste your YouTube video link</label>
            <div className={`flex items-center gap-2 rounded-2xl border bg-black/25 p-2 transition ${youtubeUrl && !videoId ? "border-rose-300/45" : videoId ? "border-[#dfff57]/40" : "border-white/12 focus-within:border-[#dfff57]/35"}`}>
              <Link2 size={17} className="ml-2 shrink-0 text-white/35"/>
              <input
                type="url"
                value={youtubeUrl}
                onChange={(event) => { setYoutubeUrl(event.target.value); setError(""); }}
                onKeyDown={(event) => { if (event.key === "Enter" && videoId && rightsConfirmed) void startImport(); }}
                placeholder="https://youtube.com/watch?v=..."
                className="min-w-0 flex-1 border-0 bg-transparent px-1 py-3 text-sm text-white outline-none placeholder:text-white/28"
                autoComplete="off"
                spellCheck={false}
              />
              <button type="button" onClick={pasteFromClipboard} className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2.5 text-xs font-bold text-white/75 transition hover:bg-white/10"><Clipboard size={14}/><span className="hidden sm:inline">Paste</span></button>
            </div>
            {youtubeUrl && !videoId && <p className="mt-2 text-xs text-rose-200">Use a direct YouTube video, Shorts, or live-replay link.</p>}

            {videoId && (
              <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                <div className="relative aspect-video overflow-hidden bg-black/30">
                  <img src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`} alt="YouTube video preview" className="h-full w-full object-cover opacity-90" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
                  <span className="absolute bottom-3 left-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#dfff57] text-[#07110d] shadow-lg"><Play size={17} fill="currentColor"/></span>
                  <span className="absolute bottom-3 right-3 rounded-full border border-white/15 bg-black/55 px-2.5 py-1 text-[10px] font-bold text-white/80 backdrop-blur">LINK VERIFIED</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-3 text-xs text-white/60"><Check size={14} className="text-[#dfff57]"/> ClipKaro recognized this YouTube video and will verify its limits before download.</div>
              </div>
            )}

            {videoId && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="sm:col-span-2"><span className="mb-1.5 block text-[11px] font-bold text-white/50">PROJECT TITLE <span className="font-medium text-white/30">· optional</span></span><input value={title} onChange={(event) => setTitle(event.target.value.slice(0, 120))} placeholder="Use YouTube title automatically" className="w-full rounded-xl border border-white/10 bg-black/20 px-3.5 py-3 text-sm text-white outline-none placeholder:text-white/25 focus:border-[#dfff57]/35"/></label>
                <label><span className="mb-1.5 block text-[11px] font-bold text-white/50">SPOKEN LANGUAGE</span><select value={language} onChange={(event) => setLanguage(event.target.value as AccountSettings["default_language"])} className="w-full rounded-xl border border-white/10 bg-[#0d1b15] px-3 py-3 text-sm text-white outline-none focus:border-[#dfff57]/35"><option value="hi">Hindi · Recommended</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option><option value="auto">Auto detect · India-first</option></select></label>
                <label><span className="mb-1.5 block text-[11px] font-bold text-white/50">CONTENT TYPE</span><select value={category} onChange={(event) => setCategory(event.target.value as AccountSettings["creator_category"])} className="w-full rounded-xl border border-white/10 bg-[#0d1b15] px-3 py-3 text-sm text-white outline-none focus:border-[#dfff57]/35"><option value="auto">Let AI decide</option><option value="education">Education</option><option value="podcast">Podcast</option><option value="business">Business</option><option value="motivation">Motivation</option><option value="spiritual">Spiritual</option><option value="local-business">Local business</option></select></label>
              </div>
            )}

            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-white/8 bg-white/[0.03] p-3.5">
              <input type="checkbox" checked={rightsConfirmed} onChange={(event) => setRightsConfirmed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#dfff57]"/>
              <span className="text-xs leading-5 text-white/58"><b className="text-white/82">Rights confirmation.</b> I own this video or have permission to create clips from it.</span>
            </label>

            {error && <div className="mt-4 flex gap-2 rounded-xl border border-rose-300/20 bg-rose-400/10 p-3 text-xs leading-5 text-rose-50"><AlertCircle size={16} className="mt-0.5 shrink-0"/><span>{error}</span></div>}

            <button
              type="button"
              disabled={!videoId || !rightsConfirmed || busy || preflight?.ready === false}
              onClick={startImport}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[#dfff57] px-5 py-4 text-sm font-black text-[#07110d] shadow-[0_14px_35px_rgba(223,255,87,.16)] transition hover:-translate-y-0.5 hover:bg-[#e8ff84] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
            >
              {busy ? <Loader2 size={17} className="animate-spin"/> : <Sparkles size={17}/>} {preflight?.ready === false ? "Processing engine unavailable" : busy ? "Starting secure import…" : "Find my best moments"} {!busy && <ChevronRight size={17}/>} 
            </button>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[10px] font-semibold text-white/35"><span>Up to 500 MB</span><span>Plan minute limits apply</span><span>Private processing</span></div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {[
          [Link2, "Paste, don't upload", "Start with the YouTube link you already have."],
          [WandSparkles, "AI finds the moments", "Transcript, hooks and ranked clips run in one workflow."],
          [LockKeyhole, "Built around private media", "Your source follows ClipKaro's existing retention and access controls."],
        ].map(([Icon, heading, copy]) => {
          const ItemIcon = Icon as typeof Link2;
          return <div key={String(heading)} className="rounded-2xl border border-[#143c2d]/10 bg-white p-4 shadow-[0_12px_35px_rgba(12,58,41,.06)]"><span className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-[#eff8cf] text-[#165f43]"><ItemIcon size={17}/></span><b className="text-sm text-[#10271d]">{String(heading)}</b><p className="mt-1 text-xs leading-5 text-[#52685f]">{String(copy)}</p></div>;
        })}
      </div>
    </div>
  );
}
