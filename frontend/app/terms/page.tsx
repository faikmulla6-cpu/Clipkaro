import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";
import Link from "next/link";

export default function TermsPage() {
  return <LegalPage title="Terms of Service" summary="The rules for using ClipKaro AI, including account eligibility, creator-content rights, AI limitations, paid plans, cancellation and dispute handling.">
    <LegalSection title="1. Agreement and operator">
      <p>These Terms govern your use of ClipKaro AI. By creating an account or continuing to use the service after accepting the current version, you agree to these Terms, the Privacy Notice, Refund Policy, Acceptable Use Policy and Copyright Policy.</p>
      <LegalOperatorCard />
    </LegalSection>

    <LegalSection title="2. Eligibility and accounts">
      <LegalList items={[
        <>You must be at least 18 years old and legally capable of entering this agreement.</>,
        <>Provide accurate account information and keep your sign-in credentials secure. You are responsible for activity performed through your account unless caused by a failure for which ClipKaro is legally responsible.</>,
        <>Do not share, sell or transfer an account in a way that defeats plan limits, security controls or applicable law.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="3. Your videos and other creator content">
      <p>You keep ownership of content you upload and outputs generated from it, subject to any rights belonging to third parties. You grant ClipKaro a limited, non-exclusive licence to host, copy, transcode, transcribe, analyse, modify and render that content only as reasonably necessary to provide, secure, troubleshoot and support the service.</p>
      <p>You may upload only content you own or are authorised to process. You are responsible for permissions relating to copyright, performers, music, trademarks, confidential information, publicity/privacy rights and any people appearing or speaking in the content.</p>
    </LegalSection>

    <LegalSection title="4. AI-generated suggestions are editorial assistance">
      <p>ClipKaro uses speech recognition, deterministic scoring and optional AI semantic ranking to identify candidate moments, titles and explanations. These are automated editorial suggestions, not promises of virality, platform performance, factual correctness or legal suitability. Review clips, captions, names, claims and timing before publishing them.</p>
    </LegalSection>

    <LegalSection title="5. Plans, usage and renewal">
      <LegalList items={[
        <>Free: no payment; usage limits reset according to the plan rules shown in the product.</>,
        <>Mini Pass: ₹59 one-time, 25 total source-processing Karo Minutes and up to 5 Short exports, valid for 30 days. It does not auto-renew.</>,
        <>Creator, Growth, Pro and Agency are monthly subscriptions. Unless cancelled or changed, the selected plan renews each month at the price shown at checkout.</>,
        <>Karo Minutes measure source-video minutes processed. Short-export allowances are separate: processing one source consumes Karo Minutes once, while editing or exporting candidates from that already-processed source does not consume those source minutes again.</>,
        <>Free source media uses the short retention window. Paid source media is kept for up to 30 days so remaining Short exports can still be used; Mini Pass source media never extends beyond the pass expiry.</>,
        <>Upgrades may apply immediately and Razorpay may prorate the active cycle. Downgrades and cancellation apply at the end of the current paid cycle unless the product clearly says otherwise.</>,
        <>You can schedule cancellation from Plans & billing. There is no ClipKaro cancellation fee, and paid access continues until the end of the already-paid cycle.</>,
      ]}/>
      <p>Prices are displayed in Indian rupees. ClipKaro does not add hidden product fees after the displayed checkout price. Applicable taxes, payment-provider treatment and invoice particulars are handled as required by law. See the <Link href="/refund-policy">Refund Policy</Link>.</p>
    </LegalSection>

    <LegalSection title="6. Payments">
      <p>Payments are processed through Razorpay or another provider identified at checkout. Payment credentials are handled by the payment provider; ClipKaro receives references and status needed to activate and manage your entitlement. A payment is not treated as successfully activating a plan until ClipKaro verifies the provider response.</p>
    </LegalSection>

    <LegalSection title="7. Acceptable use and copyright">
      <p>You must comply with the <Link href="/acceptable-use">Acceptable Use Policy</Link> and <Link href="/copyright">Copyright Policy</Link>. ClipKaro may remove content, restrict processing or suspend an account when reasonably necessary to address unlawful material, security abuse, infringement, payment fraud or serious/repeated policy violations.</p>
    </LegalSection>

    <LegalSection title="8. Service operation and changes">
      <p>We work to keep ClipKaro available, but AI providers, payment systems, networks, model downloads and video processing can fail or be delayed. We may change features, models or plan mechanics to maintain security, quality or viability. We will not retroactively take away already-earned rights contrary to applicable law, and material legal-policy changes may require renewed acceptance before future paid checkout.</p>
    </LegalSection>

    <LegalSection title="9. ClipKaro intellectual property">
      <p>ClipKaro&apos;s software, interface, brand, templates, documentation and service technology remain owned by the operator or its licensors. These Terms do not give you ownership of those materials. They also do not transfer ownership of your uploaded content to ClipKaro.</p>
    </LegalSection>

    <LegalSection title="10. Suspension and termination">
      <p>You may stop using ClipKaro at any time. Recurring billing must be cancelled through the product as described above. We may suspend or terminate access for material breach, unlawful use, fraud, attacks on the service, repeated infringement, non-payment or where required by law. Where practical and lawful, we will use proportionate measures and provide a way to raise a grievance.</p>
    </LegalSection>

    <LegalSection title="11. Disclaimers and liability">
      <p>ClipKaro is provided as a digital creator tool. To the maximum extent permitted by applicable law, we do not guarantee uninterrupted availability, that every AI suggestion is correct, or that an output will achieve a specific result. Nothing in these Terms excludes liability or consumer rights that cannot lawfully be excluded or limited.</p>
      <p>Where liability can lawfully be limited, ClipKaro will not be responsible for indirect or consequential losses caused by your publication decisions, unauthorised source content or third-party platform actions. Any monetary limitation is subject to mandatory consumer and other applicable law.</p>
    </LegalSection>

    <LegalSection title="12. Your responsibility for unauthorised content">
      <p>If your breach of these Terms—such as knowingly uploading content without required rights—causes a third-party claim against ClipKaro, you are responsible to the extent permitted by law for losses directly arising from that breach. This does not apply to losses caused by ClipKaro&apos;s own unlawful conduct or matters that cannot legally be shifted to you.</p>
    </LegalSection>

    <LegalSection title="13. Governing law and grievances">
      <p>These Terms are governed by the laws of India. Courts and legally competent consumer/dispute forums in India retain the jurisdiction given to them by law. Nothing here prevents an eligible consumer from using rights or forums available under applicable consumer law.</p>
      <p>For support or a grievance, use the customer-care or Grievance Officer details in the <Link href="/legal-notice">Legal Notice</Link>.</p>
    </LegalSection>
  </LegalPage>;
}
