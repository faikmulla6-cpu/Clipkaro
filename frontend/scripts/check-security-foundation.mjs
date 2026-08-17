import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Security foundation contract failed: ${label}`);
};
const yamlKeyCount = (text, key) => (text.match(new RegExp(`^\\s+${key}:`, "gm")) || []).length;

const authProvider = read("frontend/components/AuthProvider.tsx");
const authForm = read("frontend/components/AuthForm.tsx");
const forgotPage = read("frontend/app/forgot-password/page.tsx");
const resetPage = read("frontend/app/reset-password/page.tsx");
const caddy = read("Caddyfile");
const compose = read("docker-compose.hostinger.yml");
const backendDocker = read("backend/Dockerfile");
const frontendDocker = read("frontend/Dockerfile");
const worker = read("backend/app/worker.py");
const jobs = read("backend/app/services/jobs.py");
const main = read("backend/app/main.py");
const mediaJob = read("backend/app/media_job.py");
const cloudUploads = read("backend/app/api/cloud_uploads.py");
const migration = read("backend/migrations/versions/20260817_01_no_vps_schema.py");

requireText(authProvider, '"/forgot-password"', "forgot-password route must stay public");
requireText(authProvider, '"/reset-password"', "reset-password route must stay public");
requireText(authForm, 'href="/forgot-password"', "login must expose password recovery");
requireText(authForm, 'safePostAuthPath', "post-auth redirects must pass through the internal-path sanitizer");
requireText(authForm, 'resolved.origin !== window.location.origin', "post-auth redirects must reject cross-origin destinations");
requireText(forgotPage, '/auth/password/forgot', "forgot page must call generic recovery API");
requireText(resetPage, 'window.history.replaceState', "reset token must be removed from browser history");
requireText(resetPage, '/auth/password/reset', "reset page must submit one-time token to backend");

requireText(caddy, "Content-Security-Policy", "edge CSP must be present");
requireText(caddy, "frame-ancestors 'none'", "CSP must block framing");
requireText(caddy, "object-src 'none'", "CSP must block plugin/object content");
requireText(caddy, "https://*.razorpay.com", "CSP must explicitly scope payment origins");

requireText(compose, "UPLOAD_SCAN_REQUIRED: ${UPLOAD_SCAN_REQUIRED:-true}", "production upload scanning must fail closed");
requireText(compose, "CLAMAV_HOST: clamav", "API must use private ClamAV service");
requireText(compose, "image: clamav/clamav:1.5", "ClamAV must stay on the security-patched 1.5 feature line");
requireText(compose, 'user: "clamav"', "scanner container must run as the unprivileged clamav user");
requireText(compose, "entrypoint: /init-unprivileged", "scanner must use the official unprivileged entrypoint");
requireText(compose, "CLAMD_CONF_StreamMaxLength", "ClamAV stream ceiling must match ClipKaro upload size");
requireText(compose, "CLAMD_CONF_MaxFileSize", "ClamAV file ceiling must match ClipKaro upload size");
requireText(compose, "condition: service_healthy", "API must wait for a healthy malware scanner");
requireText(compose, "cap_drop:", "containers must drop Linux capabilities");
requireText(compose, "no-new-privileges:true", "containers must block privilege escalation");
requireText(compose, "pids_limit:", "containers must have PID limits");
requireText(compose, "mem_limit:", "containers must have memory limits");
requireText(compose, "read_only: true", "app containers must use a read-only root filesystem");

requireText(compose, "  worker:\n", "production must have a separate media worker service");
requireText(compose, 'command: ["python", "-m", "app.worker"]', "worker service must run the durable worker process");
requireText(compose, "JOB_EXECUTION_MODE: worker", "production API and worker must use durable worker mode");
requireText(compose, "WORKER_MEMORY_LIMIT", "media worker must have an independent memory ceiling");
requireText(compose, "WORKER_CPU_LIMIT", "media worker must have an independent CPU ceiling");
requireText(compose, "scanner_net:\n    internal: true", "API-to-scanner network must be internal-only");
requireText(compose, "worker_egress:", "media worker must use its own outbound network");
requireText(compose, "clamav_egress:", "ClamAV must have isolated signature-update egress");
requireText(compose, "- worker_egress", "worker must not join the public app network");
requireText(worker, "claim_next_job", "worker must atomically claim durable jobs");
requireText(worker, "run_claimed_job", "worker must reconstruct jobs from persisted state");
requireText(jobs, "job_payloads", "heavy job inputs must survive API/worker restarts");
requireText(jobs, "job_claims", "worker ownership must be persisted");
requireText(main, "production_serverless_mode", "production API must fail closed unless PostgreSQL, GCS, and Cloud Run Jobs are selected");
requireText(mediaJob, "claim_job(job_id", "Cloud Run execution must claim only its supplied durable job");
requireText(mediaJob, "TemporaryDirectory", "Cloud Run media must use bounded disposable scratch storage");
requireText(cloudUploads, '"/uploads/{session_id}/complete"', "direct upload completion must be server verified");
requireText(migration, "uq_active_checkout_per_user", "PostgreSQL must prevent cross-instance duplicate checkout state");

// Count YAML environment keys, not `${VAR:-default}` interpolations on the same line.
if (yamlKeyCount(compose, "GROQ_API_KEYS") !== 1) {
  throw new Error("Security foundation contract failed: Groq credentials must be mounted only into the media worker");
}
if (yamlKeyCount(compose, "SECRET_KEY") !== 1) {
  throw new Error("Security foundation contract failed: JWT signing secret must be mounted only into the public API");
}

requireText(backendDocker, "fonts-noto-core", "production captions must install Devanagari font coverage from the OS package manager");
requireText(backendDocker, "fonts-liberation2", "production captions must install an Arial-compatible sans font from the OS package manager");
requireText(backendDocker, "USER 10001:10001", "backend must not run as root");
requireText(frontendDocker, "USER node", "frontend must not run as root");

console.log("Security foundation contract: passed");
