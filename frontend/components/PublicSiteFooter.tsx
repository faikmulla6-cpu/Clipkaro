import { Heart } from "lucide-react";
import { Logo } from "@/components/Logo";
import { TransitionLink } from "@/components/TransitionLink";
import { LEGAL_LINKS } from "@/lib/legal";
import styles from "./PublicSiteFooter.module.css";

export function PublicSiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.top}>
        <div className={styles.brand}>
          <Logo light transition />
          <p>Paste a supported YouTube URL or upload the original file, then turn long-form video into creator-ready Shorts with ClipKaro AI.</p>
        </div>
        <div className={styles.columns}>
          <div><b>Product</b><TransitionLink href="/youtube-video-to-shorts-ai">YouTube URL → Shorts</TransitionLink><TransitionLink href="/ai-shorts-maker-india">AI Shorts Maker</TransitionLink><TransitionLink href="/youtube-channel-analyzer">Creator Pulse</TransitionLink><TransitionLink href="/pricing">Pricing</TransitionLink></div>
          <div><b>Company</b><TransitionLink href="/about">About</TransitionLink><TransitionLink href="/contact">Contact</TransitionLink><TransitionLink href="/about#founder">Founder</TransitionLink></div>
          <div><b>Legal</b>{LEGAL_LINKS.map(([label, href]) => <TransitionLink key={href} href={href}>{label}</TransitionLink>)}</div>
        </div>
      </div>
      <div className={styles.bottom}>
        <span>© 2026 ClipKaro AI. Create responsibly. Built for India.</span>
        <span className={styles.made}><Heart size={13} fill="currentColor" /> Made for creators in India 🇮🇳</span>
      </div>
    </footer>
  );
}
