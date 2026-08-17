"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";
import { api, Usage } from "@/lib/api";
import { AlertCircle, ArrowRight, Clock3, Download, FolderKanban, Loader2, Play, RefreshCw, Sparkles, TrendingUp, Upload, Video } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Project = { id: string; title: string; status: string; progress: number; stage: string; clip_count: number; export_count: number; updated_at: string };
type Analytics = { summary: { projects: number; clips: number; avg_score: number; exports: number; minutes_processed: number }; usage: Usage };

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [stats, setStats] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [projectRows, analytics] = await Promise.all([api<Project[]>("/projects"), api<Analytics>("/analytics")]);
      setProjects(projectRows);
      setStats(analytics);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Your workspace overview could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const hello = useMemo(() => greeting(), []);
  const summary = stats?.summary;

  return (
    <AppShell title="Overview" subtitle="Your content engine, live and in control." action={<Link href="/upload" className="primary-btn small"><Upload size={15}/>Upload video</Link>}>
      <section className="command-hero"><div><span className="eyebrow dark">CREATOR COMMAND CENTRE</span><h2>{hello}, {user?.name?.split(" ")[0]}.</h2><p>Turn one useful conversation into a week of content.</p><div className="command-actions"><Link href="/upload" className="command-primary"><span><Sparkles size={19}/></span><div><b>Create from a video</b><small>Upload → AI moments → export</small></div><ArrowRight/></Link><Link href="/templates" className="command-secondary"><span><FolderKanban/></span><div><b>Browse templates</b><small>Creator-ready Indian styles</small></div></Link></div></div><div className="hero-visual"><div className="vertical-card"><div className="mini-caption">THE ONE THING<br/><em>CREATORS MISS</em></div><Play/></div><div className="floating-score"><Sparkles/><div><b>{summary?.avg_score || "—"}</b><small>avg. potential</small></div></div></div></section>

      {loading ? <div className="screen-loader inline" role="status"><Loader2 className="spin" size={24}/><p>Loading your real workspace activity…</p></div> : error ? <div className="empty-state"><div className="empty-icon"><AlertCircle/></div><h3>Workspace overview unavailable</h3><p>{error}</p><button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button></div> : <>
        <div className="stat-grid launch">{[
          [Video, "Projects", summary?.projects || 0, "All-time"],
          [Sparkles, "Moments found", summary?.clips || 0, "AI ranked"],
          [Download, "Exports", summary?.exports || 0, `${stats?.usage.exports_remaining || 0} left`],
          [Clock3, "Source processed", `${summary?.minutes_processed || 0}m`, "This workspace"],
        ].map(([Icon, label, value, note]: any) => <div className="stat-card" key={label}><div className="stat-card-top"><span>{label}</span><span className="stat-icon"><Icon size={16}/></span></div><b className="stat-value">{value}</b><span className="trend">{note}</span></div>)}</div>

        <div className="dashboard-grid"><div className="panel"><div className="panel-head"><h3>Continue creating</h3><Link href="/projects">All projects <ArrowRight size={12}/></Link></div>{projects.length ? projects.slice(0, 4).map((project, index) => <Link href={`/projects/${project.id}`} className="project-item" key={project.id}><div className={`project-thumb scene-${index % 4}`}><Play size={15}/></div><div><b>{project.title}</b><span>{project.status === "ready" ? `${project.clip_count} moments · ${project.export_count} exports` : `${project.stage} · ${project.progress}%`}</span></div><span className={project.status === "ready" ? "project-status" : "processing-pill"}>{project.status}</span></Link>) : <div className="mini-empty"><Video/><p>No projects yet. Start with one upload and ClipKaro will guide you through processing.</p><Link href="/upload">Start creating</Link></div>}</div><div className="panel insight-panel"><div className="panel-head"><h3>Creator playbook</h3><span className="live-badge">WORKFLOW TIP</span></div><div className="insight-big"><TrendingUp/><b>Question-led hooks</b><p>Open with a direct question, then answer it within the first eight seconds. This is a general editing tip, not a score derived from your account.</p></div><div className="metric-list"><div><span>AI quality signal</span><b>{summary?.avg_score || "—"}</b></div><div><span>Moments available</span><b>{summary?.clips || 0}</b></div></div></div></div>
      </>}
    </AppShell>
  );
}
