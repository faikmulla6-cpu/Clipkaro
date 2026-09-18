"use client";

import { AppShell } from "@/components/AppShell";
import { API_URL, api } from "@/lib/api";
import { recordDownload } from "@/lib/behavior";
import { AlertCircle, Clock3, Download, Loader2, RefreshCw, Video } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type ExportItem = {
  id: string;
  title?: string;
  hook?: string;
  project_title?: string;
  status: string;
  progress?: number;
  resolution?: string;
  aspect_ratio?: string;
  created_at?: string;
  expires_at?: string;
};

export default function ExportsPage() {
  const [items, setItems] = useState<ExportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("All");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setItems(await api<ExportItem[]>("/exports"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Exports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => items.filter((item) => {
    if (filter === "All") return true;
    if (filter === "Ready") return item.status === "ready";
    if (filter === "Processing") return ["queued", "rendering", "processing"].includes(item.status);
    return ["failed", "expired"].includes(item.status);
  }), [items, filter]);

  return (
    <AppShell title="Exports" subtitle="Your rendered Shorts, download history, and delivery status.">
      <div className="project-toolbar">
        <div className="filter-tabs">{["All", "Ready", "Processing", "Needs attention"].map((item) => (
          <button key={item} type="button" onClick={() => setFilter(item)} className={filter === item ? "active" : ""}>{item}</button>
        ))}</div>
        <button className="secondary-btn small" type="button" onClick={() => void load()}><RefreshCw size={14}/>Refresh</button>
      </div>

      {loading ? (
        <div className="screen-loader inline" role="status"><Loader2 className="spin" size={24}/><p>Loading exports…</p></div>
      ) : error ? (
        <div className="empty-state"><div className="empty-icon"><AlertCircle/></div><h3>Exports unavailable</h3><p>{error}</p><button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button></div>
      ) : filtered.length === 0 ? (
        <div className="empty-state"><div className="empty-icon"><Video/></div><h3>No exports in this view</h3><p>Completed exports will appear here as soon as a Short finishes rendering.</p></div>
      ) : (
        <div className="project-cards">{filtered.map((item) => (
          <article className="project-card" key={item.id}>
            <div className="project-cover"><div className="cover-pattern"/><span className="project-play-indicator" aria-hidden="true"><Video size={17}/></span></div>
            <div className="project-card-body">
              <div className="project-card-title"><h3>{item.title || item.hook || "ClipKaro export"}</h3></div>
              <div className="project-meta">
                <span>{item.project_title || "Project"}</span>
                <span>{item.resolution || "Video"}{item.aspect_ratio ? ` · ${item.aspect_ratio}` : ""}</span>
              </div>
              {["queued", "rendering", "processing"].includes(item.status) ? (
                <div className="mini-processing"><div><b>Rendering</b><span>{item.progress || 0}%</span></div><div className="progress"><span style={{ width: `${item.progress || 0}%` }}/></div></div>
              ) : item.status === "ready" ? (
                <div className="ready-row">
                  <span className="ready-pill">Ready</span>
                  <a className="primary-btn small" href={`${API_URL}/exports/${item.id}/download`} onClick={() => recordDownload(item.id)}><Download size={14}/>Download MP4</a>
                </div>
              ) : (
                <div className="failed-pill"><AlertCircle size={12}/>{item.status === "expired" ? "Expired" : "Export failed"}</div>
              )}
              {item.created_at && <small><Clock3 size={11}/>Created {new Date(item.created_at).toLocaleDateString()}</small>}
            </div>
          </article>
        ))}</div>
      )}
    </AppShell>
  );
}
