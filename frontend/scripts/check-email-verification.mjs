import fs from "node:fs";

const authProvider = fs.readFileSync(new URL("../components/AuthProvider.tsx", import.meta.url), "utf8");
const authForm = fs.readFileSync(new URL("../components/AuthForm.tsx", import.meta.url), "utf8");
const verifyPage = fs.readFileSync(new URL("../app/verify-email/page.tsx", import.meta.url), "utf8");

const requirements = [
  [authProvider.includes('/auth/verification-status'), "AuthProvider must load durable verification status"],
  [authProvider.includes('/verify-email'), "unverified authenticated users must route to verification"],
  [authProvider.includes('verification?.required') && authProvider.includes('!verification.can_process'), "verification redirect must depend on backend status"],
  [authForm.includes('verificationEmailSent'), "signup must carry verification delivery state"],
  [authForm.includes('router.push(`/verify-email'), "signup/login must redirect unverified users"],
  [verifyPage.includes('window.location.hash'), "verification secret must be read from a URL fragment"],
  [verifyPage.includes('window.history.replaceState'), "verification secret must be removed from browser history"],
  [verifyPage.includes('/auth/verify-email'), "verification page must consume the one-time token through the backend"],
  [verifyPage.includes('/auth/resend-verification'), "verification page must support protected resend"],
  [verifyPage.includes("if (!result.sent)") && verifyPage.includes('setState("error")'), "resend UI must not claim an email was sent when the backend reports otherwise"],
  [verifyPage.includes("Two quick steps to unlock your first Short") && verifyPage.includes("Spam or Promotions"), "verification screen must help new creators locate the email"],
  [!verifyPage.includes('?token='), "raw verification tokens must not be placed in query strings"],
];

const failures = requirements.filter(([passed]) => !passed).map(([, message]) => message);
if (failures.length) {
  console.error("Email verification trust contract failed:\n- " + failures.join("\n- "));
  process.exit(1);
}

console.log("Email verification trust contract passed.");
