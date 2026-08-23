"use client";

import { useAuth } from "@/components/AuthProvider";
import { Logo } from "@/components/Logo";
import { postJSON } from "@/lib/api";
import { CheckCircle2, Loader2, MailCheck, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type VerifyResponse = { verified: boolean; email: string; message: string; already_verified?: boolean };
type ResendResponse = { sent: boolean; verified: boolean; retry_after: number };

type VerifyState = "idle" | "verifying" | "verified" | "expired" | "invalid" | "error";

export default function VerifyEmailPage() {
  const { user, verification, refresh, logout } = useAuth();
  const [state, setState] = useState<VerifyState>("idle");
  const [message, setMessage] = useState("");
  const [verifiedEmail, setVerifiedEmail] = useState("");
  const [resending, setResending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const query = new URLSearchParams(window.location.search);
    if (query.get("sent") === "0") {
      setMessage("Your account is protected, but the first email could not be delivered. Use resend below.");
    } else if (query.get("sent") === "1") {
      setMessage("Verification email sent. Check your inbox and spam folder.");
    }

    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = fragment.get("token");
    if (!token) return;

    window.history.replaceState(null, "", "/verify-email");
    setState("verifying");
    setMessage("Verifying this email…");
    postJSON<VerifyResponse>("/auth/verify-email", { token })
      .then(async (result) => {
        setVerifiedEmail(result.email);
        setState("verified");
        setMessage(result.message);
        await refresh();
      })
      .catch((error) => {
        const detail = error instanceof Error ? error.message : "This verification link could not be used.";
        if (/expired/i.test(detail)) setState("expired");
        else if (/invalid|replaced/i.test(detail)) setState("invalid");
        else setState("error");
        setMessage(detail);
      });
  }, [refresh]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  async function resend() {
    if (!user || cooldown > 0 || resending) return;
    setResending(true);
    setMessage("");
    try {
      const result = await postJSON<ResendResponse>("/auth/resend-verification", {});
      if (result.verified) {
        await refresh();
        setState("verified");
        setVerifiedEmail(user.email);
        setMessage("This email is already verified.");
        return;
      }
      setCooldown(result.retry_after || 60);
      setMessage("A fresh verification email was sent. The previous link no longer works.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not resend the verification email.");
    } finally {
      setResending(false);
    }
  }

  const alreadyVerified = Boolean(verification?.can_process && verification?.verified);
  const success = state === "verified" || alreadyVerified;
  const verifiedCurrentAccount = Boolean(
    user && (alreadyVerified || (verifiedEmail && user.email.toLowerCase() === verifiedEmail.toLowerCase())),
  );

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <div className="auth-brand"><Logo light /></div>
        <div className="auth-story">
          <span className="eyebrow dark">PROTECTING YOUR AI QUOTA</span>
          <h1>One real creator.<br/><em>One protected account.</em></h1>
          <p>Email verification keeps free Karo Minutes for genuine creators instead of disposable-account abuse.</p>
          <div className="auth-proof">
            <span><ShieldCheck size={15}/> Verification is required before AI processing</span>
            <span><CheckCircle2 size={15}/> Existing projects and account access stay private</span>
            <span><MailCheck size={15}/> Verification links are one-time and expire automatically</span>
          </div>
        </div>
      </div>

      <div className="auth-panel">
        <div className="auth-card">
          <div className="auth-mobile-logo"><Logo /></div>
          <span className="auth-kicker">EMAIL VERIFICATION</span>

          {state === "verifying" ? (
            <>
              <h2>Checking your link</h2>
              <p>We&apos;re confirming that this email belongs to you.</p>
              <button type="button" className="primary-btn auth-submit" disabled><Loader2 className="spin" size={17}/> Verifying…</button>
            </>
          ) : success ? (
            <>
              <h2>Email verified</h2>
              <p>{message || "Your account can now use ClipKaro AI processing."}</p>
              <Link className="primary-btn auth-submit" href={verifiedCurrentAccount ? "/dashboard" : "/login"}>
                {verifiedCurrentAccount ? "Continue to ClipKaro" : "Sign in to the verified account"}
              </Link>
            </>
          ) : (
            <>
              <h2>Verify your email</h2>
              <p>
                {user
                  ? <>We need to confirm <b>{user.email}</b> before your account can spend Karo Minutes.</>
                  : "Open the verification link from your email, or sign in to request a new one."}
              </p>

              {message && <div className={["error", "expired", "invalid"].includes(state) ? "form-error" : "processing-note"}>{message}</div>}

              {user ? (
                <>
                  <button type="button" className="primary-btn auth-submit" onClick={resend} disabled={resending || cooldown > 0}>
                    {resending
                      ? <><Loader2 className="spin" size={17}/> Sending…</>
                      : <><RefreshCw size={17}/> {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend verification email"}</>}
                  </button>
                  <div className="auth-switch">Wrong account? <button type="button" onClick={() => logout()}>Sign out</button></div>
                </>
              ) : (
                <Link className="primary-btn auth-submit" href="/login">Sign in to resend</Link>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
