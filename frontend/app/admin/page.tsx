"use client";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import { AlertCircle, Activity, CheckCircle2, Clock3, RefreshCw, ServerCog, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type CountRow = { status: string; kind?: string; count: number };
type RecentJob = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  stage: string;
  message: string;
  error?: string | null;
  project_id?: string | null;
  export_id?: string | null;
  project_title?: string | null;
  clip_title?: string | null;
  user_email?: string | null;
  updated_at: string;
  age_seconds?: number | null;
  stale?: boolean;
};
type AdminOverview = {
  users: number;
  projects: number;
  exports: number;
  jobs: CountRow[];
  jobs_by_kind: CountRow[];
  recent_jobs: RecentJob[];
  stale_after_seconds: number;
  worker?: { status?: string; heartbeat_at?: string; last_error_code?: string; capabilities?: Record<string, unknown> } | null;
};

function ageLabel(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return "unknown";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 size={15}/>;
  if (status === "failed") return <XCircle size={15}/>;
  if (status === "queued") return <Clock3 size={15}/>;
  return <Activity size={15}/>;
}

export default function AdminQueuePage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setOverview(await api<AdminOverview>("/admin/overview"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Admin queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return <AppShell title="Admin queue" subtitle="Internal visibility for failed, stale, and recently completed media jobs." action={<button className="secondary-btn small" type="button" onClick={() => void load()}><RefreshCw size={14}/>Refresh</button>}>
    {loading ? (
      <div className="screen-loader inline" role="status"><RefreshCw className="spin" size={24}/><p>Loading queue health…</p></div>
    ) : error ? (
      <div className="empty-state">
        <div className="empty-icon"><AlertCircle size={24}/></div>
        <h3>Admin queue unavailable</h3>
        <p>{error}</p>
        <button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15}/>Retry</button>
      </div>
    ) : overview && (
      <>
        <div className="stat-grid">
          <div className="stat-card"><div><span>Users</span><b>{overview.users}</b></div><ServerCog size={18}/></div>
          <div className="stat-card"><div><span>Projects</span><b>{overview.projects}</b></div><Activity size={18}/></div>
          <div className="stat-card"><div><span>Ready exports</span><b>{overview.exports}</b></div><CheckCircle2 size={18}/></div>
          <div className="stat-card"><div><span>Stale after</span><b>{Math.round(overview.stale_after_seconds / 60)}m</b></div><Clock3 size={18}/></div>
        </div>

        <div className="panel" style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0 }}>Worker</h3>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            Status: <b>{overview.worker?.status || "unknown"}</b>
            {overview.worker?.heartbeat_at ? ` · heartbeat ${new Date(overview.worker.heartbeat_at).toLocaleString()}` : ""}
            {overview.worker?.last_error_code ? ` · last error ${overview.worker.last_error_code}` : ""}
          </p>
        </div>

        <div className="panel" style={{ marginTop: 16, overflow: "auto" }}>
          <h3 style={{ marginTop: 0 }}>Recent media jobs</h3>
          <table className="admin-job-table">
            <thead><tr><th>Status</th><th>Job</th><th>Owner</th><th>Progress</th><th>Last update</th><th>Message</th></tr></thead>
            <tbody>
              {overview.recent_jobs.map((job) => (
                <tr key={job.id} className={job.stale ? "stale" : ""}>
                  <td><span className={job.status === "failed" || job.stale ? "failed-pill" : "ready-pill"}><StatusIcon status={job.status}/>{job.stale ? "stale" : job.status}</span></td>
                  <td><b>{job.kind}</b><small>{job.project_title || job.clip_title || job.id}</small></td>
                  <td>{job.user_email || "unknown"}</td>
                  <td>{job.progress || 0}% · {job.stage}</td>
                  <td>{ageLabel(job.age_seconds)} ago</td>
                  <td>{job.error || job.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    )}
  </AppShell>;
}
