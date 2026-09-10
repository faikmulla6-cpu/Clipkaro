"use client";

import { ChevronDown, Menu, X, ArrowRight, Activity, Scissors, Languages, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import { TransitionLink } from "@/components/TransitionLink";
import styles from "./PublicSiteNav.module.css";

type PublicSiteNavProps = {
  cta?: "start" | "pulse";
};

const products = [
  { href: "/youtube-video-to-shorts-ai", label: "AI Video Clipper", text: "Find the strongest moments inside long videos.", icon: Scissors },
  { href: "/ai-shorts-maker-india", label: "YouTube Shorts Maker", text: "Turn creator videos into captioned vertical Shorts.", icon: Sparkles },
  { href: "/hindi-video-to-reels", label: "Hindi & Hinglish", text: "India-first clipping and caption workflows.", icon: Languages },
  { href: "/youtube-channel-analyzer", label: "Creator Pulse", text: "₹1 channel intelligence for the next content move.", icon: Activity },
] as const;

export function PublicSiteNav({ cta = "start" }: PublicSiteNavProps) {
  const [productOpen, setProductOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [mobileOpen]);

  const closeAll = () => {
    setProductOpen(false);
    setMobileOpen(false);
  };

  return (
    <header className={styles.shell}>
      <nav className={styles.nav} aria-label="ClipKaro public navigation">
        <Logo transition />

        <div className={styles.desktopLinks}>
          <div className={styles.productMenu}>
            <button
              type="button"
              className={styles.productButton}
              aria-expanded={productOpen}
              onClick={() => setProductOpen((value) => !value)}
            >
              Product <ChevronDown size={15} className={productOpen ? styles.rotate : ""} />
            </button>
            <div className={`${styles.dropdown} ${productOpen ? styles.dropdownOpen : ""}`}>
              <div className={styles.dropdownLead}>
                <span>ClipKaro workspace</span>
                <b>One creator workflow, not a pile of disconnected tools.</b>
              </div>
              <div className={styles.dropdownGrid}>
                {products.map((item) => {
                  const Icon = item.icon;
                  return (
                    <TransitionLink href={item.href} key={item.href} onClick={closeAll}>
                      <i><Icon size={17} /></i>
                      <span><b>{item.label}</b><small>{item.text}</small></span>
                      <ArrowRight size={14} />
                    </TransitionLink>
                  );
                })}
              </div>
            </div>
          </div>

          <TransitionLink href="/youtube-channel-analyzer" className={styles.pulseLink}>Creator Pulse <span>₹1</span></TransitionLink>
          <TransitionLink href="/#use-cases">Use cases</TransitionLink>
          <TransitionLink href="/pricing">Pricing</TransitionLink>
          <TransitionLink href="/about">About</TransitionLink>
        </div>

        <div className={styles.desktopActions}>
          <TransitionLink href="/login" className={styles.login}>Log in</TransitionLink>
          <TransitionLink href={cta === "pulse" ? "/creator-pulse" : "/signup"} className={styles.primary}>
            {cta === "pulse" ? "Run Pulse · ₹1" : "Start free"} <ArrowRight size={15} />
          </TransitionLink>
        </div>

        <div className={styles.mobileActions}>
          <TransitionLink href={cta === "pulse" ? "/creator-pulse" : "/signup"} className={styles.mobileQuick} onClick={closeAll}>
            {cta === "pulse" ? "Pulse · ₹1" : "Start free"}
          </TransitionLink>
          <button type="button" className={styles.menuButton} aria-label={mobileOpen ? "Close menu" : "Open menu"} aria-expanded={mobileOpen} onClick={() => setMobileOpen((value) => !value)}>
            {mobileOpen ? <X size={21} /> : <Menu size={22} />}
          </button>
        </div>
      </nav>

      <button type="button" aria-label="Close navigation" className={`${styles.scrim} ${mobileOpen ? styles.scrimOpen : ""}`} onClick={closeAll} />
      <aside className={`${styles.mobileSheet} ${mobileOpen ? styles.mobileSheetOpen : ""}`} aria-hidden={!mobileOpen}>
        <div className={styles.mobileTop}>
          <span>Explore ClipKaro</span>
          <button type="button" onClick={closeAll} aria-label="Close menu"><X size={20} /></button>
        </div>
        <div className={styles.mobileProductList}>
          {products.map((item) => {
            const Icon = item.icon;
            return (
              <TransitionLink href={item.href} key={item.href} onClick={closeAll}>
                <i><Icon size={18} /></i>
                <span><b>{item.label}</b><small>{item.text}</small></span>
                <ArrowRight size={15} />
              </TransitionLink>
            );
          })}
        </div>
        <div className={styles.mobileSimpleLinks}>
          <TransitionLink href="/pricing" onClick={closeAll}>Pricing</TransitionLink>
          <TransitionLink href="/about" onClick={closeAll}>About</TransitionLink>
          <TransitionLink href="/contact" onClick={closeAll}>Contact</TransitionLink>
          <TransitionLink href="/login" onClick={closeAll}>Log in</TransitionLink>
        </div>
        <TransitionLink href={cta === "pulse" ? "/creator-pulse" : "/signup"} className={styles.mobilePrimary} onClick={closeAll}>
          {cta === "pulse" ? "Run Creator Pulse · ₹1" : "Create your free account"} <ArrowRight size={16} />
        </TransitionLink>
      </aside>
    </header>
  );
}
