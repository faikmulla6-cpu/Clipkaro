"use client";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { AlertCircle, FileText, Plus, RefreshCw, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Project = {
  id: string;
  title: string;
  status: string;
  clip_count: number;
  updated_at: string;
};

export default function ContentPacksPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setProjects(await api<Project[]>("/projects"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Content Packs could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const readyProjects = useMemo(
    () => projects.filter(project => project.status === "ready" && (project.clip_count || 0) > 0),
    [projects],
  );

  return (
    <AppShell
      title="Content Packs"
      subtitle="Turn each finished video into ready-to-use publishing copy for YouTube Shorts, Instagram, X and LinkedIn."
      action={<Link href="/upload" className="primary-btn small"><Plus size={14}/>New video</Link>}
    >
      <section className="content-pack-panel">
        <div className="content-pack-head">
          <div>
            <span className="eyebrow"><FileText size={12}/> ONE VIDEO → COMPLETE CONTENT PACK</span>
            <h2>Your ready projects</h2>
            <p>Open a finished project to generate or revisit titles, descriptions, captions, hashtags, X posts, LinkedIn copy, cover text, content angles and recommended publishing order.</p>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="skeleton-grid" aria-label="Loading Content Packs">{[1, 2, 3].map(item => <div key={item}/>)}</div>
      ) : error ? (
        <div className="empty-state">
          <div className="empty-icon"><AlertCircle/></div>
          <h3>Content Packs unavailable</h3>
          <p>{error}</p>
          <button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button>
        </div>
      ) : readyProjects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Sparkles/></div>
          <h3>Your first Content Pack starts with a finished video</h3>
          <p>Upload a video, let ClipKaro find the strongest moments, then open the project to generate the complete publishing pack.</p>
          <Link href="/upload" className="primary-btn"><Upload size={15}/>Upload a video</Link>
        </div>
      ) : (
        <div className="project-cards">
          {readyProjects.map(project => (
            <Link href={`/projects/${project.id}`} className="project-card" key={project.id}>
              <div className="project-cover">
                <div className="cover-pattern"/>
                <span className="project-play-indicator" aria-hidden="true"><FileText size={17}/></span>
                <span className="project-duration">Content Pack</span>
              </div>
              <div className="project-card-body">
                <div className="project-card-title"><h3>{project.title}</h3></div>
                <div className="project-meta"><span><Sparkles size={13}/>{project.clip_count || 0} moments ready</span></div>
                <div className="ready-row"><span className="ready-pill"><FileText size={12}/>Open Content Pack</span><small>Updated {new Date(project.updated_at).toLocaleDateString()}</small></div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
