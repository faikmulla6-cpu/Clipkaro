"use client";

import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";
import styles from "./AuthForm.module.css";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Captions,
  Check,
  Eye,
  EyeOff,
  Film,
  Loader2,
  LockKeyhole,
  Mail,
  Play,
  Scissors,
  Sparkles,
  User,
  WandSparkles,
} from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
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

const sketches = [
  { Icon: Scissors, className: "left-[7%] top-[18%] -rotate-12" },
  { Icon: Captions, className: "right-[9%] top-[16%] rotate-6" },
  { Icon: Film, className: "left-[10%] bottom-[13%] rotate-6" },
  { Icon: BarChart3, className: "right-[9%] bottom-[14%] -rotate-6" },
  { Icon: Play, className: "left-[26%] top-[47%] rotate-12" },
  { Icon: WandSparkles, className: "right-[25%] top-[49%] -rotate-12" },
] as const;

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { login, signup } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const reduceMotion = useReducedMotion();
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

  const title = mode === "login"
    ? creatorPulseIntent ? "Sign in for Creator Pulse" : "Welcome back"
    : creatorPulseIntent ? "Create your Creator Pulse account" : "Create your account";

  const subtitle = mode === "login"
    ? creatorPulseIntent
      ? "Sign in securely and continue directly to your ₹1 channel intelligence workflow."
      : "Enter your ClipKaro account and continue where you left off."
    : creatorPulseIntent
      ? "Create an account, verify your email, then continue straight to Creator Pulse."
      : "Start free, verify your email and enter your creator workspace.";

  return (
    <main className={`relative min-h-[100dvh] overflow-x-hidden bg-[#050806] text-white selection:bg-[#cfff47] selection:text-[#071108] ${styles.pageEnter}`}>
      <div aria-hidden="true" className="fixed inset-0 bg-[radial-gradient(circle_at_50%_-8%,rgba(139,255,108,0.15),transparent_30%),radial-gradient(circle_at_18%_77%,rgba(40,104,64,0.16),transparent_28%),radial-gradient(circle_at_84%_68%,rgba(200,255,126,0.07),transparent_24%),linear-gradient(135deg,#050806_0%,#0b110d_45%,#060907_100%)]" />
      <div aria-hidden="true" className="fixed inset-0 opacity-45 [background-image:linear-gradient(117deg,transparent_0%,transparent_34%,rgba(255,255,255,0.035)_35%,transparent_36.5%,transparent_61%,rgba(201,255,145,0.028)_62%,transparent_63.5%),linear-gradient(24deg,transparent_0%,transparent_49%,rgba(255,255,255,0.02)_50%,transparent_51%)] [background-size:720px_560px,560px_720px]" />
      <div aria-hidden="true" className="fixed left-1/2 top-1/2 h-[690px] w-[690px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.035] shadow-[0_0_150px_rgba(138,255,102,0.045)]" />

      <div aria-hidden="true" className="pointer-events-none fixed inset-0 hidden lg:block">
        {sketches.map(({ Icon, className }, index) => (
          <motion.div
            key={index}
            className={`absolute ${className} text-white/[0.045]`}
            animate={reduceMotion ? undefined : { y: [0, -9, 0], opacity: [0.36, 0.62, 0.36] }}
            transition={{ duration: 6 + index * 0.5, repeat: Infinity, ease: "easeInOut", delay: index * 0.3 }}
          >
            <Icon strokeWidth={1.05} className="h-20 w-20 xl:h-24 xl:w-24" />
          </motion.div>
        ))}
      </div>

      <div aria-hidden="true" className="fixed inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#9cff57]/55 to-transparent" />

      <div className="relative z-10 flex min-h-[100dvh] flex-col px-4 py-5 sm:px-6 sm:py-6">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.09] bg-white/[0.035] px-3.5 py-2 text-xs font-semibold text-white/70 backdrop-blur-xl transition hover:border-white/15 hover:bg-white/[0.065] hover:text-white"
          >
            <ArrowLeft size={14} /> Back to ClipKaro
          </Link>
          <span className={`hidden rounded-full px-3 py-1.5 text-[9px] font-bold uppercase tracking-[0.16em] sm:inline-flex ${styles.statusBadge}`}>
            Secure creator access
          </span>
        </div>

        <div className="flex flex-1 items-center justify-center py-7 sm:py-9">
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 16, scale: 0.988 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.42, ease: [0.22, 0.61, 0.36, 1] }}
            className={`w-full max-w-[470px] ${styles.cardEnter}`}
          >
            <div className="relative">
              <div aria-hidden="true" className="absolute -inset-[1px] rounded-[30px] bg-gradient-to-br from-white/18 via-white/[0.025] to-[#a7ff60]/18" />
              <div aria-hidden="true" className="absolute -inset-8 -z-10 rounded-[40px] bg-[#86ff5c]/[0.055] blur-3xl" />

              <section className={`relative overflow-hidden rounded-[29px] ${styles.surface}`}>
                <div aria-hidden="true" className="absolute inset-0 opacity-70 [background-image:linear-gradient(112deg,transparent_0%,transparent_31%,rgba(255,255,255,0.042)_32%,transparent_33.4%,transparent_66%,rgba(180,255,135,0.024)_67%,transparent_68.5%),linear-gradient(26deg,transparent_0%,transparent_45%,rgba(255,255,255,0.022)_46%,transparent_47%)]" />
                <div aria-hidden="true" className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[#abff68]/[0.075] blur-3xl" />
                <div aria-hidden="true" className="absolute -bottom-32 -left-28 h-72 w-72 rounded-full bg-[#2b7a4a]/[0.10] blur-3xl" />

                <div className="relative p-6 sm:p-8">
                  <div className="mb-6 flex flex-col items-center text-center sm:mb-7">
                    <div className="mb-4 rounded-[20px] border border-white/[0.09] bg-black/25 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_14px_36px_rgba(0,0,0,0.24)] backdrop-blur-xl">
                      <Logo light />
                    </div>
                    <span className={`mb-3 rounded-full px-3 py-1 text-[8.5px] font-bold uppercase tracking-[0.18em] ${styles.microBadge}`}>
                      {mode === "login" ? "Creator studio sign in" : "New creator account"}
                    </span>
                    <h1 className="max-w-sm text-[29px] font-semibold leading-[1.03] tracking-[-0.045em] text-white sm:text-[32px]">
                      {title}
                    </h1>
                    <p className="mt-2.5 max-w-sm text-[13px] leading-5 text-white/52">{subtitle}</p>
                  </div>

                  <form onSubmit={submit} autoComplete="on" className="space-y-3.5">
                    {mode === "signup" && (
                      <label className="block">
                        <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.11em] text-white/52">Your name</span>
                        <div className={`group flex h-[52px] items-center gap-3 rounded-2xl px-4 ${styles.fieldShell}`}>
                          <User size={16} className="shrink-0 text-white/38 transition group-focus-within:text-[#bfff82]" />
                          <input name="name" autoComplete="name" placeholder="Your name" required minLength={2} className={`h-full min-w-0 flex-1 text-[14px] ${styles.authInput}`} />
                        </div>
                      </label>
                    )}

                    <label className="block">
                      <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.11em] text-white/52">Email address</span>
                      <div className={`group flex h-[52px] items-center gap-3 rounded-2xl px-4 ${styles.fieldShell}`}>
                        <Mail size={16} className="shrink-0 text-white/38 transition group-focus-within:text-[#bfff82]" />
                        <input name="email" type="email" inputMode="email" autoComplete="email" placeholder="you@example.com" required className={`h-full min-w-0 flex-1 text-[14px] ${styles.authInput}`} />
                      </div>
                    </label>

                    <label className="block">
                      <div className="mb-1.5 flex items-center justify-between gap-3">
                        <span className="text-[10px] font-semibold uppercase tracking-[0.11em] text-white/52">Password</span>
                        {mode === "login" && (
                          <Link href="/forgot-password" className="text-[10.5px] font-semibold text-[#bfff82]/80 transition hover:text-[#d4ffa8]">Forgot password?</Link>
                        )}
                      </div>
                      <div className={`group flex h-[52px] items-center gap-3 rounded-2xl px-4 ${styles.fieldShell}`}>
                        <LockKeyhole size={16} className="shrink-0 text-white/38 transition group-focus-within:text-[#bfff82]" />
                        <input
                          name="password"
                          type={show ? "text" : "password"}
                          autoComplete={mode === "login" ? "current-password" : "new-password"}
                          placeholder="At least 8 characters"
                          required
                          minLength={8}
                          pattern="(?=.*[A-Z])(?=.*[0-9]).{8,}"
                          title="Use at least 8 characters, including one uppercase letter and one number."
                          className={`h-full min-w-0 flex-1 text-[14px] ${styles.authInput}`}
                        />
                        <button type="button" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)} className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg transition ${styles.iconButton}`}>
                          {show ? <EyeOff size={15}/> : <Eye size={15}/>} 
                        </button>
                      </div>
                      {mode === "signup" && <small className="mt-1.5 block text-[10px] leading-4 text-white/38">Use 8+ characters with at least one uppercase letter and one number.</small>}
                    </label>

                    {mode === "signup" && (
                      <label className={`flex items-start gap-3 rounded-2xl p-3 text-[10.5px] leading-[1.5] ${styles.legalBox}`}>
                        <input name="legal" type="checkbox" required className="mt-0.5 h-4 w-4 shrink-0" />
                        <span>
                          I am at least 18 and agree to the <Link href="/terms" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/80 underline decoration-white/20 underline-offset-2 hover:text-white">Terms of Service</Link>,{" "}
                          <Link href="/privacy" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/80 underline decoration-white/20 underline-offset-2 hover:text-white">Privacy Notice</Link> and{" "}
                          <Link href="/refund-policy" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/80 underline decoration-white/20 underline-offset-2 hover:text-white">Refund & Cancellation Policy</Link>.
                        </span>
                      </label>
                    )}

                    {error && (
                      <div className="rounded-2xl border border-red-400/20 bg-red-400/[0.07] px-4 py-3 text-xs leading-5 text-red-100" role="alert">
                        {error}
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={busy}
                      className={`group mt-1 inline-flex h-[52px] w-full items-center justify-center gap-2 rounded-2xl px-5 text-[13px] font-extrabold transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0 ${styles.submitButton}`}
                    >
                      {busy ? <><Loader2 className="animate-spin" size={16}/> Please wait</> : <>{mode === "login" ? "Sign in to ClipKaro" : "Create ClipKaro account"}<ArrowRight size={15} className="transition group-hover:translate-x-0.5"/></>}
                    </button>
                  </form>

                  <div className="my-5 flex items-center gap-3 text-[9px] uppercase tracking-[0.16em] text-white/25">
                    <span className="h-px flex-1 bg-white/[0.07]" />
                    secure email access
                    <span className="h-px flex-1 bg-white/[0.07]" />
                  </div>

                  <div className="text-center text-[11.5px] text-white/48">
                    {mode === "login"
                      ? <>New to ClipKaro? <Link href={switchHref} className="font-bold text-[#c8ff91] transition hover:text-white">Create an account</Link></>
                      : <>Already have an account? <Link href={switchHref} className="font-bold text-[#c8ff91] transition hover:text-white">Sign in</Link></>}
                  </div>
                </div>
              </section>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[9.5px] text-white/30">
              <span className="inline-flex items-center gap-1.5"><Check size={11} className="text-[#aaff68]/70"/> Email verification</span>
              <span className="inline-flex items-center gap-1.5"><Check size={11} className="text-[#aaff68]/70"/> Secure account access</span>
              <span className="inline-flex items-center gap-1.5"><Sparkles size={11} className="text-[#aaff68]/70"/> Creator-first workflow</span>
            </div>
          </motion.div>
        </div>
      </div>
    </main>
  );
}
