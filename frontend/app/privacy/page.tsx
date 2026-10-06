import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";
import { TRUST_PROFILE } from "@/lib/legal";

export default function PrivacyPage() {
  return <LegalPage title="Privacy Notice" summary="How ClipKaro collects, uses, shares, protects and retains personal data when you create an account, upload your own videos, generate Shorts or pay for a plan.">
    <LegalSection title="1. Who is responsible for your data">
      <p>ClipKaro AI is the service described in this notice. The operator, privacy contact and consumer grievance particulars are published below. If paid-launch particulars are incomplete, ClipKaro keeps paid checkout disabled.</p>
      <LegalOperatorCard />
    </LegalSection>

    <LegalSection title="2. Personal data we process">
      <LegalList items={[
        <>Account data: name, email address, password hash, plan, account preferences and verification status.</>,
        <>Creator content: videos you upload, extracted audio, transcript text and timestamps, clip candidates, hooks/titles, captions, crop choices, brand-kit values and rendered exports.</>,
        <>Usage and recommendation-interaction data: Karo Minutes, exports, project/job status, plan usage, feature settings, operational audit events, which ranked clip suggestions were shown, previewed, opened in the editor, edited, exported or downloaded, and the ranking metadata needed to interpret those actions.</>,
        <>Billing records: plan, amount, Razorpay order/subscription/payment references, payment status and billing events. ClipKaro does not receive or store your complete card, UPI PIN or banking credentials.</>,
        <>Security/technical data: session identifiers, user-agent, request IDs, rate-limit/security events and logs needed to protect and operate the service.</>,
        <>Support and legal communications you choose to send us.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="3. Why we use it">
      <LegalList items={[
        <>Provide the service: authenticate you, process uploads, transcribe speech, find candidate moments, generate captions, render exports and keep your projects available.</>,
        <>Administer plans, quotas, subscription changes, payments, refunds and fraud prevention.</>,
        <>Secure ClipKaro, investigate abuse, prevent account takeover, scan uploads and recover failed jobs.</>,
        <>Respond to support, privacy, legal, copyright and consumer-grievance requests.</>,
        <>Measure reliability and improve ClipKaro&apos;s ranking quality using privacy-minimized recommendation signals such as suggestion rank, score components, language/category and whether a suggestion was previewed, selected, edited, exported or downloaded. Suggestions that were never shown are not treated as negative feedback.</>,
      ]}/>
      <p>ClipKaro&apos;s behavioural-learning export deliberately excludes transcript text, email, IP address and user-agent. The current learning strategy is offline analysis of ClipKaro ranking signals; production interactions do not automatically rewrite ranking weights in real time.</p>
      <p>We do not sell personal data or use recommendation-interaction records for third-party behavioural advertising.</p>
      <p>ClipKaro does not use your uploaded media, transcripts or generated Shorts to train ClipKaro-owned foundation models. Third-party AI providers process only the data needed for the requested feature under the provider account/configuration used by ClipKaro; their independent handling is governed by the applicable provider terms and data-processing commitments.</p>
    </LegalSection>

    <LegalSection title="4. AI processing and service providers">
      <p>ClipKaro&apos;s media worker performs file validation, audio extraction, orchestration and FFmpeg rendering. For speech transcription, the worker sends extracted audio (not the complete source-video file) to the configured speech-to-text provider: Groq is the normal primary route, Cloudflare is the normal fallback, and a controlled Hinglish/Roman-Hinglish cohort can use ElevenLabs with the legacy route as fallback. When semantic ranking is enabled, the worker sends compact candidate transcript excerpts, timing information and local editorial scores to Groq. The ranking flow does not send the raw uploaded video.</p>
      <p>Razorpay processes payment credentials and payment authorization. ClipKaro receives provider references and status needed to activate and manage your plan. Email infrastructure processes addresses and message content for verification, password-reset and service communications. Hosting/infrastructure providers process data needed to run the service.</p>
      <p>Providers may operate infrastructure outside India. Where cross-border processing occurs, ClipKaro will apply restrictions required by applicable Indian law and contractual/provider safeguards.</p>
    </LegalSection>

    <LegalSection title="5. Cookies and similar technologies">
      <p>ClipKaro currently uses essential cookies for signed-in sessions and CSRF protection. They are necessary for account security and are not advertising cookies. Recommendation-interaction events use authenticated first-party API calls and are not third-party advertising trackers. Razorpay Checkout may use its own cookies or storage when you open the payment interface, subject to Razorpay&apos;s policies.</p>
    </LegalSection>

    <LegalSection title="6. Retention and deletion">
      <p>{TRUST_PROFILE.mediaRetention}</p>
      <LegalList items={[
        <>Free-plan source media and rendered export files use ClipKaro&apos;s short retention window, currently 24 hours. Paid-plan source media is retained for up to 30 days so creators can return to processed projects to edit, export and re-export their created Shorts. Mini Pass creation access ends at 5/5 AI Shorts or after 30 days; using all 5 creation credits does not immediately remove source media that is still inside its original retention window. Rendered export files still use the short retention window and should be downloaded if you want to keep them. Processing or operational recovery can delay deletion briefly.</>,
        <>Project records, derived transcript text, clip suggestions, recommendation-interaction records, account settings, usage and billing records can remain after the source file expires so the account/project history and product-quality analysis continue to function.</>,
        <>Deleting a project removes its associated behavioural-learning generations/events through the application database relationship. Account deletion removes the user-linked learning ledger, subject only to records ClipKaro must lawfully retain for billing, fraud, security or disputes.</>,
        <>We retain billing, fraud, security, tax/accounting and legal records for the period reasonably required by law, dispute handling and legitimate operational needs.</>,
        <>You may request deletion of personal data that is no longer required, subject to records we must keep for legal, billing, security or dispute purposes.</>,
      ]}/>
      <p>{TRUST_PROFILE.deletionSummary}</p>
    </LegalSection>

    <LegalSection title="7. Security">
      <p>ClipKaro uses measures including password hashing, revocable server-side sessions, CSRF protection, rate limits, private malware scanning, an isolated media worker, container/resource limits, restricted service networks, access controls and HTTPS/CSP browser protections. No online system can promise zero risk.</p>
    </LegalSection>

    <LegalSection title="8. Your choices and privacy requests">
      <p>You may ask for information about your personal data, correction of inaccurate account data, deletion where applicable, or raise a privacy grievance using the privacy/grievance contact in the Legal Notice. We will apply rights and response obligations required by law as they become applicable. Your machine-readable privacy export includes the recommendation generations and behavioural events associated with your account. You can also delete individual projects from the product where that control is available.</p>
      <p>India&apos;s Digital Personal Data Protection framework is being brought into force in stages. ClipKaro designed this notice and its consent records to support transparent notice, data minimisation, security, access/correction/erasure and grievance handling as the applicable provisions take effect.</p>
    </LegalSection>

    <LegalSection title="9. Children">
      <p>ClipKaro is intended for adults. You must be at least 18 years old to create an account or purchase a plan. Do not submit personal data about a child unless you have lawful authority and the processing is permitted by applicable law.</p>
    </LegalSection>

    <LegalSection title="10. Changes and contact">
      <p>If we materially change how personal data is used, we will update this notice/version and may require renewed acceptance before future paid checkout. Contact the Privacy Contact or Grievance Officer shown above for questions. {TRUST_PROFILE.supportExpectation}</p>
    </LegalSection>
  </LegalPage>;
}
