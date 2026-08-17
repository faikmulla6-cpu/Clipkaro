import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";

export default function RefundPolicyPage() {
  return <LegalPage title="Refund & Cancellation Policy" summary="How ClipKaro handles Mini Pass purchases, monthly subscriptions, cancellation, duplicate charges, failed entitlements and refund requests.">
    <LegalSection title="1. Customer care">
      <p>Refund and billing requests are handled through ClipKaro customer care. Consumer grievances may also be escalated to the Grievance Officer.</p>
      <LegalOperatorCard />
    </LegalSection>

    <LegalSection title="2. Mini Pass">
      <LegalList items={[
        <>Mini Pass costs ₹59 as a one-time purchase. It is valid for 30 days and never auto-renews.</>,
        <>A Mini Pass is generally eligible for a voluntary refund when requested within 7 days of purchase and no Karo Minutes have been processed and no paid Short has been exported from that pass.</>,
        <>Once processing or export entitlement has been consumed, the digital service has begun and the purchase is ordinarily non-refundable, except where applicable law requires otherwise or ClipKaro confirms a billing/service failure.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="3. Monthly subscriptions">
      <LegalList items={[
        <>Creator, Growth, Pro and Agency renew monthly until you cancel or change the subscription.</>,
        <>You can schedule cancellation from Plans & billing. There is no ClipKaro cancellation fee. Your existing paid access continues until the end of the current billing cycle.</>,
        <>Cancelling normally stops the next renewal; it does not automatically refund an already-started billing cycle.</>,
        <>A first subscription charge or unintended renewal may be reviewed for a voluntary refund if you contact us within 7 days and no Karo Minutes or paid exports were used in that charged period.</>,
        <>Upgrades can be charged on a prorated basis by Razorpay. Downgrades normally take effect at the next billing cycle.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="4. Billing and service failures">
      <p>We will investigate duplicate charges, a payment that succeeded but did not produce the purchased entitlement, an incorrect amount, provider-confirmed payment failure, or a material ClipKaro service failure that prevented delivery of the paid digital service. Depending on the facts, we may restore the entitlement, correct the charge or issue a full/partial refund.</p>
    </LegalSection>

    <LegalSection title="5. Cases normally not refundable">
      <LegalList items={[
        <>Karo Minutes or paid exports already consumed, except where a proven ClipKaro failure caused the consumption without delivering the service.</>,
        <>A change of mind after meaningful use of the digital service.</>,
        <>Loss caused by a third-party social platform rejecting, limiting or removing an exported Short.</>,
        <>Accounts suspended for serious fraud, security abuse, illegal content or repeated policy violations, subject to non-waivable legal rights.</>,
        <>Payment-provider or bank delays where ClipKaro has not actually received a settled charge.</>,
      ]}/>
    </LegalSection>

    <LegalSection title="6. How to request a refund">
      <p>Contact customer care using the details above and include the account email, plan, approximate payment date, Razorpay/payment reference if available, and a short explanation. Never send your card number, UPI PIN, OTP or banking password.</p>
      <p>ClipKaro aims to acknowledge consumer grievances within 48 hours and to resolve them within one month, subject to the information required to investigate and any payment-provider/bank processing time.</p>
    </LegalSection>

    <LegalSection title="7. Refund method and timing">
      <p>Approved refunds are returned through the original payment route where reasonably possible. Once ClipKaro initiates a refund, final credit timing is controlled by Razorpay, your bank, card network or UPI provider and can take additional business days.</p>
    </LegalSection>

    <LegalSection title="8. Mandatory rights">
      <p>This policy is a voluntary commercial policy in addition to rights available under applicable Indian consumer and payment law. Nothing here removes a refund, reversal, charge-dispute or other remedy that the law requires in your circumstances.</p>
    </LegalSection>
  </LegalPage>;
}
