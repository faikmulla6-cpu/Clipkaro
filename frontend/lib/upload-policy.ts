/** Keep in sync with backend/app/services/upload_limits.py. */
export const SOURCE_UPLOAD_LIMIT_MB: Record<string, number> = {
  free: 500,
  mini_pass: 500,
  creator: 1024,
  growth: 2048,
  pro: 4096,
  agency: 4096,
};

export function allowedUploadMb(plan: string | undefined, multipartEnabled: boolean): number {
  const planCap = SOURCE_UPLOAD_LIMIT_MB[(plan || "free").toLowerCase()] ?? 500;
  return multipartEnabled ? planCap : Math.min(500, planCap);
}
