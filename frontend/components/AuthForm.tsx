"use client";

import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
  { Icon: Scissors, className: "left-[7%] top-[16%] -rotate-12" },
  { Icon: Captions, className: "right-[8%] top-[13%] rotate-6" },
  { Icon: Film, className: "left-[10%] bottom-[16%] rotate-6" },
  { Icon: BarChart3, className: "right-[8%] bottom-[17%] -rotate-6" },
  { Icon: Play, className: "left-[24%] top-[44%] rotate-12" },
  { Icon: WandSparkles, className: "right-[23%] top-[46%] -rotate-12" },
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
    <main className="relative min-h-[100dvh] overflow-hidden bg-[#070b08] text-white selection:bg-[#cfff47] selection:text-[#071108]">
      <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-5%,rgba(140,255,112,0.14),transparent_30%),radial-gradient(circle_at_18%_78%,rgba(65,130,86,0.14),transparent_30%),radial-gradient(circle_at_86%_64%,rgba(210,255,126,0.07),transparent_27%),linear-gradient(135deg,#070b08_0%,#0d120f_43%,#080b09_100%)]" />
      <div aria-hidden="true" className="absolute inset-0 opacity-40 [background-image:linear-gradient(118deg,transparent_0%,transparent_36%,rgba(255,255,255,0.035)_36.5%,transparent_38%,transparent_61%,rgba(201,255,145,0.025)_61.5%,transparent_63%),linear-gradient(24deg,transparent_0%,transparent_48%,rgba(255,255,255,0.025)_48.5%,transparent_50%)] [background-size:680px_520px,520px_680px]" />
      <div aria-hidden="true" className="absolute left-1/2 top-1/2 h-[720px] w-[720px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.035] shadow-[0_0_140px_rgba(138,255,102,0.05)]" />
      <div aria-hidden="true" className="absolute left-1/2 top-1/2 h-[540px] w-[540px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/[0.025]" />

      <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden lg:block">
        {sketches.map(({ Icon, className }, index) => (
          <motion.div
            key={index}
            className={`absolute ${className} text-white/[0.055]`}
            animate={reduceMotion ? undefined : { y: [0, -10, 0], opacity: [0.35, 0.65, 0.35] }}
            transition={{ duration: 6 + index * 0.55, repeat: Infinity, ease: "easeInOut", delay: index * 0.35 }}
          >
            <Icon strokeWidth={1.05} className="h-24 w-24 xl:h-28 xl:w-28" />
          </motion.div>
        ))}
      </div>

      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#9cff57]/50 to-transparent" />

      <div className="relative z-10 flex min-h-[100dvh] flex-col px-4 py-5 sm:px-6 sm:py-7">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.035] px-3.5 py-2 text-xs font-semibold text-white/65 backdrop-blur-xl transition hover:border-white/15 hover:bg-white/[0.065] hover:text-white"
          >
            <ArrowLeft size={14} /> Back to ClipKaro
          </Link>
          <Badge className="hidden border border-[#b9ff77]/15 bg-[#b9ff77]/[0.06] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.16em] text-[#caff8d] shadow-none sm:inline-flex">
            Secure creator access
          </Badge>
        </div>

        <div className="flex flex-1 items-center justify-center py-8 sm:py-12">
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: 18, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.45, ease: [0.22, 0.61, 0.36, 1] }}
            className="w-full max-w-[540px]"
          >
            <div className="relative">
              <div aria-hidden="true" className="absolute -inset-[1px] rounded-[32px] bg-gradient-to-br from-white/20 via-white/[0.035] to-[#a7ff60]/20 opacity-80 blur-[0.2px]" />
              <div aria-hidden="true" className="absolute -inset-8 -z-10 rounded-[44px] bg-[#86ff5c]/[0.055] blur-3xl" />

              <Card className="relative overflow-hidden rounded-[31px] border border-white/[0.09] bg-[linear-gradient(145deg,rgba(255,255,255,0.095),rgba(255,255,255,0.025)_38%,rgba(255,255,255,0.055)_66%,rgba(255,255,255,0.018))] text-white shadow-[0_34px_100px_rgba(0,0,0,0.58),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl">
                <div aria-hidden="true" className="absolute inset-0 opacity-70 [background-image:linear-gradient(112deg,transparent_0%,transparent_32%,rgba(255,255,255,0.045)_33%,transparent_34.5%,transparent_65%,rgba(180,255,135,0.026)_66%,transparent_67.5%),linear-gradient(25deg,transparent_0%,transparent_45%,rgba(255,255,255,0.025)_46%,transparent_47%)]" />
                <div aria-hidden="true" className="absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[#abff68]/[0.08] blur-3xl" />
                <div aria-hidden="true" className="absolute -bottom-32 -left-28 h-72 w-72 rounded-full bg-[#2b7a4a]/[0.10] blur-3xl" />

                <CardContent className="relative p-6 sm:p-8 md:p-9">
                  <div className="mb-8 flex flex-col items-center text-center">
                    <div className="mb-5 rounded-[22px] border border-white/[0.09] bg-black/20 p-3.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_15px_40px_rgba(0,0,0,0.25)] backdrop-blur-xl">
                      <Logo light />
                    </div>
                    <Badge className="mb-4 border border-white/[0.08] bg-white/[0.055] px-3 py-1 text-[9px] font-bold uppercase tracking-[0.19em] text-white/55 shadow-none">
                      {mode === "login" ? "Creator studio sign in" : "New creator account"}
                    </Badge>
                    <h1 className="max-w-md text-balance text-[30px] font-semibold leading-[1.05] tracking-[-0.045em] text-white sm:text-[34px]">
                      {title}
                    </h1>
                    <p className="mt-3 max-w-md text-sm leading-6 text-white/48">{subtitle}</p>
                  </div>

                  <form onSubmit={submit} autoComplete="on" className="space-y-4">
                    {mode === "signup" && (
                      <label className="block">
                        <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.11em] text-white/48">Your name</span>
                        <div className="group flex h-14 items-center gap-3 rounded-2xl border border-white/[0.085] bg-black/20 px-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] transition focus-within:border-[#b8ff75]/35 focus-within:bg-black/28 focus-within:shadow-[0_0_0_3px_rgba(171,255,104,0.06)]">
                          <User size={17} className="shrink-0 text-white/35 transition group-focus-within:text-[#bfff82]" />
                          <input name="name" autoComplete="name" placeholder="Your name" required minLength={2} className="h-full min-w-0 flex-1 border-0 bg-transparent text-[15px] text-white outline-none placeholder:text-white/28" />
                        </div>
                      </label>
                    )}

                    <label className="block">
                      <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.11em] text-white/48">Email address</span>
                      <div className="group flex h-14 items-center gap-3 rounded-2xl border border-white/[0.085] bg-black/20 px-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] transition focus-within:border-[#b8ff75]/35 focus-within:bg-black/28 focus-within:shadow-[0_0_0_3px_rgba(171,255,104,0.06)]">
                        <Mail size={17} className="shrink-0 text-white/35 transition group-focus-within:text-[#bfff82]" />
                        <input name="email" type="email" inputMode="email" autoComplete="email" placeholder="you@example.com" required className="h-full min-w-0 flex-1 border-0 bg-transparent text-[15px] text-white outline-none placeholder:text-white/28" />
                      </div>
                    </label>

                    <label className="block">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.11em] text-white/48">Password</span>
                        {mode === "login" && (
                          <Link href="/forgot-password" className="text-[11px] font-semibold text-[#bfff82]/75 transition hover:text-[#cfff98]">Forgot password?</Link>
                        )}
                      </div>
                      <div className="group flex h-14 items-center gap-3 rounded-2xl border border-white/[0.085] bg-black/20 px-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] transition focus-within:border-[#b8ff75]/35 focus-within:bg-black/28 focus-within:shadow-[0_0_0_3px_rgba(171,255,104,0.06)]">
                        <LockKeyhole size={17} className="shrink-0 text-white/35 transition group-focus-within:text-[#bfff82]" />
                        <input
                          name="password"
                          type={show ? "text" : "password"}
                          autoComplete={mode === "login" ? "current-password" : "new-password"}
                          placeholder="At least 8 characters"
                          required
                          minLength={8}
                          pattern="(?=.*[A-Z])(?=.*[0-9]).{8,}"
                          title="Use at least 8 characters, including one uppercase letter and one number."
                          className="h-full min-w-0 flex-1 border-0 bg-transparent text-[15px] text-white outline-none placeholder:text-white/28"
                        />
                        <button type="button" aria-label={show ? "Hide password" : "Show password"} onClick={() => setShow(!show)} className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white/35 transition hover:bg-white/[0.055] hover:text-white/75">
                          {show ? <EyeOff size={16}/> : <Eye size={16}/>} 
                        </button>
                      </div>
                      {mode === "signup" && <small className="mt-2 block text-[10.5px] leading-5 text-white/32">Use 8+ characters with at least one uppercase letter and one number.</small>}
                    </label>

                    {mode === "signup" && (
                      <label className="flex items-start gap-3 rounded-2xl border border-white/[0.065] bg-white/[0.025] p-3.5 text-[11px] leading-[1.55] text-white/44">
                        <input name="legal" type="checkbox" required className="mt-0.5 h-4 w-4 shrink-0 accent-[#9eff62]" />
                        <span>
                          I am at least 18 and agree to the <Link href="/terms" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/72 underline decoration-white/20 underline-offset-2 hover:text-white">Terms of Service</Link>,{" "}
                          <Link href="/privacy" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/72 underline decoration-white/20 underline-offset-2 hover:text-white">Privacy Notice</Link> and{" "}
                          <Link href="/refund-policy" target="_blank" rel="noopener noreferrer" className="font-semibold text-white/72 underline decoration-white/20 underline-offset-2 hover:text-white">Refund & Cancellation Policy</Link>.
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
                      className="group mt-1 inline-flex h-14 w-full items-center justify-center gap-2 rounded-2xl border border-[#caff8a]/20 bg-[linear-gradient(180deg,#b7ff6d_0%,#8fe64d_100%)] px-5 text-sm font-extrabold text-[#0a170d] shadow-[0_18px_45px_rgba(123,221,75,0.16),inset_0_1px_0_rgba(255,255,255,0.55)] transition hover:-translate-y-0.5 hover:brightness-105 hover:shadow-[0_22px_50px_rgba(123,221,75,0.22)] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
                    >
                      {busy ? <><Loader2 className="animate-spin" size={17}/> Please wait</> : <>{mode === "login" ? "Sign in to ClipKaro" : "Create ClipKaro account"}<ArrowRight size={16} className="transition group-hover:translate-x-0.5"/></>}
                    </button>
                  </form>

                  <div className="my-6 flex items-center gap-3 text-[10px] uppercase tracking-[0.16em] text-white/22">
                    <span className="h-px flex-1 bg-white/[0.065]" />
                    secure email access
                    <span className="h-px flex-1 bg-white/[0.065]" />
                  </div>

                  <div className="text-center text-xs text-white/43">
                    {mode === "login"
                      ? <>New to ClipKaro? <Link href={switchHref} className="font-bold text-[#c8ff91] transition hover:text-white">Create an account</Link></>
                      : <>Already have an account? <Link href={switchHref} className="font-bold text-[#c8ff91] transition hover:text-white">Sign in</Link></>}
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[10.5px] text-white/30">
              <span className="inline-flex items-center gap-1.5"><Check size={12} className="text-[#aaff68]/70"/> Email verification</span>
              <span className="inline-flex items-center gap-1.5"><Check size={12} className="text-[#aaff68]/70"/> Secure account access</span>
              <span className="inline-flex items-center gap-1.5"><Sparkles size={12} className="text-[#aaff68]/70"/> Creator-first workflow</span>
            </div>
          </motion.div>
        </div>
      </div>
    </main>
  );
}
