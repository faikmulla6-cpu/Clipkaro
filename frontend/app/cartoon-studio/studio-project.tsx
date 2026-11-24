import { AlertCircle, ChevronDown, Clapperboard, Clock3, Download, Loader2, Play, RefreshCw, Send, Volume2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import styles from "./cartoon-studio.module.css";

const ANIMATION_STYLES = {
  "2d-cartoon": "2D Cartoon",
  storybook: "Storybook",
  "anime-inspired": "Anime-inspired",
  "flat-vector": "Flat vector",
  "cinematic-jannat": "Jannat cinematic",
} as const;

export const animationStyles = Object.entries(ANIMATION_STYLES);

const VOICE_LABELS: Record<string, string> = {
  af_heart: "Heart · English Female",
  af_bella: "Bella · English Female",
  am_adam: "Adam · English Male",
  hf_alpha: "Alpha · Hindi Female",
  hf_beta: "Beta · Hindi Female",
  hm_omega: "Omega · Hindi Male",
  hm_psi: "Psi · Hindi Male",
  "ur-PK-UzmaNeural": "Uzma · Urdu Female",
  "ur-PK-AsadNeural": "Asad · Urdu Male",
  "hi-IN-SwaraNeural": "Swara · Hinglish Female",
  "hi-IN-MadhurNeural": "Madhur · Hinglish Male",
  "mr-IN-AarohiNeural": "Aarohi · Marathi Female",
  "mr-IN-ManoharNeural": "Manohar · Marathi Male",
};

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
};

const PLANNER_LABELS: Record<string, string> = {
  "inclusionai/ling-3.2-flash:free": "Quick plan",
  "z-ai/glm-5.3-flash": "Detailed plan",
  "nvidia/nemotron-3.5-super-vl": "Detailed plan · NVIDIA",
  "nvidia/nemotron-3.5-super-vl-120b-a12b": "Detailed plan · NVIDIA",
};

export type CartoonProject = {
  id: string;
  title: string;
  prompt: string;
  duration_seconds: number;
  aspect_ratio: string;
  style: string;
  text_model?: string;
  status: string;
  progress: number;
  stage: string;
  error?: string | null;
  storyboard?: {
    title?: string;
    summary?: string;
    characters?: {
      id: string;
      name: string;
      role: string;
      voice_id?: string;
      appearance?: { shirt_color?: string; skin_color?: string };
    }[];
    scenes?: {
      id: string;
      scene_title: string;
      environment: string;
      action?: string;
      dialogue?: string;
      duration?: number;
      actions?: { type: string; start: number; end: number }[];
      speech?: { track: string; text: string; speaker_id: string }[];
    }[];
  };
  caption_timeline?: {
    id: string;
    speaker: string;
    text: string;
    start_seconds: number;
    end_seconds: number;
  }[] | null;
  line_timed_captions?: boolean;
  created_at?: string;
};

export function styleLabel(style: string) {
  return ANIMATION_STYLES[style as keyof typeof ANIMATION_STYLES] || "Cartoon";
}

export function voiceLabel(voice?: string) {
  if (!voice) return "Automatic voice";
  return VOICE_LABELS[voice] || voice.replace(/^[a-z]{2}-[A-Z]{2}-/, "").replace(/Neural$/, "").replaceAll("_", " ");
}

export function projectTitle(project: CartoonProject) {
  const supplied = project.storyboard?.title?.trim();
  const input = supplied || project.title || "";
  const cleaned = input
    .replace(/^\s*(?:#{1,6}\s*|title\s*:\s*)+/i, "")
    .replace(/\*{1,2}/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const title = supplied ? cleaned : cleaned.split(
    /\s+\d+\s*[–—-]\s*\d+\s*(?:s\b|sec|seconds)|\s+\d+\s*seconds?\b/i, 1,
  )[0];
  const limit = supplied ? 72 : 46;
  const characters = Array.from(title);
  if (characters.length <= limit) return title || "Untitled cartoon";
  const shortened = characters.slice(0, limit).join("");
  const lastSpace = shortened.lastIndexOf(" ");
  return (lastSpace > limit / 2 ? shortened.slice(0, lastSpace) : shortened) + "…";
}

export function isRendering(project: CartoonProject) {
  return project.status === "queued" || project.status === "processing";
}

export function ProjectStatus({ project }: { project: CartoonProject }) {
  if (project.status === "ready") return <span className={styles.statusReady}>Ready</span>;
  if (project.status === "failed") return <span className={styles.statusFailed}>Failed</span>;
  return <span className={styles.statusRunning}>{project.status === "queued" ? "Queued" : "Rendering"}</span>;
}

export function StyleArtwork({ style, className }: { style: string; className?: string }) {
  return <span aria-hidden="true" className={[styles.styleArtwork, className].filter(Boolean).join(" ")} data-style={style} />;
}

function formatCueTime(seconds: number) {
  const ms = Math.round(seconds * 1000);
  const minutes = String(Math.floor(ms / 60000)).padStart(2, "0");
  const wholeSeconds = String(Math.floor(ms / 1000) % 60).padStart(2, "0");
  return minutes + ":" + wholeSeconds + "." + String(ms % 1000).padStart(3, "0");
}

function CartoonPreview({ project }: { project: CartoonProject }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadPreview() {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ url: string }>("/cartoon-studio/projects/" + project.id + "/download");
      setUrl(result.url);
    } catch {
      setError("The preview could not load. Try again or download the MP4.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.preview}>
      {url ? (
        <video src={url} controls autoPlay playsInline preload="metadata" aria-label={projectTitle(project) + " preview"}
          onError={() => { setUrl(""); setError("The preview could not play. Try again or download the MP4."); }} />
      ) : (
        <div className={styles.previewCover}>
          <StyleArtwork style={project.style} className={styles.previewArtwork} />
          <button type="button" className={styles.previewButton} disabled={busy} onClick={loadPreview}>
            {busy ? <Loader2 size={16} className={styles.spin} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
            {busy ? "Loading preview…" : "Play preview"}
          </button>
        </div>
      )}
      {error && <p className={styles.previewError} role="alert">{error}</p>}
    </div>
  );
}

export function StudioProject({ project, busy, onDownload, onRetry }: {
  project: CartoonProject | null;
  busy: boolean;
  onDownload: () => void;
  onRetry: () => void;
}) {
  const characters = project?.storyboard?.characters || [];
  const scenes = project?.storyboard?.scenes || [];
  const ready = project?.status === "ready";
  const captionTimeline = project?.caption_timeline;
  const planner = project?.text_model ? PLANNER_LABELS[project.text_model] : "";

  return (
    <section className={styles.projectPanel} id="studio-current-project" tabIndex={-1} aria-labelledby="studio-project-title">
      <div className={styles.panelHead}>
        <div>
          <span className={styles.kicker}>03 · Current project</span>
          <h3 id="studio-project-title" dir="auto">{project ? projectTitle(project) : "Your cartoon preview"}</h3>
        </div>
        {project && <ProjectStatus project={project} />}
      </div>
      {!project ? (
        <div className={styles.projectEmpty}>
          <span className={styles.emptyIcon}><Clapperboard size={27} aria-hidden="true" /></span>
          <p>Create a cartoon or open a recent project to see its preview, voices, and captions here.</p>
        </div>
      ) : (
        <>
          <div className={styles.projectMeta}>{styleLabel(project.style)} · {project.duration_seconds}s · {project.aspect_ratio}{planner && <> · {planner}</>}</div>
          {ready && <CartoonPreview key={project.id} project={project} />}
          {isRendering(project) && <div className={styles.progressWrap}>
            <div className={styles.progressLabels}><span>{STAGE_LABELS[project.stage] || "Rendering your cartoon"}</span><strong>{project.progress}%</strong></div>
            <progress className={styles.progressTrack} aria-label="Cartoon render progress" value={project.progress} max={100} />
            <small>Rendering continues while you work elsewhere.</small>
          </div>}
          {project.error && <div className={styles.projectError}><AlertCircle size={16} aria-hidden="true" />{project.error}</div>}
          {(ready || project.status === "failed") && (
            <div className={styles.projectActions}>
              {ready ? <>
                {project.aspect_ratio === "9:16" && <Link className={styles.primaryButton} href={"/post-karo?cartoon=" + encodeURIComponent(project.id)}>
                  <Send size={17} aria-hidden="true" /> Post Karo
                </Link>}
                <button className={styles.secondaryButton} type="button" onClick={onDownload}><Download size={17} aria-hidden="true" /> Download MP4</button>
              </>
                : <button className={styles.secondaryButton} type="button" onClick={onRetry} disabled={busy}><RefreshCw size={16} aria-hidden="true" /> Retry project</button>}
            </div>
          )}
          {ready && project.aspect_ratio !== "9:16" && <p className={styles.projectMeta}>Choose 9:16 when creating a cartoon for Post Karo.</p>}
          {ready && !!captionTimeline?.length && (
            <details key={project.id + "-captions"} className={styles.captionTimeline}>
              <summary><span><Clock3 size={17} aria-hidden="true" /> Caption Timeline</span><ChevronDown size={16} aria-hidden="true" /></summary>
              <p>Want a different voice? Use these captions and times to add your own realistic voice to this cartoon.</p>
              {project.line_timed_captions && <p>Some captions are synced by spoken line.</p>}
              <ol>
                {captionTimeline.map(cue => (
                  <li key={cue.id}>
                    <span className={styles.cueTime}>{formatCueTime(cue.start_seconds)} – {formatCueTime(cue.end_seconds)}</span>
                    <div><strong dir="auto">{cue.speaker}</strong><span dir="auto">{cue.text}</span></div>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {characters.length > 0 && <div className={styles.characters}>
            <h4 className={styles.sectionTitle}>Characters and voices</h4>
            <div className={styles.characterGrid}>
              {characters.map(character => <div className={styles.characterCard} key={character.id}>
                <div className={styles.characterAvatar} style={{ background: character.appearance?.shirt_color || "#e87552" }} aria-hidden="true">
                  <span style={{ background: character.appearance?.skin_color || "#e9b58f" }} />
                </div>
                <div><strong dir="auto">{character.name}</strong><small>{character.role}</small><span><Volume2 size={12} aria-hidden="true" /> {voiceLabel(character.voice_id)}</span></div>
              </div>)}
            </div>
          </div>}
          {!!scenes.length && <details key={project.id + "-scenes"} className={styles.captionTimeline}>
            <summary><span><Clapperboard size={17} aria-hidden="true" /> Storyboard · {scenes.length} {scenes.length === 1 ? "scene" : "scenes"}</span><ChevronDown size={16} aria-hidden="true" /></summary>
            {project.storyboard?.summary && <p dir="auto">{project.storyboard.summary}</p>}
            <ol>
              {scenes.map((scene, index) => <li className={styles.sceneRow} key={scene.id}>
                <span className={styles.sceneNumber} aria-label={`Scene ${index + 1}`}>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong dir="auto">{scene.scene_title || scene.environment}{scene.duration ? " · " + scene.duration + "s" : ""}</strong>
                  {scene.actions?.length ? <span>{scene.actions.map(action =>
                    `${action.start.toFixed(1)}–${action.end.toFixed(1)}s ${action.type.replaceAll("_", " ")}`,
                  ).join(" · ")}</span> : scene.action && <span dir="auto">{scene.action}</span>}
                  {scene.speech?.map((line, lineIndex) => <span dir="auto" key={lineIndex}>{line.track === "narration" ? "Narrator" : characters.find(character => character.id === line.speaker_id)?.name || "Dialogue"} · “{line.text}”</span>)}
                  {!scene.speech && scene.dialogue && <span dir="auto">“{scene.dialogue}”</span>}
                </div>
              </li>)}
            </ol>
          </details>}
        </>
      )}
    </section>
  );
}
