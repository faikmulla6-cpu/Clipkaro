"use client";

import { useEffect } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  Clapperboard,
  Cloud,
  Instagram,
  Languages,
  Link2,
  LockKeyhole,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Upload,
  Youtube,
  WandSparkles,
  Workflow,
  Zap,
} from "lucide-react";
import { AboutCreatorPulse } from "@/components/AboutCreatorPulse";
import { Logo } from "@/components/Logo";
import { TransitionLink } from "@/components/TransitionLink";
import styles from "./about.module.css";
import polish from "./about-polish.module.css";
import story from "./about-story.module.css";

const processSteps = [
  {
    icon: Link2,
    number: "01",
    title: "URL or private upload",
    text: "A creator can start from a supported YouTube URL or upload an original file they own or are authorised to use. If direct URL acquisition is unavailable, the file-upload path keeps the workflow moving.",
  },
  {
    icon: BrainCircuit,
    number: "02",
    title: "Speech intelligence",
    text: "The platform turns speech into structured timing data so the system can understand what was said, when it was said, and how the surrounding context fits together.",
  },
  {
    icon: WandSparkles,
    number: "03",
    title: "Moment intelligence",
    text: "Potential hooks, lessons, stories, questions and high-value moments are ranked instead of forcing the creator to scrub through an entire recording manually.",
  },
  {
    icon: Clapperboard,
    number: "04",
    title: "Creator control",
    text: "ClipKaro proposes the moment. The creator still chooses what to publish, how captions should look, where they sit, how tightly the shot is framed, and whether the result deserves an export.",
  },
  {
    icon: Zap,
    number: "05",
    title: "Isolated rendering",
    text: "Heavy video work runs separately from the everyday web experience so browsing, account actions and creator decisions do not need to carry the weight of media processing.",
  },
  {
    icon: CheckCircle2,
    number: "06",
    title: "Verified delivery",
    text: "A finished export is treated as a real production object with status, retention and delivery rules—not simply as a file that may or may not have finished rendering.",
  },
];

const engineeringChallenges = [
  {
    icon: Languages,
    title: "Language is messy in the real world",
    text: "Indian creators naturally switch between Hindi, English and Hinglish. ClipKaro was shaped around preserving meaning, timing and readability instead of assuming every sentence belongs to one clean language bucket.",
  },
  {
    icon: Workflow,
    title: "AI output needs a reliable workflow",
    text: "Transcription, ranking and captions are only useful when upload state, retries, processing jobs, creator edits and exports remain consistent even when something is interrupted.",
  },
  {
    icon: Scissors,
    title: "A good clip is more than a cut",
    text: "Useful short-form moments need context, a clean beginning, a satisfying ending and a reason to watch. ClipKaro evaluates moments as communication, not only as timestamps.",
  },
  {
    icon: ShieldCheck,
    title: "Private media deserves private handling",
    text: "Source files and exports are treated as protected creator media. Access is deliberately controlled rather than turning uploaded videos into casually public assets.",
  },
  {
    icon: Cloud,
    title: "Media compute should not slow the product",
    text: "The architecture separates lightweight product interactions from demanding media work, allowing the creator experience and the rendering system to scale for different kinds of load.",
  },
  {
    icon: LockKeyhole,
    title: "Usage and billing must be durable",
    text: "Rendering is tied to real usage rules so duplicate clicks, retries or browser behaviour do not become an excuse for inaccurate quotas or an unpredictable paid experience.",
  },
];

const reliabilityCases = [
  {
    problem: "Interrupted processing",
    response: "Explicit job state + retry boundaries",
    text: "Long-running media work is tracked as durable state so a temporary failure can be handled deliberately instead of leaving a creator with a mystery spinner.",
  },
  {
    problem: "Duplicate actions",
    response: "Idempotent export + usage rules",
    text: "Retries and repeated clicks are treated as engineering cases to absorb safely, not as reasons to double-count creator usage or create duplicate final outputs.",
  },
  {
    problem: "Heavy rendering",
    response: "Isolated media workers",
    text: "Encoding and media processing are kept away from everyday product requests so opening a project, reviewing a moment and managing an account remain responsive.",
  },
  {
    problem: "Private creator media",
    response: "Controlled, time-limited delivery",
    text: "Source files and finished exports use deliberately constrained access paths so creator media does not become permanently public just because it moved through a web workflow.",
  },
];

const principles = [
  ["Creators stay in control.", "AI can recommend. The creator decides what represents their voice."],
  ["Privacy belongs in the architecture.", "Trust is a product decision, not a paragraph added after launch."],
  ["Reliability is a feature.", "A beautiful interface means very little if the final export cannot be trusted."],
  ["AI should remove repetition, not creativity.", "The goal is to give creators more time for judgment, storytelling and publishing."],
  ["Build for the full workflow.", "Upload, intelligence, review, styling, rendering and delivery should feel like one product."],
];

const futureSignals = [
  ["Understand context", "AI should recognise what matters before asking the creator to edit."],
  ["Protect creator choice", "Recommendations can accelerate the workflow without taking authorship away."],
  ["Publish with confidence", "The final file, usage state and delivery path should be as dependable as the interface."],
];

const productSurfaces = [
  {
    icon: Link2,
    title: "YouTube URL intake + file fallback",
    text: "Paste a supported YouTube video, Shorts or live-replay URL. If the source cannot be acquired directly, ClipKaro surfaces original-file upload instead of leaving the creator at a dead end.",
  },
  {
    icon: Activity,
    title: "Creator Pulse — ₹1 Channel Analysis",
    text: "Verified public YouTube performance becomes recent-upload momentum, previous-Pulse comparison and one evidence-led next-video recommendation with a title, angle, hook and downloadable thumbnail.",
  },
  {
    icon: Languages,
    title: "India Quality Mode",
    text: "A creator-facing mode for Hindi, Hinglish and Indian-English workflows, with Roman Hinglish handling and safer caption placement.",
  },
  {
    icon: Workflow,
    title: "Smart Transcript Review",
    text: "Suspicious transcript lines are shown with timestamps, jump controls, inline correction, reset and corrected text flowing into captions and Content Packs.",
  },
  {
    icon: Sparkles,
    title: "One Video → Content Pack",
    text: "Selected clips can become YouTube titles and descriptions, Instagram captions, hashtags, X posts, LinkedIn copy, cover text, content angles and recommended publishing order.",
  },
  {
    icon: Clapperboard,
    title: "Creator Studio controls",
    text: "The editor exposes zoom, manual horizontal reframe, aspect ratio, caption style, caption position, watermark, quality and Brand Kit controls before export.",
  },
  {
    icon: Scissors,
    title: "Caption-safe framing",
    text: "If the source already contains burned-in subtitles, ClipKaro can preserve the subtitle area instead of destroying it during vertical conversion.",
  },
  {
    icon: Zap,
    title: "Export-ready delivery",
    text: "Render status, download availability, quota rules and export behavior are product surfaces, not hidden backend side effects.",
  },
];

export function AboutExperience() {
  useEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>("[data-about-reveal]"));
    if (!("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add(styles.visible));
    } else {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              (entry.target as HTMLElement).classList.add(styles.visible);
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -7% 0px" },
      );

      items.forEach((item) => observer.observe(item));
      return () => observer.disconnect();
    }
  }, []);

  useEffect(() => {
    let frame = 0;
    const updateProgress = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      document.documentElement.style.setProperty("--ck-about-progress", `${ratio * 100}%`);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(updateProgress);
    };

    updateProgress();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      document.documentElement.style.removeProperty("--ck-about-progress");
    };
  }, []);

  return (
    <main className={`${styles.page} ${polish.page}`}>
      <div className={story.progress} aria-hidden="true"><span /></div>

      <nav className={`${styles.nav} ${polish.nav}`}>
        <Logo light transition />
        <div className={styles.navLinks} aria-label="About page sections">
          <a href="#mission">Mission</a>
          <a href="#technology">Technology</a>
          <a href="#product">Product</a>
          <a href="#creator-pulse-story">Creator Pulse</a>
          <a href="#principles">Principles</a>
          <a href="#founder">Founder</a>
        </div>
        <Link href="/creator-pulse" className={styles.navCta}>
          Creator Pulse · ₹1 <ArrowRight size={15} />
        </Link>
      </nav>

      <section className={`${styles.hero} ${polish.hero} ${story.heroPacing}`}>
        <div className={styles.heroGlow} aria-hidden="true" />
        <div className={`${styles.heroGrid} ${polish.heroGrid}`}>
          <div className={`${styles.heroCopy} ${polish.heroCopy}`}>
            <span className={styles.kicker}><Sparkles size={14} /> About ClipKaro</span>
            <h1 className={polish.heroTitle}>
              We&apos;re building a faster way to turn long-form video into
              <span> short-form content worth publishing.</span>
            </h1>
            <p>
              ClipKaro is an AI-powered creation platform designed for creators, educators,
              podcasters and businesses who want to find the strongest moments inside their
              content without spending hours manually searching, cutting, captioning and writing publishing copy.
            </p>
            <div className={polish.heroSignals} aria-label="ClipKaro product priorities">
              <span>AI video intelligence</span>
              <span>Creator-controlled</span>
              <span>India Quality Mode</span>
              <span>Complete Content Packs</span>
            </div>
            <div className={styles.heroActions}>
              <a href="#mission" className={styles.primaryAction}>Explore our story <ArrowRight size={17} /></a>
              <TransitionLink href="/" className={styles.secondaryAction}>Visit ClipKaro</TransitionLink>
            </div>
          </div>

          <div className={`${styles.logoStage} ${polish.logoStage}`} aria-label="ClipKaro brand mark">
            <div className={styles.logoOrbit} aria-hidden="true" />
            <div className={styles.logoHalo} aria-hidden="true" />
            <div className={polish.brandFrame}>
              <img src="/assets/clipkaro-icon.png" alt="ClipKaro logo icon" className={`${styles.brandIcon} ${polish.brandIcon}`} />
            </div>
            <span className={styles.stageLabel}>AI · VIDEO · CREATOR INTELLIGENCE</span>
          </div>
        </div>
        <div className={styles.scrollCue}>Scroll to see how the product was built <span>↓</span></div>
      </section>

      <section className={`${styles.statement} ${polish.lightSection} ${story.sectionPacing}`} id="mission">
        <div className={styles.statementInner} data-about-reveal>
          <span className={styles.sectionIndex}>01 / WHY</span>
          <h2>Creating a 60-second Short shouldn&apos;t require hours of searching through a 60-minute video.</h2>
          <p>
            Long-form content already contains stories, insights, reactions, lessons and hooks.
            The difficult part is finding the right moment, preserving the context, turning it
            into a mobile-first edit, correcting the transcript when needed and getting the clip
            ready to publish across platforms. ClipKaro was created to compress that production
            work without compressing the creator&apos;s judgment.
          </p>
        </div>
      </section>

      <section className={`${styles.originSection} ${polish.originSection} ${story.sectionPacing}`}>
        <div className={styles.originGrid}>
          <div className={styles.stickyTitle} data-about-reveal>
            <span className={styles.sectionIndex}>02 / THE ORIGIN</span>
            <h2>We didn&apos;t want to build another video trimmer.</h2>
          </div>
          <div className={styles.originCopy}>
            <article data-about-reveal>
              <span>THE OBSERVATION</span>
              <h3>The repetitive work was hiding the creative work.</h3>
              <p>
                A creator could record one valuable conversation and still spend the next few
                hours scanning footage, writing subtitles, finding a hook, reframing the shot,
                checking timing and exporting multiple versions. The workflow was technically
                possible, but unnecessarily expensive in time and attention.
              </p>
            </article>
            <article data-about-reveal>
              <span>THE PRODUCT QUESTION</span>
              <h3>What if software understood the video before asking the creator to edit it?</h3>
              <p>
                That question changed the product from a cutting tool into an intelligence
                pipeline. Speech becomes structured information. Moments are evaluated. The
                creator receives ranked possibilities, then decides what is actually worth
                turning into a Short.
              </p>
            </article>
            <article data-about-reveal>
              <span>THE STANDARD</span>
              <h3>Simple in front. Serious engineering behind it.</h3>
              <p>
                ClipKaro treats the web experience, AI systems, storage, processing, rendering,
                usage controls and delivery as one connected product. The complexity belongs
                behind the interface, not in the creator&apos;s workflow.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className={`${styles.timelineSection} ${polish.darkSection} ${story.sectionPacing}`} id="technology">
        <div className={styles.sectionLead} data-about-reveal>
          <span className={styles.sectionIndex}>03 / ONE SHORT</span>
          <h2>What happens behind one click.</h2>
          <p>
            A creator sees a simple workflow. Behind it, ClipKaro coordinates multiple systems
            so intelligence and media processing can happen in the right order.
          </p>
        </div>

        <div className={styles.timelineDemo} data-about-reveal>
          <div className={styles.sourcePanel}>
            <div className={styles.videoHeader}><Play size={15} fill="currentColor" /> 58:42 SOURCE VIDEO</div>
            <div className={styles.longTimeline}>
              <span className={styles.timelineWave} />
              <span className={`${styles.moment} ${styles.momentOne}`}>82</span>
              <span className={`${styles.moment} ${styles.momentTwo}`}>94</span>
              <span className={`${styles.moment} ${styles.momentThree}`}>88</span>
            </div>
            <div className={styles.timelineMeta}><span>Transcript intelligence</span><span>Strongest moment · 94</span></div>
          </div>
          <ArrowRight className={styles.transformArrow} size={28} />
          <div className={styles.shortPreview}>
            <div className={styles.previewLight} />
            <span className={styles.previewBadge}>BEST MOMENT</span>
            <div className={styles.captionMock}>THIS CHANGED<br/><b>EVERYTHING</b></div>
            <div className={styles.previewFooter}><span>9:16</span><span>00:37</span></div>
          </div>
        </div>

        <div className={story.railHint}>The workflow</div>
        <div className={`${styles.processGrid} ${story.horizontalRail} ${story.processRail}`}>
          {processSteps.map((step) => {
            const Icon = step.icon;
            return (
              <article className={styles.processCard} key={step.number} data-about-reveal>
                <div className={styles.processTop}><span>{step.number}</span><Icon size={20} /></div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className={`${styles.realitySection} ${polish.realitySection} ${story.sectionPacing}`}>
        <div className={styles.realityIntro} data-about-reveal>
          <span className={styles.sectionIndex}>04 / ENGINEERING REALITY</span>
          <h2>AI is only useful when the system around it is reliable.</h2>
          <p>
            Building ClipKaro meant solving the unglamorous parts too: interruptions, duplicate
            actions, media validation, language switching, protected files, long-running jobs,
            mobile workflows, accurate usage and exports that need to finish exactly once.
          </p>
        </div>

        <div className={story.railHint}>Engineering realities</div>
        <div className={`${styles.challengeGrid} ${story.horizontalRail} ${story.challengeRail}`}>
          {engineeringChallenges.map((item) => {
            const Icon = item.icon;
            return (
              <article className={styles.challengeCard} key={item.title} data-about-reveal>
                <Icon size={21} />
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </article>
            );
          })}
        </div>

        <div className={polish.reliabilityBlock} data-about-reveal>
          <div className={polish.reliabilityHeading}>
            <span>HOW THE HARD PARTS ARE TACKLED</span>
            <h3>Failure modes become product rules.</h3>
            <p>ClipKaro is designed around the idea that reliability should be visible in the outcome, not exposed as complexity in the interface.</p>
          </div>
          <div className={story.railHint}>Reliability rules</div>
          <div className={`${polish.reliabilityGrid} ${story.horizontalRail} ${story.reliabilityRail}`}>
            {reliabilityCases.map((item, index) => (
              <article className={polish.reliabilityCase} key={item.problem}>
                <span>0{index + 1}</span>
                <small>{item.problem}</small>
                <strong>{item.response}</strong>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className={`${styles.indiaSection} ${polish.indiaSection} ${story.sectionPacing} ${story.indiaLayout}`}>
        <div className={`${styles.languageVisual} ${story.indiaVisual}`} data-about-reveal>
          <span className={styles.languageChip}>Hindi</span>
          <span className={styles.languageChip}>English</span>
          <span className={`${styles.languageChip} ${styles.languageChipStrong}`}>Hinglish</span>
          <div className={styles.transcriptLine}>"Aaj ka <b>biggest lesson</b> ye tha..."</div>
          <div className={styles.captionResult}>AAJ KA <strong>BIGGEST LESSON</strong><br/>YE THA...</div>
        </div>
        <div className={`${styles.indiaCopy} ${story.indiaCopy}`} data-about-reveal>
          <span className={styles.sectionIndex}>05 / BUILT WITH INDIA IN MIND</span>
          <h2>Natural language rarely stays inside one box.</h2>
          <p>
            Indian creators often move between languages inside the same thought. ClipKaro&apos;s
            product direction recognises that transcription quality is not enough by itself:
            timing, readability and the creator&apos;s intended meaning matter too.
          </p>
          <p>
            That is why India Quality Mode, Roman Hinglish handling and Smart Transcript Review
            exist as visible workflow controls, not hidden backend claims.
          </p>
        </div>
      </section>

      <section className={`${styles.realitySection} ${polish.realitySection} ${story.sectionPacing}`} id="product">
        <div className={styles.realityIntro} data-about-reveal>
          <span className={styles.sectionIndex}>06 / PRODUCT SURFACES</span>
          <h2>Every core capability has a place creators can actually use.</h2>
          <p>
            ClipKaro does not depend on backend features that users never see. The important controls
            are exposed across Creator Pulse, Projects, Content Packs and Creator Studio so creators understand what
            exists before they spend time or money.
          </p>
        </div>
        <div className={story.railHint}>Creator-facing features</div>
        <div className={`${styles.challengeGrid} ${story.horizontalRail} ${story.challengeRail}`}>
          {productSurfaces.map((item) => {
            const Icon = item.icon;
            return (
              <article className={styles.challengeCard} key={item.title} data-about-reveal>
                <Icon size={21} />
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </article>
            );
          })}
        </div>

        <div className={polish.urlPromise} data-about-reveal>
          <div className={polish.urlPromiseCopy}>
            <span><Youtube size={15}/> URL-FIRST, FALLBACK-SAFE</span>
            <h3>A fast path when the link works.<br/><strong>A clear path when it doesn&apos;t.</strong></h3>
            <p>
              ClipKaro treats URL import as an entry point, not a dependency the creator has to trust blindly.
              Supported YouTube links can move directly into analysis. When a source cannot be retrieved,
              the product offers original-file upload and keeps the same transcript, clip, edit and export journey.
            </p>
            <div>
              <span><Link2 size={14}/> Paste supported link</span>
              <span><Upload size={14}/> Upload original fallback</span>
              <span><ShieldCheck size={14}/> Creator rights stay explicit</span>
            </div>
            <TransitionLink href="/upload" className={polish.urlPromiseCta}>Open the creator intake <ArrowRight size={15}/></TransitionLink>
          </div>
          <div className={polish.urlPromiseGlass} aria-label="Illustrative resilient YouTube URL import flow">
            <div className={polish.urlPromiseHeader}><span><i/><i/><i/></span><small>RESILIENT CREATOR INTAKE</small></div>
            <div className={polish.urlPromiseLink}><Youtube size={21}/><span><small>PRIMARY PATH</small><b>Paste YouTube URL</b></span><CheckCircle2 size={18}/></div>
            <div className={polish.urlPromiseConnector}><span/><b>if acquisition is unavailable</b><span/></div>
            <div className={polish.urlPromiseFallback}><Upload size={20}/><span><small>FALLBACK PATH</small><b>Upload original file</b></span><ArrowRight size={17}/></div>
            <div className={polish.urlPromiseDestination}><Sparkles size={18}/><span><small>SAME DESTINATION</small><b>Analyse → Refine → Export</b></span></div>
          </div>
        </div>
      </section>

      <AboutCreatorPulse />

      <section className={`${styles.principlesSection} ${polish.principlesSection} ${story.sectionPacing}`} id="principles">
        <div className={styles.principlesTitle} data-about-reveal>
          <span className={styles.sectionIndex}>07 / OUR PRINCIPLES</span>
          <h2>How we decide what belongs in ClipKaro.</h2>
        </div>
        <div className={`${styles.principleList} ${story.compactPrinciples}`}>
          {principles.map(([title, text], index) => (
            <div className={styles.principleRow} key={title} data-about-reveal>
              <span>0{index + 1}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={`${styles.founderSection} ${polish.founderSection} ${story.sectionPacing} ${story.founderLayout}`} id="founder">
        <div className={`${styles.founderImageWrap} ${polish.founderImageWrap} ${story.founderMedia}`} data-about-reveal>
          <div className={styles.founderImageGlow} aria-hidden="true" />
          <img src="/assets/faik-founder.jpg" alt="Faik Hameed Mulla, Founder and Owner of ClipKaro" className={styles.founderImage} />
          <div className={styles.founderImageCaption}>
            <span>FOUNDER / OWNER</span>
            <strong>Faik Hameed Mulla</strong>
          </div>
        </div>

        <div className={`${styles.founderCopy} ${story.founderCopy}`} data-about-reveal>
          <span className={styles.sectionIndex}>08 / FOUNDER</span>
          <h2>Built by a creator who wanted the tool to exist.</h2>
          <p className={styles.founderLead}>
            <strong>Faik Hameed Mulla</strong> is the Founder and Owner of ClipKaro and an AI/ML
            product builder focused on turning advanced artificial intelligence into practical
            software people can actually use.
          </p>
          <p>
            His work spans AI systems, full-stack product development, cloud architecture,
            automation, media-processing workflows, product design and startup execution. With
            ClipKaro, that work came together around one clear problem: make sophisticated video
            intelligence feel simple enough to become part of a creator&apos;s everyday workflow.
          </p>

          <div className={story.founderDesktopDetails}>
            <p>
              While pursuing his studies in Artificial Intelligence and Machine Learning, Faik has
              continued building across AI agents, financial intelligence, workflow automation and
              creator technology. His approach is centred on combining intelligence with dependable
              engineering rather than treating AI as a standalone feature.
            </p>
            <p>
              ClipKaro reflects that philosophy: complex systems behind the scenes, clear decisions
              in front of the creator, and a product that earns trust through what it actually does.
            </p>
          </div>

          <details className={story.founderMobileDetails}>
            <summary>More about the founder</summary>
            <div>
              <p>
                While pursuing his studies in Artificial Intelligence and Machine Learning, Faik has
                continued building across AI agents, financial intelligence, workflow automation and
                creator technology. His approach is centred on combining intelligence with dependable
                engineering rather than treating AI as a standalone feature.
              </p>
              <p>
                ClipKaro reflects that philosophy: complex systems behind the scenes, clear decisions
                in front of the creator, and a product that earns trust through what it actually does.
              </p>
            </div>
          </details>

          <div className={polish.founderChips} aria-label="Founder focus areas">
            <span>AI / ML systems</span>
            <span>Full-stack products</span>
            <span>Creator technology</span>
          </div>

          <div className={`${styles.socialLinks} ${story.socialStack}`}>
            <a href="https://www.instagram.com/clipkaro.pro/" target="_blank" rel="noreferrer">
              <Instagram size={18} /> <span><small>CLIPKARO</small>@clipkaro.pro</span> <ArrowRight size={15} />
            </a>
            <a href="https://www.instagram.com/myself.fm/" target="_blank" rel="noreferrer">
              <Instagram size={18} /> <span><small>FOUNDER</small>@myself.fm</span> <ArrowRight size={15} />
            </a>
          </div>
        </div>
      </section>

      <section className={`${styles.futureSection} ${polish.futureSection} ${story.sectionPacing}`}>
        <div className={`${styles.futureInner} ${story.futureCopy}`} data-about-reveal>
          <span className={styles.sectionIndex}>09 / WHAT COMES NEXT</span>
          <h2>The future of content creation isn&apos;t more editing. It&apos;s better creative decisions.</h2>
          <p>
            We believe creators should spend more time deciding what they want to say and less
            time repeating production work. ClipKaro is being built toward a future where AI can
            understand content, style and intent well enough to become a more capable production
            partner—while the creator remains in control.
          </p>
          <div className={`${polish.futureGrid} ${story.futureFlow}`}>
            {futureSignals.map(([title, text], index) => (
              <article key={title}>
                <span>0{index + 1}</span>
                <strong>{title}</strong>
                <p>{text}</p>
              </article>
            ))}
          </div>
          <div className={`${styles.futureLine} ${polish.futureLine} ${story.futureLineCompact}`}>
            <span>Your long-form content already contains the moments.</span>
            <strong>ClipKaro helps you find them.</strong>
          </div>
          <Link href="/signup" className={styles.futureCta}>Create your first Short <ArrowRight size={18} /></Link>
        </div>
      </section>

      <footer className={`${styles.footer} ${polish.footer}`}>
        <div className={styles.footerBrand}>
          <Logo light transition />
          <p>AI-assisted short-form creation, built for real creator workflows.</p>
        </div>
        <div className={styles.footerLinks}>
          <TransitionLink href="/">Home</TransitionLink>
          <Link href="/pricing">Pricing</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <a href="https://www.instagram.com/clipkaro.pro/" target="_blank" rel="noreferrer">Instagram</a>
        </div>
        <p className={styles.copyright}>© 2026 ClipKaro AI · Built for creators in India and beyond.</p>
      </footer>
    </main>
  );
}
