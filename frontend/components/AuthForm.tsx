"use client";

import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";
import styles from "./AuthForm.module.css";
import { ArrowRight, Check, Eye, EyeOff, Loader2, LockKeyhole, Mail, User } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { authHref, clearPostAuthNext, rememberPostAuthNext, safeInternalNext } from "@/lib/safe-next";

function safePostAuthPath(raw: string | null): string {
  const sanitized = safeInternalNext(raw, "/dashboard");
  if (typeof window === "undefined") return sanitized;
  try {
    const resolved = new URL(sanitized, window.location.origin);
    if (resolved.origin !== window.location.origin) return "/dashboard";
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return "/dashboard";
  }
}

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { login, signup } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rawNext = params.get("next");
  const requestedNext = safeInternalNext(rawNext, "");
  const nextPath = safePostAuthPath(rawNext);
  const creatorPulseIntent = nextPath === "/creator-pulse";
  const switchHref = authHref(mode === "login" ? "/signup" : "/login", requestedNext);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const result = mode === "login"
        ? await login(String(data.get("email")), String(data.get("password")))
        : await signup(
            String(data.get("name")),
            String(data.get("email")),
            String(data.get("password")),
            data.get("legal") === "on",
          );

      if (!result.canProcess) {
        rememberPostAuthNext(nextPath);
        const query = new URLSearchParams();
        if (mode === "signup") query.set("sent", result.verificationEmailSent ? "1" : "0");
        if (requestedNext) query.set("next", requestedNext);
        const suffix = query.toString();
        router.push(`/verify-email${suffix ? `?${suffix}` : ""}`);
        return;
      }

      clearPostAuthNext();
      router.push(nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not continue");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div key={mode} className={`auth-page ${styles.pageEnter}`}>
      <div className="auth-visual">
        <div className="auth-brand"><Logo light /></div>
        <div className="auth-story">
          <span className="eyebrow dark">INDIA&apos;S CREATOR COPILOT</span>
          <h1>{creatorPulseIntent ? <>Know what to create.<br/><em>Before you guess.</em></> : <>One upload.<br/><em>A month of moments.</em></>}</h1>
          <p>{creatorPulseIntent ? "Sign in securely to run Creator Pulse, review verified YouTube momentum and get one evidence-led next move." : "Find the clips worth sharing, style them in your brand, and export without learning a complex editor."}</p>
          <div className="auth-proof">
            {(creatorPulseIntent
              ? ["₹1 only for a successful Pulse", "Verified public YouTube evidence", "One next-video recommendation + thumbnail"]
              : ["AI-ranked moments with reasons", "Live processing and export progress", "Private uploads that expire automatically"]
            ).map((item) => (
              <span key={item}><Check size={15}/>{item}</span>
            ))}
          </div>
        </div>
        <div className="auth-quote"><b>Product principle:</b> {creatorPulseIntent ? "Evidence first. Creative assistance second." : "Click once. Get your Shorts."}</div>
      </div>

      <div className="auth-panel">
        <div className={`auth-card ${styles.cardEnter}`}>
          <div className={`auth-mobile-logo ${styles.brandEnter}`}><Logo /></div>
          <span className="auth-kicker">{mode === "login" ? "WELCOME BACK" : "START CREATING"}</span>
          <h2>{mode === "login" ? (creatorPulseIntent ? "Sign in to continue to Creator Pulse" : "Sign in to your studio") : (creatorPulseIntent ? "Create your account for Creator Pulse" : "Create your free account")}</h2>
          <p>
            {mode === "login"
              ? (creatorPulseIntent ? "After sign-in, you’ll return directly to Creator Pulse." : "Your projects, exports and brand presets are waiting.")
              : (creatorPulseIntent ? "No card needed to create an account. Verify your email, then continue directly to Creator Pulse." : "No card needed. Verify your email and start with the Free plan.")}
          </p>

          <form onSubmit={submit} autoComplete="on">
            {mode === "signup" && (
              <label>
                <span>Your name</span>
                <div className="input-icon"><User size={16}/><input name="name" autoComplete="name" placeholder="Your name" required minLength={2}/></div>
              </label>
            )}
            <label>
              <span>Email address</span>
              <div className="input-icon"><Mail size={16}/><input name="email" type="email" inputMode="email" autoComplete="email" placeholder="you@example.com" required/></div>
            </label>
            <label>
              <span>Password</span>
              <div className="input-icon">
                <LockKeyhole size={16}/>
                <input name="password" type={show ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="At least 8 characters" required minLength={8} pattern="(?=.*[A-Z])(?=.*[0-9]).{8,}" title="Use at least 8 characters, including one uppercase letter and one number."/>
                <button type="button" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)}>{show ? <EyeOff size={16}/> : <Eye size={16}/>}</button>
              </div>
              {mode === "signup" && <small>Use 8+ characters with at least one uppercase letter and one number.</small>}
            </label>
            {mode === "signup" && (
              <label style={{ display: "grid", gridTemplateColumns: "18px 1fr", gap: 10, alignItems: "start", fontSize: 12.5, lineHeight: 1.5 }}>
                <input name="legal" type="checkbox" required style={{ marginTop: 3 }}/>
                <span>
                  I am at least 18 and agree to the <Link href="/terms" target="_blank" rel="noopener noreferrer">Terms of Service</Link>,{" "}
                  <Link href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Notice</Link> and{" "}
                  <Link href="/refund-policy" target="_blank" rel="noopener noreferrer">Refund & Cancellation Policy</Link>.
                </span>
              </label>
            )}
            {mode === "login" && (
              <div className="auth-switch"><Link href="/forgot-password">Forgot your password?</Link></div>
            )}
            {error && <div className="form-error" role="alert">{error}</div>}
            <button type="submit" className="primary-btn auth-submit" disabled={busy}>
              {busy ? <Loader2 className="spin" size={17}/> : <>{mode === "login" ? "Sign in" : "Create account"}<ArrowRight size={16}/></>}
            </button>
          </form>

          <div className="auth-switch">
            {mode === "login"
              ? <>New to ClipKaro? <Link href={switchHref}>Create an account</Link></>
              : <>Already have an account? <Link href={switchHref}>Sign in</Link></>}
          </div>
        </div>
      </div>
    </div>
  );
}
