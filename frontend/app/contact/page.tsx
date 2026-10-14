import type { Metadata } from "next";
import { ArrowRight, Mail, ShieldCheck, UserRound } from "lucide-react";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";
import { PublicMotionShell } from "@/components/PublicMotionShell";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { TransitionLink } from "@/components/TransitionLink";
import { TRUST_PROFILE } from "@/lib/legal";

const title = "Contact ClipKaro AI — Support and legal help";
const description = "Contact ClipKaro AI for product support, billing help, privacy questions, copyright issues, and grievance escalation.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/contact" },
  openGraph: { type: "website", url: "/contact", siteName: "ClipKaro AI", title, description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "ClipKaro AI" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/assets/clipkaro-icon.png"] },
};

export default function ContactPage() {
  return (
    <PublicMotionShell>
      <div className="landing">
        <PublicSiteNav />
        <main>
          <section className="section" data-public-reveal>
            <div className="section-heading"><span>Support</span><h2>Get help without hunting for the right contact.</h2><p>Account, billing, privacy, copyright and product support all start from this page.</p></div>
            <div className="feature-grid" style={{ alignItems: "stretch" }}>
              <div className="feature-card"><div className="feature-icon"><Mail size={21}/></div><h3>Product and billing support</h3><p>For upload, processing, export, usage, payment, or cancellation questions, use the customer-care contact below and include your account email, project name, plan, and payment reference when relevant.</p></div>
              <div className="feature-card"><div className="feature-icon"><ShieldCheck size={21}/></div><h3>Privacy and legal requests</h3><p>For deletion, privacy, refund, copyright, or grievance requests, use the official operator contacts below. {TRUST_PROFILE.supportExpectation}</p></div>
              <div className="feature-card"><div className="feature-icon"><UserRound size={21}/></div><h3>Founder-led product</h3><p>ClipKaro AI is built by {TRUST_PROFILE.founderName}, {TRUST_PROFILE.founderTitle}. Read the founder story or consumer information before paying.</p><TransitionLink href="/about#founder" style={{display:"inline-flex",alignItems:"center",gap:6,marginTop:14,color:"#165f43",fontWeight:800,fontSize:12}}>Read founder story <ArrowRight size={14}/></TransitionLink></div>
            </div>
            <div className="trust-disclosure-grid"><div><b>Response expectation</b><p>{TRUST_PROFILE.supportExpectation}</p></div><div><b>Media retention</b><p>{TRUST_PROFILE.mediaRetention}</p></div><div><b>Deletion requests</b><p>{TRUST_PROFILE.deletionSummary}</p></div></div>
            <div style={{ maxWidth: 860, margin: "32px auto 0" }}><LegalOperatorCard /></div>
          </section>
        </main>
        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
