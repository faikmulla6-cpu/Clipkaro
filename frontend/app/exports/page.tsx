"use client";

import { AppShell } from "@/components/AppShell";
import { API_URL, api } from "@/lib/api";
import { AlertCircle, CheckCircle2, Clock3, Download, FileVideo, Loader2, RefreshCw, XCircle } from "lucide-react";
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

export default function Exports() {
  const [rows, setRows] = useState<ExportRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  return (
    <AppShell title="Exports" subtitle="Your rendered Shorts and private downloads in one place.">
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
                  {item.error && <div style={{ marginTop: 5, color: "var(--red)", fontSize: 11 }}>{item.error}</div>}
                </div>
                <div className="export-history-action">
                  {ready ? (
                    <a className="primary-btn small" href={`${API_URL}/exports/${item.id}/download`}>
                      <Download size={15} />Download MP4
                    </a>
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
