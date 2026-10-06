import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const must = (condition, message) => { if (!condition) throw new Error(`Legal/privacy contract failed: ${message}`); };

const frontendLegal = read("frontend/lib/legal.ts");
const backendLegal = read("backend/app/services/legal.py");
const legalApi = read("backend/app/api/legal.py");
const signupApi = read("backend/app/api/email_verification.py");
const billing = read("backend/app/services/billing.py");
const authProvider = read("frontend/components/AuthProvider.tsx");
const authForm = read("frontend/components/AuthForm.tsx");
const pricing = read("frontend/app/pricing/page.tsx") + read("frontend/app/pricing/PricingExperience.tsx");
const landing = read("frontend/app/page.tsx");
const account = read("frontend/app/account/page.tsx");
const envProd = read(".env.production.example");
const compose = read("docker-compose.hostinger.yml");

for (const file of [
  "frontend/app/terms/page.tsx",
  "frontend/app/privacy/page.tsx",
  "frontend/app/refund-policy/page.tsx",
  "frontend/app/acceptable-use/page.tsx",
  "frontend/app/copyright/page.tsx",
  "frontend/app/legal-notice/page.tsx",
]) must(fs.existsSync(path.join(root, file)), `${file} is missing`);

must(frontendLegal.includes('LEGAL_VERSION = "2026-10-06"'), "frontend legal version drifted");
must(backendLegal.includes('LEGAL_VERSION = "2026-10-06"'), "backend legal version drifted");
must(backendLegal.includes("trg_require_current_legal_before_paid_checkout"), "database paid-checkout legal trigger is missing");
must(backendLegal.includes("legal_launch_state"), "paid-launch readiness state is missing");
must(backendLegal.includes("privacy_requests"), "privacy request ledger is missing");
must(legalApi.includes('router.get("/privacy/export")'), "personal-data export endpoint is missing");
must(legalApi.includes('router.post("/privacy/requests"'), "privacy request endpoint is missing");
must(legalApi.includes('"behavioral_learning"'), "privacy export omits behavioral-learning data");
must(signupApi.includes("accept_legal") && signupApi.includes("LEGAL_VERSION"), "production signup does not enforce versioned acceptance");
must(billing.includes("_require_legal_before_provider_checkout"), "Razorpay pre-provider legal gate is missing");
must(billing.includes('{"/orders", "/subscriptions"}'), "user-specific Razorpay checkout paths are not guarded");

for (const href of ["/terms", "/privacy", "/refund-policy", "/acceptable-use", "/copyright", "/legal-notice"]) {
  must(authProvider.includes(`"${href}"`), `${href} is not public in AuthProvider`);
  must(landing.includes(href) || landing.includes("LEGAL_LINKS"), `${href} is not reachable from public landing`);
}
must(authForm.includes('name="legal"') && authForm.includes("required"), "signup legal checkbox is not affirmative/required");
must(authProvider.includes("accept_legal") && authProvider.includes("legal_version"), "signup does not send acceptance version to server");
must(pricing.includes('api<LegalStatus>("/legal/status")'), "pricing does not preflight legal status");
must(pricing.includes('postJSON<{ accepted: boolean; accepted_at?: string }>("/legal/accept"'), "existing accounts cannot re-consent before checkout");
must(pricing.includes("Renews monthly until cancelled or changed"), "recurring renewal disclosure is missing beside plans");
must(pricing.includes("never auto-renews") || pricing.includes("no auto-renewal"), "Mini Pass non-renewal disclosure is missing");
must(account.includes('api<Record<string, unknown>>("/privacy/export")'), "Settings has no privacy data export control");
must(account.includes('kind: "deletion"'), "Settings has no deletion request control");

for (const key of [
  "LEGAL_OPERATOR_NAME",
  "LEGAL_OPERATOR_ADDRESS",
  "LEGAL_CONTACT_EMAIL",
  "PRIVACY_CONTACT_EMAIL",
  "CUSTOMER_CARE_EMAIL",
  "CUSTOMER_CARE_PHONE",
  "GRIEVANCE_OFFICER_NAME",
  "GRIEVANCE_EMAIL",
  "GRIEVANCE_PHONE",
]) {
  must(envProd.includes(`${key}=`), `${key} missing from production env template`);
  const apiKeyMatches = compose.match(new RegExp(`^\\s{6}${key}:`, "gm")) || [];
  must(apiKeyMatches.length === 1, `${key} must be mounted exactly once in Compose (API only)`);
}

const privacy = read("frontend/app/privacy/page.tsx");
must(privacy.includes("sends extracted audio (not the complete source-video file) to the configured speech-to-text provider"), "privacy notice must disclose speech-provider audio flow");
must(privacy.includes("Groq is the normal primary route") && privacy.includes("Cloudflare is the normal fallback") && privacy.includes("ElevenLabs"), "privacy notice must identify the configured ASR provider roles");
must(privacy.includes("compact candidate transcript excerpts") && privacy.includes("The ranking flow does not send the raw uploaded video"), "privacy notice must match semantic-ranking data flow");
must(privacy.includes("Free-plan source media") && privacy.includes("Paid-plan source media") && privacy.includes("up to 30 days"), "privacy notice must disclose plan-aware source-media retention");
must(privacy.includes("do not sell personal data"), "current no-sale disclosure is missing");
must(privacy.includes("privacy-minimized recommendation signals"), "behavioral ranking-learning purpose is not disclosed");
must(privacy.includes("Suggestions that were never shown are not treated as negative feedback"), "unexposed-suggestion learning rule is not disclosed");
must(privacy.includes("excludes transcript text, email, IP address and user-agent"), "learning data minimization disclosure is missing");

console.log("Legal/privacy launch contract passed.");
