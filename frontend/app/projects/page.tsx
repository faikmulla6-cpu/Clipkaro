"use client";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { AlertCircle, Clock3, FolderKanban, MoreHorizontal, Play, Plus, RefreshCw, Search, Sparkles, Upload, Video } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Project = {
  id: string;
  title: string;
  status: string;
  progress: number;
  stage: string;
  duration: number;
  clip_count: number;
  export_count: number;
  video_status?: string;
  updated_at: string;
  error?: string;
};

export default function Projects() {
  const [data, setData] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<Project[]>("/projects"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Projects could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => data.filter((project) => {
    const matchesSearch = project.title.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All"
      || (filter === "Ready" && project.status === "ready")
      || (filter === "Processing" && ["processing", "queued"].includes(project.status))
      || (filter === "Needs attention" && project.status === "failed")
      || (filter === "Exported" && project.export_count > 0);
    return matchesSearch && matchesFilter;
  }), [data, query, filter]);

  return (
    <AppShell
      title="Projects"
      subtitle="Every upload, AI moment, and export in one place."
      action={<Link href="/upload" className="primary-btn small"><Plus size={14}/>New project</Link>}
    >
      <div className="project-toolbar">
        <div className="search-box"><Search size={16}/><input type="search" aria-label="Search projects" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search projects…"/></div>
        <div className="filter-tabs">{["All", "Ready", "Processing", "Needs attention", "Exported"].map((item) => (
          <button key={item} type="button" onClick={() => setFilter(item)} className={filter === item ? "active" : ""}>{item}</button>
        ))}</div>
      </div>

      {loading ? (
        <div className="skeleton-grid" aria-label="Loading projects">{[1, 2, 3].map((item) => <div key={item}/>)}</div>
      ) : error ? (
        <div className="empty-state">
          <div className="empty-icon"><AlertCircle/></div>
          <h3>Projects unavailable</h3>
          <p>{error}</p>
          <button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><FolderKanban/></div>
          <h3>{query || filter !== "All" ? "No projects match this view" : "Your first great Short starts here"}</h3>
          <p>Upload a video you own. ClipKaro finds the strongest standalone moments and prepares them for vertical feeds.</p>
          <Link href="/upload" className="primary-btn"><Upload size={15}/>Upload a video</Link>
        </div>
      ) : (
        <div className="project-cards">{filtered.map((project) => (
          <Link href={`/projects/${project.id}`} className="project-card" key={project.id}>
            <div className="project-cover">
              <div className="cover-pattern"/>
              <span className="project-play-indicator" aria-hidden="true"><Play size={17} fill="currentColor"/></span>
              <span className="project-duration">{project.duration ? `${Math.floor(project.duration / 60)}:${String(Math.round(project.duration % 60)).padStart(2, "0")}` : "Processing"}</span>
            </div>
            <div className="project-card-body">
              <div className="project-card-title"><h3>{project.title}</h3><MoreHorizontal size={17}/></div>
              <div className="project-meta"><span><Sparkles size={13}/>{project.clip_count || 0} moments</span><span><Video size={13}/>{project.export_count || 0} exports</span></div>
              {project.status === "processing" || project.status === "queued" ? (
                <div className="mini-processing"><div><b>{project.stage}</b><span>{project.progress}%</span></div><div className="progress"><span style={{ width: `${project.progress}%` }}/></div></div>
              ) : project.video_status === "expired" ? (
                <div className="failed-pill"><Clock3 size={12}/>Source expired · history kept</div>
              ) : project.status === "failed" ? (
                <div className="failed-pill" title={project.error || "Processing failed"}><AlertCircle size={12}/>Retry available</div>
              ) : (
                <div className="ready-row"><span className="ready-pill"><Sparkles size={12}/>Ready</span><small><Clock3 size={11}/>Updated {new Date(project.updated_at).toLocaleDateString()}</small></div>
              )}
            </div>
          </Link>
        ))}</div>
      )}
    </AppShell>
  );
}
