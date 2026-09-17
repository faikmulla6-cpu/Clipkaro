"use client";

import {
  AlertCircle, Check, ChevronRight, Clipboard, Clock3, Link2, Loader2,
  LockKeyhole, Play, Scissors, ShieldCheck, Sparkles, WandSparkles, Youtube,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AccountSettings, API_URL, Usage, api } from "@/lib/api";

type Job = {
  status: string; progress: number; stage: string; message: string; error?: string;
  project_id?: string; asr_state?: "queued" | "running"; queue_position?: number;
};
type Preflight = { ready: boolean; problems: string[]; recommendation: string };
type YouTubeImport = { project_id: string; job_id: string; status: string; youtube_video_id: string };

const STAGES = [
  ["importing", "Import"], ["validating", "Check"], ["audio", "Audio"],
  ["transcribing", "Transcript"], ["ranking", "Moments"], ["finishing", "Previews"],
] as const;

const DIRECT_GCS_UPLOAD = process.env.NEXT_PUBLIC_UPLOAD_MODE === "direct_gcs";

function youtubeVideoId(value: string): string {
  try {
    const url = new URL(value.trim());
    const host = url.hostname.toLowerCase().replace(/\.$/, "");
    const allowed = ["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"];
    if (!allowed.includes(host) || !["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port) return "";
    const parts = url.pathname.split("/").filter(Boolean);
    let id = "";
    if (host === "youtu.be") id = parts[0] || "";
    else if (url.pathname.replace(/\/$/, "") === "/watch") id = url.searchParams.get("v") || "";
    else if (parts.length >= 2 && ["shorts", "embed", "live"].includes(parts[0].toLowerCase())) id = parts[1];
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : "";
  } catch { return ""; }
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
    api<AccountSettings>("/settings").then((saved) => {
      setLanguage(saved.default_language); setCategory(saved.creator_category);
    }).catch(() => undefined);
  }, []);

  function watch(jobId: string, projectId: string) {
    const source = new EventSource(`${API_URL}/jobs/${jobId}/events`, { withCredentials: true });
    source.addEventListener("progress", (event) => setJob(JSON.parse((event as MessageEvent).data)));
    source.addEventListener("done", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as Job;
      setJob(data); setBusy(false); source.close();
      if (data.status === "completed") setTimeout(() => router.push(`/projects/${projectId}`), 700);
    });
    source.onerror = () => {
      source.close(); setBusy(false);
      setError("Live updates paused. Your video can still be processing — check Projects in a moment.");
    };
  }

  async function pasteLink() {
    setError("");
    try { setYoutubeUrl((await navigator.clipboard.readText()).trim()); }
    catch { setError("Clipboard access was blocked. Paste the YouTube link into the field."); }
  }

  async function startImport() {
    if (!videoId || !rightsConfirmed || busy || preflight?.ready === false) return;
    setBusy(true); setError("");
    try {
      const result = await api<YouTubeImport>("/imports/youtube", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: youtubeUrl.trim(), title: title.trim(), language, category, rights_confirmed: true }),
      });
      setJob({ status: "queued", progress: 0, stage: "queued", message: "Your YouTube video is in ClipKaro's secure processing queue", project_id: result.project_id });
      watch(result.job_id, result.project_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ClipKaro could not start this import. Please try again.");
      setBusy(false);
    }
  }

  if (job) {
    const active = STAGES.findIndex(([key]) => key === job.stage);
    const message = job.message || job.error || "Processing your video now.";
    return (
      <section className="mx-auto w-full max-w-5xl overflow-hidden rounded-[32px] border border-white/10 bg-[#07110d] text-white shadow-[0_28px_90px_rgba(3,18,12,.28)]">
        <div className="relative px-5 py-10 text-center sm:px-10 sm:py-14">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_0%,rgba(223,255,87,.14),transparent_36%)]" />
          <div className="relative mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-[#dfff57]/25 bg-[#dfff57]/10">
            {job.status === "failed" ? <AlertCircle className="text-rose-300" size={28}/> : <Loader2 className="animate-spin text-[#dfff57]" size={28}/>} 
          </div>
          <p className="relative mt-5 text-[11px] font-extrabold tracking-[.22em] text-[#dfff57]">CLIPKARO AI PIPELINE</p>
          <h2 className="relative mx-auto mt-2 max-w-2xl text-3xl font-black tracking-[-.04em] sm:text-4xl">{job.status === "failed" ? "This video needs attention" : "Turning your video into strong Shorts"}</h2>
          <p className="relative mx-auto mt-3 max-w-xl text-sm leading-6 text-white/60">{message}</p>
          <div className="relative mt-7 text-5xl font-black">{job.progress}<span className="text-xl text-[#dfff57]">%</span></div>
          <div className="relative mx-auto mt-4 h-2 max-w-xl overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[#dfff57] transition-[width] duration-500" style={{ width: `${job.progress}%` }}/></div>
        </div>
        <div className="grid gap-2 border-t border-white/10 bg-black/20 p-4 sm:grid-cols-3 lg:grid-cols-6">
          {STAGES.map(([key, label], index) => <div key={key} className={`rounded-2xl border p-3 ${index === active ? "border-[#dfff57]/40 bg-[#dfff57]/10" : index < active ? "border-emerald-400/20 bg-emerald-400/5" : "border-white/10 bg-white/[.03]"}`}><span className={`mb-2 flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-black ${index <= active ? "bg-[#dfff57] text-[#07110d]" : "bg-white/10 text-white/45"}`}>{index < active ? <Check size={13}/> : index + 1}</span><b className="text-xs text-white/80">{label}</b></div>)}
        </div>
        {job.status === "failed" && <div className="m-5 flex flex-col gap-3 rounded-2xl border border-rose-300/20 bg-rose-400/10 p-4 sm:flex-row sm:items-center"><AlertCircle className="shrink-0 text-rose-300" size={18}/><span className="flex-1 text-sm">{message}</span><button className="rounded-xl border border-white/15 px-4 py-2 text-sm font-bold hover:bg-white/10" onClick={() => { setJob(null); setBusy(false); }}>Try another link</button></div>}
        <div className="flex items-center gap-2 border-t border-white/10 px-5 py-4 text-xs text-white/45"><LockKeyhole size={14}/> Private source media follows ClipKaro&apos;s automatic retention policy.</div>
      </section>
    );
  }

  const minutesLeft = usage ? usage.processing_minutes_remaining.toLocaleString(undefined, { maximumFractionDigits: 1 }) : null;
  return (
    <div className="mx-auto w-full max-w-6xl" data-upload-fallback={DIRECT_GCS_UPLOAD ? "direct_gcs" : "api"}>
      {preflight && !preflight.ready && <div className="mb-5 flex gap-3 rounded-2xl border border-amber-300/30 bg-amber-50 p-4 text-sm text-amber-950"><AlertCircle className="shrink-0" size={20}/><div><b>Processing engine needs attention</b>{preflight.problems.map((item) => <p className="mt-1" key={item}>{item}</p>)}<small className="mt-2 block opacity-70">{preflight.recommendation}</small></div></div>}

      <section className="relative overflow-hidden rounded-[34px] border border-[#143c2d]/15 bg-[#07110d] text-white shadow-[0_30px_100px_rgba(7,40,28,.18)]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_14%_12%,rgba(223,255,87,.14),transparent_30%),radial-gradient(circle_at_90%_82%,rgba(30,190,120,.12),transparent_34%)]" />
        <Scissors className="pointer-events-none absolute left-[7%] top-12 rotate-[-12deg] text-white/[.035]" size={150}/>
        <WandSparkles className="pointer-events-none absolute bottom-4 right-[5%] rotate-12 text-[#dfff57]/[.045]" size={170}/>
        <div className="relative grid gap-8 p-5 sm:p-8 lg:grid-cols-[1.05fr_.95fr] lg:p-10">
          <div className="flex flex-col justify-center py-3 lg:py-8">
            <div className="mb-5 flex flex-wrap gap-2"><span className="inline-flex items-center gap-1.5 rounded-full border border-[#dfff57]/25 bg-[#dfff57]/10 px-3 py-1.5 text-[11px] font-extrabold tracking-[.12em] text-[#dfff57]"><Sparkles size={13}/> LINK-FIRST CREATION</span>{minutesLeft !== null && <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[.05] px-3 py-1.5 text-xs font-semibold text-white/65"><Clock3 size={13}/>{minutesLeft} Karo Minutes left</span>}</div>
            <h2 className="max-w-xl text-[clamp(2.3rem,5vw,4.5rem)] font-black leading-[.95] tracking-[-.055em]">Paste a video.<br/><span className="text-[#dfff57]">Get the moments.</span></h2>
            <p className="mt-5 max-w-lg text-sm leading-6 text-white/60 sm:text-base">Paste your YouTube link. ClipKaro securely imports the source, transcribes it, ranks the strongest moments and takes you straight into the existing creator workflow.</p>
            <div className="mt-7 grid max-w-lg grid-cols-3 gap-2">
              <Step icon={<Link2 size={16}/>} number="01" label="Paste"/><Step icon={<Sparkles size={16}/>} number="02" label="Analyse"/><Step icon={<Scissors size={16}/>} number="03" label="Clip"/>
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/[.07] p-4 shadow-[inset_0_1px_rgba(255,255,255,.08),0_24px_60px_rgba(0,0,0,.18)] backdrop-blur-xl sm:p-5">
            <div className="mb-4 flex items-center justify-between"><div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#ff0033]"><Youtube size={23}/></span><div><b className="block text-sm">YouTube source</b><span className="text-xs text-white/45">One video at a time</span></div></div><span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-bold text-emerald-200"><ShieldCheck size={12}/> PRIVATE</span></div>
            <label className="mb-2 block text-xs font-bold text-white/65">Paste your YouTube video link</label>
            <div className={`flex items-center gap-2 rounded-2xl border bg-black/25 p-2 ${youtubeUrl && !videoId ? "border-rose-300/45" : videoId ? "border-[#dfff57]/40" : "border-white/10 focus-within:border-[#dfff57]/35"}`}>
              <Link2 className="ml-2 shrink-0 text-white/35" size={17}/><input type="url" value={youtubeUrl} onChange={(e) => { setYoutubeUrl(e.target.value); setError(""); }} onKeyDown={(e) => { if (e.key === "Enter") void startImport(); }} placeholder="https://youtube.com/watch?v=..." className="min-w-0 flex-1 border-0 bg-transparent px-1 py-3 text-sm text-white outline-none placeholder:text-white/30" autoComplete="off" spellCheck={false}/><button type="button" onClick={pasteLink} className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-white/10 bg-white/[.06] px-3 py-2.5 text-xs font-bold text-white/75 hover:bg-white/10"><Clipboard size={14}/><span className="hidden sm:inline">Paste</span></button>
            </div>
            {youtubeUrl && !videoId && <p className="mt-2 text-xs text-rose-200">Use a direct YouTube video, Shorts, or live-replay link.</p>}

            {videoId && <div className="mt-4 overflow-hidden rounded-2xl border border-white/10 bg-black/20"><div className="relative aspect-video overflow-hidden"><img src={`https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`} alt="YouTube video preview" className="h-full w-full object-cover opacity-90"/><div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent"/><span className="absolute bottom-3 left-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#dfff57] text-[#07110d]"><Play size={17} fill="currentColor"/></span><span className="absolute bottom-3 right-3 rounded-full bg-black/60 px-2.5 py-1 text-[10px] font-bold">LINK VERIFIED</span></div><div className="flex items-center gap-2 px-3 py-3 text-xs text-white/60"><Check className="text-[#dfff57]" size={14}/> Link recognized. Limits are verified before heavy processing.</div></div>}

            {videoId && <div className="mt-4 grid gap-3 sm:grid-cols-2"><Field label="PROJECT TITLE · OPTIONAL" className="sm:col-span-2"><input value={title} onChange={(e) => setTitle(e.target.value.slice(0, 120))} placeholder="Use YouTube title automatically" className="w-full rounded-xl border border-white/10 bg-black/20 px-3.5 py-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#dfff57]/35"/></Field><Field label="SPOKEN LANGUAGE"><select value={language} onChange={(e) => setLanguage(e.target.value as AccountSettings["default_language"])} className="w-full rounded-xl border border-white/10 bg-[#0d1b15] px-3 py-3 text-sm text-white outline-none"><option value="hi">Hindi · Recommended</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option><option value="auto">Auto detect</option></select></Field><Field label="CONTENT TYPE"><select value={category} onChange={(e) => setCategory(e.target.value as AccountSettings["creator_category"])} className="w-full rounded-xl border border-white/10 bg-[#0d1b15] px-3 py-3 text-sm text-white outline-none"><option value="auto">Let AI decide</option><option value="education">Education</option><option value="podcast">Podcast</option><option value="business">Business</option><option value="motivation">Motivation</option><option value="spiritual">Spiritual</option><option value="local-business">Local business</option></select></Field></div>}

            <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-white/[.03] p-3.5"><input type="checkbox" checked={rightsConfirmed} onChange={(e) => setRightsConfirmed(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#dfff57]"/><span className="text-xs leading-5 text-white/60"><b className="text-white/85">Rights confirmation.</b> I own this video or have permission to create clips from it.</span></label>
            {error && <div className="mt-4 flex gap-2 rounded-xl border border-rose-300/20 bg-rose-400/10 p-3 text-xs leading-5 text-rose-50"><AlertCircle className="shrink-0" size={16}/>{error}</div>}
            <button type="button" disabled={!videoId || !rightsConfirmed || busy || preflight?.ready === false} onClick={startImport} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-[#dfff57] px-5 py-4 text-sm font-black text-[#07110d] shadow-[0_14px_35px_rgba(223,255,87,.16)] transition hover:-translate-y-0.5 hover:bg-[#e8ff84] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0">{busy ? <Loader2 className="animate-spin" size={17}/> : <Sparkles size={17}/>} {busy ? "Starting secure import…" : "Find my best moments"} {!busy && <ChevronRight size={17}/>}</button>
            <div className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-[10px] font-semibold text-white/35"><span>500 MB source cap</span><span>Plan minute limits apply</span><span>Private processing</span></div>
          </div>
        </div>
      </section>

      <div className="mt-5 grid gap-3 md:grid-cols-3"><Trust icon={<Link2 size={17}/>} title="Paste, don't hunt for files" copy="Start from the YouTube link you already have."/><Trust icon={<WandSparkles size={17}/>} title="One connected AI flow" copy="Import, transcript and ranked moments stay inside ClipKaro."/><Trust icon={<LockKeyhole size={17}/>} title="Private by design" copy="Source media keeps the same access controls and retention rules."/></div>
    </div>
  );
}

function Step({ icon, number, label }: { icon: React.ReactNode; number: string; label: string }) {
  return <div className="rounded-2xl border border-white/10 bg-white/[.035] p-3"><span className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl bg-white/[.06] text-[#dfff57]">{icon}</span><b className="text-xs text-white/80">{number} · {label}</b></div>;
}
function Field({ label, className = "", children }: { label: string; className?: string; children: React.ReactNode }) {
  return <label className={className}><span className="mb-1.5 block text-[11px] font-bold text-white/50">{label}</span>{children}</label>;
}
function Trust({ icon, title, copy }: { icon: React.ReactNode; title: string; copy: string }) {
  return <div className="rounded-2xl border border-[#143c2d]/10 bg-white p-4 shadow-[0_12px_35px_rgba(12,58,41,.06)]"><span className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-[#eff8cf] text-[#165f43]">{icon}</span><b className="text-sm text-[#10271d]">{title}</b><p className="mt-1 text-xs leading-5 text-[#52685f]">{copy}</p></div>;
}
