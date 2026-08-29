import type { Metadata } from "next";
import { ArrowRight, Check } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { LEGAL_LINKS, TRUST_PROFILE } from "@/lib/legal";
import { PricingExperience } from "./PricingExperience";

const title = "ClipKaro AI Pricing — Free, Mini Pass and creator plans";
const description = "Compare ClipKaro AI plans for turning long videos into Shorts. Start free, buy a one-time Mini Pass, or choose a monthly creator, growth, pro, or agency plan.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/pricing" },
  openGraph: {
    type: "website",
    url: "/pricing",
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

const publicPlans = [
  { id: "free", name: "Free", price: "₹0", suffix: "", tagline: "Try ClipKaro before paying", features: ["15 Karo Minutes / month", "2 Shorts / month", "720p with ClipKaro watermark"], popular: false },
  { id: "mini_pass", name: "Mini Pass", price: "₹59", suffix: " one-time", tagline: "No subscription. Use it when you need it.", features: ["25 Karo Minutes", "5 Shorts", "1080p · no watermark", "Valid for 30 days"], popular: false },
  { id: "creator", name: "Creator", price: "₹199", suffix: "/month", tagline: "For new creators building consistency", features: ["60 Karo Minutes / month", "15 Shorts / month", "1080p · no watermark", "Full AI clip quality"], popular: false },
  { id: "growth", name: "Growth", price: "₹399", suffix: "/month", tagline: "For serious creators publishing every week", features: ["180 Karo Minutes / month", "50 Shorts / month", "1080p · no watermark", "Brand kit + creator workflow"], popular: true },
  { id: "pro", name: "Pro", price: "₹799", suffix: "/month", tagline: "For daily creators and growing channels", features: ["480 Karo Minutes / month", "150 Shorts / month", "1080p · no watermark", "Priority creator workflow"], popular: false },
  { id: "agency", name: "Agency", price: "₹1,999", suffix: "/month", tagline: "For client work and high-volume teams", features: ["1,500 Karo Minutes / month", "500 Shorts / month", "1080p · no watermark", "Agency-scale usage"], popular: false },
];

function PublicPricingFallback() {
  return <div className="landing">
    <nav className="landing-nav">
      <Logo />
      <div className="nav-links">
        <Link href="/#how">How it works</Link>
        <Link href="/#features">Features</Link>
        <Link href="/about">About</Link>
        <Link href="/contact">Contact</Link>
      </div>
      <div className="nav-ctas">
        <Link href="/login" className="text-btn">Log in</Link>
        <Link href="/signup" className="primary-btn">Start free <ArrowRight size={15}/></Link>
      </div>
      <MobileLandingMenu />
    </nav>
    <section className="section">
      <div className="section-heading">
        <span>Fair Access Pricing</span>
        <h2>Start free, then pay only when ClipKaro saves real editing time.</h2>
        <p>Mini Pass is a one-time purchase. Monthly plans renew until cancelled or changed from your billing screen.</p>
      </div>
      <div className="plans-full clipkaro-plans public-pricing-grid">
        {publicPlans.map((plan) => {
          const cta = plan.id === "free" ? "Start free" : plan.id === "mini_pass" ? "Get Mini Pass" : `Choose ${plan.name}`;
          return <div className={`plan-card ${plan.popular ? "popular" : ""}`} key={plan.id}>
            {plan.popular && <span className="popular-tag">MOST POPULAR</span>}
            <h3>{plan.name}</h3>
            <p>{plan.tagline}</p>
            <div className="price">{plan.price}<small>{plan.suffix}</small></div>
            <ul>{plan.features.map((item) => <li key={item}><Check size={13}/>{item}</li>)}</ul>
            <Link href={`/signup?plan=${encodeURIComponent(plan.id)}`} className={plan.popular ? "primary-btn" : "secondary-btn"}>{cta}</Link>
            {plan.suffix === "/month" && <p className="muted-copy">Renews monthly until cancelled or changed.</p>}
            {plan.id === "mini_pass" && <p className="muted-copy">Valid for 30 days and never auto-renews.</p>}
          </div>;
        })}
      </div>
      <p style={{ textAlign: "center", marginTop: 22, color: "#657169", fontSize: 13 }}>
        Paid checkout happens only after sign-up and legal acceptance. Review <Link href="/refund-policy">refunds</Link>, <Link href="/legal-notice">consumer information</Link>, or <Link href="/contact">contact support</Link>.
      </p>
      <div className="trust-disclosure-grid">
        <div><b>Built by</b><p>{TRUST_PROFILE.founderName}, {TRUST_PROFILE.founderTitle}. <Link href="/about#founder">Founder details</Link>.</p></div>
        <div><b>Support promise</b><p>{TRUST_PROFILE.supportExpectation}</p></div>
        <div><b>Private media retention</b><p>{TRUST_PROFILE.mediaRetention}</p></div>
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

export default function PricingPage() {
  return <PricingExperience publicFallback={<PublicPricingFallback />} />;
}
