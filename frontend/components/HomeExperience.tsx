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
import { TRUST_PROFILE } from "@/lib/legal";
import styles from "./HomeExperience.module.css";

const workflow = [
  [Upload, "Upload", "Add a video file you own or have permission to process."],
  [WandSparkles, "Analyse", "ClipKaro transcribes the source and finds promising moments."],
  [Scissors, "Rank moments", "Compare clips with titles, hooks, reasons and scores."],
  [Clapperboard, "Export Shorts", "Review, frame, caption and render the moments you choose."],
] as const;

const features = [
  [Scissors, "AI Clip Finder", "Find strong, self-contained moments without scrubbing the whole timeline."],
  [Subtitles, "Smart Transcript Review", "Fix uncertain transcript lines before captions and downstream content use them."],
  [Languages, "India Quality Mode", "Creator-facing Hindi, Hinglish and Indian-English workflow support."],
  [Sparkles, "Content Pack", "Generate titles, descriptions, captions, hashtags and social copy from selected clips."],
  [Clapperboard, "Creator Studio", "Adjust aspect ratio, caption style, caption position, zoom and horizontal framing."],
  [Zap, "Reframe for vertical", "Turn landscape source footage into creator-controlled short-form framing."],
  [ShieldCheck, "Private media workflow", "Keep source and export delivery controlled instead of exposing permanent public files."],
  [Activity, "Creator Pulse", "Use verified public YouTube evidence to decide what video to create next for ₹1 per successful Pulse."],
] as const;

const audiences = [
  [Play, "YouTubers", "Turn long uploads into a repeatable Shorts pipeline."],
  [GraduationCap, "Educators", "Pull clear teaching moments from lessons, webinars and explainers."],
  [Mic2, "Podcasters", "Find standalone answers, stories and insights inside conversations."],
  [UserRound, "Founders", "Repurpose product, build-in-public and expert-led videos."],
  [UsersRound, "Businesses", "Create more useful short-form content from existing recordings."],
] as const;

const plans = [
  { name: "Free", price: "₹0", suffix: "/month", note: "Try the workflow first.", items: ["15 Karo Minutes", "2 Shorts", "720p with watermark"], href: "/signup", featured: false },
  { name: "Growth", price: "₹399", suffix: "/month", note: "For serious weekly creators.", items: ["180 Karo Minutes", "50 Shorts", "1080p · no watermark"], href: "/signup?plan=growth", featured: true },
  { name: "Pro", price: "₹799", suffix: "/month", note: "For daily creator output.", items: ["480 Karo Minutes", "150 Shorts", "1080p · no watermark"], href: "/signup?plan=pro", featured: false },
] as const;

export function HomeExperience() {
  return (
    <PublicMotionShell>
      <div className={styles.page}>
        <PublicSiteNav />

        <main>
          <section className={styles.hero}>
            <div className={styles.heroGlow} aria-hidden="true" />
            <div className={styles.heroGrid}>
              <div className={styles.heroCopy} data-public-reveal>
                <span className={styles.eyebrow}><Sparkles size={14}/> AI for creators. Built for what comes next.</span>
                <h1>Turn long videos into <span>ready-to-publish Shorts.</span></h1>
                <p>ClipKaro finds your strongest moments, helps clean uncertain transcript lines, prepares creator-ready captions and gives you the controls to turn one recording into more useful content.</p>
                <div className={styles.heroActions}>
                  <TransitionLink href="/signup" className={styles.primary}>Try ClipKaro free <ArrowRight size={17}/></TransitionLink>
                  <TransitionLink href="/pricing" className={styles.secondary}>See pricing</TransitionLink>
                </div>
                <div className={styles.heroTrust}>
                  <span><CheckCircle2 size={14}/> No card required</span>
                  <span><ShieldCheck size={14}/> Upload content you own</span>
                  <span><UserRound size={14}/> You keep creative control</span>
                </div>
              </div>

              <div className={styles.workspaceWrap} data-public-reveal>
                <div className={styles.workspace} aria-label="Illustrative ClipKaro creator workspace">
                  <div className={styles.workspaceTop}><div><span className={styles.dot}/><span className={styles.dot}/><span className={styles.dot}/></div><small>ILLUSTRATIVE PRODUCT PREVIEW</small></div>
                  <div className={styles.workspaceGrid}>
                    <aside className={styles.workspaceSide}>
                      <b>✦ ClipKaro</b>
                      <span className={styles.activeSide}>Create</span><span>Projects</span><span>Content Pack</span><span>Creator Pulse</span><span>Studio</span>
                    </aside>
                    <div className={styles.workspaceMain}>
                      <div className={styles.workspaceTitle}><div><small>How I Built My Creator Workflow</small><b>Your strongest moments are ready</b></div><span>Export selected</span></div>
                      <div className={styles.videoRow}>
                        <div className={styles.sourceVideo}>
                          <img src="/assets/faik-founder.jpg" alt="ClipKaro founder used as an illustrative source-video example" />
                          <div className={styles.sourceShade}/><span className={styles.videoBadge}>SOURCE VIDEO · 18:42</span><button type="button" aria-label="Illustrative play button"><Play size={19} fill="currentColor"/></button>
                          <strong>Build once.<br/>Repurpose smarter.</strong>
                        </div>
                        <div className={styles.shortVideo}>
                          <img src="/assets/faik-founder.jpg" alt="Illustrative vertical Short preview" />
                          <div className={styles.shortShade}/><span>SHORT PREVIEW</span><b>THE IDEA<br/>THAT SAVED<br/><em>MY TIME</em></b>
                        </div>
                        <div className={styles.momentsPanel}>
                          <div><span>Top moments</span><small>AI ranked</small></div>
                          {[94,91,87].map((score,index)=><article key={score}><i>{index+1}</i><span><b>{["The lesson worth sharing","What I would change now","The simple workflow"][index]}</b><small>{["02:13 – 02:49","06:08 – 06:45","11:24 – 12:02"][index]}</small></span><strong>{score}</strong></article>)}
                        </div>
                      </div>
                      <div className={styles.timeline}><span>Detected highlights</span><div className={styles.track}>{[16,31,52,68,82].map((left)=><i key={left} style={{left:`${left}%`}} />)}</div></div>
                    </div>
                  </div>
                </div>
                <span className={styles.handNote}>One recording → more creator-ready output ✦</span>
              </div>
            </div>

            <div className={styles.proofBar} data-public-reveal>
              <div><Upload size={19}/><span><b>Upload-first</b><small>Start from media you own.</small></span></div>
              <div><Sparkles size={19}/><span><b>AI-ranked moments</b><small>Find what is worth reviewing.</small></span></div>
              <div><ShieldCheck size={19}/><span><b>Private media window</b><small>Controlled source and export handling.</small></span></div>
              <div><Subtitles size={19}/><span><b>Creator-ready captions</b><small>Review before you publish.</small></span></div>
            </div>
          </section>

          <section className={styles.pulse} id="creator-pulse">
            <div className={styles.pulseInner}>
              <div className={styles.pulseCopy} data-public-reveal>
                <span><Activity size={14}/> Creator Pulse · ₹1 channel intelligence</span>
                <h2>Know what&apos;s working. <strong>Know what to create next.</strong></h2>
                <p>Creator Pulse compares verified public YouTube evidence, shows recent momentum and turns it into one focused next-video recommendation with a title, reason, angle, opening hook and downloadable thumbnail when generation is available.</p>
                <div className={styles.pulseChecks}><span><Check size={14}/> Public YouTube evidence</span><span><Check size={14}/> No guessed private metrics</span><span><Check size={14}/> One clear next move</span></div>
                <TransitionLink href="/creator-pulse" className={styles.limeButton}>Run Creator Pulse · ₹1 <ArrowRight size={16}/></TransitionLink>
                <small>₹1 only for a successful Pulse · No Creator Pulse subscription required.</small>
              </div>

              <div className={styles.pulsePanel} data-public-reveal>
                <div className={styles.pulseHead}><div><small>CREATOR PULSE</small><b>Verified channel snapshot</b></div><span><CheckCircle2 size={12}/> Verified</span></div>
                <div className={styles.pulseStats}><div><span>Subscribers</span><b>12.4K</b></div><div><span>Total views</span><b>684K</b></div><div><span>Recent avg.</span><b>3.8K</b></div></div>
                <div className={styles.pulseChart}><span>Recent momentum · views/day</span><div><i style={{width:"92%"}}/><b>Build update</b></div><div><i style={{width:"64%"}}/><b>What failed</b></div><div><i style={{width:"41%"}}/><b>Setup guide</b></div></div>
                <div className={styles.pulseMove}><div><span>YOUR NEXT MOVE</span><b>Turn the strongest recent theme into a practical follow-up</b><small>Opening hook: “The first version worked — here is what I would improve now.”</small></div><div className={styles.pulseThumb}><small>NEXT VIDEO</small><strong>BUILD THE<br/>UPGRADE</strong><span>DOWNLOADABLE THUMBNAIL</span></div></div>
                <p>Illustrative preview. A real Pulse uses the current public evidence from the channel you submit.</p>
              </div>
            </div>
          </section>

          <section className={styles.section} id="workflow">
            <div className={styles.sectionHead} data-public-reveal><span>One creator workflow</span><h2>From long video to creator-ready output.</h2><p>The interface keeps the work in a clear sequence so creators know what happened, what the AI suggests and what still needs their decision.</p></div>
            <div className={styles.workflowGrid}>
              {workflow.map(([Icon,title,text],index)=><article key={title} data-public-reveal><span>{index+1}</span><i><Icon size={21}/></i><div><b>{title}</b><p>{text}</p></div>{index<workflow.length-1&&<ArrowRight className={styles.stepArrow} size={18}/>}</article>)}
            </div>
          </section>

          <section className={`${styles.section} ${styles.features}`} id="features">
            <div className={styles.sectionHead} data-public-reveal><span>Everything in one place</span><h2>Purpose-built tools around the creator&apos;s real workflow.</h2><p>ClipKaro is more than one clipping button. The product connects discovery, transcript review, captioning, framing, publishing copy and channel intelligence.</p></div>
            <div className={styles.featureGrid}>
              {features.map(([Icon,title,text],index)=><article key={title} className={index===0||index===7?styles.featureWide:""} data-public-reveal><i><Icon size={21}/></i><div><b>{title}</b><p>{text}</p></div>{index===7&&<TransitionLink href="/youtube-channel-analyzer">Explore Creator Pulse <ArrowRight size={14}/></TransitionLink>}</article>)}
            </div>
          </section>

          <section className={styles.section} id="use-cases">
            <div className={styles.sectionHead} data-public-reveal><span>Built for creators who already record</span><h2>Different stories. Same need: more useful output from the content you already have.</h2></div>
            <div className={styles.audienceGrid}>
              {audiences.map(([Icon,title,text],index)=><article key={title} data-public-reveal><div className={`${styles.audienceVisual} ${styles[`audience${index+1}`]}`}><Icon size={34}/><span>{title}</span></div><div><b>{title}</b><p>{text}</p></div></article>)}
            </div>
            <div className={styles.useCaseLinks} data-public-reveal>
              <TransitionLink href="/youtube-video-to-shorts-ai">YouTube video → Shorts</TransitionLink>
              <TransitionLink href="/podcast-to-clips-india">Podcast → clips</TransitionLink>
              <TransitionLink href="/hindi-video-to-reels">Hindi video → Reels</TransitionLink>
              <TransitionLink href="/educational-video-to-shorts">Education → Shorts</TransitionLink>
              <TransitionLink href="/talking-head-video-to-reels">Talking head → Reels</TransitionLink>
            </div>
          </section>

          <section className={styles.pricing} id="pricing">
            <div className={styles.sectionHead} data-public-reveal><span>Fair access pricing</span><h2>Start small. Grow when you grow.</h2><p>Use the free plan first, choose a one-time Mini Pass when you need it, or move into a monthly plan as your publishing volume grows.</p></div>
            <div className={styles.planGrid}>
              {plans.map((plan)=><article key={plan.name} className={plan.featured?styles.planFeatured:""} data-public-reveal>{plan.featured&&<span className={styles.popular}>MOST POPULAR</span>}<h3>{plan.name}</h3><p>{plan.note}</p><div className={styles.planPrice}>{plan.price}<small>{plan.suffix}</small></div><ul>{plan.items.map((item)=><li key={item}><Check size={14}/>{item}</li>)}</ul><TransitionLink href={plan.href} className={plan.featured?styles.planPrimary:styles.planSecondary}>{plan.name==="Free"?"Start free":`Choose ${plan.name}`} <ArrowRight size={14}/></TransitionLink></article>)}
            </div>
            <div className={styles.pricingFoot} data-public-reveal><span>Mini Pass ₹59 one-time · Creator ₹199/month · Agency ₹1,999/month also available.</span><TransitionLink href="/pricing">Compare every plan <ArrowRight size={14}/></TransitionLink></div>
          </section>

          <section className={styles.trust}>
            <div className={styles.trustInner} data-public-reveal>
              <div className={styles.founderCard}><img src="/assets/faik-founder.jpg" alt={`${TRUST_PROFILE.founderName}, ClipKaro founder`} /><span><small>FOUNDER-LED PRODUCT</small><b>{TRUST_PROFILE.founderName}</b><p>{TRUST_PROFILE.founderTitle}. Public founder story and operator details are available before checkout.</p></span></div>
              <div className={styles.trustCopy}><span>Trust should be part of the product</span><h2>Clear support, private media rules and creator control.</h2><div><p><ShieldCheck size={17}/><b>Private media handling</b><small>{TRUST_PROFILE.mediaRetention}</small></p><p><UsersRound size={17}/><b>Support expectation</b><small>{TRUST_PROFILE.supportExpectation}</small></p><p><Download size={17}/><b>Review before publishing</b><small>ClipKaro prepares output; the creator decides what goes live.</small></p></div><TransitionLink href="/about">Read how ClipKaro is built <ArrowRight size={15}/></TransitionLink></div>
            </div>
          </section>

          <section className={styles.finalCta} data-public-reveal><div><span><Sparkles size={14}/> START WITH ONE VIDEO</span><h2>Make the content you already recorded work harder.</h2><p>Create a free account, upload content you own and judge the suggested clips yourself.</p></div><TransitionLink href="/signup" className={styles.limeButton}>Try ClipKaro free <ArrowRight size={16}/></TransitionLink></section>
        </main>

        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
