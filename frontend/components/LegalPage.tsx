import { PublicSiteFooter } from "@/components/PublicSiteFooter";
import { PublicSiteNav } from "@/components/PublicSiteNav";
import { LEGAL_EFFECTIVE_DATE, LEGAL_VERSION } from "@/lib/legal";
import { CSSProperties, ReactNode } from "react";

export function LegalPage({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return <div style={page}>
    <PublicSiteNav />
    <main style={mainWrap}>
      <article style={paper}>
        <div style={eyebrow}>LEGAL · VERSION {LEGAL_VERSION}</div>
        <h1 style={h1}>{title}</h1>
        <p style={summaryStyle}>{summary}</p>
        <p style={effective}>Effective {LEGAL_EFFECTIVE_DATE} · Last updated {LEGAL_EFFECTIVE_DATE}</p>
        <div style={content}>{children}</div>
      </article>
    </main>
    <PublicSiteFooter />
  </div>;
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return <section style={section}><h2 style={h2}>{title}</h2><div style={sectionBody}>{children}</div></section>;
}

export function LegalList({ items }: { items: ReactNode[] }) {
  return <ul style={list}>{items.map((item, index) => <li key={index} style={li}>{item}</li>)}</ul>;
}

const page: CSSProperties = { minHeight: "100vh", background: "#f7f9f4", color: "#18231d" };
const mainWrap: CSSProperties = { padding: "48px 20px 72px" };
const paper: CSSProperties = { maxWidth: 860, margin: "0 auto", background: "#fff", border: "1px solid #e2e5de", borderRadius: 24, padding: "clamp(28px,5vw,64px)", boxShadow: "0 20px 60px rgba(30,50,40,.07)" };
const eyebrow: CSSProperties = { color: "#527565", fontWeight: 800, fontSize: 12, letterSpacing: ".12em", marginBottom: 14 };
const h1: CSSProperties = { fontSize: "clamp(34px,6vw,58px)", lineHeight: 1.03, letterSpacing: "-.04em", margin: "0 0 18px" };
const summaryStyle: CSSProperties = { fontSize: 18, lineHeight: 1.65, color: "#415048", margin: 0, maxWidth: 720 };
const effective: CSSProperties = { marginTop: 18, color: "#718078", fontSize: 13 };
const content: CSSProperties = { marginTop: 44 };
const section: CSSProperties = { padding: "26px 0", borderTop: "1px solid #edf0ea" };
const h2: CSSProperties = { margin: "0 0 12px", fontSize: 23, letterSpacing: "-.02em" };
const sectionBody: CSSProperties = { fontSize: 15.5, lineHeight: 1.75, color: "#35443c" };
const list: CSSProperties = { paddingLeft: 22, margin: "10px 0" };
const li: CSSProperties = { margin: "7px 0" };
