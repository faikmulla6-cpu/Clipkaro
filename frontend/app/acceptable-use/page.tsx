import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import Link from "next/link";

export default function AcceptableUsePage() {
  return <LegalPage title="Acceptable Use Policy" summary="ClipKaro is built for creators processing content they own or are authorised to use. This policy defines the uses that are not allowed.">
    <LegalSection title="1. Rights-safe use">
      <p>Upload only videos, audio, logos, images and other material you own or have permission to process. Follow the <Link href="/copyright">Copyright Policy</Link> and respect privacy, publicity, confidentiality and contractual rights.</p>
    </LegalSection>

    <LegalSection title="2. Prohibited content and conduct">
      <LegalList items={[
        <>Child sexual abuse material, sexual content involving minors, grooming, or any exploitation of children.</>,
        <>Non-consensual intimate imagery, sexual extortion, voyeuristic material or content used to sexually abuse or humiliate a person.</>,
        <>Content or workflows designed for fraud, phishing, impersonation, forged evidence, deceptive financial schemes or identity theft.</>,
        <>Threats, targeted harassment, doxxing, unlawful hate content, incitement to violence, or terrorist/extremist operational material prohibited by law.</>,
        <>Malware, malicious payloads, attempts to exploit parsers or infrastructure, denial-of-service activity, credential attacks or deliberate evasion of upload/security scanning.</>,
        <>Material that unlawfully infringes copyright, trademark, privacy, publicity, trade-secret or other rights.</>,
        <>Attempts to bypass Karo Minutes, export limits, billing restrictions, authentication, rate limits, worker isolation or other technical controls.</>,
        <>Automated scraping, resale, account sharing or bulk access that materially interferes with the service or is not authorised by ClipKaro.</>,
        <>Using generated clips in a way that violates applicable law or the rules of the platform where you publish them.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="3. Synthetic or edited media">
      <p>Editing, satire, commentary and creator transformations are not automatically prohibited. However, do not use ClipKaro to create or distribute deceptive impersonation, fraudulent evidence, non-consensual intimate material or other unlawful synthetic media. Where a platform or law requires disclosure that media is altered or AI-assisted, you are responsible for making that disclosure.</p>
    </LegalSection>

    <LegalSection title="4. Enforcement">
      <p>ClipKaro may reject an upload, remove stored material, restrict processing, suspend an account or preserve/report information where reasonably necessary to protect users, comply with law, address a valid rights complaint or stop serious abuse. Measures should be proportionate to the risk and may be immediate where delay would create harm or security risk.</p>
    </LegalSection>

    <LegalSection title="5. Reporting and review">
      <p>Report suspected abuse through the customer-care or Grievance Officer details in the <Link href="/legal-notice">Legal Notice</Link>. If your account or content is restricted and you believe the decision is incorrect, you may use the same channel to request review.</p>
    </LegalSection>
  </LegalPage>;
}
