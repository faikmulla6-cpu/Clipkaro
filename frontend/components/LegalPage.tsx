import { Logo } from "@/components/Logo";
import { LEGAL_EFFECTIVE_DATE, LEGAL_LINKS, LEGAL_VERSION } from "@/lib/legal";
import Link from "next/link";
import { CSSProperties, ReactNode } from "react";

export function LegalPage({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return <div style={page}>
    <header style={header}>
      <Link href="/" aria-label="ClipKaro home"><Logo /></Link>
      <nav style={nav}>{LEGAL_LINKS.map(([label, href]) => <Link key={href} href={href} style={navLink}>{label}</Link>)}</nav>
    </header>
    <main style={paper}>
      <div style={eyebrow}>LEGAL · VERSION {LEGAL_VERSION}</div>
      <h1 style={h1}>{title}</h1>
      <p style={summaryStyle}>{summary}</p>
      <p style={effective}>Effective {LEGAL_EFFECTIVE_DATE} · Last updated {LEGAL_EFFECTIVE_DATE}</p>
      <div style={content}>{children}</div>
    </main>
    <footer style={footer}>
      <span>© 2026 ClipKaro AI</span>
      <span>These terms do not limit rights that cannot lawfully be waived.</span>
    </footer>
  </div>;
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return <section style={section}><h2 style={h2}>{title}</h2><div style={sectionBody}>{children}</div></section>;
}

export function LegalList({ items }: { items: ReactNode[] }) {
  return <ul style={list}>{items.map((item, index) => <li key={index} style={li}>{item}</li>)}</ul>;
}

const page: CSSProperties = { minHeight: "100vh", background: "#f4f5ef", color: "#18231d", padding: "0 20px 40px" };
const header: CSSProperties = { maxWidth: 1060, margin: "0 auto", padding: "24px 0", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, flexWrap: "wrap" };
const nav: CSSProperties = { display: "flex", gap: 14, flexWrap: "wrap", fontSize: 13 };
const navLink: CSSProperties = { color: "#345247", textDecoration: "none", fontWeight: 700 };
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
const footer: CSSProperties = { maxWidth: 860, margin: "24px auto 0", display: "flex", justifyContent: "space-between", gap: 14, flexWrap: "wrap", color: "#6b7971", fontSize: 12 };
