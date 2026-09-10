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
import styles from "./CreatorPulseSpotlight.module.css";

export function CreatorPulseSpotlight() {
  return (
    <section className={styles.section} id="creator-pulse" aria-labelledby="creator-pulse-title">
      <div className={styles.glow} aria-hidden="true" />
      <div className={styles.inner}>
        <div className={styles.copy}>
          <div className={styles.eyebrow}><Activity size={15}/> Creator Pulse · ₹1 channel analysis</div>
          <h2 id="creator-pulse-title">Don&apos;t just check your YouTube analytics. <span>Know what to create next.</span></h2>
          <p className={styles.lead}>
            Creator Pulse is ClipKaro&apos;s YouTube channel analysis tool for creators who want a clear next move, not another wall of numbers. It reads verified public channel data, compares recent upload momentum and turns that evidence into one focused video recommendation.
          </p>

          <div className={styles.valueGrid}>
            <div><BarChart3 size={18}/><span><b>See real momentum</b>Compare recent uploads using public performance data and views-per-day evidence.</span></div>
            <div><Lightbulb size={18}/><span><b>Get one next-video move</b>Receive a specific title, angle, reason, opening hook and confidence level.</span></div>
            <div><Download size={18}/><span><b>Leave with a thumbnail</b>Get one ready-to-download thumbnail concept generated for the recommended video.</span></div>
            <div><TrendingUp size={18}/><span><b>Compare every Pulse</b>Saved Pulse history helps you see what changed since your previous channel check.</span></div>
          </div>

          <div className={styles.actions}>
            <Link className={styles.primary} href="/creator-pulse">
              <Activity size={17}/> Run Creator Pulse · ₹1 <ArrowRight size={16}/>
            </Link>
            <Link className={styles.secondary} href="/about#creator-pulse-story">
              Why we built it
            </Link>
          </div>
          <p className={styles.priceNote}>No subscription required for Creator Pulse · ₹1 is charged only for a successful Pulse.</p>

          <div className={styles.trustRow} aria-label="Creator Pulse trust points">
            <span><Youtube size={14}/> Public YouTube evidence</span>
            <span><ShieldCheck size={14}/> No invented private metrics</span>
            <span><CheckCircle2 size={14}/> One clear recommendation</span>
          </div>
        </div>

        <div className={styles.preview} aria-label="Illustrative Creator Pulse result preview">
          <div className={styles.previewTop}>
            <div>
              <span className={styles.previewKicker}><Sparkles size={12}/> Example result</span>
              <h3>Creator Pulse</h3>
            </div>
            <span className={styles.verified}><CheckCircle2 size={13}/> Verified</span>
          </div>

          <div className={styles.snapshot}>
            <div><span>Subscribers</span><b>24.8K</b></div>
            <div><span>Channel views</span><b>1.2M</b></div>
            <div><span>Recent avg.</span><b>8.4K</b></div>
          </div>

          <div className={styles.momentum}>
            <div className={styles.panelHeading}><span>Verified momentum evidence</span><b>views / day</b></div>
            <div className={styles.barRow}><span>How I built it</span><i><em style={{ width: "92%" }}/></i><b>1.8K</b></div>
            <div className={styles.barRow}><span>What failed first</span><i><em style={{ width: "68%" }}/></i><b>1.3K</b></div>
            <div className={styles.barRow}><span>My creator setup</span><i><em style={{ width: "43%" }}/></i><b>840</b></div>
          </div>

          <div className={styles.nextMove}>
            <span className={styles.nextLabel}>YOUR NEXT MOVE</span>
            <div className={styles.recommendation}>
              <div>
                <small>Recommended next video</small>
                <h4>Build the follow-up your fastest-moving video is asking for</h4>
                <p>Continue the strongest recent theme with a deeper, practical angle instead of guessing a new topic.</p>
                <div className={styles.hook}><b>Opening hook</b><span>“The first version worked — now here&apos;s what I would change.”</span></div>
              </div>
              <div className={styles.thumbnailMock}>
                <span>ONE NEXT MOVE</span>
                <div className={styles.thumbnailLines}><i/><i/><i/></div>
                <small>Downloadable thumbnail</small>
              </div>
            </div>
          </div>

          <p className={styles.previewFoot}>Illustrative preview. Your Pulse uses your channel&apos;s current public YouTube evidence.</p>
        </div>
      </div>
    </section>
  );
}
