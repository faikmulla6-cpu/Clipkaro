"use client";

import { postJSON } from "@/lib/api";
import { CheckCircle2, Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

export default function ResetPasswordPage() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const raw = fragment.get("token") || "";
    // Remove the raw reset secret before the user starts typing a password so it
    // never remains in browser history or gets copied with the page URL.
    window.history.replaceState(null, "", "/reset-password");
    setToken(raw);
    setReady(true);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password"));
    const confirm = String(data.get("confirm"));
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await postJSON("/auth/password/reset", { token, password });
      setComplete(true);
      setToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "This reset link could not be used.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <Link href="/" className="auth-brand">✦ ClipKaro AI</Link>
        <div className="auth-story">
          <span className="eyebrow dark">SECURE RECOVERY</span>
          <h1>New password.<br/><em>Fresh sessions.</em></h1>
          <p>A successful reset signs out every existing ClipKaro session, including copied or forgotten cookies on other devices.</p>
          <div className="auth-proof">
            <span><ShieldCheck size={15}/> Reset token stored only as a hash</span>
            <span><ShieldCheck size={15}/> Link expires automatically</span>
            <span><ShieldCheck size={15}/> All existing sessions revoked</span>
          </div>
        </div>
      </div>

      <div className="auth-panel">
        <div className="auth-card">
          <Link href="/" className="auth-mobile-logo">✦ ClipKaro AI</Link>
          <span className="auth-kicker">PASSWORD RESET</span>

          {!ready ? (
            <>
              <h2>Checking reset link</h2>
              <button className="primary-btn auth-submit" disabled><Loader2 className="spin" size={17}/> Loading…</button>
            </>
          ) : complete ? (
            <>
              <CheckCircle2 size={34}/>
              <h2>Password changed</h2>
              <p>Every previous session was signed out. Sign in again with your new password.</p>
              <Link className="primary-btn auth-submit" href="/login">Sign in securely</Link>
            </>
          ) : !token ? (
            <>
              <h2>Reset link missing</h2>
              <p>This page needs the one-time link from your password reset email.</p>
              <Link className="primary-btn auth-submit" href="/forgot-password">Request a new link</Link>
            </>
          ) : (
            <>
              <h2>Choose a new password</h2>
              <p>Use at least 8 characters with an uppercase letter and a number.</p>
              <form onSubmit={submit}>
                <label>
                  <span>New password</span>
                  <div className="input-icon">
                    <LockKeyhole size={16}/>
                    <input name="password" type={show ? "text" : "password"} minLength={8} required autoComplete="new-password"/>
                    <button type="button" onClick={() => setShow(!show)}>{show ? <EyeOff size={16}/> : <Eye size={16}/>}</button>
                  </div>
                </label>
                <label>
                  <span>Confirm password</span>
                  <div className="input-icon"><LockKeyhole size={16}/><input name="confirm" type={show ? "text" : "password"} minLength={8} required autoComplete="new-password"/></div>
                </label>
                {error && <div className="form-error">{error}</div>}
                <button className="primary-btn auth-submit" disabled={busy}>
                  {busy ? <><Loader2 className="spin" size={17}/> Resetting…</> : "Reset password"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
