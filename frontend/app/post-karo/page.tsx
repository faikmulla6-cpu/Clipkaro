"use client";

import { AppShell } from "@/components/AppShell";
import { API_URL, api, deleteJSON, patchJSON, postJSON } from "@/lib/api";
import { downloadExport } from "@/lib/behavior";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowRight, CalendarClock, Check, CheckCircle2, Download, ExternalLink, FileVideo,
  History, Instagram, KeyRound, Loader2, LockKeyhole, RefreshCw, Send, ShieldCheck,
  Sparkles, Unplug, Youtube,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import styles from "./post-karo.module.css";

type Platform = "instagram" | "youtube";
type SocialAccount = {
  platform: Platform; username: string; display_name: string; connected: boolean;
  status: string; last_synced_at?: string | null;
};
type PostKaroStatus = {
  plan_eligible: boolean; required_plan: string; connection_active: boolean;
  api_key_masked?: string | null; profile_ready: boolean; accounts: SocialAccount[];
  ready: boolean; setup_step: number;
};
type ExportRow = {
  id: string; clip_id: string; status: string; title?: string; project_title?: string;
  resolution?: string; aspect_ratio?: string; created_at: string; expires_at?: string;
};
type Draft = {
  id: string; export_id: string; revision: number;
  instagram_enabled: boolean; instagram_caption: string; instagram_hashtags: string[];
  youtube_enabled: boolean; youtube_title: string; youtube_description: string;
  youtube_tags: string[]; youtube_visibility: "public" | "unlisted" | "private";
  scheduled_for?: string | null; timezone: string; updated_at?: string;
  export?: {
    id: string; clip_id: string; title: string; project_title: string;
    download_url: string; expires_at?: string; resolution?: string; aspect_ratio?: string;
  };
};
type PlatformResult = {
  platform?: string; status?: string; platformPostUrl?: string; url?: string;
  error?: string; message?: string;
};
type Publication = {
  id: string; export_id: string; draft_id: string; draft_revision: number;
  request_id: string; job_id?: string | null; mode: "now" | "schedule"; status: string;
  scheduled_for?: string | null; provider_post_id?: string | null;
  platform_results: PlatformResult[]; snapshot: Record<string, unknown>;
  error?: string | null; created_at?: string; updated_at?: string;
  job?: { progress?: number; stage?: string; message?: string; error?: string; status?: string } | null;
};
type DraftFields = {
  instagram_enabled: boolean; instagram_caption: string; instagram_hashtags: string[];
  youtube_enabled: boolean; youtube_title: string; youtube_description: string;
  youtube_tags: string[]; youtube_visibility: Draft["youtube_visibility"]; timezone: string;
};

const terminalStatuses = new Set(["scheduled", "published", "partial", "failed"]);
function fieldsOf(draft: Draft): DraftFields {
  return {
    instagram_enabled: draft.instagram_enabled,
    instagram_caption: draft.instagram_caption,
    instagram_hashtags: draft.instagram_hashtags,
    youtube_enabled: draft.youtube_enabled,
    youtube_title: draft.youtube_title,
    youtube_description: draft.youtube_description,
    youtube_tags: draft.youtube_tags,
    youtube_visibility: draft.youtube_visibility,
    timezone: draft.timezone,
  };
}
function signature(fields: DraftFields) { return JSON.stringify(fields); }
function parseTags(value: string) {
  return Array.from(new Set(value.split(/[\s,]+/).map(item => item.trim()).filter(Boolean))).slice(0, 30);
}
function accountFor(status: PostKaroStatus | null, platform: Platform) {
  return status?.accounts.find(item => item.platform === platform);
}
function accountLabel(account?: SocialAccount) {
  return account?.display_name || account?.username || "Connected account";
}
function platformIcon(platform: string, size = 20) {
  return platform === "instagram" ? <Instagram size={size}/> : <Youtube size={size}/>;
}
function SuccessOrb({ small = false }: { small?: boolean }) {
  return <motion.div
    className={small ? styles.successOrbSmall : styles.successOrb}
    initial={{ scale: .72, opacity: 0 }}
    animate={{ scale: 1, opacity: 1 }}
    transition={{ type: "spring", stiffness: 220, damping: 17 }}
  >
    <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: .18, type: "spring" }}>
      <Check size={small ? 18 : 42} strokeWidth={3}/>
    </motion.span>
    {!small && <><i/><i/><i/><i/></>}
  </motion.div>;
}
function PostKaroPageInner() {
  const search = useSearchParams();
  const returnExport = search.get("export") || "";
  const [status, setStatus] = useState<PostKaroStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [publications, setPublications] = useState<Publication[]>([]);
  const [tab, setTab] = useState<"publish" | "scheduled" | "history">("publish");
  const [draft, setDraft] = useState<Draft | null>(null);
  const draftRef = useRef<Draft | null>(null);
  const revisionRef = useRef(1);
  const lastSavedSignatureRef = useRef("");
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());
  const saveTimerRef = useRef<number | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [composerLoading, setComposerLoading] = useState(false);
  const [mode, setMode] = useState<"now" | "schedule">("now");
  const [scheduledFor, setScheduledFor] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publication, setPublication] = useState<Publication | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  useEffect(() => { draftRef.current = draft; }, [draft]);
  useEffect(() => () => {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
    if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
  }, []);
  const loadStatus = useCallback(async () => {
    setPageError("");
    try {
      const next = await api<PostKaroStatus>("/post-karo/status");
      setStatus(next);
      return next;
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Post Karo could not be loaded.");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { void loadStatus(); }, [loadStatus]);

  const loadWorkspace = useCallback(async () => {
    try {
      const all = await Promise.all([
        api<ExportRow[]>("/exports"),
        api<Publication[]>("/post-karo/publications"),
      ]);
      setExports((all[0] || []).filter(item => item.status === "ready"));
      setPublications(all[1] || []);
    } catch {
      // Setup remains usable if historical data is temporarily unavailable.
    }
  }, []);
  useEffect(() => { if (status?.ready) void loadWorkspace(); }, [status?.ready, loadWorkspace]);

  const loadDraft = useCallback(async (exportId: string) => {
    if (!exportId) return;
    setComposerLoading(true);
    setPageError("");
    try {
      const path = "/post-karo/drafts/from-export/" + encodeURIComponent(exportId);
      const prepared = await postJSON<Draft>(path, {});
      setDraft(prepared);
      draftRef.current = prepared;
      revisionRef.current = prepared.revision;
      lastSavedSignatureRef.current = signature(fieldsOf(prepared));
      setSaveState("saved");
      setPublication(null);
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Post Karo could not prepare this Short.");
    } finally {
      setComposerLoading(false);
    }
  }, []);
  useEffect(() => {
    if (status?.ready && returnExport) void loadDraft(returnExport);
  }, [status?.ready, returnExport, loadDraft]);
  async function testConnection() {
    if (!apiKey.trim() || testing) return;
    setTesting(true);
    setPageError("");
    try {
      await postJSON("/post-karo/connection/test", { api_key: apiKey.trim() });
      setApiKey("");
      await loadStatus();
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "This SIMPLE connection could not be verified.");
    } finally { setTesting(false); }
  }

  async function connectPlatform(platform: Platform) {
    if (connecting) return;
    setConnecting(platform);
    setPageError("");
    try {
      const suffix = returnExport ? "?return_export=" + encodeURIComponent(returnExport) : "";
      const target = "/post-karo/connect/" + platform + suffix;
      const result = await api<{ auth_url: string }>(target, { method: "POST" });
      window.location.assign(result.auth_url);
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Could not start the social connection.");
      setConnecting("");
    }
  }

  async function syncAccounts() {
    if (syncing) return;
    setSyncing(true);
    setPageError("");
    try {
      await postJSON("/post-karo/accounts/sync", {});
      await loadStatus();
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Could not refresh social connections.");
    } finally { setSyncing(false); }
  }

  async function disconnect() {
    const okay = window.confirm("Disconnect SIMPLE connection? Your finished Shorts and downloads stay untouched.");
    if (!okay) return;
    try {
      await deleteJSON("/post-karo/connection");
      setDraft(null);
      setPublications([]);
      await loadStatus();
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Post Karo could not be disconnected.");
    }
  }
  function updateDraft(patch: Partial<Draft>) {
    setDraft(current => current ? { ...current, ...patch } : current);
  }

  function enqueueSave(fields: DraftFields): Promise<Draft> {
    const active = draftRef.current;
    if (!active) return Promise.reject(new Error("Post Karo draft is not ready."));
    const draftId = active.id;
    const fieldSignature = signature(fields);
    let resolveTask: (value: Draft) => void = () => undefined;
    let rejectTask: (reason?: unknown) => void = () => undefined;
    const result = new Promise<Draft>((resolve, reject) => {
      resolveTask = resolve;
      rejectTask = reject;
    });
    saveChainRef.current = saveChainRef.current.catch(() => undefined).then(async () => {
      setSaveState("saving");
      try {
        const saved = await patchJSON<Draft>("/post-karo/drafts/" + draftId, {
          expected_revision: revisionRef.current,
          ...fields,
        });
        revisionRef.current = saved.revision;
        lastSavedSignatureRef.current = fieldSignature;
        setDraft(current => current && current.id === draftId
          ? { ...current, revision: saved.revision, updated_at: saved.updated_at }
          : current);
        setSaveState("saved");
        resolveTask(saved);
      } catch (cause) {
        setSaveState("error");
        rejectTask(cause);
      }
    });
    return result;
  }

  useEffect(() => {
    if (!draft) return;
    const fields = fieldsOf(draft);
    const nextSignature = signature(fields);
    if (nextSignature === lastSavedSignatureRef.current) return;
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(() => {
      saveTimerRef.current = null;
      void enqueueSave(fields).catch(() => undefined);
    }, 700);
    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
    };
  }, [
    draft?.instagram_enabled, draft?.instagram_caption, draft?.instagram_hashtags,
    draft?.youtube_enabled, draft?.youtube_title, draft?.youtube_description,
    draft?.youtube_tags, draft?.youtube_visibility, draft?.timezone,
  ]);

  async function flushLatestDraft(): Promise<number> {
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const current = draftRef.current;
    if (!current) throw new Error("Post Karo draft is not ready.");
    const fields = fieldsOf(current);
    if (signature(fields) !== lastSavedSignatureRef.current) await enqueueSave(fields);
    await saveChainRef.current;
    return revisionRef.current;
  }

  async function openConfirmation(nextMode: "now" | "schedule") {
    if (!draftRef.current) return;
    if (nextMode === "schedule" && !scheduledFor) {
      setMode("schedule");
      setPageError("Choose when you want this Short to publish.");
      return;
    }
    setPageError("");
    try {
      await flushLatestDraft();
      setMode(nextMode);
      setConfirming(true);
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Your latest edits could not be saved.");
    }
  }

  const watchPublication = useCallback(async (publicationId: string) => {
    try {
      const next = await api<Publication>("/post-karo/publications/" + publicationId);
      setPublication(next);
      if (!terminalStatuses.has(next.status)) {
        pollTimerRef.current = window.setTimeout(() => void watchPublication(publicationId), 1800);
      } else {
        setPublishing(false);
        void loadWorkspace();
      }
    } catch (cause) {
      setPageError(cause instanceof Error ? cause.message : "Could not refresh publishing status.");
      setPublishing(false);
    }
  }, [loadWorkspace]);

  async function confirmPublish() {
    if (!draftRef.current || publishing) return;
    setPublishing(true);
    setPageError("");
    try {
      const revision = await flushLatestDraft();
      const endpoint = "/post-karo/drafts/" + draftRef.current.id + "/publish";
      const result = await postJSON<Publication>(endpoint, {
        expected_revision: revision,
        request_id: crypto.randomUUID(),
        mode,
        scheduled_for: mode === "schedule" ? scheduledFor : null,
        timezone: draftRef.current.timezone,
      });
      setPublication(result);
      setConfirming(false);
      void watchPublication(result.id);
    } catch (cause) {
      setPublishing(false);
      setPageError(cause instanceof Error ? cause.message : "Post Karo could not start safely.");
    }
  }

  const instagram = accountFor(status, "instagram");
  const youtube = accountFor(status, "youtube");
  const selectedCount = Number(!!draft?.instagram_enabled) + Number(!!draft?.youtube_enabled);
  const connectedCount = Number(!!instagram?.connected) + Number(!!youtube?.connected);
  const scheduled = publications.filter(item => item.mode === "schedule" && item.status !== "failed");
  const history = publications.filter(item => item.status !== "queued" && item.status !== "processing");

  if (loading) {
    return <AppShell title="Post Karo" subtitle="Create. Review. Publish.">
      <div className="screen-loader inline"><Loader2 className="spin" size={25}/><p>Opening Post Karo…</p></div>
    </AppShell>;
  }
  if (!status) {
    return <AppShell title="Post Karo"><div className="empty-state">
      <div className="empty-icon"><Send/></div><h3>Post Karo is unavailable</h3>
      <p>{pageError || "We could not load your publishing workspace."}</p>
      <button className="primary-btn" onClick={() => void loadStatus()}><RefreshCw size={15}/>Retry</button>
    </div></AppShell>;
  }

  if (!status.plan_eligible) {
    return <AppShell title="Post Karo" subtitle="Publish without leaving ClipKaro.">
      <section className={styles.gatedHero}>
        <div className={styles.heroBadge}><LockKeyhole size={14}/> PAID PLAN FEATURE</div>
        <h2>Clip it here.<br/><span>Post it from here.</span></h2>
        <p>Post Karo connects finished Shorts to Instagram Reels and YouTube Shorts. It is available on every paid ClipKaro plan, starting with Mini Pass.</p>
        <Link href="/pricing" className="primary-btn">View plans <ArrowRight size={15}/></Link>
        <div className={styles.gatedPlatforms}><span><Instagram/> Instagram Reels</span><span><Youtube/> YouTube Shorts</span></div>
      </section>
    </AppShell>;
  }

  if (!status.ready) {
    const stepOneDone = status.connection_active && status.profile_ready;
    const stepTwoDone = connectedCount > 0;
    return <AppShell title="Post Karo" subtitle="Set it up once. Publish from ClipKaro after that.">
      {pageError && <div className="floating-error">{pageError}</div>}
      <section className={styles.setupHero}>
        <div>
          <div className={styles.heroBadge}><Sparkles size={14}/> POST KARO</div>
          <h2>Connect once. Then publish your ClipKaro Shorts directly to <span>Instagram Reels</span> and <span>YouTube Shorts.</span></h2>
          <p>Set up Post Karo once, connect the platforms you want, and publish without leaving ClipKaro.</p>
        </div>
        <div className={styles.heroMiniFlow}><span>Clip</span><i>→</i><span>Review</span><i>→</i><b>Post Karo</b></div>
      </section>
      <div className={styles.steps}>
        <motion.section className={[styles.stepCard, stepOneDone ? styles.complete : styles.active].join(" ")} layout>
          <div className={styles.stepRail}><span>01</span>{stepOneDone ? <SuccessOrb small/> : <KeyRound size={20}/>}</div>
          <div className={styles.stepBody}>
            <div className={styles.stepHeading}><div><small>STEP 1</small><h3>Activate SIMPLE Connection</h3></div>{stepOneDone && <b className={styles.donePill}>Connected ✓</b>}</div>
            {stepOneDone ? <p>Your secure connection is active. Saved key: <strong>{status.api_key_masked}</strong></p> : <>
              <p>Create a free Zernio account, create a dedicated API key named <b>ClipKaro</b>, then paste it once below.</p>
              <ol className={styles.instructions}>
                <li><span>1</span><div><b>Create or sign in to Zernio</b><small>Your Zernio account stays separate from ClipKaro.</small></div><a href="https://zernio.com" target="_blank" rel="noreferrer">Open Zernio <ExternalLink size={12}/></a></li>
                <li><span>2</span><div><b>Open API Keys → Create API Key</b><small>Name the key “ClipKaro” so you know what it is for.</small></div></li>
                <li><span>3</span><div><b>Copy the key and paste it here</b><small>ClipKaro encrypts it server-side and never shows the full key again.</small></div></li>
              </ol>
              <div className={styles.keyRow}><KeyRound size={17}/><input type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder="Paste your Zernio API key"/><button className="primary-btn" disabled={testing || !apiKey.trim()} onClick={() => void testConnection()}>{testing ? <Loader2 className="spin" size={15}/> : <ShieldCheck size={15}/>} {testing ? "Testing…" : "Test connection"}</button></div>
              <div className={styles.securityNote}><ShieldCheck size={14}/> Stored encrypted. Never placed in browser storage or shown after save.</div>
            </>}
          </div>
        </motion.section>

        <motion.section className={[styles.stepCard, !stepOneDone ? styles.locked : stepTwoDone ? styles.complete : styles.active].join(" ")} layout>
          <div className={styles.stepRail}><span>02</span>{stepTwoDone ? <SuccessOrb small/> : !stepOneDone ? <LockKeyhole size={19}/> : <Send size={19}/>}</div>
          <div className={styles.stepBody}>
            <div className={styles.stepHeading}><div><small>STEP 2</small><h3>Connect where you publish</h3></div>{stepTwoDone && <b className={styles.donePill}>{connectedCount} ready ✓</b>}</div>
            <p>Instagram and YouTube are independent. Connect either one or both—the choice is yours.</p>
            <div className={styles.platformGrid}>
              <PlatformConnectCard platform="instagram" account={instagram} locked={!stepOneDone} busy={connecting === "instagram"} onConnect={() => void connectPlatform("instagram")}/>
              <PlatformConnectCard platform="youtube" account={youtube} locked={!stepOneDone} busy={connecting === "youtube"} onConnect={() => void connectPlatform("youtube")}/>
            </div>
            {stepOneDone && <button className={styles.refreshLink} disabled={syncing} onClick={() => void syncAccounts()}>{syncing ? <Loader2 className="spin" size={13}/> : <RefreshCw size={13}/>} Refresh connections</button>}
            <div className={styles.comingSoon}><span>TikTok <b>Coming soon</b></span><span>LinkedIn <b>Coming soon</b></span><span>X <b>Coming soon</b></span><span>Threads <b>Coming soon</b></span></div>
          </div>
        </motion.section>

        <motion.section className={[styles.stepCard, !stepTwoDone ? styles.locked : styles.complete].join(" ")} layout>
          <div className={styles.stepRail}><span>03</span>{stepTwoDone ? <SuccessOrb small/> : <LockKeyhole size={19}/>}</div>
          <div className={styles.stepBody}>
            <small>STEP 3</small><h3>You’re ready to Post Karo</h3>
            {stepTwoDone ? <div className={styles.readyMoment}><SuccessOrb/><div><b>Publishing setup complete.</b><p>Keep clipping. Your connected account is ready whenever your next Short is.</p>{returnExport ? <button className="primary-btn" onClick={() => void loadDraft(returnExport)}>Continue with my Short <ArrowRight size={15}/></button> : <Link href="/exports" className="primary-btn">Choose a finished Short <ArrowRight size={15}/></Link>}</div></div> : <p>Complete the steps above to unlock direct publishing.</p>}
          </div>
        </motion.section>
      </div>
    </AppShell>;
  }

  if (composerLoading || (returnExport && !draft)) {
    return <AppShell title="Post Karo" subtitle="Preparing your exact finished Short.">
      {pageError ? <div className="empty-state"><div className="empty-icon"><FileVideo/></div><h3>Could not prepare this Short</h3><p>{pageError}</p><Link href="/exports" className="primary-btn">Back to exports</Link></div> : <div className="screen-loader inline"><Loader2 className="spin" size={25}/><p>Preparing your publishing draft…</p></div>}
    </AppShell>;
  }
  if (draft) {
    return <AppShell title="Post Karo" subtitle={draft.export?.title || "Review exactly what will publish."} action={<div className={styles.saveSignal} data-state={saveState}>{saveState === "saving" ? <Loader2 className="spin" size={13}/> : saveState === "error" ? <span>!</span> : <Check size={13}/>} {saveState === "saving" ? "Saving…" : saveState === "error" ? "Save needs attention" : "Saved"}</div>}>
      {pageError && <div className="floating-error">{pageError}</div>}
      <div className={styles.composer}>
        <section className={styles.previewColumn}>
          <div className={styles.previewTop}><span><Sparkles size={13}/> FINISHED SHORT</span><b>{draft.export?.aspect_ratio || "9:16"}</b></div>
          <div className={styles.phoneFrame}><video src={API_URL + "/exports/" + draft.export_id + "/download"} controls playsInline preload="metadata"/></div>
          <div className={styles.previewMeta}><div><b>{draft.export?.title || "ClipKaro Short"}</b><span>{draft.export?.project_title} · {draft.export?.resolution || "Ready"}</span></div><button className="secondary-btn small" onClick={() => downloadExport(draft.export_id)}><Download size={14}/> Download MP4</button></div>
          <div className={styles.ownershipNote}><ShieldCheck size={15}/><span>Your finished MP4 stays downloadable whether you publish with Post Karo or not.</span></div>
        </section>
        <section className={styles.composeColumn}>
          <div className={styles.composeIntro}><div><span className={styles.eyebrow}>DESTINATIONS</span><h2>Where should this Short go?</h2><p>Select one or both. Each platform keeps its own editable copy.</p></div><span className={styles.destinationCount}>{selectedCount} selected</span></div>
          <div className={styles.destinationCards}>
            <DestinationToggle platform="instagram" account={instagram} selected={draft.instagram_enabled} onChange={value => updateDraft({ instagram_enabled: value })}/>
            <DestinationToggle platform="youtube" account={youtube} selected={draft.youtube_enabled} onChange={value => updateDraft({ youtube_enabled: value })}/>
          </div>
          <AnimatePresence initial={false}>
            {draft.instagram_enabled && <motion.div className={styles.editorCard} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <div className={styles.editorCardHead}><div className={styles.instagramIcon}><Instagram size={19}/></div><div><b>Instagram Reels</b><span>{accountLabel(instagram)}</span></div><small>Editable</small></div>
              <label>Caption <span>AI suggested · creator controlled</span></label>
              <textarea value={draft.instagram_caption} maxLength={2200} onChange={event => updateDraft({ instagram_caption: event.target.value })} placeholder="Write the Reel caption…"/>
              <div className={styles.counter}>{draft.instagram_caption.length}/2200</div>
              <label>Hashtags</label>
              <input value={draft.instagram_hashtags.join(" ")} onChange={event => updateDraft({ instagram_hashtags: parseTags(event.target.value) })} placeholder="#creator #shorts"/>
            </motion.div>}
            {draft.youtube_enabled && <motion.div className={styles.editorCard} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
              <div className={styles.editorCardHead}><div className={styles.youtubeIcon}><Youtube size={19}/></div><div><b>YouTube Shorts</b><span>{accountLabel(youtube)}</span></div><small>Editable</small></div>
              <label>Title <span>Required</span></label>
              <input value={draft.youtube_title} maxLength={100} onChange={event => updateDraft({ youtube_title: event.target.value })} placeholder="Your Short title"/>
              <div className={styles.counter}>{draft.youtube_title.length}/100</div>
              <label>Description</label>
              <textarea value={draft.youtube_description} maxLength={5000} onChange={event => updateDraft({ youtube_description: event.target.value })} placeholder="Describe this Short…"/>
              <div className={styles.counter}>{draft.youtube_description.length}/5000</div>
              <div className={styles.twoFields}><div><label>Tags</label><input value={draft.youtube_tags.join(", ")} onChange={event => updateDraft({ youtube_tags: parseTags(event.target.value) })} placeholder="creator, shorts"/></div><div><label>Visibility</label><select value={draft.youtube_visibility} onChange={event => updateDraft({ youtube_visibility: event.target.value as Draft["youtube_visibility"] })}><option value="public">Public</option><option value="unlisted">Unlisted</option><option value="private">Private</option></select></div></div>
            </motion.div>}
          </AnimatePresence>
          {!selectedCount && <div className={styles.chooseNotice}><Send size={18}/><div><b>Choose a destination</b><span>Select Instagram, YouTube, or both before continuing.</span></div></div>}
          <div className={styles.whenCard}>
            <div><span className={styles.eyebrow}>WHEN</span><h3>Publish now or line it up?</h3></div>
            <div className={styles.modeSwitch}><button className={mode === "now" ? styles.activeMode : ""} onClick={() => setMode("now")}><Send size={14}/> Post now</button><button className={mode === "schedule" ? styles.activeMode : ""} onClick={() => setMode("schedule")}><CalendarClock size={14}/> Schedule</button></div>
            {mode === "schedule" && <motion.div className={styles.scheduleRow} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}><div><label>Date & time</label><input type="datetime-local" value={scheduledFor} onChange={event => setScheduledFor(event.target.value)}/></div><div><label>Timezone</label><input value={draft.timezone} onChange={event => updateDraft({ timezone: event.target.value })}/></div><small>Scheduling is limited to the next 6 days so temporary publishing media cannot expire before the post runs.</small></motion.div>}
          </div>
        </section>
      </div>
      <div className={styles.stickyBar}>
        <div><span>{selectedCount ? String(selectedCount) + " destination" + (selectedCount > 1 ? "s" : "") + " selected" : "Choose a destination"}</span><small>{saveState === "saving" ? "Finishing your latest save…" : "Your latest saved revision is what gets published."}</small></div>
        <button className="primary-btn" disabled={!selectedCount || publishing || saveState === "error"} onClick={() => void openConfirmation(mode)}>{publishing ? <Loader2 className="spin" size={15}/> : mode === "schedule" ? <CalendarClock size={15}/> : <Send size={15}/>} {mode === "schedule" ? "Review schedule" : "Review & Post"}</button>
      </div>
      <AnimatePresence>
        {confirming && <motion.div className={styles.modalBackdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div className={styles.confirmModal} initial={{ opacity: 0, scale: .96, y: 18 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: .97 }}>
            <div className={styles.confirmIcon}><Send/></div><span className={styles.eyebrow}>FINAL CHECK</span><h2>{mode === "schedule" ? "Ready to schedule?" : "Ready to Post Karo?"}</h2><p>ClipKaro will publish the exact saved copy shown below.</p>
            <div className={styles.confirmTargets}>
              {draft.instagram_enabled && <div><Instagram/><span><b>Instagram Reels</b><small>{accountLabel(instagram)}</small><em>{draft.instagram_caption.slice(0, 92) || "No caption"}</em></span><CheckCircle2/></div>}
              {draft.youtube_enabled && <div><Youtube/><span><b>YouTube Shorts</b><small>{accountLabel(youtube)} · {draft.youtube_visibility}</small><em>{draft.youtube_title || "Untitled"}</em></span><CheckCircle2/></div>}
            </div>
            {mode === "schedule" && <div className={styles.confirmSchedule}><CalendarClock size={16}/> {scheduledFor || "Choose a date and time"}</div>}
            <div className={styles.modalActions}><button className="secondary-btn" disabled={publishing} onClick={() => setConfirming(false)}>Back to edit</button><button className="primary-btn" disabled={publishing || (mode === "schedule" && !scheduledFor)} onClick={() => void confirmPublish()}>{publishing ? <Loader2 className="spin" size={15}/> : <Send size={15}/>} {publishing ? "Starting safely…" : mode === "schedule" ? "Schedule Short" : "Post now"}</button></div>
          </motion.div>
        </motion.div>}
      </AnimatePresence>
      <AnimatePresence>{publication && <PublicationOverlay publication={publication} onClose={() => { setPublication(null); if (terminalStatuses.has(publication.status)) setDraft(null); }}/>}</AnimatePresence>
    </AppShell>;
  }
  return <AppShell title="Post Karo" subtitle="Your publishing connection is ready.">
    {pageError && <div className="floating-error">{pageError}</div>}
    <section className={styles.connectedHero}>
      <div><div className={styles.heroBadge}><CheckCircle2 size={14}/> POST KARO READY</div><h2>Your publishing setup is <span>ready.</span></h2><p>Keep clipping. Instagram and YouTube are one review away whenever your next Short is ready.</p><div className={styles.connectedActions}><Link href="/upload" className="primary-btn"><Sparkles size={15}/> Create a new Short</Link><button className="secondary-btn" onClick={() => void syncAccounts()} disabled={syncing}>{syncing ? <Loader2 className="spin" size={14}/> : <RefreshCw size={14}/>} Refresh</button></div></div>
      <div className={styles.connectedAccounts}><ConnectedAccount platform="instagram" account={instagram} onConnect={() => void connectPlatform("instagram")}/><ConnectedAccount platform="youtube" account={youtube} onConnect={() => void connectPlatform("youtube")}/></div>
    </section>
    <div className={styles.workspaceTabs}><button className={tab === "publish" ? styles.activeTab : ""} onClick={() => setTab("publish")}><Send size={14}/> Publish</button><button className={tab === "scheduled" ? styles.activeTab : ""} onClick={() => setTab("scheduled")}><CalendarClock size={14}/> Scheduled <span>{scheduled.length}</span></button><button className={tab === "history" ? styles.activeTab : ""} onClick={() => setTab("history")}><History size={14}/> History</button></div>
    {tab === "publish" && <section className={styles.librarySection}><div className={styles.sectionHead}><div><span className={styles.eyebrow}>FINISHED SHORTS</span><h2>Choose what to publish</h2><p>Download it, post it, or do both. Your finished MP4 stays yours.</p></div><Link href="/exports">All exports <ArrowRight size={13}/></Link></div>
      {exports.length ? <div className={styles.exportGrid}>{exports.slice(0, 8).map(item => <article className={styles.exportCard} key={item.id}><div className={styles.exportVisual}><FileVideo/><span>READY</span></div><div className={styles.exportCopy}><b>{item.title || "ClipKaro Short"}</b><small>{item.project_title || "Project"} · {item.resolution || "Ready"} · {item.aspect_ratio || "9:16"}</small><div><button className="secondary-btn small" onClick={() => downloadExport(item.id)}><Download size={13}/> Download</button><button className="primary-btn small" onClick={() => void loadDraft(item.id)}><Send size={13}/> Post Karo</button></div></div></article>)}</div> : <div className={styles.emptyPanel}><Sparkles/><h3>Your next finished Short will appear here.</h3><p>Create or export a Short, then Post Karo without downloading and uploading it again.</p><Link href="/upload" className="primary-btn">Create a Short</Link></div>}
    </section>}
    {tab === "scheduled" && <PublicationList items={scheduled} emptyTitle="Nothing scheduled yet" emptyCopy="Choose a finished Short, select Schedule, and Post Karo will keep the handoff organised."/>}
    {tab === "history" && <PublicationList items={history} emptyTitle="No publishing history yet" emptyCopy="Your Instagram and YouTube publishing results will appear here after your first Post Karo."/>}
    <button className={styles.disconnectButton} onClick={() => void disconnect()}><Unplug size={13}/> Disconnect SIMPLE connection</button>
  </AppShell>;
}
function PlatformConnectCard({ platform, account, locked, busy, onConnect }: {
  platform: Platform; account?: SocialAccount; locked: boolean; busy: boolean; onConnect: () => void;
}) {
  const connected = !!account?.connected;
  return <div className={[styles.platformCard, connected ? styles.platformConnected : "", locked ? styles.platformLocked : ""].join(" ")}>
    <div className={platform === "instagram" ? styles.instagramIcon : styles.youtubeIcon}>{platformIcon(platform)}</div>
    <div><b>{platform === "instagram" ? "Instagram Reels" : "YouTube Shorts"}</b><span>{connected ? accountLabel(account) : locked ? "Complete Step 1 first" : "Not connected"}</span></div>
    {connected ? <CheckCircle2 className={styles.connectedCheck} size={21}/> : <button disabled={locked || busy} onClick={onConnect}>{busy ? <Loader2 className="spin" size={14}/> : <ArrowRight size={14}/>} Connect</button>}
  </div>;
}
function ConnectedAccount({ platform, account, onConnect }: {
  platform: Platform; account?: SocialAccount; onConnect: () => void;
}) {
  return <div className={styles.connectedAccount}>
    <div className={platform === "instagram" ? styles.instagramIcon : styles.youtubeIcon}>{platformIcon(platform)}</div>
    <div><b>{platform === "instagram" ? "Instagram Reels" : "YouTube Shorts"}</b><span>{account?.connected ? accountLabel(account) : "Not connected"}</span></div>
    {account?.connected ? <span className={styles.livePill}><i/> Connected</span> : <button onClick={onConnect}>Connect</button>}
  </div>;
}
function DestinationToggle({ platform, account, selected, onChange }: {
  platform: Platform; account?: SocialAccount; selected: boolean; onChange: (value: boolean) => void;
}) {
  const connected = !!account?.connected;
  return <button type="button" disabled={!connected} className={[styles.destinationCard, selected ? styles.destinationSelected : ""].join(" ")} onClick={() => connected && onChange(!selected)}>
    <div className={platform === "instagram" ? styles.instagramIcon : styles.youtubeIcon}>{platformIcon(platform)}</div>
    <div><b>{platform === "instagram" ? "Instagram Reels" : "YouTube Shorts"}</b><span>{connected ? accountLabel(account) : "Connect in Post Karo first"}</span></div>
    <span className={styles.selectionBox}>{selected ? <Check size={14}/> : connected ? "" : <LockKeyhole size={12}/>}</span>
  </button>;
}
function PublicationList({ items, emptyTitle, emptyCopy }: { items: Publication[]; emptyTitle: string; emptyCopy: string }) {
  if (!items.length) return <div className={styles.emptyPanel}><History/><h3>{emptyTitle}</h3><p>{emptyCopy}</p></div>;
  return <div className={styles.publicationList}>{items.map(item => <article key={item.id} className={styles.publicationRow}>
    <div className={styles.publicationStatus} data-status={item.status}>{item.status === "published" || item.status === "scheduled" ? <CheckCircle2/> : item.status === "failed" ? <span>!</span> : <Loader2 className="spin"/>}</div>
    <div><b>{item.mode === "schedule" ? "Scheduled Post Karo" : "Post Karo"}</b><span>{item.status} · {item.created_at ? new Date(item.created_at).toLocaleString() : "recently"}</span></div>
    <div className={styles.resultChips}>{item.platform_results?.map((result, index) => <span key={String(result.platform) + String(index)}>{platformIcon(result.platform || "", 13)} {result.platform || "platform"} · {result.status || "processing"}</span>)}</div>
  </article>)}</div>;
}
function PublicationOverlay({ publication, onClose }: { publication: Publication; onClose: () => void }) {
  const terminal = terminalStatuses.has(publication.status);
  const success = publication.status === "published" || publication.status === "scheduled";
  const partial = publication.status === "partial";
  const placeholders: PlatformResult[] = [
    ...(publication.snapshot.instagram_enabled ? [{ platform: "instagram", status: publication.status }] : []),
    ...(publication.snapshot.youtube_enabled ? [{ platform: "youtube", status: publication.status }] : []),
  ];
  const results = publication.platform_results?.length ? publication.platform_results : placeholders;
  return <motion.div className={styles.modalBackdrop} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
    <motion.div className={styles.publishModal} initial={{ scale: .97, opacity: 0, y: 16 }} animate={{ scale: 1, opacity: 1, y: 0 }}>
      {terminal ? <SuccessOrb/> : <div className={styles.processingOrb}><Send/><i/></div>}
      <span className={styles.eyebrow}>{terminal ? "POST KARO" : "PUBLISHING"}</span>
      <h2>{success ? (publication.status === "scheduled" ? "Post Karo scheduled." : "Post Karo complete.") : partial ? "Published with one item to review." : publication.status === "failed" ? "Publishing needs attention." : "Post Karo is working…"}</h2>
      <p>{terminal ? "Each destination reports its own result, so one platform never hides what happened on the other." : publication.job?.message || "Preparing your exact saved Short for the selected accounts."}</p>
      {!terminal && <div className={styles.publishProgress}><span style={{ width: String(publication.job?.progress || 12) + "%" }}/></div>}
      <div className={styles.platformResults}>{results.map((result, index) => {
        const url = result.platformPostUrl || result.url;
        const okay = result.status === "published" || result.status === "scheduled";
        return <div key={String(result.platform) + String(index)}>{platformIcon(result.platform || "", 20)}<span><b>{result.platform === "instagram" ? "Instagram Reels" : "YouTube Shorts"}</b><small>{result.status || "processing"}{result.error ? " · " + result.error : ""}</small></span>{okay ? <CheckCircle2 className={styles.connectedCheck}/> : result.status === "failed" ? <strong>!</strong> : <Loader2 className="spin"/>}{url && <a href={url} target="_blank" rel="noreferrer">View <ExternalLink size={11}/></a>}</div>;
      })}</div>
      {publication.error && <div className={styles.publicationError}>{publication.error}</div>}
      {terminal && <div className={styles.modalActions}><button className="secondary-btn" onClick={() => downloadExport(publication.export_id)}><Download size={14}/> Download MP4</button><button className="primary-btn" onClick={onClose}>Done <Check size={14}/></button></div>}
    </motion.div>
  </motion.div>;
}


export default function PostKaroPage() {
  return <Suspense fallback={<AppShell title="Post Karo" subtitle="Create. Review. Publish."><div className="screen-loader inline"><Loader2 className="spin" size={25}/><p>Opening Post Karo…</p></div></AppShell>}><PostKaroPageInner/></Suspense>;
}
