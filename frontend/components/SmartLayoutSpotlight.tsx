"use client";

import { useState } from "react";
import { ArrowRight, Check, CheckCircle2, Focus, Layers3, LockKeyhole, ScanFace, ShieldCheck, Sparkles, WandSparkles } from "lucide-react";
import { TransitionLink } from "@/components/TransitionLink";
import styles from "./SmartLayoutSpotlight.module.css";

type LayoutMode = "auto" | "dual" | "focus";
type Props = { context?: "home" | "about" };

const modes = [
  {
    key: "auto" as const,
    label: "Auto Director",
    icon: WandSparkles,
    hint: "A more natural cut, even when the conversation changes direction.",
    detail: "Uses speaker and shot information to choose a suitable portrait framing as the source changes.",
    status: "Adaptive framing",
  },
  {
    key: "dual" as const,
    label: "Dual Stack",
    icon: Layers3,
    hint: "Give both sides of the conversation their place.",
    detail: "Stacks two visible speakers for the moment, and can return to a single view when only one is visible.",
    status: "Two-speaker composition",
  },
  {
    key: "focus" as const,
    label: "Speaker Focus",
    icon: Focus,
    hint: "Keep the person speaking at the center of attention.",
    detail: "Builds a clean portrait crop around the detected speaker when a focused view serves the moment.",
    status: "Single-speaker emphasis",
  },
];

export function SmartLayoutSpotlight({ context = "home" }: Props) {
  const [mode, setMode] = useState<LayoutMode>("dual");
  const active = modes.find((item) => item.key === mode) ?? modes[1];
  const isAbout = context === "about";

  return (
    <section id="smart-layout" aria-labelledby={"smart-layout-heading-" + context}
      className={[styles.section, "relative isolate overflow-hidden px-5 py-20 sm:px-8 sm:py-24 lg:py-28"].join(" ")}>
      <div className={styles.ambient} aria-hidden="true" />
      <div className="relative z-10 mx-auto grid w-full max-w-[1320px] items-center gap-12 lg:grid-cols-[0.93fr_1.07fr] lg:gap-16">
        <div className="max-w-[660px]">
          <div className="mb-6 inline-flex items-center gap-2.5 text-[11px] font-extrabold uppercase tracking-[0.19em] text-[#d6f59c]">
            <span className={styles.signal} aria-hidden="true"><Sparkles size={15} /></span>
            Introducing Smart Layout
          </div>
          <h2 id={"smart-layout-heading-" + context}
            className={styles.heading}>
            {isAbout ? <>Every conversation deserves <em>a thoughtful frame.</em></> :
              <>Your story, <em>beautifully framed.</em> Automatically.</>}
          </h2>
          <p className="mt-6 max-w-[560px] text-[15px] leading-[1.85] text-[#b9cec1] sm:text-[17px]">
            {isAbout
              ? "Smart Layout is our approach to intelligent portrait composition. It looks at who is on screen, adapts to changes in the shot and leaves the final creative decision with you."
              : "Turn landscape conversations into portrait-ready Shorts with speaker-aware framing. From two-person podcasts to solo insights, Smart Layout helps the right moment take center stage."}
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <div className={styles.benefit}>
              <ScanFace size={19} aria-hidden="true" />
              <div><b>Speaker-aware composition</b><span>Adapts when people enter or leave the frame.</span></div>
            </div>
            <div className={styles.benefit}>
              <CheckCircle2 size={19} aria-hidden="true" />
              <div><b>You approve the edit</b><span>Preview, choose the layout and review before export.</span></div>
            </div>
          </div>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <TransitionLink href="/signup" className={styles.primary}>
              Try ClipKaro <ArrowRight size={17} aria-hidden="true" />
            </TransitionLink>
            <TransitionLink href="/pricing" className={styles.secondary}>
              View Smart Layout credits <ArrowRight size={16} aria-hidden="true" />
            </TransitionLink>
          </div>
          <p className="mt-5 flex max-w-[585px] items-start gap-2 text-[12px] leading-[1.7] text-[#9fb5a8]">
            <LockKeyhole size={15} className="mt-0.5 shrink-0 text-[#c5e5b0]" aria-hidden="true" />
            Premium analysis uses separate Smart Layout credits with explicit cost consent.
            Classic framing remains available. Plan limits apply.
          </p>
        </div>

        <div className={styles.demoShell}>
          <div className={styles.demoTop}>
            <div className="flex items-center gap-2">
              <span className={styles.windowDot} /><span className={styles.windowDot} /><span className={styles.windowDot} />
              <span className="ml-2 text-[11px] font-bold tracking-[0.08em] text-[#dceade]">CLIPKARO STUDIO</span>
            </div>
            <span className={styles.liveMark}><span aria-hidden="true" /> VISUAL WALKTHROUGH</span>
          </div>

          <div className={styles.demoBody}>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#83a28e]">Portrait composition</span>
                <h3 className="mt-1 text-[20px] font-extrabold tracking-[-0.035em] text-[#ecf6ef] sm:text-[22px]">See the difference in framing.</h3>
              </div>
              <span className={styles.ratio}>9:16 output</span>
            </div>

            <div role="tablist" aria-label="Explore Smart Layout modes" className={styles.tabs}>
              {modes.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button key={item.key} type="button" id={"smart-layout-tab-" + context + "-" + item.key}
                    role="tab" aria-selected={mode === item.key}
                    aria-controls={"smart-layout-panel-" + context}
                    tabIndex={mode === item.key ? 0 : -1}
                    className={[styles.tab, mode === item.key ? styles.tabActive : ""].join(" ")}
                    onClick={() => setMode(item.key)}
                    onKeyDown={(event) => {
                      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
                      event.preventDefault();
                      const next = modes[(index + (event.key === "ArrowRight" ? 1 : modes.length - 1)) % modes.length];
                      setMode(next.key);
                      document.getElementById("smart-layout-tab-" + context + "-" + next.key)?.focus();
                    }}>
                    <Icon size={15} aria-hidden="true" /><span>{item.label}</span>
                  </button>
                );
              })}
            </div>

            <div id={"smart-layout-panel-" + context} role="tabpanel"
              aria-labelledby={"smart-layout-tab-" + context + "-" + mode} tabIndex={0}
              className={styles.canvas}>
              <div className={styles.inputCard}>
                <span className={styles.panelLabel}>SOURCE · 16:9</span>
                <div className={styles.sourceThumb}>
                  <img src="/assets/usecase-podcaster.png" alt="Illustrative podcast source frame" />
                  <span className={styles.sourceDivider} aria-hidden="true" />
                </div>
                <span className={styles.sourceCaption}><Check size={13} aria-hidden="true" /> Speaker and shot analysis</span>
              </div>
              <ArrowRight className={styles.canvasArrow} size={22} aria-hidden="true" />
              <div className={styles.previewHolder}>
                <span className={styles.panelLabel}>PORTRAIT · {active.status}</span>
                <div className={styles.phone}>
                  <div className={styles.phoneCamera} aria-hidden="true" />
                  <div className={styles.phoneVisual} data-layout={mode}>
                    {mode === "dual" ? (
                      <>
                        <div className={styles.personTop}><img src="/assets/usecase-podcaster.png" alt="Illustrative first speaker crop" /></div>
                        <div className={styles.personBottom}><img src="/assets/usecase-founder-demo.png" alt="Illustrative second speaker crop" /></div>
                        <span className={styles.frameLine} aria-hidden="true" />
                      </>
                    ) : (
                      <div className={styles.personFull}>
                        <img src={mode === "auto" ? "/assets/usecase-podcaster.png" : "/assets/usecase-founder-demo.png"}
                          alt={mode === "auto" ? "Illustrative automatically framed speaker" : "Illustrative single-speaker portrait crop"} />
                      </div>
                    )}
                    <span className={styles.frameCaption}>
                      {mode === "dual" ? <>TWO VOICES.<br /><strong>ONE STORY.</strong></> :
                        mode === "auto" ? <>FOLLOW THE <strong>CONVERSATION.</strong></> :
                          <>KEEP THE <strong>FOCUS.</strong></>}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className={styles.modeInfo} aria-live="polite">
              <div className={styles.modeIcon}><active.icon size={18} aria-hidden="true" /></div>
              <div><b>{active.hint}</b><p>{active.detail}</p></div>
            </div>
            <div className={styles.demoFooter}>
              <span><ShieldCheck size={14} aria-hidden="true" /> Private, owner-scoped analysis</span>
              <span>Illustrative preview · Results depend on footage</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
