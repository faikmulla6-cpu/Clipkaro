import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Download,
  Lightbulb,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Youtube,
} from "lucide-react";
import styles from "./AboutCreatorPulse.module.css";

export function AboutCreatorPulse() {
  return (
    <section className={styles.section} id="creator-pulse-story" aria-labelledby="about-creator-pulse-title">
      <div className={styles.inner}>
        <div className={styles.heading}>
          <span className={styles.index}>CREATOR PULSE / WHY IT EXISTS</span>
          <h2 id="about-creator-pulse-title">From editing yesterday&apos;s video to deciding <span>tomorrow&apos;s one.</span></h2>
          <p>
            ClipKaro began by reducing the repetitive work inside long-form video. Creator Pulse extends that idea to a different creator problem: deciding what to publish next when a dashboard gives you numbers but no clear next action.
          </p>
        </div>

        <div className={styles.storyGrid}>
          <article>
            <div className={styles.icon}><Lightbulb size={19}/></div>
            <span>WHY WE CREATED IT</span>
            <h3>Creators should not have to guess after reading their analytics.</h3>
            <p>
              Public YouTube data can show what happened, but creators still have to connect the dots between recent uploads, momentum and the next content decision. Creator Pulse was built to make that decision smaller, clearer and more actionable.
            </p>
          </article>
          <article>
            <div className={styles.icon}><ShieldCheck size={19}/></div>
            <span>HOW WE BUILT THE IDEA</span>
            <h3>Evidence first. Creative assistance second.</h3>
            <p>
              The workflow starts with verified public channel information, compares recent upload performance and keeps previous Pulse history. Only after that evidence is established does ClipKaro prepare one recommended next video, rather than inventing private analytics the channel has not provided.
            </p>
          </article>
          <article>
            <div className={styles.icon}><TrendingUp size={19}/></div>
            <span>THE CREATOR BENEFIT</span>
            <h3>Less dashboard time. Less topic guessing. One usable next move.</h3>
            <p>
              A successful Pulse turns channel evidence into a specific title, the reason behind it, a practical angle, an opening hook, a confidence level and one downloadable thumbnail. The creator still decides what represents their voice.
            </p>
          </article>
        </div>

        <div className={styles.flowCard}>
          <div className={styles.flowHeading}>
            <span><Activity size={15}/> What one ₹1 Pulse does</span>
            <b>Successful Pulse only</b>
          </div>
          <div className={styles.flow} aria-label="Creator Pulse workflow">
            <div><Youtube size={18}/><b>Verify</b><span>Public YouTube channel data</span></div>
            <i aria-hidden="true">→</i>
            <div><BarChart3 size={18}/><b>Compare</b><span>Recent momentum + previous Pulse</span></div>
            <i aria-hidden="true">→</i>
            <div><Sparkles size={18}/><b>Decide</b><span>One evidence-led next video</span></div>
            <i aria-hidden="true">→</i>
            <div><Download size={18}/><b>Prepare</b><span>Hook, angle + downloadable thumbnail</span></div>
          </div>
        </div>

        <div className={styles.boundary}>
          <CheckCircle2 size={18}/>
          <p><b>What Creator Pulse is:</b> decision support based on the public evidence available in that Pulse. <b>What it is not:</b> a promise of views, virality or hidden metrics such as private retention, CTR or impressions that were not supplied.</p>
        </div>

        <div className={styles.cta}>
          <div>
            <span>Ready to stop guessing?</span>
            <h3>Run a Creator Pulse for ₹1.</h3>
            <p>If you&apos;re already signed in, the button opens Creator Pulse directly. New creators can create an account, verify their email and continue back to the same feature.</p>
          </div>
          <Link href="/creator-pulse" className={styles.button}>
            <Activity size={17}/> Try Creator Pulse · ₹1 <ArrowRight size={16}/>
          </Link>
        </div>
      </div>
    </section>
  );
}
