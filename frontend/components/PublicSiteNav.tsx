"use client";

import {
  Activity,
  ArrowRight,
  ChevronDown,
  Languages,
  Link2,
  Menu,
  Sparkles,
  X,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Logo } from "@/components/Logo";
import { TransitionLink } from "@/components/TransitionLink";
import { cn } from "@/lib/utils";

type PublicSiteNavProps = {
  cta?: "start" | "pulse";
};

const products = [
  {
    href: "/ai-video-clipper-india",
    label: "AI Video Clipper",
    text: "Long video → ranked moments → edited Shorts.",
    icon: Sparkles,
  },
  {
    href: "/youtube-video-to-shorts-ai",
    label: "YouTube URL → Shorts",
    text: "Paste a supported link or use the original-file fallback.",
    icon: Link2,
  },
  {
    href: "/ai-shorts-maker-india",
    label: "AI Shorts Maker",
    text: "Turn creator videos into captioned vertical Shorts.",
    icon: Sparkles,
  },
  {
    href: "/hindi-video-to-reels",
    label: "Hindi & Hinglish",
    text: "India-first clipping and caption workflows.",
    icon: Languages,
  },
  {
    href: "/post-shorts-instagram-youtube",
    label: "Post Karo",
    text: "Publish finished Shorts to Instagram + YouTube.",
    icon: ArrowRight,
  },
  {
    href: "/youtube-channel-analyzer",
    label: "Creator Pulse",
    text: "₹1 channel intelligence for your next content move.",
    icon: Activity,
  },
] as const;

const simpleLinks = [
  { href: "/#use-cases", label: "Use cases" },
  { href: "/pricing", label: "Pricing" },
  { href: "/about", label: "About" },
] as const;

export function PublicSiteNav({ cta = "start" }: PublicSiteNavProps) {
  const pathname = usePathname();
  const productMenuRef = useRef<HTMLDivElement>(null);
  const [productOpen, setProductOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const productActive = products.some((item) => item.href === pathname);

  useEffect(() => {
    if (!mobileOpen) return;

    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };

    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousHtmlOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen]);

  useEffect(() => {
    if (!productOpen) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!productMenuRef.current?.contains(event.target as Node)) {
        setProductOpen(false);
      }
    };

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProductOpen(false);
    };

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [productOpen]);

  useEffect(() => {
    setProductOpen(false);
    setMobileOpen(false);
  }, [pathname]);

  const closeAll = () => {
    setProductOpen(false);
    setMobileOpen(false);
  };

  const primaryHref = cta === "pulse" ? "/creator-pulse" : "/signup";
  const primaryLabel = cta === "pulse" ? "Run Pulse · ₹1" : "Start free";

  return (
    <>
      <header className="sticky top-0 z-[100] w-full px-3 pt-3 sm:px-4 lg:px-6">
        <nav
          aria-label="ClipKaro public navigation"
          className="mx-auto flex h-[64px] w-full max-w-[1380px] items-center justify-between gap-4 rounded-[20px] border border-emerald-950/10 bg-white/90 px-3 shadow-[0_18px_55px_rgba(10,48,30,0.10)] backdrop-blur-xl sm:px-4 lg:h-[68px] lg:px-5"
        >
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 rounded-xl px-1 py-1 transition-transform duration-200 hover:-translate-y-0.5">
              <Logo transition />
            </div>
          </div>

          <div className="hidden items-center gap-1 lg:flex">
            <div className="relative" ref={productMenuRef}>
              <button
                type="button"
                className={cn(
                  "inline-flex h-10 items-center gap-1.5 rounded-xl px-3 text-[13px] font-extrabold text-slate-700 transition-all duration-200 hover:bg-emerald-50 hover:text-emerald-800",
                  productActive && "bg-emerald-50 text-emerald-800",
                )}
                aria-expanded={productOpen}
                aria-haspopup="menu"
                onClick={() => setProductOpen((value) => !value)}
              >
                Product
                <ChevronDown
                  size={15}
                  className={cn("transition-transform duration-200", productOpen && "rotate-180")}
                />
              </button>

              <div
                role="menu"
                className={cn(
                  "absolute left-1/2 top-[calc(100%+14px)] w-[680px] -translate-x-1/2 rounded-[24px] border border-emerald-950/10 bg-white/95 p-3 shadow-[0_30px_90px_rgba(8,43,26,0.18)] backdrop-blur-2xl transition-all duration-200",
                  productOpen
                    ? "visible translate-y-0 opacity-100"
                    : "invisible -translate-y-2 opacity-0 pointer-events-none",
                )}
              >
                <div className="mb-2 rounded-[18px] bg-gradient-to-br from-emerald-950 to-emerald-800 p-4 text-white">
                  <div className="flex items-center justify-between gap-6">
                    <div>
                      <span className="text-[10px] font-black uppercase tracking-[0.18em] text-lime-300">
                        ClipKaro workspace
                      </span>
                      <p className="mt-2 max-w-[430px] text-[17px] font-extrabold leading-snug tracking-[-0.02em]">
                        One connected workflow to clip, edit and publish creator-ready Shorts.
                      </p>
                    </div>
                    <span className="shrink-0 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[10px] font-extrabold text-emerald-50">
                      Built for creators
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {products.map((item) => {
                    const Icon = item.icon;
                    const active = pathname === item.href;
                    return (
                      <TransitionLink
                        href={item.href}
                        key={item.href}
                        role="menuitem"
                        onClick={closeAll}
                        className={cn(
                          "group grid grid-cols-[42px_1fr_18px] items-center gap-3 rounded-[17px] border border-transparent p-3 transition-all duration-200 hover:-translate-y-0.5 hover:border-emerald-900/10 hover:bg-emerald-50/80 hover:shadow-sm",
                          active && "border-emerald-900/10 bg-emerald-50",
                        )}
                      >
                        <span className="grid h-[42px] w-[42px] place-items-center rounded-[13px] bg-emerald-100 text-emerald-800">
                          <Icon size={18} />
                        </span>
                        <span className="min-w-0">
                          <b className="block text-[12.5px] font-black text-slate-900">{item.label}</b>
                          <small className="mt-1 block text-[10.5px] leading-[1.45] text-slate-500">{item.text}</small>
                        </span>
                        <ArrowRight
                          size={15}
                          className="text-slate-400 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-emerald-700"
                        />
                      </TransitionLink>
                    );
                  })}
                </div>
              </div>
            </div>

            <TransitionLink
              href="/youtube-channel-analyzer"
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-xl px-3 text-[13px] font-extrabold text-slate-700 transition-all duration-200 hover:bg-emerald-50 hover:text-emerald-800",
                pathname === "/youtube-channel-analyzer" && "bg-emerald-50 text-emerald-800",
              )}
            >
              Creator Pulse
              <span className="rounded-full bg-lime-200 px-2 py-0.5 text-[9px] font-black text-emerald-950">₹1</span>
            </TransitionLink>

            {simpleLinks.map((item) => (
              <TransitionLink
                key={item.href}
                href={item.href}
                className={cn(
                  "inline-flex h-10 items-center rounded-xl px-3 text-[13px] font-extrabold text-slate-700 transition-all duration-200 hover:bg-emerald-50 hover:text-emerald-800",
                  pathname === item.href && "bg-emerald-50 text-emerald-800",
                )}
              >
                {item.label}
              </TransitionLink>
            ))}
          </div>

          <div className="hidden shrink-0 items-center gap-2 lg:flex">
            <TransitionLink
              href="/login"
              className="inline-flex h-10 items-center rounded-xl px-3 text-[13px] font-extrabold text-slate-700 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-950"
            >
              Log in
            </TransitionLink>
            <TransitionLink
              href={primaryHref}
              className="group inline-flex h-11 items-center gap-2 rounded-[13px] bg-emerald-800 px-4 text-[12.5px] font-black text-white shadow-[0_12px_28px_rgba(22,101,72,0.22)] transition-all duration-200 hover:-translate-y-0.5 hover:bg-emerald-900 hover:shadow-[0_16px_34px_rgba(22,101,72,0.28)]"
            >
              {primaryLabel}
              <ArrowRight size={15} className="transition-transform duration-200 group-hover:translate-x-0.5" />
            </TransitionLink>
          </div>

          <div className="flex shrink-0 items-center gap-2 lg:hidden">
            <TransitionLink
              href={primaryHref}
              onClick={closeAll}
              className="inline-flex h-10 items-center rounded-[12px] bg-emerald-800 px-3 text-[10.5px] font-black text-white shadow-[0_8px_20px_rgba(22,101,72,0.18)] sm:px-4 sm:text-[11px]"
            >
              {cta === "pulse" ? "Pulse · ₹1" : "Start free"}
            </TransitionLink>
            <button
              type="button"
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
              aria-expanded={mobileOpen}
              aria-controls="clipkaro-mobile-menu"
              onClick={() => setMobileOpen((value) => !value)}
              className="grid h-10 w-10 place-items-center rounded-[12px] border border-emerald-950/10 bg-white text-emerald-950 shadow-sm transition-all duration-200 active:scale-95"
            >
              {mobileOpen ? <X size={20} /> : <Menu size={21} />}
            </button>
          </div>
        </nav>
      </header>

      <button
        type="button"
        aria-label="Close navigation"
        onClick={closeAll}
        tabIndex={mobileOpen ? 0 : -1}
        className={cn(
          "fixed inset-0 z-[90] border-0 bg-emerald-950/45 backdrop-blur-[2px] transition-opacity duration-200 lg:hidden",
          mobileOpen ? "visible opacity-100" : "invisible pointer-events-none opacity-0",
        )}
      />

      <aside
        id="clipkaro-mobile-menu"
        aria-hidden={!mobileOpen}
        aria-label="Explore ClipKaro"
        className={cn(
          "fixed bottom-3 right-3 top-[82px] z-[95] flex w-[calc(100%-1.5rem)] max-w-[430px] flex-col overflow-y-auto overscroll-contain rounded-[24px] border border-emerald-950/10 bg-white/95 p-4 shadow-[0_28px_90px_rgba(7,39,23,0.28)] backdrop-blur-2xl transition-all duration-300 lg:hidden",
          mobileOpen
            ? "visible translate-x-0 opacity-100"
            : "invisible translate-x-[108%] pointer-events-none opacity-0",
        )}
      >
        <div className="rounded-[18px] bg-gradient-to-br from-emerald-950 via-emerald-900 to-emerald-800 p-4 text-white">
          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-lime-300">Explore ClipKaro</span>
          <h2 className="mt-2 text-[19px] font-black leading-tight tracking-[-0.03em]">Create, edit and publish Shorts from one connected workflow.</h2>
          <p className="mt-2 text-[11px] leading-relaxed text-emerald-100/85">AI clipping, captions, Post Karo publishing, creator intelligence and pricing in one place.</p>
        </div>

        <div className="mt-3 grid gap-2">
          {products.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <TransitionLink
                href={item.href}
                key={item.href}
                onClick={closeAll}
                className={cn(
                  "grid grid-cols-[44px_1fr_17px] items-center gap-3 rounded-[17px] border border-emerald-950/10 bg-white p-3 shadow-[0_7px_18px_rgba(10,48,30,0.04)] transition-all duration-200 active:scale-[0.99]",
                  active && "border-emerald-800/20 bg-emerald-50",
                )}
              >
                <span className="grid h-11 w-11 place-items-center rounded-[13px] bg-emerald-100 text-emerald-800">
                  <Icon size={18} />
                </span>
                <span className="min-w-0">
                  <b className="block text-[12.5px] font-black text-slate-900">{item.label}</b>
                  <small className="mt-1 block text-[10px] leading-[1.45] text-slate-500">{item.text}</small>
                </span>
                <ArrowRight size={15} className="text-slate-400" />
              </TransitionLink>
            );
          })}
        </div>

        <div className="my-3 grid grid-cols-2 gap-2">
          {simpleLinks.map((item) => (
            <TransitionLink
              href={item.href}
              key={item.href}
              onClick={closeAll}
              className="rounded-[13px] border border-emerald-950/10 bg-slate-50 px-3 py-3 text-center text-[11px] font-black text-slate-700 transition-colors duration-200 hover:bg-emerald-50 hover:text-emerald-800"
            >
              {item.label}
            </TransitionLink>
          ))}
          <TransitionLink
            href="/contact"
            onClick={closeAll}
            className="rounded-[13px] border border-emerald-950/10 bg-slate-50 px-3 py-3 text-center text-[11px] font-black text-slate-700"
          >
            Contact
          </TransitionLink>
          <TransitionLink
            href="/login"
            onClick={closeAll}
            className="rounded-[13px] border border-emerald-950/10 bg-slate-50 px-3 py-3 text-center text-[11px] font-black text-slate-700"
          >
            Log in
          </TransitionLink>
        </div>

        <TransitionLink
          href={primaryHref}
          onClick={closeAll}
          className="group mt-auto inline-flex min-h-[52px] items-center justify-center gap-2 rounded-[15px] bg-emerald-800 px-4 text-[12px] font-black text-white shadow-[0_14px_30px_rgba(22,101,72,0.22)]"
        >
          {cta === "pulse" ? "Run Creator Pulse · ₹1" : "Create your free account"}
          <ArrowRight size={16} className="transition-transform duration-200 group-hover:translate-x-0.5" />
        </TransitionLink>
      </aside>
    </>
  );
}
