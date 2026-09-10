import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  Check,
  CheckCircle2,
  Download,
  GraduationCap,
  Lightbulb,
  Mic2,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Youtube,
} from "lucide-react";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { TransitionLink } from "@/components/TransitionLink";
import { LEGAL_LINKS } from "@/lib/legal";
import styles from "./page.module.css";

const title = "YouTube Channel Analyzer — Creator Pulse | ClipKaro AI";
const description = "Analyse public YouTube channel performance with Creator Pulse for ₹1 per successful Pulse. Compare recent upload momentum and get one evidence-led next-video idea, hook, angle and downloadable thumbnail.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/youtube-channel-analyzer" },
  openGraph: {
    type: "website",
    url: "/youtube-channel-analyzer",
    siteName: "ClipKaro AI",
    title,
    description,
    images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: "Creator Pulse by ClipKaro AI" }],
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
    images: ["/assets/clipkaro-icon.png"],
  },
};

const webPageSchema = {
  "@context": "https://schema.org",
  "@type": "WebPage",
  name: "YouTube Channel Analyzer — Creator Pulse by ClipKaro AI",
  url: "https://clipkaro.pro/youtube-channel-analyzer",
  description,
  isPartOf: {
    "@type": "WebSite",
    name: "ClipKaro AI",
    url: "https://clipkaro.pro/",
  },
  about: {
    "@type": "SoftwareApplication",
    name: "Creator Pulse by ClipKaro AI",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
  },
};

const breadcrumbSchema = {
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  itemListElement: [
    { "@type": "ListItem", position: 1, name: "ClipKaro AI", item: "https://clipkaro.pro/" },
    { "@type": "ListItem", position: 2, name: "Creator Pulse", item: "https://clipkaro.pro/youtube-channel-analyzer" },
  ],
};

const included = [
  {
    icon: BarChart3,
    title: "Verified channel snapshot",
    text: "See public subscriber count when available, total channel views, published videos and recent average views from the channel evidence available to the Pulse.",
  },
  {
    icon: TrendingUp,
    title: "Recent-upload momentum",
    text: "Compare recent uploads using transparent views-per-day maths so the fastest-moving videos are visible without inventing private analytics.",
  },
  {
    icon: Activity,
    title: "Change since your last Pulse",
    text: "Saved Pulse history lets returning creators compare the current snapshot with the previous stored analysis instead of treating every scan as isolated.",
  },
  {
    icon: Lightbulb,
    title: "One next-video decision",
    text: "Turn the verified evidence into one focused recommendation with a title, reason, practical angle, opening hook and an explicit confidence level.",
  },
  {
    icon: Download,
    title: "One downloadable thumbnail",
    text: "A successful intelligence result prepares one thumbnail for the recommended idea, with a download action when generation is available.",
  },
  {
    icon: ShieldCheck,
    title: "Truth-first boundaries",
    text: "Creator Pulse does not pretend to know private CTR, impressions, retention, watch-time or search-volume data that was not supplied to the analysis.",
  },
];

const steps = [
  ["01", "Enter your public YouTube channel", "Use the channel handle or supported channel identifier. Creator Pulse starts from public YouTube evidence rather than asking for private Studio access."],
  ["02", "Verify and calculate the snapshot", "ClipKaro checks the channel, calculates recent performance and compares the new Pulse with saved history when a previous snapshot exists."],
  ["03", "Turn evidence into one next move", "The result explains what deserves attention and prepares one evidence-led next-video title, reason, angle, opening hook and confidence state."],
  ["04", "Take the idea into production", "Use the recommendation and download the prepared thumbnail when available. The creator remains responsible for the final topic, claims, edit and publishing decision."],
] as const;

const audiences = [
  [Youtube, "YouTubers", "Creators deciding what to make after a recent upload starts moving."],
  [GraduationCap, "Educators", "Teaching channels choosing which explanation or tutorial deserves a follow-up."],
  [Mic2, "Podcasters", "Conversation-led channels looking for recurring themes worth expanding."],
  [BriefcaseBusiness, "Founders & businesses", "Expert-led channels turning public performance into a clearer next content decision."],
] as const;

const faqs = [
  ["How much does Creator Pulse cost?", "Creator Pulse costs ₹1 for a successful Pulse. It is separate from ClipKaro's normal Karo Minute and Short-export plans."],
  ["Do I need to connect YouTube Studio?", "No. Creator Pulse is designed around public YouTube channel evidence and does not require private Studio analytics access for the current workflow."],
  ["Does Creator Pulse guarantee views or virality?", "No. It provides decision support from the evidence available in the Pulse. It cannot guarantee future views, subscribers, revenue or virality."],
  ["Does it know my CTR, impressions or retention?", "Not unless that information is explicitly available to the product. The current public-data workflow does not invent private CTR, impressions, watch time, retention or search-volume metrics."],
  ["What happens if the recommendation or thumbnail service is unavailable?", "Your verified channel analysis remains the important result. Optional intelligence is designed to fail without erasing the successful Pulse data."],
] as const;

export default function YoutubeChannelAnalyzerPage() {
  return (
    <div className={`landing ${styles.page}`}>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(webPageSchema) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }} />

      <nav className={`landing-nav ${styles.nav}`} aria-label="Creator Pulse marketing navigation">
        <TransitionLink href="/" aria-label="ClipKaro AI home"><Logo /></TransitionLink>
        <div className={`nav-links ${styles.desktopNav}`}>
          <TransitionLink href="/youtube-video-to-shorts-ai">AI Video Clipper</TransitionLink>
          <TransitionLink href="/ai-shorts-maker-india">YouTube Shorts Maker</TransitionLink>
          <a href="#included">What you get</a>
          <TransitionLink href="/pricing">Pricing</TransitionLink>
          <TransitionLink href="/about">About</TransitionLink>
        </div>
        <div className={`nav-ctas ${styles.desktopNav}`}>
          <TransitionLink href="/login" className="text-btn">Log in</TransitionLink>
          <Link href="/creator-pulse" className="primary-btn">Run Pulse · ₹1 <ArrowRight size={15}/></Link>
        </div>
        <MobileLandingMenu />
      </nav>

      <header className={styles.hero}>
        <div className={styles.heroGlow} aria-hidden="true" />
        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <div className={styles.kicker}><Activity size={14}/> Creator Pulse · ₹1 successful analysis</div>
            <h1>A YouTube channel analyzer that ends with <span>a next move.</span></h1>
            <p>
              Creator Pulse analyses the public evidence around your YouTube channel, compares recent upload momentum and turns that evidence into one clear content decision — including a title, reason, angle, opening hook and one downloadable thumbnail when available.
            </p>
            <div className={styles.actions}>
              <Link href="/creator-pulse" className={styles.primary}><Activity size={17}/> Run Creator Pulse · ₹1 <ArrowRight size={16}/></Link>
              <a href="#included" className={styles.secondary}>See what one Pulse includes</a>
            </div>
            <div className={styles.microTrust}>
              <span><CheckCircle2 size={14}/> ₹1 only for a successful Pulse</span>
              <span><Youtube size={14}/> Public YouTube evidence</span>
              <span><ShieldCheck size={14}/> No guessed private metrics</span>
            </div>
          </div>

          <div className={styles.preview} aria-label="Illustrative Creator Pulse result">
            <div className={styles.previewHead}>
              <div><small>ILLUSTRATIVE PRODUCT PREVIEW</small><h2>Creator Pulse</h2></div>
              <span><CheckCircle2 size={13}/> Verified</span>
            </div>
            <div className={styles.stats}>
              <div><span>Subscribers</span><b>12.4K</b></div>
              <div><span>Channel views</span><b>684K</b></div>
              <div><span>Recent avg.</span><b>3.8K</b></div>
            </div>
            <div className={styles.chart}>
              <div className={styles.chartTitle}><span>Recent momentum</span><b>views/day</b></div>
              <div><span>Build update</span><i><em style={{ width: "92%" }}/></i><b>2.8K</b></div>
              <div><span>What failed</span><i><em style={{ width: "62%" }}/></i><b>1.9K</b></div>
              <div><span>Setup guide</span><i><em style={{ width: "38%" }}/></i><b>1.1K</b></div>
            </div>
            <div className={styles.nextMove}>
              <div className={styles.nextCopy}>
                <span>YOUR NEXT MOVE</span>
                <h3>Turn the strongest recent theme into a practical follow-up</h3>
                <p>Continue what the public momentum supports instead of jumping to a random topic.</p>
                <small><b>Opening hook:</b> “The first version worked — here is the upgrade I would make now.”</small>
              </div>
              <div className={styles.thumb}>
                <span>THE NEXT<br/>UPGRADE</span>
                <small>DOWNLOADABLE THUMBNAIL</small>
              </div>
            </div>
            <p className={styles.previewNote}>Example only. A real Pulse uses the current public evidence from the channel you submit.</p>
          </div>
        </div>
      </header>

      <main>
        <section className={styles.audienceStrip} aria-label="Creator Pulse audiences">
          <span>Built for</span>
          {audiences.map(([Icon, label]) => <div key={label}><Icon size={16}/>{label}</div>)}
        </section>

        <section className={styles.section} id="included">
          <div className={styles.sectionHead}>
            <span>WHAT ONE PULSE INCLUDES</span>
            <h2>Not another wall of analytics. A smaller, clearer creator decision.</h2>
            <p>Creator Pulse separates verified evidence from creative assistance so creators can see what the system knows, what it calculated and what it is recommending.</p>
          </div>
          <div className={styles.featureGrid}>
            {included.map((item) => {
              const Icon = item.icon;
              return <article key={item.title}><div><Icon size={19}/></div><h3>{item.title}</h3><p>{item.text}</p></article>;
            })}
          </div>
        </section>

        <section className={styles.decisionSection}>
          <div className={styles.decisionCopy}>
            <span>FROM NUMBERS TO ACTION</span>
            <h2>See what is moving. Then leave with something you can actually make.</h2>
            <p>A successful Pulse is designed to move from observation to action without pretending that public analytics can predict the future.</p>
            <div className={styles.decisionList}>
              {["One recommended next-video title", "Why the evidence supports that direction", "A practical angle instead of a vague topic", "An opening hook to begin the video", "An explicit Strong, Moderate or Limited confidence state", "One downloadable thumbnail when generation is available"].map((item) => <div key={item}><Check size={15}/><span>{item}</span></div>)}
            </div>
            <Link href="/creator-pulse" className={styles.primary}><Activity size={17}/> Analyse my channel · ₹1 <ArrowRight size={16}/></Link>
          </div>
          <div className={styles.boundaryCard}>
            <div className={styles.boundaryIcon}><ShieldCheck size={22}/></div>
            <span>TRUTH-FIRST BOUNDARY</span>
            <h3>What Creator Pulse deliberately does not guess.</h3>
            <p>Public YouTube evidence cannot reveal every private Studio metric. Creator Pulse is designed not to fabricate missing data just to make a recommendation sound more certain.</p>
            <div className={styles.noGuessGrid}>
              {["CTR", "Impressions", "Retention", "Watch time", "Search volume", "Future virality"].map((item) => <span key={item}>{item}</span>)}
            </div>
            <small>Decision support, not a promise of performance.</small>
          </div>
        </section>

        <section className={styles.workflowSection}>
          <div className={styles.sectionHead}>
            <span>HOW CREATOR PULSE WORKS</span>
            <h2>Four steps from a channel handle to your next content decision.</h2>
          </div>
          <div className={styles.steps}>
            {steps.map(([number, heading, text]) => <article key={number}><span>{number}</span><h3>{heading}</h3><p>{text}</p></article>)}
          </div>
        </section>

        <section className={styles.peopleSection}>
          <div className={styles.sectionHead}>
            <span>WHO IT HELPS</span>
            <h2>Useful when the hard question is not “what happened?” but “what should I make next?”</h2>
          </div>
          <div className={styles.peopleGrid}>
            {audiences.map(([Icon, titleText, text]) => <article key={titleText}><div className={styles.personIcon}><Icon size={22}/></div><h3>{titleText}</h3><p>{text}</p></article>)}
          </div>
          <p className={styles.peopleNote}>These are creator types, not endorsements or fabricated customer testimonials.</p>
        </section>

        <section className={styles.faqSection}>
          <div className={styles.sectionHead}>
            <span>CREATOR PULSE FAQ</span>
            <h2>Know the limits before you spend ₹1.</h2>
          </div>
          <div className={styles.faqs}>
            {faqs.map(([question, answer]) => <details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}
          </div>
        </section>

        <section className={styles.finalCta}>
          <div><span><Sparkles size={14}/> READY FOR ONE CLEARER NEXT MOVE?</span><h2>Run Creator Pulse for ₹1.</h2><p>Already signed in? Go straight in. New to ClipKaro? Create your account, verify your email and continue back to Creator Pulse.</p></div>
          <Link href="/creator-pulse" className={styles.finalButton}>Run Creator Pulse · ₹1 <ArrowRight size={17}/></Link>
        </section>
      </main>

      <footer className="landing-footer">
        <div className={styles.footerInner}>
          <div><Logo light/><p>© 2026 ClipKaro AI. Create responsibly. Built for India.</p></div>
          <div className={styles.footerLinks}>
            <TransitionLink href="/youtube-video-to-shorts-ai">AI Video Clipper</TransitionLink>
            <TransitionLink href="/ai-shorts-maker-india">YouTube Shorts Maker</TransitionLink>
            <TransitionLink href="/youtube-channel-analyzer">Creator Pulse</TransitionLink>
            <TransitionLink href="/pricing">Pricing</TransitionLink>
            <TransitionLink href="/about">About</TransitionLink>
            <TransitionLink href="/contact">Contact</TransitionLink>
            {LEGAL_LINKS.slice(0, 3).map(([label, href]) => <TransitionLink key={href} href={href}>{label}</TransitionLink>)}
          </div>
        </div>
      </footer>
    </div>
  );
}
