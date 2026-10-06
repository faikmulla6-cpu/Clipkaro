import { ArrowRight, Check, ShieldCheck, Sparkles } from "lucide-react";
import { PublicMotionShell } from "@/components/PublicMotionShell";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { TransitionLink } from "@/components/TransitionLink";
import { TRUST_PROFILE } from "@/lib/legal";
import styles from "./PublicPricingView.module.css";

export type PublicPlanView = {
  id: string;
  name: string;
  price: string;
  suffix: string;
  tagline: string;
  features: string[];
  popular?: boolean;
};

export function PublicPricingView({ plans }: { plans: PublicPlanView[] }) {
  return (
    <PublicMotionShell>
      <div className={styles.page}>
        <PublicSiteNav />
        <main>
          <header className={styles.hero} data-public-reveal>
            <span><Sparkles size={14}/> Extremely affordable creator pricing</span>
            <h1>Start free. <em>Pay for creation capacity, not every post.</em></h1>
            <p>ClipKaro starts at ₹0, offers a ₹59 one-time Mini Pass and Creator from ₹199/month. Paid plans charge for AI Short creation capacity—not repeated renders—so finished Shorts can be exported and re-exported without another paid credit. The Mini Pass expires for new creation at 5/5 AI Shorts or after 30 days, whichever comes first.</p>
            <div className={styles.heroTrust}><b>No card required to start</b><b>Unlimited exports & re-exports on paid plans</b><b>Unlimited Post Karo on every plan</b><b>Mini Pass never auto-renews</b></div>
          </header>

          <section className={styles.planSection} data-public-reveal>
            <div className={styles.planGrid}>
              {plans.map((plan) => {
                const cta = plan.id === "free" ? "Start free" : plan.id === "mini_pass" ? "Get Mini Pass" : `Choose ${plan.name}`;
                return (
                  <article key={plan.id} className={plan.popular ? styles.popular : ""}>
                    {plan.popular && <span className={styles.popularTag}>MOST POPULAR</span>}
                    <h2>{plan.name}</h2>
                    <p>{plan.tagline}</p>
                    <div className={styles.price}>{plan.price}<small>{plan.suffix}</small></div>
                    <ul>{plan.features.map((item)=><li key={item}><Check size={14}/>{item}</li>)}</ul>
                    <TransitionLink href={`/signup?plan=${encodeURIComponent(plan.id)}`} className={plan.popular ? styles.primary : styles.secondary}>{cta} <ArrowRight size={14}/></TransitionLink>
                    {plan.suffix === "/month" && <small className={styles.renewal}>Renews monthly until cancelled or changed.</small>}
                    {plan.id === "mini_pass" && <small className={styles.renewal}>Expires at 5/5 AI Shorts or after 30 days. One-time purchase.</small>}
                  </article>
                );
              })}
            </div>
          </section>

          <section className={styles.pulseCard} data-public-reveal>
            <div><span><Sparkles size={13}/> Separate from clipping plans</span><h2>Creator Pulse stays simple: ₹1 per successful channel analysis.</h2><p>Creator Pulse uses its own wallet balance and does not consume Karo Minutes or Short-export quota. Use the recommendation to plan the next video, then bring the finished recording back into ClipKaro for clipping, editing and Post Karo publishing.</p></div>
            <TransitionLink href="/youtube-channel-analyzer">Explore Creator Pulse <ArrowRight size={15}/></TransitionLink>
          </section>

          <section className={styles.trust} data-public-reveal>
            <div className={styles.trustHead}><ShieldCheck size={22}/><span><b>Know what you are buying before checkout.</b><p>Paid checkout happens only after sign-up and current legal acceptance.</p></span></div>
            <div className={styles.trustGrid}><article><b>Founder-led</b><p>{TRUST_PROFILE.founderName}, {TRUST_PROFILE.founderTitle}. Operator details are public before payment.</p></article><article><b>Support expectation</b><p>{TRUST_PROFILE.supportExpectation}</p></article><article><b>Private media</b><p>{TRUST_PROFILE.mediaRetention}</p></article></div>
            <div className={styles.trustLinks}><TransitionLink href="/refund-policy">Refund policy</TransitionLink><TransitionLink href="/legal-notice">Consumer information</TransitionLink><TransitionLink href="/contact">Contact support</TransitionLink></div>
          </section>
        </main>
        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
