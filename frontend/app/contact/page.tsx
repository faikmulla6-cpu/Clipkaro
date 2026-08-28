import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Mail, ShieldCheck } from "lucide-react";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { LEGAL_LINKS } from "@/lib/legal";

const title = "Contact ClipKaro AI — Support and legal help";
const description = "Contact ClipKaro AI for product support, billing help, privacy questions, copyright issues, and grievance escalation.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/contact" },
  openGraph: {
    type: "website",
    url: "/contact",
    title,
    description,
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: ["/assets/clipkaro-icon.png"],
  },
};

export default function ContactPage() {
  return <div className="landing">
    <nav className="landing-nav">
      <Logo />
      <div className="nav-links">
        <Link href="/#how">How it works</Link>
        <Link href="/#features">Features</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/about">About</Link>
      </div>
      <div className="nav-ctas">
        <Link href="/login" className="text-btn">Log in</Link>
        <Link href="/signup" className="primary-btn">Start free <ArrowRight size={15}/></Link>
      </div>
      <MobileLandingMenu />
    </nav>

    <section className="section">
      <div className="section-heading">
        <span>Support</span>
        <h2>Get help with ClipKaro AI.</h2>
        <p>Use this page for account help, billing questions, privacy requests, copyright notices, and product support.</p>
      </div>

      <div className="feature-grid" style={{ alignItems: "stretch" }}>
        <div className="feature-card">
          <div className="feature-icon"><Mail size={21}/></div>
          <h3>Product and billing support</h3>
          <p>For upload, processing, export, usage, payment, or cancellation questions, include your account email and project name so support can investigate faster.</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon"><ShieldCheck size={21}/></div>
          <h3>Privacy and legal requests</h3>
          <p>For deletion, privacy, refund, copyright, or grievance requests, use the official operator contacts below.</p>
        </div>
        <div className="feature-card">
          <div className="feature-icon"><ArrowRight size={21}/></div>
          <h3>Self-service links</h3>
          <p><Link href="/login?next=/help">Sign in for help centre</Link> · <Link href="/pricing">Plans and billing</Link> · <Link href="/refund-policy">Refund policy</Link> · <Link href="/privacy">Privacy notice</Link></p>
        </div>
      </div>

      <div style={{ maxWidth: 860, margin: "32px auto 0" }}>
        <LegalOperatorCard />
      </div>
    </section>

    <footer className="landing-footer">
      <div className="footer-inner" style={{ alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
        <div><Logo light/><p>© 2026 ClipKaro AI. Create responsibly. Built for India.</p></div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12 }}>
          <Link href="/about">About</Link>
          <Link href="/contact">Contact</Link>
          {LEGAL_LINKS.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
        </div>
      </div>
    </footer>
  </div>;
}
