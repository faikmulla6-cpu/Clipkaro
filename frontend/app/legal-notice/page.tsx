import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";
import { TRUST_PROFILE } from "@/lib/legal";
import Link from "next/link";

export default function LegalNoticePage() {
  return <LegalPage title="Legal Notice & Consumer Information" summary="Public operator, customer-care and grievance information plus the key billing disclosures ClipKaro publishes before accepting paid users.">
    <LegalSection title="1. Service provider particulars">
      <LegalOperatorCard />
      <p>ClipKaro AI is built by {TRUST_PROFILE.founderName}, {TRUST_PROFILE.founderTitle}. Production paid checkout remains disabled until the required operator identity, principal address, customer-care and grievance details contain real deployment values.</p>
    </LegalSection>

    <LegalSection title="2. Digital service and prices">
      <p>ClipKaro AI is a digital video-processing service. Plan prices are shown in Indian rupees before checkout. The amount sent to Razorpay matches the selected plan price configured in ClipKaro. There are no undisclosed ClipKaro product fees added after the displayed checkout price. Taxes and invoice particulars are handled as applicable.</p>
      <LegalList items={[
        <>Mini Pass: ₹59 one-time, 25 Karo Minutes, 5 Shorts, valid 30 days, no automatic renewal.</>,
        <>Creator: ₹199 per month, 60 Karo Minutes and 15 Shorts per billing period.</>,
        <>Growth: ₹399 per month, 180 Karo Minutes and 50 Shorts per billing period.</>,
        <>Pro: ₹799 per month, 480 Karo Minutes and 150 Shorts per billing period.</>,
        <>Agency: ₹1,999 per month, 1,500 Karo Minutes and 500 Shorts per billing period.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="3. Subscription renewal and cancellation">
      <p>Creator, Growth, Pro and Agency are recurring monthly subscriptions and renew until cancelled or changed. Cancellation can be scheduled from Plans & billing without a ClipKaro cancellation fee. Paid access normally remains available through the already-paid billing cycle. Mini Pass is not a subscription.</p>
      <p>See the <Link href="/refund-policy">Refund & Cancellation Policy</Link> before purchase.</p>
    </LegalSection>

    <LegalSection title="4. Payment processing">
      <p>Razorpay currently provides ClipKaro checkout/payment processing. Razorpay receives the payment credentials needed to authorise your transaction. ClipKaro receives payment/order/subscription references and status needed to activate and manage service access. Never send card credentials, UPI PINs, OTPs or banking passwords to ClipKaro support.</p>
    </LegalSection>

    <LegalSection title="5. Grievance handling">
      <p>Customer-care and grievance channels are displayed above. {TRUST_PROFILE.supportExpectation} Privacy and copyright complaints may use the dedicated contacts/policies linked on this site.</p>
    </LegalSection>

    <LegalSection title="6. Media retention and deletion">
      <p>{TRUST_PROFILE.mediaRetention}</p>
      <p>{TRUST_PROFILE.deletionSummary}</p>
    </LegalSection>

    <LegalSection title="7. Important policy links">
      <LegalList items={[
        <><Link href="/terms">Terms of Service</Link> — account, creator-content and paid-service terms.</>,
        <><Link href="/privacy">Privacy Notice</Link> — personal-data collection, AI processing, sharing and retention.</>,
        <><Link href="/refund-policy">Refund & Cancellation Policy</Link> — refunds, renewal and cancellation.</>,
        <><Link href="/acceptable-use">Acceptable Use Policy</Link> — prohibited content and abuse.</>,
        <><Link href="/copyright">Copyright & Rights Policy</Link> — rights ownership and complaint process.</>,
      ]}/>
    </LegalSection>
  </LegalPage>;
}
