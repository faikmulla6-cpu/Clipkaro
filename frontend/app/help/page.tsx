"use client";
import { CircleHelp, CreditCard, FileVideo, LifeBuoy, ShieldCheck, Upload } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/AppShell";

export default function HelpPage() {
  return <AppShell title="Help centre" subtitle="Quick answers for the workflows creators use most.">
    <div className="settings-grid">
      <section className="settings-card">
        <div className="settings-card-head"><Upload size={18}/><div><h3>Upload & processing</h3><p>Use a video you own, choose the language carefully, then keep the tab open while upload finishes.</p></div></div>
        <Link href="/upload" className="secondary-btn small">Open upload</Link>
      </section>
      <section className="settings-card">
        <div className="settings-card-head"><FileVideo size={18}/><div><h3>Projects & exports</h3><p>Open a project to review AI moments, edit captions, choose a style and render the final Short.</p></div></div>
        <Link href="/projects" className="secondary-btn small">Open projects</Link>
      </section>
      <section className="settings-card">
        <div className="settings-card-head"><CreditCard size={18}/><div><h3>Plans & billing</h3><p>See current limits, one-time Mini Pass access and recurring plan controls in one place.</p></div></div>
        <Link href="/pricing" className="secondary-btn small">Plans & billing</Link>
      </section>
      <section className="settings-card">
        <div className="settings-card-head"><ShieldCheck size={18}/><div><h3>Privacy, refunds & support</h3><p>Review ClipKaro's current policies and the public support/grievance contacts configured for launch.</p></div></div>
        <Link href="/legal-notice" className="secondary-btn small">Legal & support</Link>
      </section>
    </div>
    <div className="calendar-note"><LifeBuoy/><div><b>Something still not working?</b><p>Use the customer-care details on the Legal Notice once they are configured for the public launch.</p></div></div>
  </AppShell>;
}
