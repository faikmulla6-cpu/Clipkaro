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

function dayLabel(day: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  return match ? `${match[3]}/${match[2]}` : day;
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api<AnalyticsData>("/analytics");
      setData(result);
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

  return (
    <AppShell title="Analytics" subtitle="Understand output, quality and cost—not vanity metrics.">
      <div className="stat-grid">
        {[
          [Video, "Projects", s.projects, "All-time"],
          [Sparkles, "Average potential", s.avg_score, "Across AI moments"],
          [Download, "Exports", s.exports, `${data.usage.exports_remaining} remaining`],
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
            <span className="trend">Completed exports only</span>
          </div>

          {hasActivity ? (
            <div className="chart modern" aria-label="Completed export activity">
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
              <h3>{s.exports === 0 ? "No exports yet" : "No recent exports"}</h3>
              <p>
                {s.exports === 0
                  ? "Your publishing activity will appear here after your first completed Short export."
                  : "You have completed exports in your history, but there is no activity in the recent export-day series."}
              </p>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head"><h3>Plan efficiency</h3></div>
          <div className="metric-list">
            <div><span>Source minutes</span><b>{data.usage.source_minutes}</b></div>
            <div><span>Exports used</span><b>{data.usage.exports_used}/{data.usage.exports_limit}</b></div>
            <div><span>Moment-to-export</span><b>{s.clips ? Math.round((s.exports / s.clips) * 100) : 0}%</b></div>
          </div>
          <div className="insight">
            <TrendingUp size={18} />
            <p>Render only selected moments. That cost-control rule is active across your workspace.</p>
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
