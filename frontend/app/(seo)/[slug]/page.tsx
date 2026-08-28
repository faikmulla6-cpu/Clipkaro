import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Check, ShieldCheck, Sparkles, Upload, WandSparkles } from "lucide-react";
import { Logo } from "@/components/Logo";
import { MobileLandingMenu } from "@/components/MobileLandingMenu";
import { TransitionLink } from "@/components/TransitionLink";
import { LEGAL_LINKS } from "@/lib/legal";
import { getSeoPage, SEO_PAGES } from "@/lib/seo-pages";

type PageProps = {
  params: Promise<{ slug: string }>;
};

export const dynamicParams = false;

export function generateStaticParams() {
  return SEO_PAGES.map((page) => ({ slug: page.slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const page = getSeoPage(slug);
  if (!page) return {};
  return {
    title: page.metaTitle,
    description: page.description,
    alternates: { canonical: `/${page.slug}` },
    openGraph: {
      type: "website",
      url: `/${page.slug}`,
      siteName: "ClipKaro AI",
      title: page.metaTitle,
      description: page.description,
      images: [{ url: "/assets/clipkaro-icon.png", width: 1024, height: 1024, alt: page.title }],
    },
    twitter: {
      card: "summary_large_image",
      title: page.metaTitle,
      description: page.description,
      images: ["/assets/clipkaro-icon.png"],
    },
  };
}

export default async function SeoLandingPage({ params }: PageProps) {
  const { slug } = await params;
  const page = getSeoPage(slug);
  if (!page) notFound();

  const schema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "ClipKaro AI",
    applicationCategory: "MultimediaApplication",
    operatingSystem: "Web",
    url: `https://clipkaro.pro/${page.slug}`,
    description: page.description,
    offers: {
      "@type": "Offer",
      priceCurrency: "INR",
      price: "59",
      availability: "https://schema.org/InStock",
    },
  };

  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: page.faq.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };

  return (
    <div className="landing seo-landing">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema) }} />

      <nav className="landing-nav">
        <Link href="/" aria-label="ClipKaro AI home"><Logo /></Link>
        <div className="nav-links">
          <a href="#workflow">Workflow</a>
          <a href="#use-cases">Use cases</a>
          <a href="#faq">FAQ</a>
          <Link href="/pricing">Pricing</Link>
        </div>
        <div className="nav-ctas">
          <Link href="/login" className="text-btn">Login</Link>
          <Link href="/signup" className="primary-btn">Start free <ArrowRight size={16}/></Link>
        </div>
        <MobileLandingMenu />
      </nav>

      <header className="seo-hero">
        <span className="eyebrow"><Sparkles size={14}/>{page.eyebrow}</span>
        <h1>{page.h1}</h1>
        <p>{page.lead}</p>
        <div className="hero-actions">
          <Link href="/signup" className="primary-btn">Try ClipKaro free <ArrowRight size={16}/></Link>
          <Link href="/pricing" className="secondary-btn">See pricing</Link>
        </div>
      </header>

      <main>
        <section className="seo-product-strip">
          <div><Upload size={19}/><b>Upload-first</b><span>Use video files you own or have permission to process.</span></div>
          <div><WandSparkles size={19}/><b>AI-ranked moments</b><span>Hooks, titles, reasons and platform-fit suggestions.</span></div>
          <div><ShieldCheck size={19}/><b>Private media window</b><span>Source and export files expire automatically after the configured retention window.</span></div>
        </section>

        <section className="section seo-section">
          <div className="seo-two-col">
            <div>
              <span className="section-kicker">Built for</span>
              <h2>{page.audience}</h2>
            </div>
            <p>{page.promise}</p>
          </div>
        </section>

        <section className="section seo-section" id="workflow">
          <div className="section-heading">
            <span>Workflow</span>
            <h2>From source video to short-form output</h2>
          </div>
          <div className="seo-steps">
            {page.workflow.map((step, index) => (
              <article key={step}>
                <span>{index + 1}</span>
                <p>{step}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="section seo-section" id="use-cases">
          <div className="section-heading">
            <span>Best-fit use cases</span>
            <h2>High-intent workflows this page serves</h2>
          </div>
          <div className="seo-use-case-grid">
            {page.useCases.map((item) => (
              <div key={item}><Check size={16}/><span>{item}</span></div>
            ))}
          </div>
        </section>

        <section className="section seo-section">
          <div className="seo-trust-note">
            <ShieldCheck size={22}/>
            <div>
              <b>Honest capability note</b>
              <p>{page.trust}</p>
            </div>
          </div>
        </section>

        <section className="section seo-section" id="faq">
          <div className="section-heading">
            <span>Questions</span>
            <h2>Before you try ClipKaro</h2>
          </div>
          <div className="seo-faq-list">
            {page.faq.map((item) => (
              <details key={item.question}>
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="seo-final-cta">
          <h2>Start with one video. Judge the clips yourself.</h2>
          <p>The fastest proof is whether ClipKaro finds moments you would actually publish.</p>
          <Link href="/signup" className="primary-btn">Create your first clips <ArrowRight size={16}/></Link>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-inner" style={{ alignItems: "flex-start", gap: 20, flexWrap: "wrap" }}>
          <div><Logo light/><p>© 2026 ClipKaro AI. Create responsibly. Built for India.</p></div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12 }}>
            <TransitionLink href="/about">About</TransitionLink>
            <Link href="/contact">Contact</Link>
            {SEO_PAGES.slice(0, 4).map((item) => <Link key={item.slug} href={`/${item.slug}`}>{item.title}</Link>)}
            {LEGAL_LINKS.map(([label, href]) => <Link key={href} href={href}>{label}</Link>)}
          </div>
        </div>
      </footer>
    </div>
  );
}
