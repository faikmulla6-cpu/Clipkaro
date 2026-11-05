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
          <p>ClipKaro AI turns long videos into Shorts, gives creators final control in Creator Studio, offers ₹1 Creator Pulse intelligence and includes unlimited Post Karo publishing access on every plan.</p>
        </div>
        <div className={styles.columns}>
          <div><b>Product</b><TransitionLink href="/youtube-video-to-shorts-ai">YouTube URL → Shorts · Soon</TransitionLink><TransitionLink href="/ai-video-clipper-india">AI Video Clipper India</TransitionLink><TransitionLink href="/affordable-ai-video-clipper-unlimited-posting">Affordable Clipping + Unlimited Posting</TransitionLink><TransitionLink href="/shorts-video-editor-ai">Creator Studio Editor</TransitionLink><TransitionLink href="/post-shorts-instagram-youtube">Unlimited Post Karo Publishing</TransitionLink><TransitionLink href="/youtube-channel-analyzer">Creator Pulse · ₹1</TransitionLink><TransitionLink href="/pricing">Pricing</TransitionLink></div>
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
