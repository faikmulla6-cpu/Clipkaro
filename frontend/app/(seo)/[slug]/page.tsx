import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  Check,
  Clapperboard,
  Languages,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Upload,
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
    openGraph: { type: "website", url: `/${page.slug}`, siteName: "ClipKaro AI", title: page.metaTitle, description: page.description, images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: page.title }] },
    twitter: { card: "summary_large_image", title: page.metaTitle, description: page.description, images: ["/assets/clipkaro-icon.png"] },
  };
}

const capabilities = [
  { icon: Scissors, title: "Start from ranked moments", text: "ClipKaro analyses the source before asking you to edit, so the first screen is a shortlist of moments with titles, hooks, reasons and scores — not a blank timeline." },
  { icon: Subtitles, title: "Review speech before captions", text: "Transcript Review helps you inspect uncertain lines before corrected text flows into captions and downstream creator assets." },
  { icon: Languages, title: "Built for Indian creator speech", text: "Hindi, Hinglish and Indian-English workflows are treated as real creator inputs, with India Quality Mode available where the creator wants that extra review layer." },
  { icon: Clapperboard, title: "Finish inside one creator workflow", text: "Choose the moment, adjust framing and caption presentation, render the Short, then continue into publishing copy instead of rebuilding the work in separate tools." },
] as const;

export default async function SeoLandingPage({ params }: PageProps) {
  const { slug } = await params;
  const page = getSeoPage(slug);
  if (!page) notFound();

  const schema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "ClipKaro AI",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: `https://clipkaro.pro/${page.slug}`,
    description: page.description,
    offers: { "@type": "Offer", priceCurrency: "INR", price: "59", availability: "https://schema.org/InStock" },
  };
  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: page.faq.map((item) => ({ "@type": "Question", name: item.question, acceptedAnswer: { "@type": "Answer", text: item.answer } })),
  };

  const words = page.h1.split(" ");
  const leadWords = words.slice(0, -2).join(" ");
  const accentWords = words.slice(-2).join(" ");

  return (
    <PublicMotionShell>
      <div className={styles.page}>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />
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
              <span><ShieldCheck size={13}/> Upload content you own</span>
              <span><Scissors size={13}/> AI-ranked moments</span>
              <span><Clapperboard size={13}/> Creator-controlled export</span>
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
            <div className={styles.proofItem}><Upload size={18}/><b>Upload-first</b><span>Use video files you own or have permission to process.</span></div>
            <div className={styles.proofItem}><WandSparkles size={18}/><b>AI-ranked moments</b><span>Start with promising hooks and complete ideas instead of scrubbing blindly.</span></div>
            <div className={styles.proofItem}><ShieldCheck size={18}/><b>Private media window</b><span>Source and export files follow ClipKaro&apos;s configured retention and access rules.</span></div>
          </section>

          <section className={styles.story} data-public-reveal>
            <div className={styles.storyCopy}><span className={styles.kicker}>BUILT FOR THE REAL WORKFLOW</span><h2>{page.audience}</h2><p>{page.promise}</p></div>
            <div className={styles.audienceCard}><span>GOOD FIT WHEN YOU ALREADY HAVE CONTENT</span><h3>Record once. Find the moments. Keep the creative decision.</h3><div className={styles.usePills}>{page.useCases.slice(0,6).map((item)=><b key={item}>{item}</b>)}</div></div>
          </section>

          <section className={styles.darkSection} data-public-reveal>
            <div className={styles.darkInner}>
              <div className={styles.darkCopy}><span>FROM A LONG TIMELINE TO A SHORTLIST</span><h2>Let the product do the searching before you do the editing.</h2><p>ClipKaro is designed around the expensive part of repurposing: finding the moment that can survive outside the full video. The creator sees ranked possibilities first, then chooses what actually deserves an export.</p><div className={styles.darkList}><div><Check size={15}/><span>Rank moments by hook, clarity, value and clean endings.</span></div><div><Check size={15}/><span>Keep the surrounding context visible before you commit to a cut.</span></div><div><Check size={15}/><span>Move from selection into captions, framing and export without restarting.</span></div></div></div>
              <div className={styles.rankPanel} aria-label="Illustrative ranked ClipKaro moments"><div className={styles.rankPanelTop}><span>AI-RANKED MOMENTS</span><b>ILLUSTRATIVE PREVIEW</b></div>{[["01","The mistake almost every creator makes","Strong hook · complete thought","94"],["02","The practical 3-step explanation","Actionable · clear payoff","91"],["03","The story that changes the context","Standalone · emotional turn","87"]].map(([number,titleText,reason,score])=><div className={styles.rankRow} key={number}><span>{number}</span><div className={styles.rankInfo}><b>{titleText}</b><small>{reason}</small></div><div className={styles.rankScore}><b>{score}</b><small>moment</small></div></div>)}</div>
            </div>
          </section>

          <section className={styles.section} id="workflow" data-public-reveal><div className={styles.sectionHead}><span>ONE CONNECTED WORKFLOW</span><h2>From source video to creator-ready short-form output.</h2><p>The interface stays clear because the sequence is clear: source → intelligence → review → export.</p></div><div className={styles.workflow}>{page.workflow.map((step,index)=><article className={styles.step} key={step}><span className={styles.stepNumber}>0{index+1}</span><h3>{["Bring in the source","Find the moments","Review the result","Export with intent"][index] || `Step ${index+1}`}</h3><p>{step}</p></article>)}</div></section>

          <section className={styles.capabilities} data-public-reveal><div className={styles.section} style={{paddingBottom:45}}><div className={styles.sectionHead}><span>MORE THAN A CUT BUTTON</span><h2>One product language from transcript to final Short.</h2><p>The core ClipKaro surfaces stay connected so creators do not feel like they are jumping between unrelated tools.</p></div></div><div className={styles.capGrid}>{capabilities.map((item)=>{const Icon=item.icon;return <article className={styles.capCard} key={item.title}><span className={styles.capGlow}/><div className={styles.capIcon}><Icon size={20}/></div><h3>{item.title}</h3><p>{item.text}</p></article>;})}</div></section>

          <section className={styles.section} id="use-cases" data-public-reveal><div className={styles.sectionHead}><span>BEST-FIT USE CASES</span><h2>Use the workflow where long-form content already exists.</h2></div><div className={styles.useGrid}>{page.useCases.map((item)=><div className={styles.useItem} key={item}><Check size={15}/><span>{item}</span></div>)}</div></section>

          <section className={styles.section} data-public-reveal><div className={styles.trustNote}><ShieldCheck size={22}/><div><b>Honest capability note</b><p>{page.trust}</p></div></div></section>

          <section className={styles.section} id="faq" data-public-reveal><div className={styles.sectionHead}><span>QUESTIONS BEFORE YOU START</span><h2>Know what the workflow does before you upload.</h2></div><div className={styles.faq}>{page.faq.map((item)=><details key={item.question}><summary>{item.question}</summary><p>{item.answer}</p></details>)}</div></section>

          <section className={styles.finalCta} data-public-reveal><h2>Start with one video. Judge the clips yourself.</h2><p>The useful test is simple: does ClipKaro surface moments you would actually want to publish?</p><TransitionLink href="/signup" className={styles.primary}>Create your first clips <ArrowRight size={16}/></TransitionLink></section>
        </main>

        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
