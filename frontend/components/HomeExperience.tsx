import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  Clapperboard,
  Download,
  GraduationCap,
  Languages,
  Mic2,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Upload,
  UserRound,
  UsersRound,
  WandSparkles,
  Zap,
} from "lucide-react";
import { PublicMotionShell } from "@/components/PublicMotionShell";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { TransitionLink } from "@/components/TransitionLink";
import FeatureSection from "@/components/ui/feature-section";
import { TRUST_PROFILE } from "@/lib/legal";
import styles from "./HomeExperience.module.css";

const workflow = [
  [Upload, "Upload", "Add a video file you own or have permission to process."],
  [WandSparkles, "Analyse", "ClipKaro transcribes the source and finds promising moments."],
  [Scissors, "Edit & refine", "Review the suggested moments, captions and framing before export."],
  [Clapperboard, "Export & share", "Render the Shorts you choose and take them into your publishing workflow."],
] as const;

const features = [
  [Scissors, "AI Clip Finder", "Find strong, self-contained moments without scrubbing the whole timeline.", "timeline"],
  [Subtitles, "Smart Transcript Review", "Fix uncertain transcript lines before captions and downstream content use them.", "transcript"],
  [Languages, "India Quality Mode", "Creator-facing Hindi, Hinglish and Indian-English workflow support.", "language"],
  [Sparkles, "Content Pack", "Generate titles, descriptions, captions, hashtags and social copy from selected clips.", "social"],
  [Clapperboard, "Creator Studio", "Adjust aspect ratio, caption style, caption position, zoom and horizontal framing.", "studio"],
  [Zap, "Auto captions", "Prepare readable short-form captions and review the transcript before publishing.", "caption"],
  [WandSparkles, "Thumbnail & cover direction", "Turn clip context into creator-ready cover text and thumbnail direction where available.", "thumbnail"],
  [Download, "Export controls", "Choose the output you want and keep the final publishing decision with the creator.", "export"],
] as const;

const audiences = [
  { Icon: Play, title: "YouTubers", text: "Turn long uploads into a repeatable Shorts pipeline.", image: "/assets/usecase-youtuber.jpg" },
  { Icon: GraduationCap, title: "Educators", text: "Pull clear teaching moments from lessons, webinars and explainers.", image: "/assets/usecase-educator.jpg" },
  { Icon: Mic2, title: "Podcasters", text: "Find standalone answers, stories and insights inside conversations.", image: "/assets/usecase-podcaster.jpg" },
  { Icon: UserRound, title: "Founders", text: "Repurpose product, build-in-public and expert-led videos.", image: "/assets/usecase-founder.jpg" },
  { Icon: UsersRound, title: "Businesses", text: "Create more useful short-form content from existing recordings.", image: "/assets/creator-demo.jpg" },
] as const;

const plans = [
  { name: "Free", price: "₹0", suffix: "/month", note: "Try ClipKaro before paying.", items: ["15 Karo Minutes", "2 Shorts", "720p with watermark"], href: "/signup", featured: false },
  { name: "Mini Pass", price: "₹59", suffix: "one-time", note: "Use it when you need it.", items: ["25 Karo Minutes", "5 Shorts", "1080p · no watermark"], href: "/signup?plan=mini_pass", featured: false },
  { name: "Growth", price: "₹399", suffix: "/month", note: "For serious weekly creators.", items: ["180 Karo Minutes", "50 Shorts", "1080p · no watermark"], href: "/signup?plan=growth", featured: true },
  { name: "Pro", price: "₹799", suffix: "/month", note: "For daily creator output.", items: ["480 Karo Minutes", "150 Shorts", "1080p · no watermark"], href: "/signup?plan=pro", featured: false },
  { name: "Agency", price: "₹1,999", suffix: "/month", note: "For higher-volume client work.", items: ["1,500 Karo Minutes", "500 Shorts", "1080p · no watermark"], href: "/signup?plan=agency", featured: false },
] as const;

const questions = [
  ["Can I paste a YouTube URL?", "ClipKaro is upload-first today. Download or export source media you own or have permission to use, then upload it to ClipKaro."],
  ["Will the clips be 9:16?", "Creator Studio supports vertical short-form framing and gives you controls to review framing before export."],
  ["Does ClipKaro choose clips automatically?", "ClipKaro suggests and ranks promising moments, but you decide which clips to keep, edit and export."],
  ["Do I need to connect YouTube Studio for Creator Pulse?", "No. Creator Pulse works from the public YouTube channel evidence available for the channel you submit."],
] as const;

export function HomeExperience() {
  return (
    <PublicMotionShell>
      <div className={styles.page}>
        <PublicSiteNav />

        <main>
          <section className={styles.hero}>
            <div className={styles.heroAura} aria-hidden="true"><i/><i/><i/></div>
            <div className={styles.heroGrid}>
              <div className={styles.heroCopy} data-public-reveal="left">
                <span className={styles.eyebrow}><Sparkles size={14}/> AI-powered video clipping for creators</span>
                <h1>Turn long videos into <span>ready-to-publish Shorts.</span></h1>
                <p>ClipKaro finds your best moments, helps prepare captions, reframes for Shorts and gives you a connected creator workflow — so one recording can become more useful content.</p>
                <div className={styles.heroActions}>
                  <TransitionLink href="/signup" className={styles.primary}>Try ClipKaro free <ArrowRight size={17}/></TransitionLink>
                  <a href="#workflow" className={styles.secondary}><Play size={15}/> See how it works</a>
                </div>
                <div className={styles.heroTrust}>
                  <span><CheckCircle2 size={14}/> No card required</span>
                  <span><Languages size={14}/> Hindi, Hinglish & English workflows</span>
                  <span><ShieldCheck size={14}/> You keep creative control</span>
                </div>
              </div>

              <div className={styles.workspaceWrap} data-public-reveal="scale">
                <div className={`${styles.floatNote} ${styles.floatNoteOne}`}><Sparkles size={15}/><span><b>AI finds strong moments</b><small>Review before export</small></span></div>
                <div className={`${styles.floatNote} ${styles.floatNoteTwo}`}><Subtitles size={15}/><span><b>Caption-ready</b><small>Creator-reviewed text</small></span></div>
                <div className={styles.workspace} aria-label="Illustrative ClipKaro creator workspace">
                  <div className={styles.workspaceTop}><div><span className={styles.dot}/><span className={styles.dot}/><span className={styles.dot}/></div><small>ILLUSTRATIVE PRODUCT PREVIEW</small></div>
                  <div className={styles.workspaceGrid}>
                    <aside className={styles.workspaceSide}>
                      <b>✦ ClipKaro</b>
                      <span className={styles.activeSide}>Create</span><span>Projects</span><span>Content Pack</span><span>Creator Pulse</span><span>Studio</span>
                    </aside>
                    <div className={styles.workspaceMain}>
                      <div className={styles.workspaceTitle}><div><small>Creator workflow</small><b>Your strongest moments are ready</b></div><span>Export selected</span></div>
                      <div className={styles.videoRow}>
                        <div className={styles.sourceVideo}>
                          <img src="/assets/creator-demo.jpg" alt="Illustrative fictional creator used in a ClipKaro source-video demo" />
                          <div className={styles.sourceShade}/><span className={styles.videoBadge}>SOURCE VIDEO · 18:42</span><button type="button" aria-label="Illustrative play button"><Play size={19} fill="currentColor"/></button>
                          <strong>Small steps.<br/>Big results.</strong>
                        </div>
                        <div className={styles.shortVideo}>
                          <img src="/assets/creator-demo.jpg" alt="Illustrative vertical Short preview using a fictional creator" />
                          <div className={styles.shortShade}/><span>SHORT PREVIEW</span><b>TURN IDEAS<br/>INTO <em>IMPACT</em></b>
                        </div>
                        <div className={styles.momentsPanel}>
                          <div><span>Top moments</span><small>AI ranked</small></div>
                          {[94,91,87].map((score,index)=><article key={score}><i>{index+1}</i><span><b>{["The lesson worth sharing","What I would change now","The simple workflow"][index]}</b><small>{["02:13 – 02:49","06:08 – 06:45","11:24 – 12:02"][index]}</small></span><strong>{score}</strong></article>)}
                        </div>
                      </div>
                      <div className={styles.timeline}><span>Detected highlights</span><div className={styles.track}>{[16,31,52,68,82].map((left)=><i key={left} style={{left:`${left}%`}} />)}<b/></div></div>
                    </div>
                  </div>
                </div>
                <div className={styles.workspaceActions}><span><Zap size={14}/> Reframe to 9:16</span><span><Subtitles size={14}/> Add captions</span><span><Download size={14}/> Export & share</span></div>
              </div>
            </div>

            <div className={styles.productRail} data-public-reveal="scale">
              <TransitionLink href="/youtube-video-to-shorts-ai"><Scissors size={19}/><span><b>AI Video Clipper</b><small>Find the strongest moments</small></span></TransitionLink>
              <TransitionLink href="/ai-shorts-maker-india"><Sparkles size={19}/><span><b>YouTube Shorts Maker</b><small>Turn videos into vertical Shorts</small></span></TransitionLink>
              <TransitionLink href="/hindi-video-to-reels"><Languages size={19}/><span><b>Hindi & Hinglish</b><small>India-first creator workflows</small></span></TransitionLink>
              <TransitionLink href="/youtube-channel-analyzer"><Activity size={19}/><span><b>Creator Pulse</b><small>₹1 channel intelligence</small></span></TransitionLink>
            </div>
          </section>

          <section className={styles.pulse} id="creator-pulse">
            <div className={styles.pulseGlow} aria-hidden="true" />
            <div className={styles.pulseInner}>
              <div className={styles.pulseCopy} data-public-reveal="left">
                <span><Activity size={14}/> Creator Pulse · know before you create</span>
                <h2>Stop guessing. <strong>Know what to create next.</strong></h2>
                <p>Creator Pulse compares verified public YouTube evidence, shows recent momentum and turns it into one focused next-video recommendation with a title, reason, angle, opening hook and downloadable thumbnail when generation is available.</p>
                <div className={styles.pulseChecks}><span><Check size={14}/> Public YouTube evidence</span><span><Check size={14}/> No guessed private metrics</span><span><Check size={14}/> One clear next move</span></div>
                <TransitionLink href="/creator-pulse" className={styles.limeButton}>Run Creator Pulse · ₹1 <ArrowRight size={16}/></TransitionLink>
                <small>₹1 only for a successful Pulse · No Creator Pulse subscription required.</small>
              </div>

              <div className={styles.pulsePanel} data-public-reveal="right">
                <div className={styles.pulseHead}><div><small>CHANNEL OVERVIEW</small><b>Verified channel snapshot</b></div><span><CheckCircle2 size={12}/> Verified</span></div>
                <div className={styles.pulseStats}><div><span>Subscribers</span><b>12.4K</b></div><div><span>Total views</span><b>684K</b></div><div><span>Recent avg.</span><b>3.8K</b></div></div>
                <div className={styles.pulseDashboard}>
                  <div className={styles.lineChart}><span>Recent momentum</span><svg viewBox="0 0 300 100" role="img" aria-label="Illustrative momentum chart"><path className={styles.chartArea} d="M0,87 L35,72 L62,78 L92,55 L125,62 L160,39 L195,48 L229,28 L264,33 L300,14 L300,100 L0,100 Z"/><path className={styles.chartLine} d="M0,87 L35,72 L62,78 L92,55 L125,62 L160,39 L195,48 L229,28 L264,33 L300,14"/></svg></div>
                  <div className={styles.nextMove}><span>YOUR NEXT MOVE</span><b>Turn the strongest recent theme into a practical follow-up</b><small>Use the evidence, then make the creative decision yourself.</small></div>
                </div>
                <div className={styles.opportunities}><span>Top content opportunities</span><div>{["High potential","Growing topic","Follow-up angle"].map((item,index)=><article key={item}><img src={["/assets/usecase-youtuber.jpg","/assets/usecase-podcaster.jpg","/assets/usecase-founder.jpg"][index]} alt=""/><i>{index+1}</i><b>{item}</b></article>)}</div></div>
                <p>Illustrative preview. A real Pulse uses the current public evidence from the channel you submit.</p>
              </div>
            </div>
          </section>

          <section className={styles.workflowSection} id="workflow">
            <div className={styles.workflowLead} data-public-reveal="left"><span>Simple process. Powerful results.</span><h2>From long video to creator-ready output.</h2></div>
            <p className={styles.workflowIntro} data-public-reveal="right">Upload your video, let ClipKaro analyse it, then review the suggested clips, captions and framing before you publish.</p>
            <div className={styles.workflowGrid}>
              {workflow.map(([Icon,title,text],index)=><article key={title} data-public-reveal="scale"><span>{index+1}</span><i><Icon size={21}/></i><div><b>{title}</b><p>{text}</p></div>{index<workflow.length-1&&<ArrowRight className={styles.stepArrow} size={18}/>}</article>)}
            </div>
          </section>

          <FeatureSection />

          <section className={styles.featureStage} id="features">
            <div className={styles.featureLead} data-public-reveal="left"><span>A complete creator toolkit</span><h2>More than just clipping.<br/>Everything you need to grow.</h2></div>
            <div className={styles.featureAside} data-public-reveal="right"><p>From transcripts to publishing copy, ClipKaro keeps the creator workflow connected instead of scattering it across unrelated tools.</p><TransitionLink href="/youtube-video-to-shorts-ai">Explore the workflow <ArrowRight size={14}/></TransitionLink></div>
            <div className={styles.featureGrid}>
              {features.map(([Icon,title,text,kind])=><article key={title} className={styles.featureCard} data-kind={kind} data-public-reveal="scale"><div className={styles.featureTitle}><i><Icon size={18}/></i><b>{title}</b></div><div className={styles.featureVisual} aria-hidden="true">{kind==="timeline"&&<><span/><span/><span/><b/></>}{kind==="transcript"&&<><p>Review uncertain transcript line</p><p>Creator-approved wording</p></>}{kind==="language"&&<strong>ये बात बहुत important है</strong>}{kind==="social"&&<div><i>YT</i><i>IG</i><i>X</i><i>LI</i></div>}{kind==="studio"&&<><span/><span/><span/></>}{kind==="caption"&&<strong>This changed everything</strong>}{kind==="thumbnail"&&<div className={styles.miniThumb}><img src="/assets/creator-demo.jpg" alt=""/><b>THE NEXT MOVE</b></div>}{kind==="export"&&<div className={styles.ratios}><i>9:16</i><i>1:1</i><i>16:9</i></div>}</div><p>{text}</p></article>)}
            </div>
          </section>

          <section className={styles.audienceSection} id="use-cases">
            <div className={styles.audienceHead}><div data-public-reveal="left"><span>Built for real creator workflows</span><h2>Different creators. Same workflow. Bigger possibilities.</h2></div><p data-public-reveal="right">Whether you teach, entertain, build or share — ClipKaro adapts to the content you already record.</p></div>
            <div className={styles.audienceGrid}>
              {audiences.map(({Icon,title,text,image})=><article key={title} data-public-reveal="scale"><div className={styles.audiencePhoto}><img src={image} alt={`Illustrative ${title.toLowerCase()} creator workflow`}/><span><Icon size={18}/></span></div><div><b>{title}</b><p>{text}</p></div></article>)}
            </div>
            <div className={styles.useCaseLinks} data-public-reveal="scale">
              <TransitionLink href="/youtube-video-to-shorts-ai">YouTube video → Shorts</TransitionLink>
              <TransitionLink href="/podcast-to-clips-india">Podcast → clips</TransitionLink>
              <TransitionLink href="/hindi-video-to-reels">Hindi video → Reels</TransitionLink>
              <TransitionLink href="/educational-video-to-shorts">Education → Shorts</TransitionLink>
              <TransitionLink href="/talking-head-video-to-reels">Talking head → Reels</TransitionLink>
            </div>
          </section>

          <section className={styles.pricing} id="pricing">
            <div className={styles.pricingHead}><div data-public-reveal="left"><span>Simple pricing</span><h2>Start small. Grow when you grow.</h2></div><p data-public-reveal="right">Try the product first. Choose a one-time Mini Pass when you need it, or move into a monthly plan as your publishing volume grows.</p></div>
            <div className={styles.planGrid}>
              {plans.map((plan)=><article key={plan.name} className={plan.featured?styles.planFeatured:""} data-public-reveal="scale">{plan.featured&&<span className={styles.popular}>MOST POPULAR</span>}<h3>{plan.name}</h3><p>{plan.note}</p><div className={styles.planPrice}>{plan.price}<small>{plan.suffix}</small></div><ul>{plan.items.map((item)=><li key={item}><Check size={14}/>{item}</li>)}</ul><TransitionLink href={plan.href} className={plan.featured?styles.planPrimary:styles.planSecondary}>{plan.name==="Free"?"Start free":plan.name==="Mini Pass"?"Get Mini Pass":`Choose ${plan.name}`} <ArrowRight size={14}/></TransitionLink></article>)}
            </div>
            <div className={styles.pricingFoot} data-public-reveal="scale"><span>Creator ₹199/month is also available in the full plan comparison.</span><TransitionLink href="/pricing">Compare every plan <ArrowRight size={14}/></TransitionLink></div>
          </section>

          <section className={styles.creatorStory}>
            <div className={styles.creatorStoryInner}>
              <div className={styles.creatorStoryCopy} data-public-reveal="left"><span>Creator-led product</span><h2>Built for creators who want the work to feel lighter.</h2><p>ClipKaro is designed around a simple idea: remove repetitive editing work while keeping the creator in control of what gets published.</p><TransitionLink href="/about" className={styles.limeButton}>Read the ClipKaro story <ArrowRight size={15}/></TransitionLink></div>
              <div className={styles.creatorScene} data-public-reveal="scale"><img src="/assets/creator-demo.jpg" alt="Illustrative fictional creator at a content workstation"/><div><span>ILLUSTRATIVE CREATOR WORKFLOW</span><b>One recording.<br/>More ways to use it.</b></div></div>
              <blockquote data-public-reveal="right"><span>“</span><p>Build practical creator tools that are clear, affordable and honest about what the AI can and cannot do.</p><footer><b>{TRUST_PROFILE.founderName}</b><small>{TRUST_PROFILE.founderTitle}</small></footer></blockquote>
            </div>
          </section>

          <section className={styles.faqSection}>
            <div className={styles.faqHead} data-public-reveal="left"><span>Common questions</span><h2>You ask. We answer.</h2></div>
            <div className={styles.faqGrid} data-public-reveal="right">{questions.map(([question,answer])=><details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}</div>
          </section>

          <section className={styles.finalCta} data-public-reveal="scale"><div><span><Sparkles size={14}/> START WITH ONE VIDEO</span><h2>Make the content you already recorded work harder.</h2><p>Create a free account, upload content you own and judge the suggested clips yourself.</p></div><TransitionLink href="/signup" className={styles.limeButton}>Start creating free <ArrowRight size={16}/></TransitionLink></section>
        </main>

        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
