"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Menu, X } from "lucide-react";
import { TransitionLink } from "./TransitionLink";
import styles from "./mobile-landing-menu.module.css";

const productLinks = [
  ["AI Video Clipper", "/youtube-video-to-shorts-ai"],
  ["YouTube Shorts Maker", "/ai-shorts-maker-india"],
  ["Creator Pulse · ₹1", "/youtube-channel-analyzer"],
  ["Hindi & Hinglish", "/hindi-video-to-reels"],
  ["Pricing", "/pricing"],
  ["About ClipKaro", "/about"],
  ["Contact support", "/contact"],
] as const;

export function MobileLandingMenu() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className={styles.mobileOnly}>
      <Link href="/creator-pulse" className={styles.quickStart}>Run Pulse · ₹1 <ArrowRight size={15}/></Link>
      <button
        type="button"
        className={styles.menuButton}
        aria-label={open ? "Close navigation" : "Open navigation"}
        aria-controls="mobile-landing-navigation"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <X size={21} /> : <Menu size={22} />}
      </button>

      <div className={`${styles.scrim} ${open ? styles.open : ""}`} onClick={() => setOpen(false)} aria-hidden="true" />

      <div id="mobile-landing-navigation" className={`${styles.sheet} ${open ? styles.open : ""}`} aria-hidden={!open}>
        <div className={styles.sheetTop}>
          <span>Explore ClipKaro</span>
          <small>Clipping, Shorts creation and Creator Pulse channel intelligence.</small>
        </div>

        <nav className={styles.links} aria-label="Mobile ClipKaro navigation">
          {productLinks.map(([label, href], index) => (
            <TransitionLink href={href} key={href} onClick={() => setOpen(false)}>
              <span>0{index + 1}</span>
              <strong>{label}</strong>
              <ArrowRight size={17} />
            </TransitionLink>
          ))}
        </nav>

        <div className={styles.actions}>
          <Link href="/login" onClick={() => setOpen(false)} className={styles.login}>Log in</Link>
          <Link href="/creator-pulse" onClick={() => setOpen(false)} className={styles.start}>
            Run Pulse · ₹1 <ArrowRight size={17} />
          </Link>
        </div>
      </div>
    </div>
  );
}
