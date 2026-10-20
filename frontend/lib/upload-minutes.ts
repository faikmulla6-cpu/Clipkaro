/** UI-only early source-duration check. Backend is the final billing authority. */
export type MinuteAllowance = {
  plan: string;
  processing_minutes_remaining: number;
  source_video_limit_minutes: number;
  shorts_remaining: number;
};

export function uploadQuotaWarning(durationSeconds: number | null, limits: MinuteAllowance | null): string | null {
  if (!limits || durationSeconds === null || !Number.isFinite(durationSeconds) || durationSeconds <= 0) return null;
  const durationMinutes = durationSeconds / 60;
  const maxSource = limits.source_video_limit_minutes;
  if (Number.isFinite(maxSource) && maxSource > 0 && durationMinutes > maxSource + (1 / 60)) {
    return "This video is " + durationMinutes.toFixed(1) + " minutes, but your " + limits.plan +
      " plan allows up to " + maxSource.toFixed(1) + " minutes per source video. Choose a shorter video or review your plan.";
  }
  // /usage rounds balance to one decimal, so permit the maximum possible
  // +0.05-minute rounding margin. Never incorrectly reject a short clip.
  const remaining = limits.processing_minutes_remaining;
  if (Number.isFinite(remaining) && durationMinutes > Math.max(0, remaining) + 0.05) {
    return "This video is " + durationMinutes.toFixed(1) + " minutes, but only " +
      Math.max(0, remaining).toFixed(1) + " Karo Minutes remain on this plan. Uploading it will fail. Choose a shorter video or review your billing plan.";
  }
  if (limits.shorts_remaining <= 0) {
    return "All AI Shorts credits for this billing period have been used. Review your plan before uploading another source video.";
  }
  return null;
}

/** Best-effort local metadata inspection: does not upload or retain user media. */
export async function readLocalVideoDurationSeconds(file: File): Promise<number | null> {
  if (typeof document === "undefined" || typeof URL === "undefined") return null;
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    let finished = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const finish = (duration: number | null) => {
      if (finished) return;
      finished = true;
      if (timeout !== undefined) clearTimeout(timeout);
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
      resolve(duration);
    };
    video.preload = "metadata";
    video.muted = true;
    video.onloadedmetadata = () => {
      const duration = video.duration;
      finish(Number.isFinite(duration) && duration > 0 ? duration : null);
    };
    video.onerror = () => finish(null);
    timeout = setTimeout(() => finish(null), 7000);
    video.src = url;
  });
}
