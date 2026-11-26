import type { Metadata } from "next";
import { ArrowRight, Clapperboard } from "lucide-react";
import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { CARTOON_SECONDS } from "@/lib/pricing-contract";
import styles from "./cartoon-maker.module.css";

const title = "AI Cartoon Maker from Text | Cartoon Studio by ClipKaro";
const description = "Turn a written story into a short animated cartoon with character voices and captions. Download an MP4 or review a vertical cartoon in Post Karo.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/ai-cartoon-maker" },
  robots: { index: true, follow: true },
  openGraph: { type: "website", url: "/ai-cartoon-maker", title, description, siteName: "ClipKaro AI" },
  twitter: { card: "summary", title, description },
};

export default function CartoonMakerPage() {
  return (
    <>
      <PublicSiteNav />
      <main className={styles.page}>
        <header className={styles.hero}>
          <div className={styles.intro}>
            <p className={styles.label}><Clapperboard size={18} aria-hidden="true" /> Cartoon Studio</p>
            <h1>Turn a written story into an <span>animated cartoon</span></h1>
            <p>ClipKaro’s AI cartoon maker plans scenes from your story and creates a short video with character voices and captions.</p>
            <div className={styles.actions}>
              <a className={styles.studioLink} href="/cartoon-studio">Open Cartoon Studio <ArrowRight size={18} aria-hidden="true" /></a>
              <a href="/pricing">Compare plan allowances</a>
            </div>
            <p className={styles.allowance}>The Free plan includes one cartoon up to {CARTOON_SECONDS.free} seconds per account. Sign in and connect your own story planner API key to create.</p>
          </div>
          <aside className={styles.example} aria-labelledby="example-prompt-title">
            <h2 id="example-prompt-title">Try this story idea</h2>
            <p>A young fox finds a red kite tangled in a garden fence. She asks a rabbit for help, and they work together to set it free. When the kite lifts off, the fox says, “Your turn to fly it!”</p>
          </aside>
        </header>

        <section className={styles.section} aria-labelledby="cartoon-workflow">
          <h2 id="cartoon-workflow">How to make a cartoon from text</h2>
          <ol className={styles.steps}>
            <li><h3>Write your story</h3><p>Describe the characters, what happens, and any dialogue you want them to say. A short idea or a scene-by-scene script both work as starting points.</p></li>
            <li><h3>Choose the video settings</h3><p>Pick an animation style, language, and aspect ratio. Video lengths range from 15 to 60 seconds, depending on your available allowance.</p></li>
            <li><h3>Download or publish</h3><p>Play the finished cartoon, check the caption timeline, and download the MP4. Send a finished 9:16 cartoon to Post Karo to review and publish to a connected account.</p></li>
          </ol>
        </section>
      </main>
      <PublicSiteFooter />
    </>
  );
}
