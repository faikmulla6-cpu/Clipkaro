import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  Check,
  Clapperboard,
  Languages,
  Link2,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Subtitles,
  WandSparkles,
} from "lucide-react";
import { PublicMotionShell } from "@/components/PublicMotionShell";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { TransitionLink } from "@/components/TransitionLink";
import { getSeoPage, SEO_PAGES } from "@/lib/seo-pages";
import styles from "./seo-product-page.module.css";

type PageProps = { params: Promise<{ slug: string }> };

export const dynamicParams = false;
export function generateStaticParams() { return SEO_PAGES.map((page) => ({ slug: page.slug })); }

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const page = getSeoPage(slug);
  if (!page) return {};
  return {
    title: page.metaTitle,
    description: page.description,
    alternates: { canonical: `/${page.slug}` },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-video-preview": -1,
        "max-image-preview": "large",
        "max-snippet": -1,
      },
    },
    openGraph: { type: "website", url: `/${page.slug}`, siteName: "ClipKaro AI", title: page.metaTitle, description: page.description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: page.title }] },
    twitter: { card: "summary_large_image", title: page.metaTitle, description: page.description, images: ["/assets/clipkaro-icon.png"] },
  };
}

const capabilities = [
  { icon: Scissors, title: "Start from ranked moments", text: "ClipKaro analyses the source before asking you to edit, so the first screen is a shortlist of moments with titles, hooks, reasons and scores — not a blank timeline." },
  { icon: Subtitles, title: "Review speech before captions", text: "Transcript Review helps you inspect uncertain lines before corrected text flows into captions and downstream creator assets." },
  { icon: Languages, title: "Built for Indian creator speech", text: "Hindi, Hinglish and Indian-English workflows are treated as real creator inputs, with India Quality Mode available where the creator wants that extra review layer." },
  { icon: Clapperboard, title: "Creator Studio keeps the final edit yours", text: "Drag captions, resize them from 65% to 160%, change text alignment, zoom or reframe video, switch Hook Text on or off, preserve source subtitles and export 9:16, 4:5 or 1:1." },
] as const;

export default async function SeoLandingPage({ params }: PageProps) {
  const { slug } = await params;
  const page = getSeoPage(slug);
  if (!page) notFound();

  const schema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "@id": "https://clipkaro.pro/#software",
    name: "ClipKaro AI",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: "https://clipkaro.pro/",
    description: page.description,
    mainEntityOfPage: { "@id": `https://clipkaro.pro/${page.slug}#page` },
    publisher: { "@id": "https://clipkaro.pro/#organization" },
    audience: { "@type": "Audience", audienceType: page.audience },
    featureList: ["AI-ranked clip discovery", "Smart Transcript Review", "Drag-and-place caption controls", "65% to 160% caption sizing with automatic reflow", "Caption alignment controls", "Video zoom and manual horizontal reframe", "Hook Text On/Off", "9:16, 4:5 and 1:1 exports", "Unlimited Post Karo publishing access on every plan", "₹1 Creator Pulse channel intelligence"],
    isAccessibleForFree: true,
    offers: { "@type": "Offer", priceCurrency: "INR", price: "0", url: "https://clipkaro.pro/pricing", availability: "https://schema.org/InStock", description: "Start free; ₹59 one-time Mini Pass and Creator from ₹249/month are available. Unlimited Post Karo access is included on every plan." },
  };
  const breadcrumbSchema = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://clipkaro.pro/" },
      { "@type": "ListItem", position: 2, name: page.title, item: `https://clipkaro.pro/${page.slug}` },
    ],
  };
  const webPageSchema = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "@id": `https://clipkaro.pro/${page.slug}#page`,
    url: `https://clipkaro.pro/${page.slug}`,
    name: page.metaTitle,
    description: page.description,
    about: { "@id": "https://clipkaro.pro/#software" },
    publisher: { "@id": "https://clipkaro.pro/#organization" },
    inLanguage: "en-IN",
    dateModified: "2026-09-24",
  };

  const words = page.h1.split(" ");
  const leadWords = words.slice(0, -2).join(" ");
  const accentWords = words.slice(-2).join(" ");

  return (
    <PublicMotionShell>
      <div className={styles.page}>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(webPageSchema) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbSchema) }} />
        <PublicSiteNav />

        <header className={styles.hero} data-public-reveal>
          <div className={styles.heroGlow} aria-hidden="true" />
          <div className={styles.heroCopy}>
            <span className={styles.eyebrow}><Sparkles size={13}/>{page.eyebrow}</span>
            <h1>{leadWords} <span>{accentWords}</span></h1>
            <p className={styles.heroLead}>{page.lead}</p>
            <div className={styles.heroActions}>
              <TransitionLink href="/signup" className={styles.primary}>Try ClipKaro free <ArrowRight size={16}/></TransitionLink>
              <TransitionLink href="/pricing" className={styles.secondary}>See pricing</TransitionLink>
            </div>
            <div className={styles.microTrust}>
              <span><ShieldCheck size={13}/> Use content you own or can process</span>
              <span><Scissors size={13}/> AI-ranked moments</span>
              <span><Clapperboard size={13}/> Unlimited Post Karo · every plan</span>
            </div>
          </div>

          <div className={styles.demo} aria-label="Illustrative ClipKaro clipping workflow">
            <div className={styles.demoWindow}>
              <div className={styles.demoTop}><div className={styles.windowDots}><i/><i/><i/></div><span>CLIPKARO · CREATOR WORKSPACE</span></div>
              <div className={styles.demoBody}>
                <div className={styles.sourceCard}>
                  <div className={styles.sourceVisual}><span className={styles.sourceBadge}>48:32 SOURCE VIDEO</span><span className={styles.creatorHead}/><span className={styles.creatorBody}/><span className={styles.sourcePlay}><Play size={13} fill="currentColor"/></span></div>
                  <div className={styles.sourceMeta}><b>{page.useCases[0] || "Creator video"}</b><span>Transcript ready</span></div>
                  <div className={styles.timeline}><span className={styles.wave}/><span className={`${styles.moment} ${styles.momentOne}`}>82</span><span className={`${styles.moment} ${styles.momentTwo}`}>94</span><span className={`${styles.moment} ${styles.momentThree}`}>88</span></div>
                </div>
                <div className={styles.transform}><span><ArrowRight size={18}/></span></div>
                <div className={styles.shortCard}><div className={styles.shortTop}><span>BEST MOMENT</span><b>94</b></div><span className={styles.shortPerson}/><div className={styles.caption}>TURN ONE IDEA INTO<br/><span>A SHORT WORTH POSTING</span></div><div className={styles.shortFooter}><span>9:16 EXPORT</span><span>CAPTIONS ON</span></div></div>
              </div>
            </div>
            <p className={styles.demoNote}>Illustrative product preview — the actual result depends on the source video, speech and selected moment.</p>
          </div>
        </header>

        <main>
          <section className={styles.proofStrip} data-public-reveal>
            <div className={styles.proofItem}><Link2 size={18}/><b>URL or original file</b><span>Paste a supported YouTube link or upload the source you own or have permission to process.</span></div>
            <div className={styles.proofItem}><WandSparkles size={18}/><b>AI-ranked moments</b><span>Start with promising hooks and complete ideas instead of scrubbing blindly.</span></div>
            <div className={styles.proofItem}><ShieldCheck size={18}/><b>Private media window</b><span>Source and export files follow ClipKaro&apos;s configured retention and access rules.</span></div>
          </section>

          <section className={styles.story} data-public-reveal>
            <div className={styles.storyCopy}><span className={styles.kicker}>QUICK ANSWER</span><h2>What does {page.title} help you do?</h2><p>{page.lead}</p><p>{page.promise}</p></div>
            <div className={styles.audienceCard}><span>WHO IT IS FOR</span><h3>{page.audience}</h3><div className={styles.usePills}>{page.useCases.slice(0,6).map((item)=><b key={item}>{item}</b>)}</div></div>
          </section>

          {page.decisionFacts && <section className={styles.section} data-public-reveal><div className={styles.sectionHead}><span>PRICE + PUBLISHING ANSWER</span><h2>Know exactly what is affordable, what is unlimited and what still has plan limits.</h2><p>ClipKaro separates creation capacity from publishing access so the comparison is clear before you sign up.</p></div><div className={styles.useGrid}>{page.decisionFacts.map((fact)=><div className={styles.useItem} key={fact.label}><Check size={15}/><span><b>{fact.label}:</b> {fact.value}</span></div>)}</div></section>}

          <section className={styles.section} data-public-reveal><div className={styles.sectionHead}><span>CLIPKARO FACTS AT A GLANCE</span><h2>Affordable creation. Creator-controlled editing. Unlimited publishing access.</h2><p>These product facts stay consistent across ClipKaro so creators and search systems can understand the same offering without hidden conditions.</p></div><div className={styles.useGrid}><div className={styles.useItem}><Check size={15}/><span>Start free · Mini Pass ₹59 one-time · Creator ₹249/month</span></div><div className={styles.useItem}><Check size={15}/><span>Unlimited Post Karo access on every plan · no ClipKaro per-post quota</span></div><div className={styles.useItem}><Check size={15}/><span>Creator Studio: drag, resize and align captions · zoom · reframe · Hook Text On/Off</span></div><div className={styles.useItem}><Check size={15}/><span>Creator Pulse: ₹1 per successful public-channel analysis</span></div></div></section>

          <section className={styles.darkSection} data-public-reveal>
            <div className={styles.darkInner}>
              <div className={styles.darkCopy}><span>FROM A LONG TIMELINE TO A SHORTLIST</span><h2>Let the product do the searching before you do the editing.</h2><p>ClipKaro is designed around the expensive part of repurposing: finding the moment that can survive outside the full video. The creator sees ranked possibilities first, then chooses what actually deserves an export.</p><div className={styles.darkList}><div><Check size={15}/><span>Rank moments by hook, clarity, value and clean endings.</span></div><div><Check size={15}/><span>Keep the surrounding context visible before you commit to a cut.</span></div><div><Check size={15}/><span>Move from selection into captions, framing and export without restarting.</span></div></div></div>
              <div className={styles.rankPanel} aria-label="Illustrative ranked ClipKaro moments"><div className={styles.rankPanelTop}><span>AI-RANKED MOMENTS</span><b>ILLUSTRATIVE PREVIEW</b></div>{[["01","The mistake almost every creator makes","Strong hook · complete thought","94"],["02","The practical 3-step explanation","Actionable · clear payoff","91"],["03","The story that changes the context","Standalone · emotional turn","87"]].map(([number,titleText,reason,score])=><div className={styles.rankRow} key={number}><span>{number}</span><div className={styles.rankInfo}><b>{titleText}</b><small>{reason}</small></div><div className={styles.rankScore}><b>{score}</b><small>moment</small></div></div>)}</div>
            </div>
          </section>

          <section className={styles.section} id="workflow" data-public-reveal><div className={styles.sectionHead}><span>ONE CONNECTED WORKFLOW</span><h2>From source video to creator-ready short-form output.</h2><p>The interface stays clear because the sequence is clear: URL or file → intelligence → review → export.</p></div><div className={styles.workflow}>{page.workflow.map((step,index)=><article className={styles.step} key={step}><span className={styles.stepNumber}>0{index+1}</span><h3>{["Bring in the source","Find the moments","Review the result","Export with intent"][index] || `Step ${index+1}`}</h3><p>{step}</p></article>)}</div></section>

          <section className={styles.capabilities} data-public-reveal><div className={styles.section} style={{paddingBottom:45}}><div className={styles.sectionHead}><span>MORE THAN A CUT BUTTON</span><h2>One product language from transcript to final Short.</h2><p>The core ClipKaro surfaces stay connected so creators do not feel like they are jumping between unrelated tools.</p></div></div><div className={styles.capGrid}>{capabilities.map((item)=>{const Icon=item.icon;return <article className={styles.capCard} key={item.title}><span className={styles.capGlow}/><div className={styles.capIcon}><Icon size={20}/></div><h3>{item.title}</h3><p>{item.text}</p></article>;})}</div></section>

          <section className={styles.section} id="use-cases" data-public-reveal><div className={styles.sectionHead}><span>BEST-FIT USE CASES</span><h2>Use the workflow where long-form content already exists.</h2></div><div className={styles.useGrid}>{page.useCases.map((item)=><div className={styles.useItem} key={item}><Check size={15}/><span>{item}</span></div>)}</div></section>

          <section className={styles.section} data-public-reveal><div className={styles.trustNote}><ShieldCheck size={22}/><div><b>Honest capability note</b><p>{page.trust}</p></div></div></section>

          <section className={styles.section} id="faq" data-public-reveal><div className={styles.sectionHead}><span>QUESTIONS BEFORE YOU START</span><h2>Know what the workflow does before you upload.</h2></div><div className={styles.faq}>{page.faq.map((item)=><details key={item.question}><summary>{item.question}</summary><p>{item.answer}</p></details>)}</div></section>

          <section className={styles.finalCta} data-public-reveal><h2>Start free. Find the moment. Finish the edit. Post Karo.</h2><p>Try the clipping workflow at ₹0, keep final control in Creator Studio, then use unlimited Post Karo publishing access on any plan when the Short is ready.</p><TransitionLink href="/signup" className={styles.primary}>Create my first Short free <ArrowRight size={16}/></TransitionLink></section>
        </main>

        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
