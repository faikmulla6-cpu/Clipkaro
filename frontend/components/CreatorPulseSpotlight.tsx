import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Check,
  CheckCircle2,
  Download,
  ShieldCheck,
  Sparkles,
  Youtube,
} from "lucide-react";
import styles from "./CreatorPulseSpotlight.module.css";

export function CreatorPulseSpotlight() {
  return (
    <section className={styles.section} id="creator-pulse" aria-labelledby="creator-pulse-title">
      <div className={styles.ambient} aria-hidden="true" />
      <div className={styles.inner}>
        <div className={styles.copy}>
          <div className={styles.eyebrow}><Activity size={15}/> Creator Pulse · ₹1 channel intelligence</div>
          <h2 id="creator-pulse-title">Know what&apos;s working. <span>Know what to create next.</span></h2>
          <p className={styles.lead}>
            Creator Pulse analyses your public YouTube channel, compares recent uploads, identifies real momentum and turns that evidence into one clear next-video decision — including a title, angle, opening hook and downloadable thumbnail when generation is available.
          </p>

          <div className={styles.proofList} aria-label="Creator Pulse benefits">
            <div><Check size={16}/><span><b>Verified YouTube evidence</b>Public channel data and recent-upload momentum, not guessed private metrics.</span></div>
            <div><Check size={16}/><span><b>One focused next-video decision</b>A recommended topic with the reasoning, angle, title, hook and confidence behind it.</span></div>
            <div><Check size={16}/><span><b>One downloadable thumbnail when available</b>A finished thumbnail can be prepared around the recommendation so you can move from insight to action faster.</span></div>
          </div>

          <div className={styles.actions}>
            <Link className={styles.primary} href="/creator-pulse">
              <Activity size={17}/> Run Creator Pulse for ₹1 <ArrowRight size={16}/>
            </Link>
            <Link className={styles.secondary} href="/youtube-channel-analyzer">
              Explore Creator Pulse
            </Link>
          </div>
          <p className={styles.priceNote}>₹1 only for a successful Pulse · No Creator Pulse subscription required.</p>

          <div className={styles.trustRow} aria-label="Creator Pulse trust points">
            <span><Youtube size={14}/> Public YouTube data</span>
            <span><ShieldCheck size={14}/> Evidence-led</span>
            <span><Download size={14}/> Downloadable result</span>
          </div>
        </div>

        <div className={styles.previewWrap}>
          <div className={styles.previewGlow} aria-hidden="true" />
          <div className={styles.preview} aria-label="Illustrative Creator Pulse result preview">
            <div className={styles.previewTop}>
              <div>
                <span className={styles.previewKicker}><Sparkles size={12}/> Creator Pulse result</span>
                <h3>One clear Pulse.</h3>
              </div>
              <span className={styles.verified}><CheckCircle2 size={13}/> Verified</span>
            </div>

            <div className={styles.channelRow}>
              <div className={styles.channelAvatar}>C</div>
              <div><b>Creator Channel</b><span>@creator · public YouTube data</span></div>
              <small>Illustrative example</small>
            </div>

            <div className={styles.snapshot}>
              <div><span>Subscribers</span><b>24.8K</b></div>
              <div><span>Total views</span><b>1.2M</b></div>
              <div><span>Videos</span><b>86</b></div>
              <div><span>Recent avg.</span><b>8.4K</b></div>
            </div>

            <div className={styles.momentum}>
              <div className={styles.panelHeading}>
                <div><BarChart3 size={13}/><span>Verified momentum evidence</span></div>
                <b>views / day</b>
              </div>
              <div className={styles.barRow}><span>How I built it</span><i><em style={{ width: "94%" }}/></i><b>1.8K</b></div>
              <div className={styles.barRow}><span>What failed first</span><i><em style={{ width: "69%" }}/></i><b>1.3K</b></div>
              <div className={styles.barRow}><span>My creator setup</span><i><em style={{ width: "45%" }}/></i><b>840</b></div>
            </div>

            <div className={styles.nextMove}>
              <div className={styles.nextMoveHead}>
                <span>YOUR NEXT MOVE</span>
                <small><CheckCircle2 size={11}/> Strong confidence</small>
              </div>
              <div className={styles.recommendation}>
                <div className={styles.recommendationCopy}>
                  <small>Recommended next video</small>
                  <h4>Build the follow-up your fastest-moving video is asking for</h4>
                  <p>Continue the strongest recent theme with a deeper practical angle instead of guessing a completely new topic.</p>
                  <div className={styles.ideaGrid}>
                    <div><span>BEST ANGLE</span><b>Show the upgrade step-by-step and prove what changed.</b></div>
                    <div><span>OPENING HOOK</span><b>“The first version worked — now here&apos;s what I would change.”</b></div>
                  </div>
                </div>

                <div className={styles.thumbnailColumn}>
                  <div className={styles.thumbnailMock}>
                    <div className={styles.thumbBadge}>NEXT VIDEO</div>
                    <div className={styles.thumbVisual} aria-hidden="true">
                      <span className={styles.thumbOrb}/>
                      <span className={styles.thumbRing}/>
                      <span className={styles.thumbWave}/>
                    </div>
                    <strong>BUILD THE<br/>UPGRADE</strong>
                    <span className={styles.thumbAccent}>STEP BY STEP</span>
                  </div>
                  <span className={styles.thumbFoot}><Download size={11}/> Example of one downloadable thumbnail</span>
                </div>
              </div>
            </div>

            <p className={styles.previewFoot}>Illustrative preview. Your Pulse is generated from your channel&apos;s current public YouTube evidence.</p>
          </div>
        </div>
      </div>
    </section>
  );
}
