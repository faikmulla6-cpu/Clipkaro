"use client";

import { AppShell } from "@/components/AppShell";
import { api, Usage } from "@/lib/api";
import {
  AlertCircle,
  Clock3,
  Download,
  Loader2,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Video,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type AnalyticsData = {
  summary: {
    projects: number;
    clips: number;
    avg_score: number;
    exports: number;
    minutes_processed: number;
  };
  usage: Usage;
  categories: { category: string; count: number }[];
  activity: { day: string; exports: number }[];
};

type ExportHistory = {
  id: string;
  status: string;
  created_at?: string | null;
};

function dayLabel(day: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  return match ? `${match[3]}/${match[2]}` : day;
}

function historicalExportActivity(exports: ExportHistory[]) {
  const completed = exports.filter((item) => item.status === "ready" || item.status === "expired");
  const byDay = new Map<string, number>();
  for (const item of completed) {
    const day = String(item.created_at || "").slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(day)) byDay.set(day, (byDay.get(day) || 0) + 1);
  }
  const activity = [...byDay.entries()]
    .sort(([left], [right]) => right.localeCompare(left))
    .slice(0, 14)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([day, count]) => ({ day, exports: count }));
  return { completedCount: completed.length, activity };
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [result, exports] = await Promise.all([
        api<AnalyticsData>("/analytics"),
        api<ExportHistory[]>("/exports"),
      ]);
      const history = historicalExportActivity(exports);
      setData({
        ...result,
        summary: { ...result.summary, exports: history.completedCount },
        activity: history.activity,
      });
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : "Analytics could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAnalytics();
  }, [loadAnalytics]);

  if (loading) {
    return (
      <AppShell title="Analytics" subtitle="Understand output, quality and cost—not vanity metrics.">
        <div className="screen-loader inline" role="status">
          <Loader2 className="spin" size={24} />
          <p>Loading your real activity…</p>
        </div>
      </AppShell>
    );
  }

  if (error || !data) {
    return (
      <AppShell title="Analytics" subtitle="Understand output, quality and cost—not vanity metrics.">
        <div className="empty-state">
          <div className="empty-icon"><AlertCircle size={24} /></div>
          <h3>Analytics unavailable</h3>
          <p>{error || "ClipKaro could not load your analytics. Your account data has not been replaced with sample activity."}</p>
          <button className="primary-btn" type="button" onClick={() => void loadAnalytics()}>
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      </AppShell>
    );
  }

  const s = data.summary;
  const hasActivity = data.activity.some((item) => item.exports > 0);
  const maxExports = Math.max(1, ...data.activity.map((item) => item.exports));
  const exportsPerMoment = s.clips ? (s.exports / s.clips).toFixed(1) : "0.0";

  return (
    <AppShell title="Analytics" subtitle="Understand output, quality and cost—not vanity metrics.">
      <div className="stat-grid">
        {[
          [Video, "Projects", s.projects, "All-time"],
          [Sparkles, "Average potential", s.avg_score, "Across AI moments"],
          [Download, "Historical exports", s.exports, "Includes expired downloads"],
          [Clock3, "Minutes processed", s.minutes_processed, "Source content"],
        ].map(([Icon, label, value, note]: any) => (
          <div className="stat-card" key={label}>
            <div className="stat-card-top">
              <span>{label}</span>
              <span className="stat-icon"><Icon size={16} /></span>
            </div>
            <b className="stat-value">{value}</b>
            <span className="trend">{note}</span>
          </div>
        ))}
      </div>

      <div className="analytics-grid">
        <div className="panel">
          <div className="panel-head">
            <h3>Publishing output</h3>
            <span className="trend">Completed export history</span>
          </div>

          {hasActivity ? (
            <div className="chart modern" aria-label="Completed export history">
              {data.activity.map((item) => {
                const height = item.exports === 0 ? 0 : Math.max(8, Math.round((item.exports / maxExports) * 100));
                return (
                  <div className="bar-group" key={item.day} title={`${item.day}: ${item.exports} export${item.exports === 1 ? "" : "s"}`}>
                    <span
                      className="bar"
                      style={{ height: `${height}%` }}
                      aria-label={`${item.exports} completed export${item.exports === 1 ? "" : "s"} on ${item.day}`}
                    />
                    <span className="bar-label">{dayLabel(item.day)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state" style={{ border: 0, background: "transparent", padding: "46px 20px" }}>
              <div className="empty-icon"><Download size={24} /></div>
              <h3>No completed exports yet</h3>
              <p>Your publishing history will appear here after your first completed Short export. Expired download files still remain part of historical export analytics.</p>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Plan efficiency</h3></div>
          <div className="metric-list">
            <div><span>Source minutes this plan period</span><b>{data.usage.source_minutes}</b></div>
            <div><span>Exports used this plan period</span><b>{data.usage.exports_used}/{data.usage.exports_limit}</b></div>
            <div><span>Historical exports per moment</span><b>{exportsPerMoment}×</b></div>
          </div>
          <div className="insight">
            <TrendingUp size={18} />
            <p>Plan-period usage resets with billing rules; historical completed exports remain visible separately above.</p>
          </div>
        </div>
      </div>

      <div className="analytics-grid">
        <div className="panel">
          <div className="panel-head"><h3>Content mix</h3></div>
          <div className="category-list">
            {data.categories.length ? data.categories.map((item, index) => (
              <div key={item.category}>
                <span className={`category-dot c${index}`} />
                <b>{item.category}</b>
                <i><span style={{ width: `${Math.max(18, item.count * 20)}%` }} /></i>
                <strong>{item.count}</strong>
              </div>
            )) : <p className="muted-copy">Upload projects to see your content mix.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Quality benchmark</h3></div>
          <div className="quality-gauge">
            <div style={{ "--gauge": `${s.avg_score * 1.8}deg` } as React.CSSProperties}>
              <b>{s.avg_score}</b><span>potential</span>
            </div>
            <p>Strong clips score well across hook, clarity, emotional pull, viewer value, and flow.</p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
