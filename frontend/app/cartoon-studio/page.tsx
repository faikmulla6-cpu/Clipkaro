"use client";

import { AppShell } from "@/components/AppShell";
import { api, deleteJSON, postJSON } from "@/lib/api";
import {
  AlertCircle, Check, Clapperboard, Clock3, Download, KeyRound, Loader2,
  LockKeyhole, Play, RefreshCw, ShieldCheck, Sparkles, Volume2, WandSparkles,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import styles from "./cartoon-studio.module.css";

type Character = {
  id: string;
  name: string;
  role: string;
  species?: string;
  voice_id?: string;
  appearance?: { shirt_color?: string; hair_color?: string; skin_color?: string };
};
type Scene = {
  id: string;
  scene_title: string;
  environment: string;
  action: string;
  dialogue: string;
  speaker_id: string;
  start?: number;
  duration?: number;
  actions?: {type: string; character_id: string; start: number; end: number}[];
  speech?: {track: string; text: string; speaker_id: string}[];
};
type Storyboard = {
  title?: string;
  summary?: string;
  characters?: Character[];
  scenes?: Scene[];
};
type CartoonProject = {
  id: string;
  title: string;
  prompt: string;
  duration_seconds: number;
  aspect_ratio: string;
  style: string;
  language: string;
  text_model?: string;
  status: string;
  progress: number;
  stage: string;
  error?: string | null;
  storyboard?: Storyboard;
  editable_available?: boolean;
  voiceover_kit_available?: boolean;
  line_timed_captions?: boolean;
  created_at?: string;
};
type ProviderStatus = {
  openrouter: SavedProvider;
  nvidia?: SavedProvider;
  storyboard_test_enabled?: boolean;
};
type SavedProvider = { connected: boolean; masked_key: string; validated_at?: string | null };
type PlannerProvider = "nvidia" | "openrouter";
type ProjectPlanner = "free" | "glm" | "nvidia";
const PROVIDER_NAMES: Record<PlannerProvider, string> = { openrouter: "OpenRouter", nvidia: "NVIDIA API" };
const EMPTY_PROVIDER: SavedProvider = { connected: false, masked_key: "" };
const PROJECT_PLANNER_NAMES: Record<string, string> = {
  "inclusionai/ling-3.2-flash:free": "Ling 3.2 Flash · Free planning",
  "z-ai/glm-5.3-flash": "GLM",
  "nvidia/nemotron-3.5-super-vl": "NVIDIA Nemotron",
  "nvidia/nemotron-3.5-super-vl-120b-a12b": "NVIDIA API",
};
type TTSModel = { id: string; name: string; voices: string[]; languages: string[]; voices_by_language?: Record<string, string[]>; description: string };
type TTSResponse = { models: TTSModel[]; default_model: string };

const STAGE_LABELS: Record<string, string> = {
  queued: "Waiting in queue",
  preparing: "Preparing your project",
  story_planning: "Writing your story",
  story_ready: "Story and characters ready",
  voice_generation: "Creating character voices",
  animating: "Building character animation",
  checking: "Checking scenes",
  rendering: "Rendering your video",
  uploading: "Saving your MP4",
  ready: "Ready to download",
  failed: "Needs attention",
};

export default function CartoonStudioPage() {
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [models, setModels] = useState<TTSModel[]>([]);
  const [requestedTtsModel, setTtsModel] = useState("");
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

  const mergeProject = useCallback((project: CartoonProject) => {
    setSelected(project);
    setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
  }, []);

  const loadModels = useCallback(async () => {
    const response = await api<TTSResponse>("/cartoon-studio/tts-models");
    setModels(response.models || []);
    setTtsModel((current) => current || response.default_model || response.models?.[0]?.id || "");
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
      const active = (projectData || []).find((item) => item.status === "processing" || item.status === "queued");
      if (active) setSelected(active);
      setLoading(false);
    }).catch((cause) => {
      if (!cancelled) {
        setError(cause instanceof Error ? cause.message : "Cartoon Studio could not be loaded.");
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    loadModels().catch((cause) => {
      setError(cause instanceof Error ? cause.message : "Voice models could not be loaded.");
    });
  }, [loadModels]);

  useEffect(() => {
    if (!selected || (selected.status !== "queued" && selected.status !== "processing")) return;
    const timer = window.setInterval(() => {
      api<CartoonProject>("/cartoon-studio/projects/" + selected.id)
        .then(mergeProject)
        .catch(() => null);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selected?.id, selected?.status, mergeProject]);

  const activeCharacters = useMemo(
    () => selected?.storyboard?.characters || [],
    [selected?.storyboard?.characters],
  );
  const isRendering = selected?.status === "queued" || selected?.status === "processing";
  const connected = Boolean(provider?.openrouter.connected);
  const voiceModels = models.filter(model => model.languages?.includes(language)
    ?? (model.id === "system/edge-tts-urdu" && language === "ur"));
  const selectedVoiceModel = voiceModels.find(model => model.id === requestedTtsModel)
    || (language === "ur" ? voiceModels.find(model => model.id === "system/edge-tts-urdu") : undefined)
    || voiceModels[0];
  const ttsModel = selectedVoiceModel?.id || "";
  const voiceChoices = selectedVoiceModel?.voices_by_language?.[language] || selectedVoiceModel?.voices || [];
  const voiceId = voiceChoices.includes(requestedVoiceId) ? requestedVoiceId : "";
  const nvidiaAvailable = Boolean(provider?.storyboard_test_enabled && provider?.nvidia);
  const nvidiaConnected = Boolean(provider?.nvidia?.connected);
  const missingProvider = projectPlanner === "nvidia"
    ? (nvidiaConnected ? "" : "NVIDIA API")
    : (connected ? "" : "OpenRouter");

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
    if (busy || providerBusy || missingProvider || !ttsModel) return;
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
      body.set("tts_model", ttsModel);
      body.set("voice_id", voiceId);
      body.set("story_planner", projectPlanner);
      if (projectPlanner !== "nvidia" && reference) body.set("reference_video", reference);
      const project = await api<CartoonProject>("/cartoon-studio/projects", { method: "POST", body });
      mergeProject(project);
      setNotice("Your cartoon is queued. You can leave this page while it renders.");
      setReference(null);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : "Cartoon generation could not start.");
    } finally {
      setBusy(false);
    }
  }

  async function openProject(projectId: string) {
    setError("");
    try {
      const project = await api<CartoonProject>("/cartoon-studio/projects/" + projectId);
      mergeProject(project);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Project details could not be loaded.");
    }
  }

  async function retryProject() {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      const project = await api<CartoonProject>(
        "/cartoon-studio/projects/" + selected.id + "/retry",
        { method: "POST" },
      );
      mergeProject(project);
      setNotice("Retry queued. Saved storyboard and completed voice files will be reused.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The project could not be retried.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadProject(editable = false) {
    if (!selected || selected.status !== "ready") return;
    setError("");
    try {
      const result = await api<{ url: string }>("/cartoon-studio/projects/" + selected.id + (editable ? "/editable" : "/download"));
      window.location.assign(result.url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The MP4 could not be downloaded.");
    }
  }

  return (
    <AppShell
      title="Cartoon Studio"
      subtitle="Create original animated stories with consistent characters and their own voices."
    >
      <div className={styles.page}>
        <div className={styles.hero}>
          <div>
            <span className={styles.eyebrow}><Sparkles size={13} /> CARTOON STUDIO · BETA</span>
            <h2>Give your story <em>a voice.</em></h2>
            <p>Choose a story planner and describe your scene. Each character gets a saved voice, and HyperFrames builds the animation.</p>
          </div>
          <div className={styles.heroMark}><Clapperboard size={32} /><span>2D<br />ANIMATION</span></div>
        </div>

        {error && <div className={styles.alertError} role="alert"><AlertCircle size={17} />{error}<button onClick={() => setError("")} aria-label="Dismiss error">×</button></div>}
        {notice && <div className={styles.alertSuccess} role="status"><Check size={17} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss message">×</button></div>}

        <div className={styles.grid}>
          <section className={styles.panel}>
            <div className={styles.panelHead}>
              <div><span className={styles.kicker}>01 · YOUR STORY</span><h3>Create a cartoon</h3></div>
              <span className={styles.freeBadge}>No image-generation credits</span>
            </div>
            <form onSubmit={createCartoon} className={styles.form}>
              <label className={styles.field}>
                <span>What should happen in your story?</span>
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  placeholder="Example: A curious little fox finds a glowing map in the forest and asks a wise owl for help..."
                  rows={5}
                  maxLength={3000}
                  required
                />
                <small>{prompt.length}/3000 · Original, family-friendly stories work best.</small>
              </label>
              <div className={styles.fieldsTwo}>
                <label className={styles.field}><span>Video length</span>
                  <select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>
                    <option value={15}>15 seconds</option><option value={30}>30 seconds</option>
                    <option value={45}>45 seconds</option><option value={60}>60 seconds</option>
                  </select>
                </label>
                <label className={styles.field}><span>Aspect ratio</span>
                  <select value={ratio} onChange={(event) => setRatio(event.target.value)}>
                    <option value="9:16">9:16 · Reels / Shorts</option>
                    <option value="16:9">16:9 · YouTube</option><option value="1:1">1:1 · Square</option>
                    <option value="4:5">4:5 · Portrait posts</option>
                  </select>
                </label>
                <label className={styles.field}><span>Animation style</span>
                  <select value={style} onChange={(event) => {
                    const nextStyle = event.target.value;
                    setStyle(nextStyle);
                    if (nextStyle === "cinematic-jannat") {
                      setLanguage("ur");
                      setTtsModel("system/edge-tts-urdu");
                    }
                  }}>
                    <option value="2d-cartoon">2D Cartoon</option><option value="storybook">Storybook</option>
                    <option value="anime-inspired">Anime-inspired</option><option value="flat-vector">Flat vector</option><option value="cinematic-jannat">Jannat cinematic (reference)</option>
                  </select>
                  {style === "cinematic-jannat" && (
                    <small className={styles.languageHint}>A suspense storytelling preset with consistent characters, timed movement and Urdu word-timed voices. Supports every aspect ratio.</small>
                  )}
                </label>
                <label className={styles.field}><span>Story language</span>
                  <select value={language} onChange={(event) => setLanguage(event.target.value)} disabled={style === "cinematic-jannat"}>
                    <option value="hi">Hindi</option><option value="hinglish">Hinglish</option>
                    <option value="en">English</option><option value="mr">Marathi</option><option value="ur">Urdu</option><option value="auto">Auto</option>
                  </select>
                </label>
              </div>
              <label className={styles.field}><span>Story planner</span>
                <select value={projectPlanner} onChange={(event) => setProjectPlanner(event.target.value as ProjectPlanner)} disabled={busy}>
                  <option value="free">Ling 3.2 Flash · Free planning</option>
                  <option value="glm">GLM via OpenRouter · Paid planning</option>
                  {nvidiaAvailable && <option value="nvidia">NVIDIA API</option>}
                </select>
                {projectPlanner === "free" && <small>Planning uses the free OpenRouter model.</small>}
              </label>
              <label className={styles.field}>
                <span>Voice model</span>
                <select value={ttsModel} onChange={(event) => {setTtsModel(event.target.value);setVoiceId("");}} disabled={voiceModels.length === 0}>
                  {voiceModels.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
                </select>
                <small>{selectedVoiceModel?.description}</small>
              </label>
              {voiceChoices.length > 0 && <label className={styles.field}><span>Narrator / lead voice</span>
                <select value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>
                  <option value="">Match the character automatically</option>
                  {voiceChoices.map(voice => <option key={voice} value={voice}>{voice}</option>)}
                </select>
                <small>Other characters keep their own assigned voices. Providers without word timestamps use audio alignment for captions.</small>
              </label>}
              {projectPlanner !== "nvidia" && <label className={styles.fileField}>
                <span>Optional reference video</span>
                <input type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska" onChange={(event) => setReference(event.target.files?.[0] || null)} />
                <small>{reference ? reference.name : "Up to 50 MB. Used only to analyse visual style; not required."}</small>
              </label>}
              <button className={styles.primaryButton} type="submit" disabled={Boolean(missingProvider || busy || providerBusy || !ttsModel)}>
                {busy ? <Loader2 className={styles.spin} size={18} /> : <WandSparkles size={18} />}
                {busy ? "Queuing your cartoon…" : "Create my cartoon"}
              </button>
              {createError && <div className={styles.alertError} role="alert"><AlertCircle size={17} />{createError}</div>}
              {missingProvider && <a className={styles.setupLink} href="#studio-api-keys">Connect your {missingProvider} key</a>}
            </form>
          </section>

          <div className={styles.sideColumn}>
            <section className={styles.providerPanel} id="studio-api-keys" aria-labelledby="studio-api-keys-title">
              <div className={styles.panelHead}>
                <div><h3 id="studio-api-keys-title">API keys</h3><p>Connect once and use your saved keys for every cartoon.</p></div>
                <span className={styles.keysIcon}><KeyRound size={20} aria-hidden="true" /></span>
              </div>
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
                          <p>{isNvidia ? "Nemotron story planning" : "Ling and GLM story planning"}</p>
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
                      {isNvidia && <p className={styles.keyHelp}>NVIDIA checks access when you create. Use fictional prompts for preview evaluation.</p>}
                      {feedback && <p className={feedback.error ? styles.keyError : styles.keyHelp}
                        role={feedback.error ? "alert" : "status"}>{feedback.message}</p>}
                    </section>
                  );
                })}
              </div>
              {provider?.storyboard_test_enabled && !nvidiaAvailable && <p className={styles.keyHelp}>NVIDIA key setup is unavailable on this backend.</p>}
              <div className={styles.securityNote}><LockKeyhole size={15} aria-hidden="true" /><span>Saved keys are encrypted. Only masked values are shown here.</span></div>
              <div className={styles.billingNote}><Volume2 size={15} aria-hidden="true" /><span>Built-in voices need no speech API key.</span></div>
            </section>

            <section className={styles.stepsPanel}>
              <span className={styles.kicker}>HOW IT WORKS</span>
              <div className={styles.step}><span>1</span><div><strong>Build the characters</strong><small>Structured character designs, reusable across scenes.</small></div></div>
              <div className={styles.step}><span>2</span><div><strong>Give each one a voice</strong><small>One saved voice ID per character, not one random voice per line.</small></div></div>
              <div className={styles.step}><span>3</span><div><strong>Animate and export</strong><small>SVG rigs, GSAP motion, HyperFrames and FFmpeg.</small></div></div>
            </section>
          </div>
        </div>

        {selected && (
          <section className={styles.projectPanel}>
            <div className={styles.panelHead}>
              <div><span className={styles.kicker}>03 · CURRENT PROJECT</span><h3>{selected.storyboard?.title || selected.title}</h3>
                {selected.text_model && <small>{PROJECT_PLANNER_NAMES[selected.text_model]}</small>}
              </div>
              <span className={selected.status === "ready" ? styles.statusReady : selected.status === "failed" ? styles.statusFailed : styles.statusRunning}>
                {selected.status === "ready" ? "Ready" : selected.status === "failed" ? "Failed" : "Rendering"}
              </span>
            </div>
            <p className={styles.projectPrompt}>{selected.storyboard?.summary || selected.prompt}</p>
            {isRendering && <div className={styles.progressWrap}>
              <div className={styles.progressLabels}><span>{STAGE_LABELS[selected.stage] || selected.stage}</span><strong>{selected.progress}%</strong></div>
              <div className={styles.progressTrack}><span style={{ width: selected.progress + "%" }} /></div>
              <small>Keep this tab open to watch progress, or return later from Recent projects.</small>
            </div>}
            {selected.error && <div className={styles.projectError}><AlertCircle size={16} />{selected.error}</div>}
            {selected.status === "ready" && selected.line_timed_captions && (
              <p className={styles.projectPrompt}>Some captions are synced by spoken line because word-level timing was unavailable.</p>
            )}
            {activeCharacters.length > 0 && <div className={styles.characters}>
              <div className={styles.sectionTitle}><strong>Characters and their voices</strong><small>Saved voice identities</small></div>
              <div className={styles.characterGrid}>
                {activeCharacters.map((character) => <div className={styles.characterCard} key={character.id}>
                  <div className={styles.characterAvatar} style={{ background: character.appearance?.shirt_color || "#e87552" }}>
                    <span style={{ background: character.appearance?.skin_color || "#e9b58f" }} />
                  </div>
                  <div><strong>{character.name}</strong><small>{character.role}</small><span><Volume2 size={12} /> {character.voice_id || "Voice assigned"}</span></div>
                </div>)}
              </div>
            </div>}
            {selected.storyboard?.scenes?.length ? <div className={styles.scenes}>
              <div className={styles.sectionTitle}><strong>Storyboard</strong><small>{selected.storyboard.scenes.length} scenes</small></div>
              {selected.storyboard.scenes.map((scene, index) => <div className={styles.sceneRow} key={scene.id}>
                <span className={styles.sceneNumber}>{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{scene.scene_title || scene.environment}{scene.duration ? " · " + scene.duration + "s" : ""}</strong>
                  <small>{scene.actions?.map(action => action.start.toFixed(1) + "–" + action.end.toFixed(1) + "s: " + action.type.replaceAll("_", " ")).join(" · ") || scene.action}</small>
                  {scene.speech?.map((line,index) => <p key={index}>{line.track === "narration" ? "Narrator" : line.speaker_id}: “{line.text}”</p>)}
                  {!scene.speech && scene.dialogue && <p>“{scene.dialogue}”</p>}</div>
              </div>)}
            </div> : null}
            {selected.status === "ready" && selected.voiceover_kit_available && (
              <p className={styles.projectPrompt}>To add your own voice, download the caption timeline. Generate the lines in a service such as ElevenLabs, then place each clip at its listed time in your editor.</p>
            )}
            <div className={styles.projectActions}>
              {selected.status === "ready" && <><button className={styles.primaryButton} type="button" onClick={() => downloadProject()}><Download size={17} /> Download MP4</button>
                {selected.editable_available && <button className={styles.secondaryButton} type="button" onClick={() => downloadProject(true)}><Download size={17} /> {selected.voiceover_kit_available ? "Editable project & caption timeline" : "Editable project"}</button>}</>}
              {selected.status === "failed" && <button className={styles.secondaryButton} type="button" onClick={retryProject} disabled={busy}><RefreshCw size={16} /> Retry project</button>}
              {isRendering && <span><Loader2 className={styles.spin} size={15} /> Rendering in the background</span>}
            </div>
          </section>
        )}

        <section className={styles.recentPanel}>
          <div className={styles.panelHead}><div><span className={styles.kicker}>YOUR LIBRARY</span><h3>Recent cartoons</h3></div><span>{projects.length} projects</span></div>
          {loading ? <div className={styles.loading}><Loader2 className={styles.spin} /> Loading projects...</div> :
            projects.length === 0 ? <div className={styles.empty}><Play size={20} /><strong>Your first cartoon starts here</strong><span>Create a story above to see its storyboard, voices and MP4 here.</span></div> :
            <div className={styles.recentList}>{projects.map((project) => <button type="button" className={styles.recentItem} key={project.id} onClick={() => openProject(project.id)}>
              <span className={styles.recentIcon}><Clapperboard size={18} /></span>
              <span className={styles.recentCopy}><strong>{project.storyboard?.title || project.title}</strong><small>{project.duration_seconds}s · {project.aspect_ratio} · {new Date(project.created_at || Date.now()).toLocaleDateString()}</small></span>
              <span className={project.status === "ready" ? styles.statusReady : project.status === "failed" ? styles.statusFailed : styles.statusRunning}>{project.status}</span>
            </button>)}</div>}
        </section>
      </div>
    </AppShell>
  );
}
