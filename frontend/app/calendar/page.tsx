"use client";

import { AppShell } from "@/components/AppShell";
import { api, deleteJSON, postJSON } from "@/lib/api";
import { AlertCircle, CalendarDays, ChevronLeft, ChevronRight, Clock3, Instagram, Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Post = { id: string; platform: string; caption: string; scheduled_for: string; status: string };
type Export = { id: string; title: string; status: string };

function firstDayOfMonth(value = new Date()) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function localInputMin() {
  const now = new Date(Date.now() + 60_000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export default function Calendar() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [exports, setExports] = useState<Export[]>([]);
  const [month, setMonth] = useState(() => firstDayOfMonth());
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyDelete, setBusyDelete] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [calendar, completedExports] = await Promise.all([api<Post[]>("/calendar"), api<Export[]>("/exports")]);
      setPosts(calendar);
      setExports(completedExports.filter((item) => item.status === "ready"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Calendar could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const cells = useMemo(() => {
    const first = (month.getDay() + 6) % 7;
    const daysIn = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    const prevDays = new Date(month.getFullYear(), month.getMonth(), 0).getDate();
    return Array.from({ length: 42 }, (_, index) => {
      const day = index - first + 1;
      if (day < 1) return { day: prevDays + day, date: new Date(month.getFullYear(), month.getMonth() - 1, prevDays + day), outside: true };
      if (day > daysIn) return { day: day - daysIn, date: new Date(month.getFullYear(), month.getMonth() + 1, day - daysIn), outside: true };
      return { day, date: new Date(month.getFullYear(), month.getMonth(), day), outside: false };
    });
  }, [month]);

  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError("");
    try {
      const rawDate = String(data.get("scheduled_for") || "");
      const scheduled = new Date(rawDate);
      if (!rawDate || Number.isNaN(scheduled.getTime()) || scheduled.getTime() <= Date.now()) {
        throw new Error("Choose a future date and time.");
      }
      await postJSON("/calendar", {
        export_id: data.get("export_id"),
        platform: data.get("platform"),
        caption: data.get("caption"),
        hashtags: data.get("hashtags"),
        scheduled_for: scheduled.toISOString(),
      });
      setShow(false);
      form.reset();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add this calendar draft.");
    }
  }

  async function remove(postId: string) {
    if (!window.confirm("Remove this calendar draft?")) return;
    setBusyDelete(postId);
    setError("");
    try {
      await deleteJSON(`/calendar/${postId}`);
      setPosts((current) => current.filter((item) => item.id !== postId));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not remove this calendar draft.");
    } finally {
      setBusyDelete("");
    }
  }

  return (
    <AppShell title="Content calendar" subtitle="Plan completed exports without losing momentum." action={<button className="primary-btn small" type="button" onClick={() => setShow(true)}><Plus size={14}/>Schedule export</button>}>
      {show && <div className="modal-backdrop"><form className="schedule-modal" onSubmit={schedule}>
        <div className="panel-head"><h3>Schedule a completed export</h3><button type="button" className="icon-btn" onClick={() => setShow(false)} aria-label="Close"><X/></button></div>
        <div className="field"><label>Export</label><select name="export_id" required><option value="">Choose an export</option>{exports.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div>
        <div className="form-row"><div className="field"><label>Platform</label><select name="platform"><option value="youtube">YouTube Shorts</option><option value="instagram">Instagram Reels</option><option value="tiktok">TikTok</option><option value="linkedin">LinkedIn</option></select></div><div className="field"><label>Date and time</label><input name="scheduled_for" type="datetime-local" min={localInputMin()} required/></div></div>
        <div className="field"><label>Post caption</label><textarea name="caption" placeholder="Write the value of this clip…" required/></div>
        <div className="field"><label>Hashtags</label><input name="hashtags" placeholder="#shorts #creator"/></div>
        {!exports.length && <div className="form-error">Finish an export before scheduling it.</div>}
        {error && <div className="form-error">{error}</div>}
        <button className="primary-btn" disabled={!exports.length}>Add to calendar</button>
      </form></div>}

      <div className="calendar-head"><div><button type="button" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft/></button><h2>{month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</h2><button type="button" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight/></button></div><button className="secondary-btn small" type="button" onClick={() => setMonth(firstDayOfMonth())}>Today</button></div>

      {loading ? <div className="screen-loader inline" role="status"><Loader2 className="spin" size={24}/><p>Loading your calendar…</p></div> : error && !show ? (
        <div className="empty-state"><div className="empty-icon"><AlertCircle/></div><h3>Calendar unavailable</h3><p>{error}</p><button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button></div>
      ) : <div className="calendar-grid">
        <div>MON</div><div>TUE</div><div>WED</div><div>THU</div><div>FRI</div><div>SAT</div><div>SUN</div>
        {cells.map((cell, index) => <section className={cell.outside ? "outside" : ""} key={index}><span>{cell.day}</span>{posts.filter((post) => { const date = new Date(post.scheduled_for); return date.getFullYear() === cell.date.getFullYear() && date.getMonth() === cell.date.getMonth() && date.getDate() === cell.date.getDate(); }).map((post) => <article className={`cal-post ${post.platform}`} key={post.id}>{post.platform === "instagram" ? <Instagram size={12}/> : <Clock3 size={12}/>}<b>{post.caption.slice(0, 22)}</b><small>{new Date(post.scheduled_for).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small><button type="button" className="cal-delete" disabled={busyDelete === post.id} onClick={() => void remove(post.id)} aria-label="Remove calendar draft">{busyDelete === post.id ? <Loader2 className="spin" size={10}/> : <Trash2 size={10}/>}</button></article>)}</section>)}
      </div>}
      <div className="calendar-note"><CalendarDays/><div><b>Publishing connections stay opt-in</b><p>Calendar items are drafts until you connect and authorize an owned social account.</p></div></div>
    </AppShell>
  );
}
