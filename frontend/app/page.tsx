import { ArrowRight, Check, Clapperboard, Headphones, Languages, LockKeyhole, Play, Scissors, ShieldCheck, Sparkles, Subtitles, Upload, UserRound, WandSparkles, Zap } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { SmoothAnchorLink } from "@/components/SmoothAnchorLink";
import { TransitionLink } from "@/components/TransitionLink";
import { LEGAL_LINKS, TRUST_PROFILE } from "@/lib/legal";
import { SEO_PAGES } from "@/lib/seo-pages";
import home from "./home-polish.module.css";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const softwareStructuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "ClipKaro AI",
  url: "https://clipkaro.pro/",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  description:
    "AI video clipping and content repurposing for Indian creators with smart clip detection, India Quality Mode, transcript review, captions, vertical export and Content Packs.",
  featureList: [
    "AI clip detection and ranking",
    "India Quality Mode for Hindi, Hinglish and Indian-English creator workflows",
    "Roman Hinglish caption support",
    "Smart Transcript Review with inline corrections",
    "Caption-safe vertical video rendering",
    "One video to complete Content Pack",
    "YouTube Shorts, Instagram Reels, X and LinkedIn copy generation",
    "Creator Studio zoom from 100% to 200%",
    "Manual horizontal reframe and focus positioning",
    "9:16, 4:5 and 1:1 export controls",
    "Caption style and caption position controls",
    "Brand Kit support",
  ],
};

export default function Home() {
  return <div className="landing">
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareStructuredData) }} />
    <nav className="landing-nav">
      <Logo />
      <div className={`nav-links ${home.desktopNavigation}`}>
        <SmoothAnchorLink href="#how">How it works</SmoothAnchorLink>
        <SmoothAnchorLink href="#features">Features</SmoothAnchorLink>
        <SmoothAnchorLink href="#use-cases">Use cases</SmoothAnchorLink>
        <SmoothAnchorLink href="#pricing">Pricing</SmoothAnchorLink>
        <TransitionLink href="/about">About</TransitionLink>
      </div>
      <div className={`nav-ctas ${home.desktopNavigation}`}>
        <Link href="/login" className="text-btn">Log in</Link>
        <Link href="/signup" className="primary-btn">Start free <ArrowRight size={15}/></Link>
      </div>
      <MobileLandingMenu />
    </nav>
    <section className="hero"><span className="eyebrow"><Sparkles size={13}/> Built for Indian creators</span><h1>Turn long videos into <span className="lime-underline">scroll-stopping Shorts</span></h1><p>ClipKaro AI finds your strongest moments, improves India-first captions, lets you review uncertain transcript lines, and turns each selected clip into a ready-to-publish Content Pack.</p><div className="hero-actions"><Link className="primary-btn" href="/signup"><Upload size={17}/> Create your first Short</Link><SmoothAnchorLink className="secondary-btn" href="#how"><Play size={15}/> See how it works</SmoothAnchorLink></div><div className="hero-note">No card required · Start free · Upload content you own</div>
      <div className="hero-product"><div className="mock-window"><div className="mock-side"><div className="mini-logo">✦ ClipKaro</div><div className="mock-nav"><span>Overview</span><span>Upload video</span><span>My projects</span><span>Content Pack</span></div></div><div className="mock-body"><div className="mock-title"><div><h3>Your best moments are ready</h3><small>5 clips found in “How I grew my channel”</small></div><span className="mock-export-label" aria-hidden="true">Export selected</span></div><div className="mock-stats"><div className="mock-stat"><span>Moments found</span><b>05</b></div><div className="mock-stat"><span>Best moment score</span><b>94</b></div><div className="mock-stat"><span>Minutes saved</span><b>47</b></div></div>{["The mistake almost every creator makes", "My simple 3-step growth system"].map((t,i)=><div className="clip-row" key={t}><div className="clip-thumb"><Play size={18}/></div><div className="clip-copy"><b>{t}</b><span>{i?'06:18 – 06:57':'02:10 – 02:46'} · Educational insight</span></div><div className="score">{i?'89':'94'}</div></div>)}</div></div></div>
    </section>
    <div className="trust-strip">Designed for <b>YouTubers · Coaches · Teachers · Podcasters · Local businesses · Agencies</b></div>
    <section className="section" id="how"><div className="section-heading"><span>One smart workflow</span><h2>From long video to polished Short — and the content around it</h2><p>Upload once. ClipKaro finds the moments, helps clean uncertain transcript lines, prepares captions and exports, then creates platform-ready copy for the clips you want to publish.</p></div><div className="feature-grid">{[[Upload,"Upload your own video","Drag in an MP4, MOV, WebM or MKV. Your files stay private and expire automatically."],[WandSparkles,"AI finds the moments","Transcript scoring discovers strong hooks, lessons, stories, questions and surprising moments."],[Clapperboard,"Review, export & repurpose","Fix flagged transcript lines when needed, export a 9:16 Short, and open its Content Pack for publishing copy."]].map(([I,t,d]:any)=><div className="feature-card" key={t}><div className="feature-icon"><I size={21}/></div><h3>{t}</h3><p>{d}</p></div>)}</div></section>
    <section className="section sample-output-section" id="sample-output">
      <div className="sample-output-copy">
        <span className="section-kicker">Sample output</span>
        <h2>Know what you get before you upload.</h2>
        <p>This example shows the kind of ranked moment, caption treatment and export checklist ClipKaro is built to produce. Real quality still depends on your source audio, language and lighting.</p>
        <div className="sample-output-list">
          {["A ranked clip with hook, reason and score", "Mobile-readable captions with India-aware review controls", "A 9:16 MP4 plus publishing copy for the selected moment"].map((item)=><div key={item}><Check size={15}/><span>{item}</span></div>)}
        </div>
        <Link href="/signup" className="primary-btn"><Upload size={16}/> Try with your own video</Link>
      </div>
      <div className="sample-output-preview" aria-label="Example ClipKaro output preview">
        <div className="sample-phone-frame">
          <div className="sample-video-face"><Play size={28} fill="currentColor"/></div>
          <div className="sample-caption"><span>The mistake most creators make is waiting for a perfect idea.</span></div>
          <div className="sample-watermark">ClipKaro AI sample</div>
        </div>
        <div className="sample-output-panel">
          <span>AI-ranked moment</span>
          <h3>The creator mistake that kills consistency</h3>
          <p>Strong standalone advice, clear first sentence, clean ending and useful takeaway for Indian creator audiences.</p>
          <div><b>92</b><small>hook score</small></div>
        </div>
      </div>
    </section>
    <section className={`section ${home.featureLift}`} id="features"><div className="section-heading"><span>ClipKaro AI features</span><h2>Every major feature has a real creator UI</h2><p>From transcript review to zoom, Content Packs and caption-safe export, ClipKaro surfaces the controls creators actually need instead of hiding them in the backend.</p></div><div className="feature-grid">{[[Scissors,"Smart AI Clip Finder","Ranks moments by hook, clarity, emotion, value and clean endings so creators can reach the strongest parts faster."],[Languages,"India Quality Mode","Optional India-first workflow for Hindi, Hinglish and Indian-English content with Roman Hinglish handling and safer caption placement."],[Subtitles,"Smart Transcript Review","Flags suspicious transcript segments, jumps to the source timestamp, and lets you correct or reset text before captions and Content Packs use it."],[Sparkles,"One Video → Content Pack","Turns selected clips into YouTube Shorts titles and descriptions, Instagram captions, hashtags, X posts, contextual LinkedIn copy and cover-text ideas."],[Clapperboard,"Caption-safe vertical export","Preserve burned-in source subtitles when needed and keep generated captions away from protected subtitle areas in 9:16 output."],[Zap,"Zoom and manual reframe","Creator Studio gives 100%, 150% and 200% zoom plus horizontal focus controls so the final Short is framed intentionally."],[Clapperboard,"Multiple export shapes","Choose 9:16 Shorts/Reels, 4:5 social crops or 1:1 square outputs from the editor before rendering."],[Subtitles,"Caption styles and positions","Pick caption personalities such as Kinetic, Clean, Bold, Minimal and India Pop, then place captions at bottom, above or center."],[WandSparkles,"Hooks, titles & clip reasons","Each suggestion includes a title, hook, reason, score and best-platform context to make selection easier."],[ShieldCheck,"Brand Kit and rights-safe workflow","Use creator branding where available and keep the upload-first workflow focused on content you own or have permission to use."],[Zap,"Cost-smart rendering","Videos render only after you choose a moment, keeping processing efficient and plans affordable."],[ShieldCheck,"Private media handling","Source videos and exports use private delivery, retention rules and ownership checks instead of public file links."]].map(([I,t,d]:any)=><div className="feature-card" key={t}><div className="feature-icon"><I size={21}/></div><h3>{t}</h3><p>{d}</p></div>)}</div><p className={home.smoothFeatureNote}>These are not placeholder claims: the authenticated product includes project results, Content Pack workspace, Transcript Review, Creator Studio, export/download and quota-aware flows.</p></section>
    <section className={`section ${home.workflowLift}`} id="creator-workflow"><div className="section-heading"><span>More than an AI clipper</span><h2>One video can now become a complete creator-ready package</h2><p>ClipKaro connects the steps that usually force creators to jump between multiple tools.</p></div><div className="feature-grid">{[[Languages,"India-first caption quality","Use India Quality Mode for Hindi, Hinglish and Indian-English workflows, including Roman Hinglish support where it fits the transcript."],[Subtitles,"Fix uncertain speech before export","Smart Transcript Review surfaces suspicious lines, keeps your correction after refresh, and uses the corrected text in captions and downstream content."],[Sparkles,"Publish beyond the video file","Content Pack keeps each asset grounded in the selected clip and prepares titles, descriptions, captions, hashtags, social posts, cover text and recommended clip order."],[Clapperboard,"Frame the Short your way","Adjust aspect ratio, caption position, zoom and horizontal focus before rendering so the final video matches the platform."],[WandSparkles,"Keep corrections connected","Transcript corrections flow into visible clip text, captions, Creator Studio seed text and regenerated Content Packs."],[ShieldCheck,"Preserve source subtitles","When a source video already has burned-in captions, ClipKaro can preserve the subtitle area instead of cropping it away."]].map(([I,t,d]:any)=><div className="feature-card" key={t}><div className="feature-icon"><I size={21}/></div><h3>{t}</h3><p>{d}</p></div>)}</div></section>
    <section className="section homepage-use-case-section" id="use-cases"><div className="section-heading"><span>Popular workflows</span><h2>Repurpose the videos creators already have</h2><p>High-intent ClipKaro workflows for YouTube creators, Hindi and Hinglish speakers, podcasters, educators and agencies.</p></div><div className="seo-use-case-grid homepage-use-cases">{SEO_PAGES.slice(0,6).map((item)=><TransitionLink key={item.slug} href={`/${item.slug}`}><Check size={16}/><span>{item.title}</span></TransitionLink>)}</div></section>
    <section className="section pricing-preview" id="pricing"><div className="section-heading"><span>Fair Access Pricing</span><h2>Start small. Grow when you grow.</h2><p>Professional AI clipping from ₹59 without forcing you into a subscription.</p></div><div className="price-grid">{[{n:'Mini Pass',p:'₹59',s:'one-time',d:'For students & small creators',f:['25 Karo Minutes','5 Shorts','1080p · no watermark']},{n:'Growth',p:'₹399',s:'/month',d:'Most popular for serious creators',f:['180 Karo Minutes','50 Shorts','1080p · no watermark'],hot:true},{n:'Pro',p:'₹799',s:'/month',d:'For daily publishing',f:['480 Karo Minutes','150 Shorts','Same strong ClipKaro AI']}].map(x=><div className={`price-card ${x.hot?'featured':''}`} key={x.n}><h3>{x.n}</h3><p>{x.d}</p><div className="price">{x.p}<small>{x.s}</small></div><ul>{x.f.map(y=><li key={y}><Check size={14}/>{y}</li>)}</ul><Link href="/pricing" className="primary-btn">View {x.n}</Link></div>)}</div><p style={{textAlign:"center",marginTop:20,color:"#657169",fontSize:13}}>Mini Pass never auto-renews. Monthly plans renew until cancelled or changed. <Link href="/refund-policy">Refund & cancellation policy</Link>.</p></section>
    <section className="trust-band" aria-label="ClipKaro trust commitments">
      <div className="trust-band-heading">
        <span>Trust before upload</span>
        <h2>Built by a real founder, with clear support and private media rules.</h2>
        <p>Before a creator uploads a video or pays, ClipKaro should answer the obvious trust questions directly.</p>
      </div>
      <div className="trust-card">
        <i><UserRound size={20}/></i>
        <span>Founder-led</span>
        <b>{TRUST_PROFILE.founderName}</b>
        <p>{TRUST_PROFILE.founderTitle}. Direct product ownership, public founder story and clear operator details before checkout.</p>
        <TransitionLink href="/about#founder">Read founder story <ArrowRight size={14}/></TransitionLink>
      </div>
      <div className="trust-card">
        <i><Headphones size={20}/></i>
        <span>Support expectation</span>
        <b>48-hour acknowledgement</b>
        <p>Billing, upload and account questions use visible customer-care contacts with a published response expectation.</p>
        <TransitionLink href="/contact">Contact support <ArrowRight size={14}/></TransitionLink>
      </div>
      <div className="trust-card">
        <i><LockKeyhole size={20}/></i>
        <span>Private media</span>
        <b>Uploads expire automatically</b>
        <p>Source videos and exports use a short retention window, with privacy and deletion rules explained plainly.</p>
        <TransitionLink href="/privacy">See retention details <ArrowRight size={14}/></TransitionLink>
      </div>
    </section>
    <footer className="landing-footer"><div className="footer-inner" style={{alignItems:"flex-start",gap:20,flexWrap:"wrap"}}><div><Logo light/><p>© 2026 ClipKaro AI. Create responsibly. Built for India.</p></div><div style={{display:"flex",gap:12,flexWrap:"wrap",fontSize:12}}><TransitionLink href="/about">About</TransitionLink><Link href="/contact">Contact</Link>{LEGAL_LINKS.map(([label,href])=><Link key={href} href={href}>{label}</Link>)}</div></div></footer>
  </div>;
}
