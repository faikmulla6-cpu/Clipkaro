"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { api, postJSON, Usage, usageMiniPassExhausted } from "@/lib/api";
import { LEGAL_LINKS, LEGAL_VERSION, LegalStatus, TRUST_PROFILE } from "@/lib/legal";
import { PUBLIC_PRICING, planFeatureMinutes, smartLayoutFeature, type PricingPlanId } from "@/lib/pricing-contract";
import { ArrowRight, Check, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

type Plan = {
  id: string;
  name: string;
  price: number;
  exports: number;
  shorts: number;
  unlimited_exports: boolean;
  processing_minutes: number;
  source_minutes_per_short?: number | null;
  watermark: boolean;
  resolution: string;
  billing: "free" | "one_time" | "subscription";
  popular: boolean;
};

type Checkout = {
  key_id?: string;
  kind: "one_time" | "subscription" | "subscription_change";
  plan: string;
  plan_name?: string;
  amount?: number;
  currency?: string;
  name?: string;
  description?: string;
  order_id?: string;
  subscription_id?: string;
  prefill?: { name: string; email: string };
  change?: "immediate_upgrade" | "scheduled_downgrade" | "scheduled_cancellation" | "scheduled_change_cancelled";
  target_plan?: string;
  effective_at?: string | null;
};

type BillingStatus = {
  plan: string;
  billing_reference?: string | null;
  plan_started_at?: string | null;
  plan_expires_at?: string | null;
  cancel_at_period_end: boolean;
  scheduled_plan?: string | null;
  scheduled_plan_effective_at?: string | null;
  scheduled_change_type?: "downgrade" | "cancel" | null;
  mini_pass_exhausted?: boolean;
  entitlement_state?: "active" | "exhausted" | "free";
};

type RazorpayResult = {
  razorpay_payment_id: string;
  razorpay_signature: string;
  razorpay_order_id?: string;
  razorpay_subscription_id?: string;
};

type RazorpayFailure = {
  error?: {
    code?: string;
    description?: string;
    source?: string;
    step?: string;
    reason?: string;
    metadata?: Record<string, unknown>;
  };
};

type RazorpayCheckout = {
  open: () => void;
  on?: (event: "payment.failed", handler: (response: RazorpayFailure) => void) => void;
};

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => RazorpayCheckout;
  }
}

const copy: Record<string, { tagline: string; features: string[] }> = {
  free: { tagline: "Try ClipKaro before paying", features: [smartLayoutFeature("free"), "2 AI Shorts / month", "15 total source-processing minutes / month", "Up to 2 exports / month", "Source media kept 24 hours", "720p with ClipKaro watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  mini_pass: { tagline: "One-time pass · 5 finished AI Shorts", features: [smartLayoutFeature("mini_pass"), "5 unique finished AI Shorts", planFeatureMinutes("mini_pass"), "Creation access ends when 5 Shorts or 25 Karo Minutes are used, or after 30 days", "Existing Mini Pass purchases retain their original 125-minute allowance", "Unlimited re-exports of finished Shorts while source media is retained", "1080p · no watermark", "Unlimited Post Karo · Instagram + YouTube"] },
  creator: { tagline: "For new creators building consistency", features: [smartLayoutFeature("creator"), "15 unique finished AI Shorts / month", planFeatureMinutes("creator"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Full AI clip quality", "Unlimited Post Karo · Instagram + YouTube"] },
  growth: { tagline: "For serious creators publishing every week", features: [smartLayoutFeature("growth"), "50 unique finished AI Shorts / month", planFeatureMinutes("growth"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Brand kit + creator workflow", "Unlimited Post Karo · Instagram + YouTube"] },
  pro: { tagline: "For daily creators and growing channels", features: [smartLayoutFeature("pro"), "150 unique finished AI Shorts / month", planFeatureMinutes("pro"), "Unlimited re-exports of finished Shorts", "Paid source media kept up to 30 days", "1080p · no watermark", "Priority creator workflow", "Unlimited Post Karo · Instagram + YouTube"] },
  agency: { tagline: "For client work and high-volume teams", features: [smartLayoutFeature("agency"), "500 AI Shorts / month", "1,500 total source-processing minutes / month", "Unlimited exports & re-exports", "Paid source media kept up to 30 days", "1080p · no watermark", "Agency-scale usage", "Unlimited Post Karo · Instagram + YouTube"] },
};

const fallbackPlans: Plan[] = [
  { id: "free", name: "Free", price: 0, exports: 2, shorts: 2, unlimited_exports: false, processing_minutes: 15, watermark: true, resolution: "720p", billing: "free", popular: false },
  { id: "mini_pass", name: "Mini Pass", price: 59, exports: 5, shorts: 5, unlimited_exports: true, processing_minutes: 25, source_minutes_per_short: 25, watermark: false, resolution: "1080p", billing: "one_time", popular: false },
  { id: "creator", name: "Creator", price: 249, exports: 15, shorts: 15, unlimited_exports: true, processing_minutes: 120, source_minutes_per_short: 60, watermark: false, resolution: "1080p", billing: "subscription", popular: false },
  { id: "growth", name: "Growth", price: 599, exports: 50, shorts: 50, unlimited_exports: true, processing_minutes: 300, source_minutes_per_short: 90, watermark: false, resolution: "1080p", billing: "subscription", popular: true },
  { id: "pro", name: "Pro", price: 1299, exports: 150, shorts: 150, unlimited_exports: true, processing_minutes: 600, source_minutes_per_short: 180, watermark: false, resolution: "1080p", billing: "subscription", popular: false },
  { id: "agency", name: "Agency", price: 1999, exports: 500, shorts: 500, unlimited_exports: true, processing_minutes: 1500, watermark: false, resolution: "1080p", billing: "subscription", popular: false },
];

const RAZORPAY_CHECKOUT_SRC = "https://checkout.razorpay.com/v1/checkout.js";
let razorpayLoadPromise: Promise<void> | null = null;

function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  if (razorpayLoadPromise) return razorpayLoadPromise;

  razorpayLoadPromise = new Promise((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      if (error) {
        razorpayLoadPromise = null;
        reject(error);
        return;
      }
      resolve();
    };

    const onLoad = () => {
      if (window.Razorpay) finish();
      else finish(new Error("Razorpay Checkout loaded, but the payment library was unavailable."));
    };
    const onError = () => finish(new Error("Razorpay Checkout could not load. Check your connection and try again."));
    const timeoutId = window.setTimeout(
      () => finish(new Error("Razorpay Checkout took too long to load. Check your connection and try again.")),
      12_000,
    );

    const existing = document.querySelector<HTMLScriptElement>(`script[src="${RAZORPAY_CHECKOUT_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", onLoad, { once: true });
      existing.addEventListener("error", onError, { once: true });
      // If another part of the page loaded the script before this listener was
      // attached, the load event will not fire again. Give the global one turn
      // to appear; otherwise the timeout above fails deterministically instead
      // of leaving the pricing page permanently busy.
      window.setTimeout(() => {
        if (window.Razorpay) finish();
      }, 0);
      return;
    }

    const script = document.createElement("script");
    script.src = RAZORPAY_CHECKOUT_SRC;
    script.async = true;
    script.addEventListener("load", onLoad, { once: true });
    script.addEventListener("error", onError, { once: true });
    document.body.appendChild(script);
  });

  return razorpayLoadPromise;
}

function formatDate(value?: string | null) {
  if (!value) return "the next billing cycle";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "the next billing cycle" : parsed.toLocaleDateString();
}

function PublicPricing({ plans }: { plans: Plan[] }) {
  const visiblePlans = plans.length ? plans : fallbackPlans;
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
        {visiblePlans.map((plan) => {
          const details = copy[plan.id] || { tagline: "", features: [] };
          const suffix = plan.billing === "one_time" ? " one-time" : plan.billing === "subscription" ? "/month" : "";
          const cta = plan.id === "free" ? "Start free" : plan.id === "mini_pass" ? "Get Mini Pass" : `Choose ${plan.name}`;
          return <div className={`plan-card ${plan.popular ? "popular" : ""}`} key={plan.id}>
            {plan.popular && <span className="popular-tag">MOST POPULAR</span>}
            <h3>{plan.name}</h3>
            <p>{details.tagline}</p>
            <div className="price">₹{plan.price.toLocaleString("en-IN")}<small>{suffix}</small></div>
            <ul>{details.features.map((item) => <li key={item}><Check size={13}/>{item}</li>)}</ul>
            <Link href={`/signup?plan=${encodeURIComponent(plan.id)}`} className={plan.popular ? "primary-btn" : "secondary-btn"}>{cta}</Link>
            {plan.billing === "subscription" && <p className="muted-copy">Renews monthly until cancelled or changed.</p>}
            {plan.billing === "one_time" && <p className="muted-copy">Creation access expires after 5 finished Shorts, 25 total Karo Minutes, or 30 days, whichever comes first. Never auto-renews. Existing pass rights are protected.</p>}
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

export function PricingExperience({ publicFallback }: { publicFallback?: React.ReactNode }) {
  const { user, refresh } = useAuth();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [legalStatus, setLegalStatus] = useState<LegalStatus | null>(null);
  const [legalChecked, setLegalChecked] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refreshStatus = () => api<BillingStatus>("/billing/status").then((result) => {
    setStatus(result);
    return result;
  });
  const refreshUsage = () => api<Usage>("/usage").then((result) => {
    setUsage(result);
    return result;
  });
  const refreshLegalStatus = () => api<LegalStatus>("/legal/status").then((result) => {
    setLegalStatus(result);
    return result;
  });

  useEffect(() => {
    api<Plan[]>("/plans").then(setPlans).catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load plans."));
  }, []);

  useEffect(() => {
    if (!user) return;
    refreshStatus().catch(() => undefined);
    refreshUsage().catch(() => undefined);
    refreshLegalStatus().catch(() => setError("Could not load ClipKaro's legal checkout status. Paid checkout is paused until it can be verified."));
  }, [user]);

  async function ensureLegalCheckoutReady() {
    const current = legalStatus || await refreshLegalStatus();
    if (!current.checkout_allowed) {
      throw new Error(current.checkout_reason || "Checkout is not available.");
    }
    if (current.accepted) return;
    if (!legalChecked) {
      throw new Error("Review and accept the current Terms, Privacy Notice and Refund Policy before starting paid checkout.");
    }
    const accepted = await postJSON<{ accepted: boolean; accepted_at?: string }>("/legal/accept", {
      accepted: true,
      version: LEGAL_VERSION,
    });
    setLegalStatus({ ...current, accepted: true, accepted_at: accepted.accepted_at || new Date().toISOString() });
  }

  function createsOrIncreasesPaidCommitment(plan: Plan) {
    if (plan.billing === "free") return false;
    const activePlan = plans.find((item) => item.id === (status?.plan || user?.plan || "free"));
    const hasRecurringSubscription = Boolean(status?.billing_reference?.startsWith("sub_"));
    if (!hasRecurringSubscription || !activePlan) return true;
    // Cancelling a scheduled downgrade keeps the higher paid commitment, so it
    // should still require the current legal version. Ordinary downgrades never
    // require accepting new terms merely to reduce future spend.
    if (status?.scheduled_change_type === "downgrade" && plan.id === status.plan) return true;
    return plan.price > activePlan.price;
  }

  async function choose(plan: Plan) {
    setBusy(plan.id);
    setError("");
    setNotice("");
    try {
      const expected = PUBLIC_PRICING[plan.id as PricingPlanId];
      if (!expected || plan.price !== expected.price || plan.shorts !== expected.shorts
          || plan.processing_minutes !== expected.minutes
          || (plan.id !== "free" && plan.id !== "agency"
             && plan.source_minutes_per_short !== expected.maxVideo)) {
        throw new Error("Plan details are updating. Checkout is temporarily unavailable until pricing and backend limits match.");
      }
      if (createsOrIncreasesPaidCommitment(plan)) await ensureLegalCheckoutReady();
      const checkout = await postJSON<Checkout>("/billing/checkout", { plan: plan.id, expected_price_paise: plan.price * 100 });

      if (checkout.kind === "subscription_change") {
        const targetName = plans.find((item) => item.id === checkout.target_plan)?.name || plan.name;
        if (checkout.change === "immediate_upgrade") {
          setNotice(`${targetName} is active now. Razorpay prorated the current billing cycle, and your existing ClipKaro usage was carried forward.`);
        } else if (checkout.change === "scheduled_downgrade") {
          setNotice(`${targetName} is scheduled for ${formatDate(checkout.effective_at)}. Your current plan and limits remain active until then.`);
        } else if (checkout.change === "scheduled_cancellation") {
          setNotice(`Downgrade to Free is scheduled for ${formatDate(checkout.effective_at)}. Your paid plan remains active until then.`);
        } else {
          setNotice("The scheduled downgrade was cancelled. Your current subscription will continue renewing normally.");
        }
        await refreshStatus();
        await refreshUsage().catch(() => undefined);
        await refresh();
        setBusy("");
        return;
      }

      await loadRazorpay();
      if (!window.Razorpay || !checkout.key_id || !checkout.name || !checkout.description || !checkout.prefill) {
        throw new Error("Razorpay Checkout is unavailable in this browser.");
      }

      const options: Record<string, unknown> = {
        key: checkout.key_id,
        name: checkout.name,
        description: checkout.description,
        prefill: checkout.prefill,
        notes: { clipkaro_plan: checkout.plan },
        theme: { color: "#165F43" },
        modal: { ondismiss: () => setBusy("") },
        handler: async (response: RazorpayResult) => {
          try {
            const verified = await postJSON<{ verified: boolean; activated: boolean; plan: string }>("/billing/verify", response);
            if (!verified.activated) {
              const synced = await postJSON<BillingStatus>("/billing/sync", {});
              if (synced.plan !== checkout.plan) {
                setNotice(
                  checkout.kind === "subscription"
                    ? "Payment authorization succeeded. Razorpay is activating the subscription; refresh Plans & billing shortly if the plan has not changed yet."
                    : "Payment was authenticated and is waiting for Razorpay capture. Your Mini Pass will activate only after capture is confirmed."
                );
                await refreshStatus();
                return;
              }
            }
            setNotice(`${checkout.plan_name || plan.name} is active. Your ClipKaro limits have been updated.`);
            await refreshStatus();
            await refreshUsage().catch(() => undefined);
            await refresh();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Payment was received but could not be verified.");
          } finally {
            setBusy("");
          }
        },
      };
      if (checkout.kind === "one_time") {
        options.order_id = checkout.order_id;
        options.amount = checkout.amount;
        options.currency = checkout.currency;
      } else {
        options.subscription_id = checkout.subscription_id;
      }
      const razorpay = new window.Razorpay(options);
      razorpay.on?.("payment.failed", (response: RazorpayFailure) => {
        // Standard Checkout keeps the modal available for Razorpay's retry
        // flow. Surface a useful message without clearing `busy` until the
        // customer closes the modal, preventing a second checkout from being
        // launched while the first one is still open.
        const reason = response.error?.description?.trim();
        setError(reason || "This payment attempt failed. You can retry securely in Razorpay Checkout.");
      });
      razorpay.open();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update billing.");
      setBusy("");
    }
  }

  async function cancelSubscription() {
    setBusy("cancel");
    setError("");
    setNotice("");
    try {
      const result = await postJSON<{ cancel_at_period_end: boolean; plan_expires_at?: string }>("/billing/cancel", {});
      setNotice(`Downgrade to Free is scheduled. Your paid access continues until ${formatDate(result.plan_expires_at)}.`);
      await refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not schedule cancellation.");
    } finally {
      setBusy("");
    }
  }

  async function cancelScheduledDowngrade() {
    setBusy("cancel-change");
    setError("");
    setNotice("");
    try {
      await postJSON<BillingStatus>("/billing/cancel-scheduled-change", {});
      setNotice("Scheduled downgrade cancelled. Your current subscription will continue renewing normally.");
      await refreshStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not cancel the scheduled downgrade.");
    } finally {
      setBusy("");
    }
  }

  const currentPlan = (status?.plan || user?.plan || "free").toLowerCase();
  const miniPassExhausted = currentPlan === "mini_pass" && Boolean(status?.mini_pass_exhausted || (usage && usageMiniPassExhausted(usage)));
  const currentIsRecurring = ["creator", "growth", "pro", "agency"].includes(currentPlan);
  const currentPrice = typeof usage?.plan_price_paise === "number"
    ? usage.plan_price_paise / 100
    : plans.find((plan) => plan.id === currentPlan)?.price || 0;
  const currentCatalog = PUBLIC_PRICING[currentPlan as PricingPlanId];
  const protectedLegacy = Boolean(usage && currentCatalog
    && typeof usage.plan_price_paise === "number" && usage.short_unit && (
    usage.processing_minutes_limit !== currentCatalog.minutes
    || usage.plan_price_paise !== currentCatalog.price * 100
    || (["mini_pass", "creator", "growth", "pro"].includes(currentPlan)
      && usage.short_unit === "source_projects")
  ));
  const scheduledPlan = status?.scheduled_plan || null;
  const scheduledPlanName = plans.find((plan) => plan.id === scheduledPlan)?.name || (scheduledPlan === "free" ? "Free" : scheduledPlan);

  if (!user) {
    return publicFallback || <PublicPricing plans={plans} />;
  }

  function buttonState(plan: Plan) {
    const current = currentPlan === plan.id;
    const scheduled = scheduledPlan === plan.id;
    let disabled = !!busy;
    let label = plan.id === "mini_pass" ? "Buy Mini Pass" : `Choose ${plan.name}`;

    if (scheduled) {
      disabled = true;
      label = status?.scheduled_change_type === "cancel" ? "Scheduled to Free" : "Scheduled next cycle";
    } else if (current && !(plan.id === "mini_pass" && miniPassExhausted)) {
      disabled = true;
      label = "Current plan";
    } else if (plan.id === "mini_pass" && miniPassExhausted) {
      disabled = !!busy;
      label = "Buy another Mini Pass";
    } else if (status?.scheduled_change_type === "cancel") {
      disabled = true;
      label = "Available after subscription ends";
    } else if (currentIsRecurring) {
      if (plan.id === "mini_pass") {
        disabled = true;
        label = "Available after subscription ends";
      } else if (plan.id === "free") {
        disabled = !!status?.cancel_at_period_end;
        label = status?.cancel_at_period_end ? "Cancellation scheduled" : "Downgrade to Free";
      } else if (plan.billing === "subscription") {
        label = plan.price > currentPrice ? `Upgrade to ${plan.name} now` : `Downgrade to ${plan.name} next cycle`;
      }
    } else if (plan.id === "free") {
      disabled = true;
      label = currentPlan === "free" ? "Current plan" : "Included";
    }

    if (busy === plan.id) label = "Updating…";
    return { disabled, label };
  }

  return <AppShell title="Plans & billing" subtitle="Fair Access Pricing — same strong AI, pay only for the usage you need.">
    <div className="billing-principle"><Sparkles size={18}/><div><b>Start small. Grow when you grow.</b><span>Every paid plan includes 1080p, no watermark and unlimited exports & re-exports of created Shorts. New Mini Pass creation access ends at 5 finished Shorts, 25 Karo Minutes, or 30 days, whichever comes first. Existing passes retain their purchased minutes.</span></div><ShieldCheck size={18}/></div>
    {legalStatus && legalStatus.razorpay_mode === "test" && <div className="info-banner" style={{background: "#e8f5e9", border: "1px solid #c8e6c9", color: "#1b5e20", padding: 12, borderRadius: 8, marginBottom: 16}}>🧪 <b>Razorpay Test Mode</b> — Payments are simulated. No real money will be charged. Use test card numbers from Razorpay documentation.</div>}
    {legalStatus && legalStatus.razorpay_mode === "live" && legalStatus.development_live_opt_in && <div className="error-banner"><span>⚠️ <b>Razorpay LIVE Mode</b> — this local checkout can charge real money. Use only an account/payment method you intentionally want to charge.</span></div>}
    {error && <div className="error-banner"><span>{error}</span></div>}
    {notice && <div className="success-banner"><span>{notice}</span></div>}
    {protectedLegacy && usage && <div className="billing-manage">
      <div>
        <b>Your previously purchased plan is protected</b>
        <span>You are on the existing {currentPlan} terms: ₹{(usage.plan_price_paise || 0) / 100}{currentPlan === "mini_pass" ? " one-time" : "/month"}, {usage.processing_minutes_limit} Karo Minutes for this billing period and {usage.shorts_limit ?? usage.exports_limit} source-project creation credits. These remain your effective limits and bill; the new-price offers below apply only to newly selected plans.</span>
      </div>
    </div>}

    <div className="billing-manage">
      <div>
        <b>Before you pay</b>
        <span>Mini Pass is ₹59 one-time for 25 total source-processing minutes and 5 finished Shorts. New passes expire on exhausted minutes, 5 created Shorts, or after 30 days; existing paid passes keep their original 125 minutes. Already-created Shorts keep unlimited export and re-export access while their retained source media remains available. Creator, Growth, Pro and Agency renew monthly at the selected plan price until cancelled or changed. Review the <Link href="/refund-policy" target="_blank" rel="noopener noreferrer">Refund Policy</Link> and <Link href="/legal-notice" target="_blank" rel="noopener noreferrer">consumer information</Link>.</span>
      </div>
    </div>

    {legalStatus && !legalStatus.checkout_allowed && <div className="error-banner"><span>{legalStatus.checkout_reason}</span></div>}
    {legalStatus && !legalStatus.accepted && <div className="billing-manage">
      <div>
        <b>Legal documents updated</b>
        <span>Existing accounts must accept the current document version before starting a new paid plan or increasing paid spend. Downgrades and cancellations remain available without new acceptance.</span>
      </div>
      <label style={{ display: "flex", gap: 9, alignItems: "flex-start", maxWidth: 460, fontSize: 13, lineHeight: 1.5 }}>
        <input type="checkbox" checked={legalChecked} onChange={(event) => setLegalChecked(event.target.checked)} style={{ marginTop: 3 }}/>
        <span>I agree to the current <Link href="/terms" target="_blank" rel="noopener noreferrer">Terms</Link>, <Link href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Notice</Link> and <Link href="/refund-policy" target="_blank" rel="noopener noreferrer">Refund Policy</Link>.</span>
      </label>
    </div>}

    {currentIsRecurring && scheduledPlan && <div className="billing-manage">
      <div>
        <b>{status?.scheduled_change_type === "cancel" ? "Subscription ending" : "Plan change scheduled"}</b>
        <span>
          {status?.scheduled_change_type === "cancel"
            ? `Your ${plans.find((plan) => plan.id === currentPlan)?.name || currentPlan} plan stays active until ${formatDate(status?.scheduled_plan_effective_at)}, then your account moves to Free.`
            : `${scheduledPlanName || scheduledPlan} starts on ${formatDate(status?.scheduled_plan_effective_at)}. Until then, your current plan and limits stay unchanged.`}
        </span>
      </div>
      {status?.scheduled_change_type === "downgrade" && <button className="secondary-btn" disabled={!!busy} onClick={cancelScheduledDowngrade}>
        {busy === "cancel-change" ? <Loader2 className="spin" size={14}/> : "Cancel scheduled downgrade"}
      </button>}
    </div>}

    <div className="plans-full clipkaro-plans">
      {plans.map((plan) => {
        const current = currentPlan === plan.id && !(plan.id === "mini_pass" && miniPassExhausted);
        const details = copy[plan.id] || { tagline: "", features: [] };
        const suffix = plan.billing === "one_time" ? " one-time" : plan.billing === "subscription" ? "/month" : "";
        const button = buttonState(plan);
        return <div className={`plan-card ${plan.popular ? "popular" : ""}`} key={plan.id}>
          {plan.popular && <span className="popular-tag">MOST POPULAR</span>}
          <h3>{plan.name}</h3>
          <p>{details.tagline}</p>
          <div className="price">₹{plan.price.toLocaleString("en-IN")}<small>{suffix}</small></div>
          <ul>{details.features.map((item) => <li key={item}><Check size={13}/>{item}</li>)}</ul>
          <button
            disabled={button.disabled}
            onClick={() => choose(plan)}
            className={plan.popular ? "primary-btn" : "secondary-btn"}
          >
            {busy === plan.id && <Loader2 className="spin" size={14}/>} {button.label}
          </button>
          {plan.billing === "subscription" && !current && <p className="muted-copy">Renews monthly until cancelled or changed.</p>}
          {plan.billing === "one_time" && <p className="muted-copy">{miniPassExhausted ? "Previous Mini Pass creation allowance ended · buy another anytime." : "One-time purchase · ends at 5 finished Shorts, 25 total minutes, or 30 days · no auto-renewal."}</p>}
          {current && status?.scheduled_change_type === "downgrade" && <p className="muted-copy">Current until {formatDate(status.scheduled_plan_effective_at)}</p>}
        </div>;
      })}
    </div>

    {currentIsRecurring && <div className="billing-manage">
      <div><b>Manage subscription</b><span>{status?.cancel_at_period_end ? "Cancellation is already scheduled and your paid access remains active until the cycle ends." : "Upgrades apply immediately. Downgrades and cancellation apply at the end of your paid cycle."}</span></div>
      <button className="secondary-btn" disabled={!!busy || !!status?.cancel_at_period_end} onClick={cancelSubscription}>{busy === "cancel" ? <Loader2 className="spin" size={14}/> : status?.cancel_at_period_end ? "Cancellation scheduled" : "Downgrade to Free at cycle end"}</button>
    </div>}
  </AppShell>;
}
