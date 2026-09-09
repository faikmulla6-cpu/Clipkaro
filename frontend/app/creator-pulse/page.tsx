"use client";

import { AppShell } from "@/components/AppShell";
import { api, postJSON } from "@/lib/api";
import {
  Activity,
  ArrowUpRight,
  BadgeIndianRupee,
  BarChart3,
  CheckCircle2,
  Clock3,
  Eye,
  Heart,
  Loader2,
  MessageCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  WalletCards,
  Youtube,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import styles from "./pulse.module.css";

type PulseVideo = {
  id: string;
  title: string;
  published_at: string;
  thumbnail_url?: string | null;
  views: number;
  likes?: number | null;
  comments?: number | null;
  age_days: number;
  views_per_day: number;
  engagement_rate?: number | null;
  vs_recent_average_pct: number;
};

type PulseDelta = {
  available: boolean;
  previous_captured_at?: string | null;
  subscriber_change?: number | null;
  view_change?: number | null;
  video_count_change?: number | null;
};

type PulseInsight = {
  key: string;
  label: string;
  title: string;
  detail: string;
  tone: "positive" | "neutral" | "watch";
};

type PulseReport = {
  id: string;
  request_key: string;
  captured_at: string;
  charged_paise: number;
  channel: {
    id: string;
    handle: string;
    title: string;
    description?: string | null;
    thumbnail_url?: string | null;
    subscribers?: number | null;
    hidden_subscriber_count: boolean;
    total_views: number;
    video_count: number;
  };
  recent: {
    average_views: number;
    average_engagement_rate?: number | null;
    upload_cadence_days?: number | null;
    videos: PulseVideo[];
  };
  delta: PulseDelta;
  insights: PulseInsight[];
  balance_paise: number;
};

type PulseHistoryItem = {
  id: string;
  channel_title: string;
  handle: string;
  captured_at: string;
  total_views: number;
  subscribers?: number | null;
};

type PulseStatus = {
  balance_paise: number;
  price_paise: number;
  topup_options_rupees: number[];
  youtube_configured: boolean;
  recent_scans: PulseHistoryItem[];
};

type PulseCheckout = {
  key_id: string;
  order_id: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  prefill: { name: string; email: string };
};

type RazorpayResult = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

const RAZORPAY_SRC = "https://checkout.razorpay.com/v1/checkout.js";
let razorpayPromise: Promise<void> | null = null;

function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  if (razorpayPromise) return razorpayPromise;
  razorpayPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${RAZORPAY_SRC}"]`);
    const timeout = window.setTimeout(() => reject(new Error("Razorpay Checkout took too long to load.")), 12_000);
    const done = () => { window.clearTimeout(timeout); window.Razorpay ? resolve() : reject(new Error("Razorpay Checkout is unavailable.")); };
    if (existing) {
      existing.addEventListener("load", done, { once: true });
      existing.addEventListener("error", () => reject(new Error("Razorpay Checkout could not load.")), { once: true });
      window.setTimeout(() => window.Razorpay && done(), 0);
      return;
    }
    const script = document.createElement("script");
    script.src = RAZORPAY_SRC;
    script.async = true;
    script.onload = done;
    script.onerror = () => reject(new Error("Razorpay Checkout could not load."));
    document.body.appendChild(script);
  }).catch((error) => {
    razorpayPromise = null;
    throw error;
  });
  return razorpayPromise;
}

function inrFromPaise(value: number) {
  return `₹${(Math.max(0, value) / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function compact(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function exact(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-IN");
}

function dateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

function signed(value?: number | null) {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toLocaleString("en-IN")}`;
}

function normalizeHandle(value: string) {
  const clean = value.trim();
  if (!clean) return "";
  const match = clean.match(/youtube\.com\/@([^/?#]+)/i);
  const raw = match?.[1] || clean.replace(/^@/, "").replace(/^https?:\/\//i, "");
  return raw ? `@${raw.trim()}` : "";
}

function InsightIcon({ tone }: { tone: PulseInsight["tone"] }) {
  if (tone === "positive") return <TrendingUp size={18} />;
  if (tone === "watch") return <TrendingDown size={18} />;
  return <Activity size={18} />;
}

export default function CreatorPulsePage() {
  const [status, setStatus] = useState<PulseStatus | null>(null);
  const [report, setReport] = useState<PulseReport | null>(null);
  const [handle, setHandle] = useState("");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [topupBusy, setTopupBusy] = useState(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadStatus = useCallback(async () => {
    const next = await api<PulseStatus>("/creator-pulse/status");
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    setLoading(true);
    loadStatus().catch((err: unknown) => setError(err instanceof Error ? err.message : "Creator Pulse could not be loaded."))
      .finally(() => setLoading(false));
  }, [loadStatus]);

  const canScan = Boolean(status?.youtube_configured && status.balance_paise >= (status.price_paise || 100) && normalizeHandle(handle));
  const pulsePrice = status?.price_paise ?? 100;
  const currentBalance = report?.balance_paise ?? status?.balance_paise ?? 0;

  const strongestVideo = useMemo(() => report?.recent.videos.reduce<PulseVideo | null>((best, item) => !best || item.views_per_day > best.views_per_day ? item : best, null) || null, [report]);
  const rankedVideos = useMemo(() => report ? [...report.recent.videos].sort((left, right) => right.views_per_day - left.views_per_day) : [], [report]);

  async function addBalance(rupees: number) {
    setTopupBusy(rupees);
    setError("");
    setNotice("");
    try {
      const checkout = await postJSON<PulseCheckout>("/creator-pulse/balance/checkout", { amount_rupees: rupees });
      await loadRazorpay();
      if (!window.Razorpay) throw new Error("Razorpay Checkout is unavailable in this browser.");
      const razorpay = new window.Razorpay({
        key: checkout.key_id,
        order_id: checkout.order_id,
        amount: checkout.amount,
        currency: checkout.currency,
        name: checkout.name,
        description: checkout.description,
        prefill: checkout.prefill,
        theme: { color: "#165f43" },
        modal: { ondismiss: () => setTopupBusy(0) },
        handler: async (result: RazorpayResult) => {
          try {
            const verified = await postJSON<{ verified: boolean; credited_paise: number; balance_paise: number }>("/creator-pulse/balance/verify", result);
            if (!verified.verified) throw new Error("Payment could not be verified.");
            setNotice(`${inrFromPaise(verified.credited_paise)} added to your Pulse Balance. No subscription was created.`);
            await loadStatus();
          } catch (err) {
            setError(err instanceof Error ? err.message : "Payment was received but could not be verified.");
          } finally {
            setTopupBusy(0);
          }
        },
      });
      razorpay.on?.("payment.failed", (response) => setError(response.error?.description || "Payment failed. You can retry securely in Razorpay Checkout."));
      razorpay.open();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start secure balance top-up.");
      setTopupBusy(0);
    }
  }

  async function runPulse() {
    const normalized = normalizeHandle(handle);
    if (!normalized) {
      setError("Enter a YouTube @handle or channel URL.");
      return;
    }
    setScanning(true);
    setError("");
    setNotice("");
    try {
      const result = await postJSON<PulseReport>("/creator-pulse/analyse", {
        handle: normalized,
        request_key: crypto.randomUUID(),
      });
      setReport(result);
      setHandle(result.channel.handle || normalized);
      setStatus((current) => current ? { ...current, balance_paise: result.balance_paise } : current);
      setNotice(`Pulse verified and saved. ${inrFromPaise(result.charged_paise)} was deducted only for this successful analysis.`);
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Creator Pulse could not complete this analysis.");
      await loadStatus().catch(() => undefined);
    } finally {
      setScanning(false);
    }
  }

  if (loading) {
    return <AppShell title="Creator Pulse" subtitle="Daily YouTube channel intelligence — ₹1 per successful Pulse.">
      <div className="screen-loader inline"><Loader2 className="spin" size={24}/><p>Opening Creator Pulse…</p></div>
    </AppShell>;
  }

  return <AppShell title="Creator Pulse" subtitle="Daily YouTube channel intelligence — ₹1 per successful Pulse.">
    <div className={styles.page}>
      {error && <div className="error-banner"><span>{error}</span></div>}
      {notice && <div className="success-banner"><span>{notice}</span></div>}

      <section className={styles.hero}>
        <div className={styles.heroGlow}/>
        <div className={styles.heroMain}>
          <div className={styles.eyebrow}><ShieldCheck size={14}/> Official YouTube public data · no guessed metrics</div>
          <h2>Your channel. <span>One clear Pulse.</span></h2>
          <p>See what is moving, what is slowing down, and how your latest uploads compare — for exactly ₹1 per verified analysis.</p>
          <div className={styles.searchBox}>
            <Youtube size={21}/>
            <input value={handle} onChange={(event) => setHandle(event.target.value)} onKeyDown={(event) => event.key === "Enter" && canScan && void runPulse()} placeholder="@yourchannel or youtube.com/@yourchannel" aria-label="YouTube channel handle"/>
            <button className="primary-btn" disabled={!canScan || scanning} onClick={() => void runPulse()}>
              {scanning ? <Loader2 className="spin" size={16}/> : <Activity size={16}/>} {scanning ? "Reading channel…" : "Run Pulse · ₹1"}
            </button>
          </div>
          <div className={styles.trustLine}>
            <span><CheckCircle2 size={14}/> ₹1 deducted only after a successful stored Pulse</span>
            <span><CheckCircle2 size={14}/> No subscription or auto-renewal</span>
            <span><CheckCircle2 size={14}/> Public YouTube data only</span>
          </div>
        </div>
        <aside className={styles.balanceCard}>
          <div className={styles.balanceTop}><span>Pulse Balance</span><WalletCards size={19}/></div>
          <strong>{inrFromPaise(currentBalance)}</strong>
          <p>{Math.floor(currentBalance / Math.max(1, pulsePrice))} Pulse{Math.floor(currentBalance / Math.max(1, pulsePrice)) === 1 ? "" : "s"} available</p>
          <div className={styles.balanceRule}><BadgeIndianRupee size={15}/><span><b>₹1</b> per successful analysis</span></div>
          <div className={styles.topups}>
            {(status?.topup_options_rupees || [10, 20, 50]).map((amount) => <button key={amount} disabled={!!topupBusy} onClick={() => void addBalance(amount)}>
              {topupBusy === amount ? <Loader2 className="spin" size={13}/> : `+₹${amount}`}
            </button>)}
          </div>
          <small>Secure one-time top-up via Razorpay. Balance does not auto-renew.</small>
        </aside>
      </section>

      {!status?.youtube_configured && <section className={styles.blocked}>
        <ShieldCheck size={22}/><div><b>Creator Pulse is not connected yet</b><p>The YouTube API key is not configured on the backend. The feature stays fail-closed instead of showing sample data.</p></div>
      </section>}

      {!report ? <div className={styles.preReportGrid}>
        <section className={styles.emptyPanel}>
          <div className={styles.emptyIcon}><BarChart3 size={26}/></div>
          <span className={styles.kicker}>YOUR FIRST PULSE</span>
          <h3>Real channel intelligence starts with a handle.</h3>
          <p>Creator Pulse reads the current channel and latest uploads, stores a time-stamped snapshot, and compares future Pulses against your own previous verified snapshot.</p>
          <div className={styles.previewRows}>
            <div><Eye size={17}/><span>Current channel + recent video views</span><b>Verified</b></div>
            <div><Heart size={17}/><span>Likes, comments and engagement rate</span><b>Calculated</b></div>
            <div><TrendingUp size={17}/><span>Growth since your previous Pulse</span><b>Stored history</b></div>
          </div>
        </section>
        <section className={styles.historyPanel}>
          <div className={styles.sectionHead}><div><span>Recent Pulses</span><h3>Your saved channel checks</h3></div><RefreshCw size={17}/></div>
          {status?.recent_scans?.length ? <div className={styles.historyList}>{status.recent_scans.map((item) => <div key={item.id}>
            <div><b>{item.channel_title}</b><span>{item.handle} · {dateTime(item.captured_at)}</span></div>
            <strong>{compact(item.total_views)} views</strong>
          </div>)}</div> : <div className={styles.historyEmpty}>No Pulse history yet. We will never invent activity to fill this space.</div>}
        </section>
      </div> : <>
        <section className={styles.channelHeader}>
          <div className={styles.channelIdentity}>
            {report.channel.thumbnail_url ? <Image src={report.channel.thumbnail_url} alt="" width={64} height={64} className={styles.avatar}/> : <div className={styles.avatarFallback}><Youtube size={24}/></div>}
            <div><span>VERIFIED CHANNEL SNAPSHOT</span><h2>{report.channel.title}</h2><p>{report.channel.handle} · captured {dateTime(report.captured_at)}</p></div>
          </div>
          <a className={styles.youtubeLink} href={`https://youtube.com/${report.channel.handle}`} target="_blank" rel="noreferrer">Open on YouTube <ArrowUpRight size={14}/></a>
        </section>

        <div className={styles.statGrid}>
          <article><span>Subscribers</span><strong>{report.channel.hidden_subscriber_count ? "Hidden" : compact(report.channel.subscribers)}</strong><small>{report.delta.available ? `${signed(report.delta.subscriber_change)} since last Pulse` : "First saved snapshot"}</small></article>
          <article><span>Total channel views</span><strong>{compact(report.channel.total_views)}</strong><small>{report.delta.available ? `${signed(report.delta.view_change)} since last Pulse` : exact(report.channel.total_views)}</small></article>
          <article><span>Videos published</span><strong>{exact(report.channel.video_count)}</strong><small>{report.delta.available ? `${signed(report.delta.video_count_change)} since last Pulse` : "Current public total"}</small></article>
          <article><span>Recent average views</span><strong>{compact(report.recent.average_views)}</strong><small>Across latest {report.recent.videos.length} uploads</small></article>
        </div>

        {report.delta.available && <section className={styles.deltaStrip}>
          <div><Clock3 size={18}/><span>Compared with</span><b>{dateTime(report.delta.previous_captured_at)}</b></div>
          <div><span>Views</span><b>{signed(report.delta.view_change)}</b></div>
          <div><span>Subscribers</span><b>{report.channel.hidden_subscriber_count ? "Hidden" : signed(report.delta.subscriber_change)}</b></div>
          <div><span>Uploads</span><b>{signed(report.delta.video_count_change)}</b></div>
        </section>}

        <div className={styles.reportGrid}>
          <section className={styles.performancePanel}>
            <div className={styles.sectionHead}><div><span>RECENT PERFORMANCE</span><h3>Latest uploads, ranked by real momentum</h3></div><div className={styles.methodPill}>No AI guesswork</div></div>
            <div className={styles.videoList}>
              {rankedVideos.map((video, index) => <article key={video.id}>
                <span className={styles.rank}>{String(index + 1).padStart(2, "0")}</span>
                <div className={styles.videoThumb}>{video.thumbnail_url ? <Image src={video.thumbnail_url} alt="" fill sizes="112px"/> : <Youtube size={20}/>}</div>
                <div className={styles.videoCopy}><b>{video.title}</b><span>{dateTime(video.published_at)} · {video.age_days.toFixed(1)} days old</span></div>
                <div className={styles.videoMetric}><span>Views</span><b>{compact(video.views)}</b></div>
                <div className={styles.videoMetric}><span>Views/day</span><b>{compact(video.views_per_day)}</b></div>
                <div className={styles.videoMetric}><span>Engagement</span><b>{video.engagement_rate === null || video.engagement_rate === undefined ? "—" : `${video.engagement_rate.toFixed(2)}%`}</b></div>
              </article>)}
            </div>
          </section>

          <aside className={styles.signalsPanel}>
            <div className={styles.sectionHead}><div><span>PULSE SIGNALS</span><h3>What deserves attention</h3></div><Sparkles size={17}/></div>
            <div className={styles.insightList}>{report.insights.map((insight) => <article key={insight.key} data-tone={insight.tone}>
              <div className={styles.insightIcon}><InsightIcon tone={insight.tone}/></div><div><span>{insight.label}</span><b>{insight.title}</b><p>{insight.detail}</p></div>
            </article>)}</div>
            {strongestVideo && <div className={styles.formulaNote}><ShieldCheck size={16}/><p><b>Transparent method.</b> Momentum uses public view count divided by upload age. Engagement uses public likes + comments divided by views. Missing YouTube metrics stay blank — never estimated.</p></div>}
          </aside>
        </div>
      </>}

      <section className={styles.trustFooter}>
        <div><ShieldCheck size={19}/><p><b>Truth-first by design.</b> Creator Pulse stores the exact timestamp and public counters returned by YouTube. “Since last Pulse” means since your previous stored scan, not a claimed 24-hour change unless the timestamps actually support it.</p></div>
        <Link href="/privacy">Privacy Notice</Link>
      </section>
    </div>
  </AppShell>;
}
