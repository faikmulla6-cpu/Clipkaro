/** Secure, deterministic Smart Layout v2 geometry.
 *
 * Preview and FFmpeg must consume the same versioned crop rectangles. This
 * module does not fetch media, create exports, inspect faces, call AI APIs or
 * alter storage permissions. Callers must supply an already-authorized video.
 */
export type LayoutKind = "dual_stack" | "single" | "speaker_focus" | "wide";
export type Rect = [number, number, number, number]; // source pixels x/y/w/h
export type SpeakerChange = [number, number]; // scene-relative seconds, face index

export type SmartLayoutScene = {
  start: number;
  end: number;
  layout: LayoutKind;
  crops: Rect[];
  switches: SpeakerChange[];
  caption_zone: "middle" | "bottom";
};

export type SmartLayoutPlan = {
  version: 2;
  requested_mode: "auto" | "dual_stack" | "speaker_focus";
  source_width: number;
  source_height: number;
  source_start: number;
  duration: number;
  preview_width: 360;
  preview_height: 640;
  scenes: SmartLayoutScene[];
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const numberIn = (n: unknown, minimum: number, maximum: number): n is number =>
  finite(n) && n >= minimum && n <= maximum;
const validMode = (m: unknown) => m === "auto" || m === "dual_stack" || m === "speaker_focus";
const validKind = (m: unknown) => m === "dual_stack" || m === "single" || m === "speaker_focus" || m === "wide";

export function parseSmartLayoutPlan(input: unknown): SmartLayoutPlan | null {
  if (!isObject(input) || input.version !== 2 || !validMode(input.requested_mode)
      || !Number.isInteger(input.source_width) || !numberIn(input.source_width, 240, 16384)
      || !Number.isInteger(input.source_height) || !numberIn(input.source_height, 160, 16384)
      || !numberIn(input.source_start, 0, 86400)
      || !numberIn(input.duration, .1, 180)
      || input.preview_width !== 360 || input.preview_height !== 640
      || !Array.isArray(input.scenes) || input.scenes.length < 1 || input.scenes.length > 24) return null;

  const width = input.source_width as number;
  const height = input.source_height as number;
  const duration = input.duration as number;
  let previousEnd = 0;

  for (const raw of input.scenes) {
    if (!isObject(raw) || !validKind(raw.layout)
        || !numberIn(raw.start, 0, duration)
        || !numberIn(raw.end, 0, duration + .01)
        || (raw.end as number) - (raw.start as number) < .03
        || Math.abs((raw.start as number) - previousEnd) > .065
        || !Array.isArray(raw.crops)
        || !Array.isArray(raw.switches) || raw.switches.length > 42
        || raw.caption_zone !== (raw.layout === "dual_stack" ? "middle" : "bottom")) return null;

    const count = raw.layout === "dual_stack" || raw.layout === "speaker_focus" ? 2 : 1;
    if (raw.crops.length !== count) return null;
    for (const crop of raw.crops) {
      if (!Array.isArray(crop) || crop.length !== 4 || !crop.every(Number.isInteger)) return null;
      const [x, y, w, h] = crop;
      if (x < 0 || y < 0 || w < 2 || h < 2 || x + w > width || y + h > height) return null;
    }
    if (raw.layout === "dual_stack" && JSON.stringify(raw.crops[0]) === JSON.stringify(raw.crops[1])) return null;
    if (raw.layout !== "speaker_focus" && raw.layout !== "dual_stack" && raw.switches.length) return null;
    let lastTime = -1;
    for (const change of raw.switches) {
      if (!Array.isArray(change) || change.length !== 2
          || !numberIn(change[0], 0, (raw.end as number) - (raw.start as number) + .05)
          || change[0] < lastTime || !Number.isInteger(change[1])
          || change[1] < 0 || change[1] >= count) return null;
      lastTime = change[0];
    }
    previousEnd = raw.end as number;
  }
  if (Math.abs(previousEnd - duration) > .065) return null;
  return input as unknown as SmartLayoutPlan;
}

/** Report how much of the actual analyzed clip can truly show two live faces. */
export function dualStackCoverageSeconds(plan: SmartLayoutPlan): number {
  return plan.scenes.reduce((total, scene) => total + (scene.layout === "dual_stack" ? scene.end - scene.start : 0), 0);
}

export function findScene(plan: SmartLayoutPlan, sourceTime: number): SmartLayoutScene | null {
  if (!finite(sourceTime)) return null;
  const local = sourceTime - plan.source_start;
  return plan.scenes.find(s => s.start <= local && local < s.end) ||
    (Math.abs(local - plan.duration) < .001 ? plan.scenes.at(-1) || null : null);
}

const smoothstep = (value: number): number => {
  const v = Math.max(0, Math.min(1, value));
  return v * v * (3 - 2 * v);
};

export function focusRectAt(scene: SmartLayoutScene, sceneRelativeTime: number): Rect {
  const first = scene.crops[0];
  if (scene.layout !== "speaker_focus" || scene.crops.length < 2 || !scene.switches.length) return first;
  // FFmpeg's focus expression interpolates only x; y and crop size remain
  // those of the scene's first speaker. Transition lasts up to 0.4 seconds.
  let currentIndex = scene.switches[0][1];
  let previousChange = scene.switches[0][0];
  let x = scene.crops[currentIndex][0];
  for (let j = 1; j < scene.switches.length; j += 1) {
    const [nextTime, nextIndex] = scene.switches[j];
    const begin = Math.max(previousChange, nextTime - .2);
    const end = nextTime + .2;
    if (sceneRelativeTime < begin) break;
    const nextX = scene.crops[nextIndex][0];
    if (sceneRelativeTime < end) {
      const eased = smoothstep((sceneRelativeTime - begin) / Math.max(.05, end - begin));
      x += (nextX - x) * eased;
      break;
    }
    x = nextX;
    currentIndex = nextIndex;
    previousChange = nextTime;
  }
  return [x, first[1], first[2], first[3]];
}

/** Return the two independent source crops in the order rendered by FFmpeg.
 * Switches are scene-local timestamps and apply only after confirmed turns.
 */
export function dualStackCropsAt(scene: SmartLayoutScene, sceneRelativeTime: number): [Rect, Rect] {
  const first = scene.crops[0];
  const second = scene.crops[1];
  let top = 0;
  for (const [time, speaker] of scene.switches) {
    if (sceneRelativeTime + 0.0001 < time) break;
    top = speaker;
  }
  return top === 1 ? [second, first] : [first, second];
}

/** Paint only layout pixels. Existing editor captions stay in React above canvas.
 * A SecurityError means private media is not CORS-enabled: fail visibly in the
 * caller; NEVER broaden B2 bucket CORS or disclose a signed URL as a workaround.
 */
export function paintSmartLayoutFrame(
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  plan: SmartLayoutPlan,
  sourceTime: number,
): boolean {
  const scene = findScene(plan, sourceTime);
  if (!scene || video.readyState < 2) return false;
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  if (w <= 0 || h <= 0) return false;
  const draw = (rect: Rect, dx: number, dy: number, dw: number, dh: number) =>
    ctx.drawImage(video, rect[0], rect[1], rect[2], rect[3], dx, dy, dw, dh);
  ctx.save();
  try {
    ctx.clearRect(0, 0, w, h);
    if (scene.layout === "dual_stack") {
      const band = (640 * .12 | 0) & ~1;
      const half = (640 - band) / 2;
      const relative = sourceTime - plan.source_start - scene.start;
      const [top, bottom] = dualStackCropsAt(scene, relative);
      draw(top, 0, 0, w, half / 640 * h);
      ctx.fillStyle = "#111827";
      ctx.fillRect(0, half / 640 * h, w, band / 640 * h);
      draw(bottom, 0, (half + band) / 640 * h, w, half / 640 * h);
    } else if (scene.layout === "wide") {
      const sourceAspect = plan.source_width / plan.source_height;
      const outputAspect = w / h;
      const rw = sourceAspect > outputAspect ? plan.source_height * outputAspect : plan.source_width;
      const rh = sourceAspect > outputAspect ? plan.source_height : plan.source_width / outputAspect;
      const bx = (plan.source_width - rw) / 2;
      const by = (plan.source_height - rh) / 2;
      ctx.filter = "blur(14px)";
      draw([bx, by, rw, rh], 0, 0, w, h);
      ctx.filter = "none";
      const scale = Math.min(w / plan.source_width, h / plan.source_height);
      const fw = plan.source_width * scale;
      const fh = plan.source_height * scale;
      draw(scene.crops[0], (w - fw) / 2, (h - fh) / 2, fw, fh);
    } else {
      const relative = sourceTime - plan.source_start - scene.start;
      draw(focusRectAt(scene, relative), 0, 0, w, h);
    }
    return true;
  } finally {
    ctx.restore();
  }
}
