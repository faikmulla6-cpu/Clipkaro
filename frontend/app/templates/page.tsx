"use client";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { AlertCircle, ArrowRight, LayoutTemplate, Loader2, Play, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Template = { id: string; name: string; category: string; caption_style: string; primary: string; accent: string; best_for: string };

export default function Templates() {
  const [data, setData] = useState<Template[]>([]);
  const [filter, setFilter] = useState("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setData(await api<Template[]>("/templates")); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Templates could not be loaded."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);
  const shown = useMemo(() => filter === "All" ? data : data.filter((item) => item.category === filter), [data, filter]);

  return (
    <AppShell title="Template gallery" subtitle="Preview distinctive creator looks, then choose the matching caption personality in Creator Studio.">
      <div className="template-feature"><div><span className="eyebrow dark"><Sparkles size={12}/> FEATURED THIS WEEK</span><h2>India Pop</h2><p>High-energy captions built for Hindi talking-head clips. Hinglish support is still under controlled quality validation and is not generally available yet.</p><Link href="/upload" className="primary-btn">Start a video <ArrowRight size={15}/></Link></div><div className="template-phone"><div className="template-person"/><div className="template-caption">AAPKI EK <em>MISTAKE</em><br/>GROWTH ROK RAHI HAI</div></div></div>
      <div className="section-line"><h3>All creator styles</h3><div className="filter-tabs">{["All", "Education", "Podcast", "Business", "Spiritual"].map((item) => <button key={item} type="button" onClick={() => setFilter(item)} className={filter === item ? "active" : ""}>{item}</button>)}</div></div>
      {loading ? (
        <div className="screen-loader inline" role="status"><Loader2 className="spin" size={24}/><p>Loading templates…</p></div>
      ) : error ? (
        <div className="empty-state"><div className="empty-icon"><AlertCircle/></div><h3>Templates unavailable</h3><p>{error}</p><button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button></div>
      ) : shown.length === 0 ? (
        <div className="empty-state"><div className="empty-icon"><LayoutTemplate/></div><h3>No styles in this category yet</h3><p>Choose another category or start with one of the available creator styles.</p></div>
      ) : (
        <div className="template-grid">{shown.map((template, index) => {
          const bestFor = template.id === "india-pop" ? "Hindi talking-head clips" : template.best_for;
          return (
          <article className="template-card" key={template.id}>
            <div className="template-preview" style={{ background: `linear-gradient(150deg,${template.accent},${template.primary})` }}><div className="template-face"/><div className={`template-demo ${template.caption_style}`}>{index % 2 ? "THE IDEA THAT" : "STOP MAKING"}<br/><em>{index % 2 ? "CHANGED IT" : "THIS MISTAKE"}</em></div><span className="template-play-indicator" aria-hidden="true"><Play size={17} fill="currentColor"/></span></div>
            <div className="template-info"><div><span>{template.category}</span><h3>{template.name}</h3><p>Best for {bestFor}</p></div><Link href="/upload" aria-label={`Start a video inspired by ${template.name}`} title="Start a video, then choose the matching caption personality in Creator Studio"><ArrowRight size={17}/></Link></div>
          </article>
        );})}</div>
      )}
    </AppShell>
  );
}
