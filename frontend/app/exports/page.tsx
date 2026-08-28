"use client";

import { AppShell } from "@/components/AppShell";
import { API_URL, api } from "@/lib/api";
import { recordDownload } from "@/lib/behavior";
import { AlertCircle, CheckCircle2, Clock3, Download, FileVideo, Loader2, RefreshCw, XCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type ExportRow = {
  id: string;
  clip_id: string;
  status: string;
  progress: number;
  title?: string;
  hook?: string;
  project_title?: string;
  resolution?: string;
  aspect_ratio?: string;
  created_at: string;
  expires_at?: string;
  error?: string | null;
  job_id?: string | null;
  job_status?: string | null;
  job_stage?: string | null;
  job_message?: string | null;
  job_updated_at?: string | null;
  job_age_seconds?: number | null;
  attention_needed?: boolean;
};

type ExportStatus = {
  id: string;
  status: string;
  progress: number;
  download_url?: string | null;
  expires_at: string;
};

function createdLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function statusIcon(status: string) {
  if (status === "ready") return <CheckCircle2 size={16} />;
  if (status === "failed") return <XCircle size={16} />;
  if (status === "expired") return <Clock3 size={16} />;
  return <Loader2 className="spin" size={16} />;
}

function jobAgeLabel(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 90) return "updated just now";
  const minutes = Math.floor(seconds / 60);
  return `last update ${minutes} min ago`;
}

export default function Exports() {
  const [rows, setRows] = useState<ExportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloadNotice, setDownloadNotice] = useState("");
  const [downloadingId, setDownloadingId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api<ExportRow[]>("/exports");
      setRows(Array.isArray(result) ? result : []);
    } catch (cause) {
      setRows([]);
      setError(cause instanceof Error ? cause.message : "Exports could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function downloadExport(exportId: string) {
    if (!exportId || downloadingId) return;
    setDownloadingId(exportId);
    setDownloadNotice("");
    try {
      // Re-check the authoritative status immediately before navigation. This
      // keeps an expired/still-finishing export inside ClipKaro instead of
      // exposing a raw API error page to the creator.
      const state = await api<ExportStatus>(`/exports/${exportId}`);
      if (state.status !== "ready" || !state.download_url) {
        setRows(current => current.map(row => row.id === exportId ? { ...row, status: state.status, progress: state.progress } : row));
        setDownloadNotice(state.status === "expired"
          ? "This private download has expired. Your export history is still preserved."
          : "This Short is still finishing securely. Try Download again in a moment.");
        return;
      }
      recordDownload(exportId);
      window.location.assign(`${API_URL}/exports/${exportId}/download`);
    } catch (cause) {
      setDownloadNotice(cause instanceof Error ? cause.message : "The download could not be prepared yet.");
    } finally {
      setDownloadingId("");
    }
  }

  return (
    <AppShell title="Exports" subtitle="Your rendered Shorts and private downloads in one place.">
      {downloadNotice && <div className="floating-error">{downloadNotice}</div>}
      {loading ? (
        <div className="screen-loader inline" role="status">
          <Loader2 className="spin" size={24} />
          <p>Loading your exports…</p>
        </div>
      ) : error ? (
        <div className="empty-state">
          <div className="empty-icon"><AlertCircle size={24} /></div>
          <h3>Exports unavailable</h3>
          <p>{error}</p>
          <button className="primary-btn" type="button" onClick={() => void load()}><RefreshCw size={15} />Retry</button>
        </div>
      ) : rows.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><FileVideo size={24} /></div>
          <h3>No exports yet</h3>
          <p>Finished Shorts will appear here after you render a selected AI moment.</p>
        </div>
      ) : (
        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          {rows.map((item, index) => {
            const ready = item.status === "ready";
            const preparing = downloadingId === item.id;
            const pending = item.status === "queued" || item.status === "processing";
            return (
              <div
                className="export-history-row"
                key={item.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "46px minmax(0,1fr) auto",
                  gap: 14,
                  alignItems: "center",
                  padding: "18px 20px",
                  borderTop: index ? "1px solid var(--line)" : "0",
                  background: "#fff",
                }}
              >
                <div className="stat-icon" style={{ width: 42, height: 42, borderRadius: 12, display: "grid", placeItems: "center", background: "#edf7e8", color: "var(--green)" }}>
                  <FileVideo size={18} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <b className="export-history-title" style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "100%" }}>{item.title || "ClipKaro Short"}</b>
                    <span className={ready ? "ready-pill" : item.status === "failed" ? "failed-pill" : "ready-pill"} style={!ready && item.status !== "failed" ? { color: "#6f746f", background: "#f1f3f0" } : undefined}>
                      {statusIcon(item.status)}{item.status === "ready" ? "Ready" : item.status === "expired" ? "Expired" : item.status === "failed" ? "Failed" : `${item.progress || 0}%`}
                    </span>
                  </div>
                  <div className="export-history-meta" style={{ marginTop: 5, color: "var(--muted)", fontSize: 11 }}>
                    {item.project_title || "Project"} · {item.resolution || "720p"} · {item.aspect_ratio || "9:16"} · {createdLabel(item.created_at)}
                  </div>
                  {item.job_message && pending && <div style={{ marginTop: 5, color: item.attention_needed ? "var(--red)" : "var(--muted)", fontSize: 11 }}>
                    {item.attention_needed ? "Taking longer than usual: " : ""}{item.job_message}{item.job_age_seconds ? ` · ${jobAgeLabel(item.job_age_seconds)}` : ""}
                  </div>}
                  {item.error && <div style={{ marginTop: 5, color: "var(--red)", fontSize: 11 }}>{item.error}</div>}
                </div>
                <div className="export-history-action">
                  {ready ? (
                    <button className="primary-btn small" type="button" disabled={preparing} onClick={() => void downloadExport(item.id)}>
                      {preparing ? <Loader2 className="spin" size={15} /> : <Download size={15} />}{preparing ? "Preparing…" : "Download MP4"}
                    </button>
                  ) : item.status === "failed" ? (
                    <Link className="primary-btn small" href={`/editor/${item.clip_id}`}>
                      <RefreshCw size={14} />Retry export
                    </Link>
                  ) : pending ? (
                    <button className="secondary-btn small" type="button" onClick={() => void load()}>
                      <RefreshCw size={14} />{item.attention_needed ? "Refresh status" : "Still rendering"}
                    </button>
                  ) : (
                    <button className="secondary-btn small" type="button" disabled style={{ opacity: .55 }}>
                      <Clock3 size={14} />{item.status === "expired" ? "Expired" : "Unavailable"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
