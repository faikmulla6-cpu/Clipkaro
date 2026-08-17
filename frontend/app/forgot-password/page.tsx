"use client";

import { postJSON } from "@/lib/api";
import { ArrowLeft, Loader2, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

export default function ForgotPasswordPage() {
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await postJSON("/auth/password/forgot", { email: String(data.get("email")) });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not request a reset link.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <Link href="/" className="auth-brand">✦ ClipKaro AI</Link>
        <div className="auth-story">
          <span className="eyebrow dark">ACCOUNT RECOVERY</span>
          <h1>Recover access.<br/><em>Keep every device safe.</em></h1>
          <p>Reset links are one-time, expire automatically, and never reveal whether an email is registered.</p>
          <div className="auth-proof">
            <span><ShieldCheck size={15}/> One-time reset token</span>
            <span><ShieldCheck size={15}/> Existing sessions revoked after reset</span>
            <span><ShieldCheck size={15}/> Rate-limited recovery requests</span>
          </div>
        </div>
      </div>

      <div className="auth-panel">
        <div className="auth-card">
          <Link href="/" className="auth-mobile-logo">✦ ClipKaro AI</Link>
          <span className="auth-kicker">PASSWORD RESET</span>
          <h2>{sent ? "Check your email" : "Forgot your password?"}</h2>
          <p>
            {sent
              ? "If a ClipKaro account exists for that email, a reset link is on its way. Check spam too."
              : "Enter your account email. For privacy, the response is the same whether or not an account exists."}
          </p>

          {!sent && (
            <form onSubmit={submit}>
              <label>
                <span>Email address</span>
                <div className="input-icon"><Mail size={16}/><input name="email" type="email" placeholder="you@example.com" required/></div>
              </label>
              {error && <div className="form-error">{error}</div>}
              <button className="primary-btn auth-submit" disabled={busy}>
                {busy ? <><Loader2 className="spin" size={17}/> Sending…</> : "Send reset link"}
              </button>
            </form>
          )}

          <div className="auth-switch"><Link href="/login"><ArrowLeft size={14}/> Back to sign in</Link></div>
        </div>
      </div>
    </div>
  );
}
