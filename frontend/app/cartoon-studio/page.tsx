"use client";

import { AppShell } from "@/components/AppShell";
import { api, deleteJSON, postJSON } from "@/lib/api";
import Link from "next/link";
import {
  AlertCircle, Check, ChevronDown, Clapperboard, KeyRound, Loader2,
  LockKeyhole, Play, ShieldCheck, Sparkles, Volume2, WandSparkles, X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import styles from "./cartoon-studio.module.css";
import { animationStyles, type CartoonProject, isRendering, projectTitle, ProjectStatus, StudioProject, StyleArtwork, styleLabel, voiceLabel } from "./studio-project";

type ProviderStatus = {
  openrouter: SavedProvider;
  nvidia?: SavedProvider;
};
type SavedProvider = { connected: boolean; masked_key: string; validated_at?: string | null };
type PlannerProvider = "nvidia" | "openrouter";
type ProjectPlanner = "free" | "glm" | "nvidia";
const PROVIDER_NAMES: Record<PlannerProvider, string> = { openrouter: "OpenRouter", nvidia: "NVIDIA API" };
const EMPTY_PROVIDER: SavedProvider = { connected: false, masked_key: "" };
const STORY_PLANNERS: Record<ProjectPlanner, { label: string; hint: string }> = {
  free: { label: "Quick · Free", hint: "A quick starting point for everyday stories." },
  glm: { label: "Detailed · Paid", hint: "Use this for stories with more direction. Your provider charges for planning." },
  nvidia: { label: "Detailed · NVIDIA", hint: "Use your NVIDIA account to plan a text-only story." },
};
type TTSModel = { id: string; voices: string[]; languages: string[]; voices_by_language?: Record<string, string[]> };
type TTSResponse = { models: TTSModel[] };
type CartoonUsage = {
  plan: string; base_seconds: number; remaining_seconds: number; reserved_seconds: number;
  refill_available_at: string | null; refill_claimable: boolean; refill_claimed: boolean;
  period_ends_at: string | null;
};

function cartoonTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return [minutes ? minutes + "m" : "", remainder || !minutes ? remainder + "s" : ""].filter(Boolean).join(" ");
}

function cartoonUsageNote(usage: CartoonUsage) {
  if (usage.reserved_seconds) return cartoonTime(usage.reserved_seconds) + " reserved for your render";
  if (usage.plan === "free") return "One free cartoon per account";
  if (usage.plan === "mini_pass") return "One minute per Mini Pass";
  if (usage.refill_claimable) return "Your one-time refill is ready";
  const dateLabel = (value: string) => new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  if (usage.refill_available_at) return "Refill unlocks " + dateLabel(usage.refill_available_at);
  if (usage.remaining_seconds <= 30 && usage.period_ends_at) return "Next allowance " + dateLabel(usage.period_ends_at);
  if (usage.refill_claimed) return "Refill used this billing cycle";
  return "One refill unlocks 24 hours after 30s or less remain";
}

export default function CartoonStudioPage() {
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [models, setModels] = useState<TTSModel[]>([]);
  const [requestedVoiceId, setVoiceId] = useState("");
  const [projects, setProjects] = useState<CartoonProject[]>([]);
  const [selected, setSelected] = useState<CartoonProject | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [projectPlanner, setProjectPlanner] = useState<ProjectPlanner>("free");
  const [nvidiaKey, setNvidiaKey] = useState("");
  const [providerBusy, setProviderBusy] = useState<PlannerProvider | null>(null);
  const [providerFeedback, setProviderFeedback] = useState<{ provider: PlannerProvider; message: string; error: boolean } | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(30);
  const [ratio, setRatio] = useState("9:16");
  const [style, setStyle] = useState("2d-cartoon");
  const [language, setLanguage] = useState("hi");
  const [reference, setReference] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [createError, setCreateError] = useState("");
  const [usage, setUsage] = useState<CartoonUsage | null>(null);
  const [claimingRefill, setClaimingRefill] = useState(false);
  const usageRequest = useRef(0);
  const [libraryFilter, setLibraryFilter] = useState<"recent" | "failed">("recent");
  const advancedRef = useRef<HTMLDetailsElement>(null);
  const advancedSummaryRef = useRef<HTMLElement>(null);
  const referenceInputRef = useRef<HTMLInputElement>(null);
  const projectRequest = useRef(0);

  const refreshUsage = useCallback(async () => {
    const request = ++usageRequest.current;
    try {
      const result = await api<CartoonUsage | null>("/cartoon-studio/usage");
      if (request === usageRequest.current) setUsage(result);
    } catch {
      // The API checks availability on every creation and refill request.
    }
  }, []);

  useEffect(() => { void refreshUsage(); }, [refreshUsage]);

  useEffect(() => {
    const dates = [usage?.refill_claimable ? null : usage?.refill_available_at, usage?.period_ends_at];
    const now = Date.now();
    const next = Math.min(...dates.filter((value): value is string => !!value).map(value => Date.parse(value)).filter(value => value > now));
    if (!Number.isFinite(next)) return;
    const timer = window.setTimeout(() => void refreshUsage(), Math.min(next - now + 1000, 60000));
    return () => window.clearTimeout(timer);
  }, [usage, refreshUsage]);

  async function claimRefill() {
    if (!usage?.refill_claimable || claimingRefill) return;
    setClaimingRefill(true);
    setError("");
    try {
      ++usageRequest.current;
      setUsage(await postJSON<CartoonUsage>("/cartoon-studio/usage/refill", {}));
      setNotice("Your cartoon time has been refilled.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not claim your cartoon refill.");
    } finally {
      setClaimingRefill(false);
      void refreshUsage();
    }
  }

  const updateProject = useCallback((project: CartoonProject) => {
    setProjects(current => current.some(item => item.id === project.id)
      ? current.map(item => item.id === project.id ? project : item)
      : [project, ...current]);
    setSelected(current => current?.id === project.id ? project : current);
  }, []);

  function showProject(project: CartoonProject) {
    setSelected(project);
    updateProject(project);
  }

  const loadModels = useCallback(async () => {
    const response = await api<TTSResponse>("/cartoon-studio/tts-models");
    setModels(response.models || []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api<ProviderStatus>("/cartoon-studio/providers"),
      api<CartoonProject[]>("/cartoon-studio/projects"),
    ]).then(([providerData, projectData]) => {
      if (cancelled) return;
      setProvider(providerData);
      setProjects(projectData || []);
      const projects = projectData || [];
      const initial = projects.find(isRendering) || projects.find(project => project.status === "ready");
      if (initial) {
        setSelected(current => current || initial);
        if (initial.status === "ready") {
          api<CartoonProject>("/cartoon-studio/projects/" + initial.id)
            .then(project => { if (!cancelled && projectRequest.current === 0) updateProject(project); })
            .catch(() => null);
        }
      }
      setLoading(false);
    }).catch((cause) => {
      if (!cancelled) {
        setError(cause instanceof Error ? cause.message : "Cartoon Studio could not be loaded.");
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [updateProject]);

  useEffect(() => {
    loadModels().catch((cause) => {
      setError(cause instanceof Error ? cause.message : "Voice models could not be loaded.");
    });
  }, [loadModels]);

  const renderingId = projects.find(isRendering)?.id;
  useEffect(() => {
    if (!renderingId) return;
    let cancelled = false;
    let pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return;
      pending = true;
      try {
        const project = await api<CartoonProject>("/cartoon-studio/projects/" + renderingId);
        if (!cancelled) {
          updateProject(project);
          if (!isRendering(project)) void refreshUsage();
        }
      } catch {
        // Keep showing the last known status while the connection recovers.
      } finally {
        pending = false;
      }
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [renderingId, updateProject, refreshUsage]);

  const failedCount = projects.filter(project => project.status === "failed").length;
  const visibleProjects = projects.filter(project => (project.status === "failed") === (libraryFilter === "failed"));
  const connected = Boolean(provider?.openrouter.connected);
  const selectedVoiceModel = models.find(model => model.languages?.includes(language)
    ?? (model.id === "system/edge-tts-urdu" && language === "ur"));
  const voiceChoices = selectedVoiceModel?.voices_by_language?.[language] || selectedVoiceModel?.voices || [];
  const voiceId = voiceChoices.includes(requestedVoiceId) ? requestedVoiceId : "";
  const nvidiaAvailable = Boolean(provider?.nvidia);
  const nvidiaConnected = Boolean(provider?.nvidia?.connected);
  const missingProvider = projectPlanner === "nvidia"
    ? (nvidiaConnected ? "" : "NVIDIA API")
    : (connected ? "" : "OpenRouter");
  const durationExceedsBalance = usage !== null && duration > usage.remaining_seconds;

  async function connectProvider(event: FormEvent<HTMLFormElement>, name: PlannerProvider) {
    event.preventDefault();
    const key = (name === "nvidia" ? nvidiaKey : apiKey).trim();
    if (!key || busy || providerBusy) return;
    setProviderBusy(name);
    setProviderFeedback(null);
    try {
      const saved = await postJSON<SavedProvider>(
        "/cartoon-studio/providers/" + name,
        { api_key: key },
      );
      setProvider((current) => current && { ...current, [name]: saved });
      if (name === "nvidia") setNvidiaKey("");
      else setApiKey("");
      setProviderFeedback({ provider: name, message: "Key saved securely.", error: false });
    } catch (cause) {
      setProviderFeedback({ provider: name, message: cause instanceof Error ? cause.message : "The API key could not be saved.", error: true });
    } finally {
      setProviderBusy(null);
    }
  }

  async function disconnectProvider(name: PlannerProvider) {
    if (busy || providerBusy) return;
    setProviderBusy(name);
    setProviderFeedback(null);
    try {
      await deleteJSON("/cartoon-studio/providers/" + name);
      setProvider((current) => current && { ...current, [name]: EMPTY_PROVIDER });
      setProviderFeedback({ provider: name, message: "Key disconnected.", error: false });
    } catch (cause) {
      setProviderFeedback({ provider: name, message: cause instanceof Error ? cause.message : "The API key could not be removed.", error: true });
    } finally {
      setProviderBusy(null);
    }
  }

  async function createCartoon(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || renderingId || providerBusy || missingProvider || durationExceedsBalance) return;
    setCreateError("");
    if (prompt.trim().length < 8) {
      setCreateError("Describe your story in at least 8 characters.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const body = new FormData();
      body.set("prompt", prompt.trim());
      body.set("duration_seconds", String(duration));
      body.set("aspect_ratio", ratio);
      body.set("style", style);
      body.set("language", language);
      body.set("voice_id", voiceId);
      body.set("story_planner", projectPlanner);
      if (reference) body.set("reference_video", reference);
      const project = await api<CartoonProject>("/cartoon-studio/projects", { method: "POST", body });
      projectRequest.current += 1;
      showProject(project);
      setNotice("Your cartoon is queued. You can leave this page while it renders.");
      setReference(null);
      if (referenceInputRef.current) referenceInputRef.current.value = "";
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : "Cartoon generation could not start.");
    } finally {
      setBusy(false);
      void refreshUsage();
    }
  }

  async function openProject(projectId: string) {
    const request = ++projectRequest.current;
    setError("");
    try {
      const project = await api<CartoonProject>("/cartoon-studio/projects/" + projectId);
      if (request !== projectRequest.current) return;
      showProject(project);
      document.getElementById("studio-current-project")?.focus();
    } catch (cause) {
      if (request === projectRequest.current) setError(cause instanceof Error ? cause.message : "Project details could not be loaded.");
    }
  }

  function openAdvanced() {
    if (advancedRef.current) advancedRef.current.open = true;
    advancedSummaryRef.current?.focus();
  }

  async function retryProject() {
    if (!selected || busy || renderingId) return;
    setBusy(true);
    setError("");
    try {
      const project = await api<CartoonProject>(
        "/cartoon-studio/projects/" + selected.id + "/retry",
        { method: "POST" },
      );
      projectRequest.current += 1;
      showProject(project);
      setNotice("Retry queued. Saved storyboard and completed voice files will be reused.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The project could not be retried.");
    } finally {
      setBusy(false);
      void refreshUsage();
    }
  }

  async function downloadProject() {
    if (!selected || selected.status !== "ready") return;
    setError("");
    try {
      const result = await api<{ url: string }>("/cartoon-studio/projects/" + selected.id + "/download");
      window.location.assign(result.url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The MP4 could not be downloaded.");
    }
  }

  return (
    <AppShell
      title="Cartoon Studio"
      compactBalance
    >
      <div className={styles.page}>
        <div className={styles.hero}>
          <div>
            <span className={styles.eyebrow}><Sparkles size={13} /> CARTOON STUDIO</span>
            <h2>Give your story <em>a voice.</em></h2>
            <p>Turn your story into a cartoon with character voices and synced captions.</p>
          </div>
          <div className={styles.heroMark} aria-hidden="true"><Clapperboard size={30} /></div>
        </div>

        {error && <div className={styles.alertError} role="alert"><AlertCircle size={17} />{error}<button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {notice && <div className={styles.toast}>
          <Check size={17} aria-hidden="true" />
          <span role="status">{notice}</span>
          <button type="button" onClick={() => setNotice("")} aria-label="Dismiss queued notification"><X size={17} aria-hidden="true" /></button>
        </div>}

        <div className={styles.grid}>
          <div className={styles.creationColumn}>
            <section className={styles.panel} aria-labelledby="studio-create-title">
              <div className={styles.panelHead}><h3 id="studio-create-title">Create a cartoon</h3></div>
              {usage && <div className={styles.usageBalance} aria-label="Cartoon allowance">
                <div>
                  <strong>{cartoonTime(usage.remaining_seconds)} of cartoon time available</strong>
                  <small>{cartoonUsageNote(usage)}</small>
                </div>
                {usage.refill_available_at && !usage.refill_claimed
                  ? <button className={styles.secondaryButton} type="button" disabled={!usage.refill_claimable || claimingRefill} onClick={claimRefill}>
                    {claimingRefill ? "Claiming…" : "Claim one-time refill"}
                  </button>
                  : usage.remaining_seconds < 15 && (usage.plan === "free" || usage.plan === "mini_pass") && <Link href="/pricing">View plans</Link>}
              </div>}
              <form onSubmit={createCartoon} className={styles.form}>
                <label className={styles.field}>
                  <span>What should happen in your story?</span>
                  <textarea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    placeholder="Example: A curious little fox finds a glowing map in the forest and asks a wise owl for help..."
                    rows={3}
                    maxLength={3000}
                    required
                  />
                  <small>{prompt.length}/3000 · Original, family-friendly stories work best.</small>
                </label>
                <div className={styles.fieldsTwo}>
                  <label className={styles.field}><span>Video length</span>
                    <select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>
                      {[15, 30, 45, 60].map(seconds => <option key={seconds} value={seconds} disabled={usage !== null && seconds > usage.remaining_seconds}>
                        {seconds} seconds
                      </option>)}
                    </select>
                  </label>
                  <label className={styles.field}><span>Aspect ratio</span>
                    <select value={ratio} onChange={(event) => setRatio(event.target.value)}>
                      <option value="9:16">9:16 · Vertical</option>
                      <option value="16:9">16:9 · Wide</option><option value="1:1">1:1 · Square</option>
                      <option value="4:5">4:5 · Portrait</option>
                    </select>
                  </label>
                  <label className={styles.field}><span>Animation style</span>
                    <span className={styles.styleControl}>
                      <StyleArtwork style={style} className={styles.styleSwatch} />
                      <select value={style} onChange={event => {
                        const nextStyle = event.target.value;
                        setStyle(nextStyle);
                        if (nextStyle === "cinematic-jannat") setLanguage("ur");
                      }}>
                        {animationStyles.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                      </select>
                    </span>
                    {style === "cinematic-jannat" && <small className={styles.languageHint}>Suspense preset with Urdu voices.</small>}
                  </label>
                  <label className={styles.field}><span>Story language</span>
                    <select value={language} onChange={(event) => setLanguage(event.target.value)} disabled={style === "cinematic-jannat"}>
                      <option value="hi">Hindi</option><option value="hinglish">Hinglish</option>
                      <option value="en">English</option><option value="mr">Marathi</option><option value="ur">Urdu</option><option value="auto">Auto</option>
                    </select>
                  </label>
                </div>
                <div className={`${styles.fieldsTwo} ${styles.plannerFields}`}>
                  <label className={styles.field}><span>Story planner</span>
                    <select value={projectPlanner} onChange={event => setProjectPlanner(event.target.value as ProjectPlanner)} disabled={busy}>
                      {Object.entries(STORY_PLANNERS).filter(([value]) => value !== "nvidia" || nvidiaAvailable)
                        .map(([value, planner]) => <option key={value} value={value}>{planner.label}</option>)}
                    </select>
                    <small>{STORY_PLANNERS[projectPlanner].hint}</small>
                  </label>
                  {voiceChoices.length > 0 && <label className={styles.field}><span>Narrator / lead voice</span>
                    <select value={voiceId} onChange={event => setVoiceId(event.target.value)}>
                      <option value="">Automatic</option>
                      {voiceChoices.map(voice => <option key={voice} value={voice}>{voiceLabel(voice)}</option>)}
                    </select>
                  </label>}
                </div>
                {durationExceedsBalance && !renderingId && <small className={styles.languageHint}>
                  {usage.remaining_seconds >= 15 ? "Choose a shorter video to use your remaining time." : "You need at least 15 seconds of available cartoon time to start."}
                </small>}
                <button className={styles.primaryButton} type="submit" disabled={Boolean(missingProvider || renderingId || busy || providerBusy || durationExceedsBalance)}>
                  {busy ? <Loader2 className={styles.spin} size={18} /> : <WandSparkles size={18} />}
                  {busy ? "Queuing your cartoon…" : renderingId ? "Cartoon rendering…" : "Create my cartoon"}
                </button>
                {createError && <div className={styles.alertError} role="alert"><AlertCircle size={17} />{createError}</div>}
                {provider && missingProvider && <button className={styles.setupLink} type="button" onClick={openAdvanced}>Connect a planner key</button>}
                <details className={styles.referencePanel}>
                  <summary>Reference video {reference ? "added" : "(optional)"}<ChevronDown size={15} aria-hidden="true" /></summary>
                  <label className={styles.fileField}>
                    <span>Choose a reference video</span>
                    <input ref={referenceInputRef} type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" onChange={event => setReference(event.target.files?.[0] || null)} />
                    {reference && <small>{reference.name}</small>}
                    <small>Up to 50 MB and 90 seconds. {projectPlanner === "nvidia" ? "NVIDIA" : "OpenRouter"} receives a few frames to guide the visual style.</small>
                  </label>
                </details>
              </form>
            </section>

            <details ref={advancedRef} className={styles.providerPanel}>
              <summary ref={advancedSummaryRef}>
                <span><KeyRound size={17} aria-hidden="true" /> API Keys &amp; Advanced Settings</span>
                <ChevronDown size={16} aria-hidden="true" />
              </summary>
              <div className={styles.providerContent}>
                <div className={styles.providerList}>
                  {(nvidiaAvailable ? (["openrouter", "nvidia"] as const) : (["openrouter"] as const)).map((name) => {
                    const isNvidia = name === "nvidia";
                    const key = isNvidia ? nvidiaKey : apiKey;
                    const saved = provider?.[name];
                    const feedback = providerFeedback?.provider === name ? providerFeedback : null;
                    return (
                      <section className={styles.providerCard} key={name} aria-labelledby={`studio-key-${name}`}>
                        <div className={styles.providerCardHead}>
                          <div><h4 id={`studio-key-${name}`}>{PROVIDER_NAMES[name]}</h4>
                            <p>{isNvidia ? "Detailed NVIDIA planning" : "Quick and detailed planning"}</p>
                          </div>
                          {saved?.connected && <span className={styles.savedKey}><ShieldCheck size={13} aria-hidden="true" />{isNvidia ? "Saved" : "Connected"}</span>}
                        </div>
                        {saved?.connected ? (
                          <div className={styles.savedKeyRow}>
                            <code>{saved.masked_key}</code>
                            <button type="button" className={styles.textButton} aria-label={`Disconnect ${PROVIDER_NAMES[name]}`}
                              onClick={() => void disconnectProvider(name)} disabled={busy || Boolean(providerBusy)}>
                              {providerBusy === name ? "Disconnecting…" : "Disconnect"}
                            </button>
                          </div>
                        ) : (
                          <form onSubmit={(event) => void connectProvider(event, name)} className={styles.keyForm}>
                            <label className={styles.field}><span>{isNvidia ? "NVIDIA API key" : "OpenRouter API key"}</span>
                              <input type="password" value={key} onChange={(event) => (isNvidia ? setNvidiaKey : setApiKey)(event.target.value)}
                                placeholder={isNvidia ? "nvapi-…" : "sk-or-v1-…"} autoComplete="off" spellCheck={false}
                                minLength={20} maxLength={500} required disabled={Boolean(providerBusy)} />
                            </label>
                            <div className={styles.keyActions}>
                              <button className={styles.secondaryButton} type="submit" disabled={!provider || busy || Boolean(providerBusy) || !key.trim()}>
                                {providerBusy === name ? <Loader2 className={styles.spin} size={15} aria-hidden="true" /> : null}
                                {isNvidia ? "Save key" : "Connect key"}
                              </button>
                              <a href={isNvidia ? "https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b" : "https://openrouter.ai/keys"}
                                target="_blank" rel="noreferrer">Get a key ↗</a>
                            </div>
                          </form>
                        )}
                        {isNvidia && <p className={styles.keyHelp}>NVIDIA checks access when you create a cartoon.</p>}
                        {feedback && <p className={feedback.error ? styles.keyError : styles.keyHelp}
                          role={feedback.error ? "alert" : "status"}>{feedback.message}</p>}
                      </section>
                    );
                  })}
                </div>
                <div className={styles.securityNote}><LockKeyhole size={15} aria-hidden="true" /><span>Saved keys are encrypted. Only masked values are shown here.</span></div>
                <div className={styles.billingNote}><Volume2 size={15} aria-hidden="true" /><span>Built-in voices need no speech API key.</span></div>
              </div>
            </details>
          </div>

          <div className={styles.sideColumn}>
            <StudioProject project={selected} busy={busy || Boolean(renderingId)} onDownload={downloadProject} onRetry={retryProject} />

            <section className={styles.stepsPanel}>
              <h3>How it works</h3>
              <div className={styles.step}><span>1</span><div><strong>Describe your story</strong><small>Add the characters, setting, and what happens next.</small></div></div>
              <div className={styles.step}><span>2</span><div><strong>Bring it to life</strong><small>ClipKaro animates the scenes and gives each character a consistent voice.</small></div></div>
              <div className={styles.step}><span>3</span><div><strong>Watch and download</strong><small>Preview the finished cartoon with captions or save the MP4.</small></div></div>
            </section>
          </div>
        </div>

        <section className={styles.recentPanel} aria-labelledby="studio-library-title">
          <div className={styles.panelHead}>
            <h3 id="studio-library-title">Recent cartoons</h3>
            <div className={styles.libraryFilters} role="group" aria-label="Filter recent cartoons">
              <button type="button" aria-pressed={libraryFilter === "recent"} onClick={() => setLibraryFilter("recent")}>Recent <span>{projects.length - failedCount}</span></button>
              <button type="button" aria-pressed={libraryFilter === "failed"} onClick={() => setLibraryFilter("failed")}>Failed <span>{failedCount}</span></button>
            </div>
          </div>
          {loading ? <div className={styles.loading} role="status"><Loader2 className={styles.spin} size={18} aria-hidden="true" /> Loading projects…</div>
            : visibleProjects.length === 0 ? <div className={styles.empty}>
              <Play size={20} aria-hidden="true" />
              <strong>{libraryFilter === "failed" ? "No failed renders" : "No recent cartoons"}</strong>
              {libraryFilter === "recent" && <span>Create a cartoon above to add it to your library.</span>}
            </div>
            : <div className={styles.recentList}>
              {visibleProjects.map(project => <button type="button" className={styles.recentItem} key={project.id}
                aria-current={selected?.id === project.id ? "true" : undefined} onClick={() => void openProject(project.id)}>
                <StyleArtwork style={project.style} className={styles.recentArtwork} />
                <span className={styles.recentCopy}>
                  <strong dir="auto">{projectTitle(project)}</strong>
                  <small>{styleLabel(project.style)} · {project.duration_seconds}s · {project.aspect_ratio}</small>
                </span>
                <ProjectStatus project={project} />
              </button>)}
            </div>}
        </section>
      </div>
    </AppShell>
  );
}
