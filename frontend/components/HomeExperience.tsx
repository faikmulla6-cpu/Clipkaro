import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  Clapperboard,
  Download,
  GraduationCap,
  Languages,
  Link2,
  Mic2,
  Play,
  Scissors,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Upload,
  Youtube,
  UserRound,
  UsersRound,
  WandSparkles,
  Zap,
} from "lucide-react";
import { PublicMotionShell } from "@/components/PublicMotionShell";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { SmartLayoutSpotlight } from "@/components/SmartLayoutSpotlight";
import { TransitionLink } from "@/components/TransitionLink";
import FeatureSection from "@/components/ui/feature-section";
import { TRUST_PROFILE } from "@/lib/legal";
import styles from "./HomeExperience.module.css";

const workflow = [
  [Upload, "Upload your video", "Start with the original file you own or have permission to process. YouTube URL import is coming soon."],
  [WandSparkles, "Analyse", "ClipKaro transcribes the source and finds promising moments."],
  [Scissors, "Edit & refine", "Review the suggested moments, captions and framing before export."],
  [Clapperboard, "Publish with Post Karo", "Render the Shorts you choose, then publish to Instagram Reels or YouTube Shorts from ClipKaro after you connect your account."],
] as const;

const features = [
  [Scissors, "AI Clip Finder", "Find strong, self-contained moments without scrubbing the whole timeline.", "timeline"],
  [Subtitles, "Smart Transcript Review", "Fix uncertain transcript lines before captions or other content use them.", "transcript"],
  [Languages, "India Quality Mode", "Hindi, Hinglish and Indian-English creator workflows.", "language"],
  [Sparkles, "Content Pack", "Generate titles, descriptions, hashtags and social copy for YouTube, Instagram, X and LinkedIn from selected clips.", "social"],
  [Clapperboard, "Creator Studio", "Drag captions anywhere, resize them from 65% to 160%, align text, zoom and reframe video, toggle Hook Text, preserve source captions, apply Brand Kit and export in 9:16, 4:5 or 1:1.", "studio"],
  [Zap, "Auto captions", "Prepare readable captions, then review the transcript before publishing.", "caption"],
  [WandSparkles, "Thumbnail & cover direction", "Turn clip context into cover text and thumbnail direction where available.", "thumbnail"],
  [Download, "Export controls", "Paid plans include unlimited exports and re-exports of the Shorts you create.", "export"],
  [Youtube, "Post Karo", "Unlimited publishing access for finished Shorts to connected Instagram Reels and YouTube Shorts accounts on every ClipKaro plan.", "publish"],
] as const;

const audiences = [
  { Icon: Play, title: "YouTubers", text: "Turn long uploads into a repeatable Shorts pipeline.", image: "/assets/usecase-youtuber.jpg" },
  { Icon: GraduationCap, title: "Educators", text: "Pull clear teaching moments from lessons, webinars and explainers.", image: "/assets/usecase-educator.jpg" },
  { Icon: Mic2, title: "Podcasters", text: "Find standalone answers, stories and insights inside conversations.", image: "/assets/usecase-podcaster.jpg" },
  { Icon: UserRound, title: "Founders", text: "Repurpose product, build-in-public and expert-led videos.", image: "/assets/usecase-founder.jpg" },
  { Icon: UsersRound, title: "Businesses", text: "Create more useful short-form content from existing recordings.", image: "/assets/creator-demo.jpg" },
] as const;

const plans = [
  { name: "Free", price: "₹0", suffix: "/month", note: "Try the full create-to-publish loop.", items: ["2 AI Shorts / month", "15 source-processing minutes", "Up to 2 exports", "Source media kept 24 hours", "720p with watermark", "Unlimited Post Karo"], href: "/signup", featured: false },
  { name: "Mini Pass", price: "₹59", suffix: "one-time", note: "For a one-off project.", items: ["5 finished AI Shorts", "25 total Karo Minutes/pass", "Up to 25 minutes per source video", "Ends at Shorts/minutes exhaustion or 30 days", "Existing purchased passes retain 125 minutes", "Unlimited re-exports of finished Shorts while source is retained", "1080p · no watermark", "Unlimited Post Karo"], href: "/signup?plan=mini_pass", featured: false },
  { name: "Growth", price: "₹599", suffix: "/month", note: "For serious weekly creators.", items: ["50 unique finished AI Shorts / month", "300 total Karo Minutes/month", "Up to 90 minutes per source video", "Unlimited re-exports of finished Shorts", "Source media kept up to 30 days", "1080p · no watermark", "Unlimited Post Karo"], href: "/signup?plan=growth", featured: true },
  { name: "Pro", price: "₹1,299", suffix: "/month", note: "For daily creator output.", items: ["150 unique finished AI Shorts / month", "600 total Karo Minutes/month", "Up to 180 minutes per source video", "Unlimited re-exports of finished Shorts", "Source media kept up to 30 days", "1080p · no watermark", "Unlimited Post Karo"], href: "/signup?plan=pro", featured: false },
  { name: "Agency", price: "₹1,999", suffix: "/month", note: "For higher-volume client work.", items: ["500 AI Shorts / month", "1,500 source-processing minutes", "Unlimited exports & re-exports", "Source media kept up to 30 days", "1080p · no watermark", "Unlimited Post Karo"], href: "/signup?plan=agency", featured: false },
] as const;

const questions = [
  ["Can I paste a YouTube URL?", "YouTube URL import is coming soon while we improve reliability. For now, upload an original video you own or have permission to process and use the full AI clipping workflow."],
  ["How do I create Shorts while URL import is coming soon?", "Upload your original video file. ClipKaro then continues with transcript review, clip-finding, editing and export."],
  ["Will the clips be 9:16?", "Creator Studio supports vertical short-form framing and gives you controls to review framing before export."],
  ["What is Smart Layout?", "Smart Layout adds premium speaker-aware portrait framing in Auto Director, Dual Stack and Speaker Focus modes. Preview the result and review camera choices before export; results depend on the source footage."],
  ["Does Smart Layout use credits?", "Yes. Real Smart Layout analysis uses a separate plan-based credit balance. ClipKaro shows the cost before you authorise analysis, and you can continue using Classic framing without premium analysis."],
  ["Does ClipKaro choose clips automatically?", "ClipKaro suggests and ranks promising moments, but you decide which clips to keep, edit and export."],
  ["Can ClipKaro publish my finished Shorts directly?", "Yes. Post Karo lets signed-in users publish finished Shorts to connected Instagram Reels and YouTube Shorts accounts. You review and confirm the post; ClipKaro does not publish without your action."],
  ["Is Post Karo unlimited?", "ClipKaro does not apply a per-post Post Karo quota. Unlimited publishing access is included on every plan, including Free. You still review and confirm each post, creation limits still apply, and Instagram or YouTube provider rules may apply."],
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
                <span className={styles.eyebrow}><Sparkles size={14}/> AI VIDEO CLIPPER FOR INDIA</span>
                <h1><span className={styles.heroTitleLead}>One long video in.</span>{" "}<span>Strong Shorts out.</span></h1>
                <p>Upload an original video and let AI find moments worth sharing. Refine them in Creator Studio, then publish the Shorts you choose with Post Karo.</p>
                <div className={styles.heroActions}>
                  <TransitionLink href="/signup" className={styles.primary}>Try ClipKaro free <ArrowRight size={17}/></TransitionLink>
                  <a href="#youtube-url-to-shorts" className={styles.secondary}><Link2 size={15}/> See the workflow</a>
                </div>
                <div className={styles.heroTrust}>
                  <span><CheckCircle2 size={14}/> No card required</span>
                  <span><Languages size={14}/> Hindi, Hinglish & English workflows</span>
                  <span><ShieldCheck size={14}/> You keep creative control</span>
                  <span><Youtube size={14}/> Unlimited Post Karo on every plan</span>
                </div>
                <a href="#smart-layout" className={styles.smartLayoutLink}>
                  <Sparkles size={15} className="shrink-0" aria-hidden="true" />
                  <span><strong>Smart Layout</strong> · Speaker-aware vertical framing</span>
                  <ArrowRight size={14} className="shrink-0" aria-hidden="true" />
                </a>
              </div>

              <div className={styles.workspaceWrap} data-public-reveal="scale">
                <div className={`${styles.floatNote} ${styles.floatNoteOne}`}><Sparkles size={15}/><span><b>AI finds strong moments</b><small>Review before export</small></span></div>
                <div className={`${styles.floatNote} ${styles.floatNoteTwo}`}><Youtube size={15}/><span><b>Post Karo ready</b><small>Instagram + YouTube</small></span></div>
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
                <div className={styles.workspaceActions}><span><Zap size={14}/> Reframe to 9:16</span><span><Subtitles size={14}/> Add captions</span><span><Youtube size={14}/> Post to IG + YT</span></div>
              </div>
            </div>

            <div className={styles.productRail} data-public-reveal="scale">
              <TransitionLink href="/youtube-video-to-shorts-ai"><Link2 size={19}/><span><b>YouTube URL → Shorts</b><small>Coming soon · upload works today</small></span></TransitionLink>
              <TransitionLink href="/post-shorts-instagram-youtube"><Youtube size={19}/><span><b>Post Karo</b><small>Unlimited publishing · every plan</small></span></TransitionLink>
              <TransitionLink href="/hindi-video-to-reels"><Languages size={19}/><span><b>Hindi & Hinglish</b><small>India-first creator workflows</small></span></TransitionLink>
              <TransitionLink href="/youtube-channel-analyzer"><Activity size={19}/><span><b>Creator Pulse</b><small>₹1 channel intelligence</small></span></TransitionLink>
            </div>
          </section>

          <SmartLayoutSpotlight context="home" />

          <section className={styles.urlFeature} id="youtube-url-to-shorts">
            <div className={styles.urlGlow} aria-hidden="true" />
            <div className={styles.urlFeatureInner}>
              <div className={styles.urlCopy} data-public-reveal="left">
                <span className={styles.urlEyebrow}><Youtube size={15}/> YOUTUBE URL IMPORT · COMING SOON</span>
                <h2>Upload your original video.</h2>
                <p>
                  YouTube link import is temporarily paused while we improve reliability.
                  You can create Shorts today from a video file you own or have permission to process.
                </p>
                <div className={styles.urlBenefits}>
                  <span><ShieldCheck size={15}/> Permissioned video sources</span>
                </div>
                <div className={styles.urlActions}>
                  <TransitionLink href="/upload" className={styles.urlPrimary}>Upload a video now <ArrowRight size={16}/></TransitionLink>
                  <TransitionLink href="/youtube-video-to-shorts-ai" className={styles.urlSecondary}>See what is coming</TransitionLink>
                </div>
                <small>The link preview is illustrative. No link-import job is started.</small>
              </div>

              <div className={styles.urlGlassStage} data-public-reveal="right" aria-label="Preview of upcoming YouTube URL importing, currently coming soon">
                <div className={styles.urlGlassTop}>
                  <span><i/><i/><i/></span>
                  <small>CLIPKARO · COMING SOON PREVIEW</small>
                </div>
                <div className={styles.urlInputCard}>
                  <div className={styles.urlSourceIcon}><Youtube size={22}/></div>
                  <div className={styles.urlInputBody}>
                    <span>YouTube video link · coming soon</span>
                    <div><Link2 size={15}/><b>youtube.com/watch?v=your-video</b><em>SOON</em></div>
                  </div>
                  <i className={styles.urlVerified}><Check size={13}/></i>
                </div>
                <div className={styles.urlFlowLine}><span/><b>planned URL import</b><span/></div>
                <div className={styles.urlPipeline}>
                  <div><Sparkles size={18}/><span><b>Analyse</b><small>Transcript + moments</small></span></div>
                  <ArrowRight size={16}/>
                  <div><Scissors size={18}/><span><b>Refine</b><small>Captions + framing</small></span></div>
                  <ArrowRight size={16}/>
                  <div><Clapperboard size={18}/><span><b>Export or post</b><small>Post Karo · Instagram + YouTube</small></span></div>
                </div>
                <div className={styles.fallbackCard}>
                  <div className={styles.fallbackIcon}><Upload size={18}/></div>
                  <div><span>Ready to create now?</span><b>Upload the original file.</b><small>AI Shorts workflow available today</small></div>
                  <ArrowRight size={17}/>
                </div>
                <div className={styles.urlOrbitOne} aria-hidden="true"><Link2 size={16}/></div>
                <div className={styles.urlOrbitTwo} aria-hidden="true"><Upload size={16}/></div>
              </div>
            </div>
          </section>

          <section className={styles.answerSection} id="answers">
            <div className={styles.answerLead} data-public-reveal="left">
              <span>ClipKaro at a glance</span>
              <h2>What is ClipKaro AI?</h2>
              <p>
                ClipKaro AI is an India-first AI video clipper for Hindi, Hinglish and English creators.
                Here’s what you can do with a recording you already have.
              </p>
            </div>
            <div className={styles.answerGrid} data-public-reveal="right">
              <article>
                <h3>What does ClipKaro do?</h3>
                <p>ClipKaro turns authorised long videos into ranked short-form moments, then lets you refine captions and framing before exporting or publishing the finished Short.</p>
              </article>
              <article>
                <h3>Is ClipKaro an affordable AI clipper with unlimited posting?</h3>
                <p>Yes. ClipKaro starts free at ₹0, offers a ₹59 one-time Mini Pass and Creator from ₹249/month. Every plan includes unlimited Post Karo publishing access with no ClipKaro per-post quota; creation limits and connected-platform rules still apply.</p>
              </article>
              <article>
                <h3>Is Post Karo unlimited?</h3>
                <p>Yes—ClipKaro applies no per-post Post Karo quota. Unlimited publishing access is included on every plan; you review each post and Instagram or YouTube provider rules can still apply.</p>
              </article>
              <article>
                <h3>What can Creator Studio edit?</h3>
                <p>Drag and resize captions, control text alignment, reframe and zoom video, choose output ratios, turn Hook Text on or off, preserve source captions and apply Brand Kit settings.</p>
              </article>
            </div>
          </section>

          <section className={styles.pulse} id="creator-pulse">
            <div className={styles.pulseGlow} aria-hidden="true" />
            <div className={styles.pulseInner}>
              <div className={styles.pulseCopy} data-public-reveal="left">
                <span><Activity size={14}/> Creator Pulse</span>
                <h2>Find your next <strong>video idea.</strong></h2>
                <p>Creator Pulse compares verified public YouTube evidence, shows recent momentum and turns it into one focused next-video recommendation with a title, reason, angle, opening hook and downloadable thumbnail when generation is available.</p>
                <div className={styles.pulseChecks}><span><Check size={14}/> Public YouTube evidence</span><span><Check size={14}/> No guessed private metrics</span><span><Check size={14}/> One clear next move</span></div>
                <TransitionLink href="/youtube-channel-analyzer" className={styles.limeButton}>Explore Creator Pulse · ₹1 <ArrowRight size={16}/></TransitionLink>
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
            <div className={styles.workflowLead} data-public-reveal="left"><h2>From recording to finished Short.</h2></div>
            <div className={styles.workflowGrid}>
              {workflow.map(([Icon,title,text],index)=><article key={title} data-public-reveal="scale"><span>{index+1}</span><i><Icon size={21}/></i><div><b>{title}</b><p>{text}</p></div>{index<workflow.length-1&&<ArrowRight className={styles.stepArrow} size={18}/>}</article>)}
            </div>
          </section>

          <FeatureSection />

          <section className={styles.featureStage} id="features">
            <div className={styles.featureLead} data-public-reveal="left"><h2>Tools for every step of the edit.</h2></div>
            <div className={styles.featureAside} data-public-reveal="right"><TransitionLink href="/shorts-video-editor-ai">Explore Creator Studio <ArrowRight size={14}/></TransitionLink></div>
            <div className={styles.featureGrid}>
              {features.map(([Icon,title,text,kind])=><article key={title} className={styles.featureCard} data-kind={kind} data-public-reveal="scale">{kind==="publish"&&<em className={styles.featureBadge}>UNLIMITED · EVERY PLAN</em>}<div className={styles.featureTitle}><i><Icon size={18}/></i><b>{title}</b></div><div className={styles.featureVisual} aria-hidden="true">{kind==="timeline"&&<><span/><span/><span/><b/></>}{kind==="transcript"&&<><p>Review uncertain transcript line</p><p>Creator-approved wording</p></>}{kind==="language"&&<strong>ये बात बहुत important है</strong>}{kind==="social"&&<div><i>YT</i><i>IG</i><i>X</i><i>LI</i></div>}{kind==="studio"&&<><span/><span/><span/></>}{kind==="caption"&&<strong>This changed everything</strong>}{kind==="thumbnail"&&<div className={styles.miniThumb}><img src="/assets/creator-demo.jpg" alt=""/><b>THE NEXT MOVE</b></div>}{kind==="export"&&<div className={styles.ratios}><i>9:16</i><i>1:1</i><i>16:9</i></div>}{kind==="publish"&&<strong>Instagram + YouTube</strong>}</div><p>{text}</p></article>)}
            </div>
          </section>

          <section className={styles.audienceSection} id="use-cases">
            <div className={styles.audienceHead}><div data-public-reveal="left"><h2>Make more of what you already record.</h2></div></div>
            <div className={styles.audienceGrid}>
              {audiences.map(({Icon,title,text,image})=><article key={title} data-public-reveal="scale"><div className={styles.audiencePhoto}><img src={image} alt={`Illustrative ${title.toLowerCase()} creator workflow`}/><span><Icon size={18}/></span></div><div><b>{title}</b><p>{text}</p></div></article>)}
            </div>
            <div className={styles.useCaseLinks} data-public-reveal="scale">
              <TransitionLink href="/youtube-video-to-shorts-ai">YouTube URL → Shorts · Coming soon</TransitionLink>
              <TransitionLink href="/podcast-to-clips-india">Podcast → clips</TransitionLink>
              <TransitionLink href="/hindi-video-to-reels">Hindi video → Reels</TransitionLink>
              <TransitionLink href="/educational-video-to-shorts">Education → Shorts</TransitionLink>
              <TransitionLink href="/talking-head-video-to-reels">Talking head → Reels</TransitionLink>
              <TransitionLink href="/affordable-ai-video-clipper-unlimited-posting">Affordable clipping + unlimited posting</TransitionLink>
            </div>
          </section>

          <section className={styles.cartoonSection} aria-labelledby="cartoon-studio-heading">
            <div className={styles.cartoonPanel}>
              <div className={styles.cartoonCopy}>
                <div className={styles.cartoonLabel}><Clapperboard size={18} aria-hidden="true" /> Cartoon Studio</div>
                <h2 id="cartoon-studio-heading">Turn your story into a cartoon</h2>
                <p>
                  Write a short story and turn it into an animated video with character voices and synced captions.
                </p>
                <a className={styles.cartoonCta} href="/ai-cartoon-maker" aria-describedby="cartoon-studio-access">
                  Explore Cartoon Studio <ArrowRight size={17} aria-hidden="true" />
                </a>
                <p className={styles.cartoonAccess} id="cartoon-studio-access">
                  Free includes one cartoon up to 30 seconds per account. Connect your own story planner API key in Cartoon Studio to create.
                </p>
              </div>
              <ul className={styles.cartoonSteps} aria-label="Ways to use your finished cartoon">
                <li><Download size={20} aria-hidden="true" /> Download the finished MP4</li>
                <li><Upload size={20} aria-hidden="true" /> Or send a vertical 9:16 cartoon to Post Karo to review and publish</li>
              </ul>
            </div>
          </section>

          <section className={styles.pricing} id="pricing">
            <div className={styles.pricingHead}><div data-public-reveal="left"><h2>Plans for every editing schedule.</h2></div><p data-public-reveal="right">Choose the Karo Minutes and Short creation allowance you need. Every plan includes unlimited Post Karo publishing access.</p></div>
            <div className={styles.planGrid}>
              {plans.map((plan)=><article key={plan.name} className={plan.featured?styles.planFeatured:""} data-public-reveal="scale">{plan.featured&&<span className={styles.popular}>MOST POPULAR</span>}<h3>{plan.name}</h3><p>{plan.note}</p><div className={styles.planPrice}>{plan.price}<small>{plan.suffix}</small></div><ul>{plan.items.map((item)=><li key={item}><Check size={14}/>{item}</li>)}</ul><TransitionLink href={plan.href} className={plan.featured?styles.planPrimary:styles.planSecondary}>{plan.name==="Free"?"Start free":plan.name==="Mini Pass"?"Get Mini Pass":`Choose ${plan.name}`} <ArrowRight size={14}/></TransitionLink></article>)}
            </div>
            <div className={styles.pricingFoot} data-public-reveal="scale"><span>Creator is also available from ₹249/month.</span><TransitionLink href="/pricing">Compare every plan <ArrowRight size={14}/></TransitionLink></div>
          </section>

          <section className={styles.creatorStory}>
            <div className={styles.creatorStoryInner}>
              <div className={styles.creatorStoryCopy} data-public-reveal="left"><span>Creator-led product</span><h2>Built for creators who want the work to feel lighter.</h2><p>ClipKaro is designed around a simple idea: remove repetitive editing work while keeping the creator in control of what gets published.</p><TransitionLink href="/about" className={styles.limeButton}>Read the ClipKaro story <ArrowRight size={15}/></TransitionLink></div>
              <div className={styles.creatorScene} data-public-reveal="scale"><img src="/assets/creator-demo.jpg" alt="Illustrative fictional creator at a content workstation"/><div><span>ILLUSTRATIVE CREATOR WORKFLOW</span><b>One recording.<br/>More ways to use it.</b></div></div>
              <blockquote data-public-reveal="right"><span>“</span><p>Build practical creator tools that are clear, affordable and honest about what the AI can and cannot do.</p><footer><b>{TRUST_PROFILE.founderName}</b><small>{TRUST_PROFILE.founderTitle}</small></footer></blockquote>
            </div>
          </section>

          <section className={styles.faqSection}>
            <div className={styles.faqHead} data-public-reveal="left"><h2>Common questions</h2></div>
            <div className={styles.faqGrid} data-public-reveal="right">{questions.map(([question,answer])=><details key={question}><summary>{question}<span>+</span></summary><p>{answer}</p></details>)}</div>
          </section>

          <section className={styles.finalCta} data-public-reveal="scale"><div><h2>Make your first Short.</h2><p>Start with an original recording you own or have permission to use.</p></div><TransitionLink href="/signup" className={styles.limeButton}>Create my first Short free <ArrowRight size={16}/></TransitionLink></section>
        </main>

        <PublicSiteFooter />
      </div>
    </PublicMotionShell>
  );
}
