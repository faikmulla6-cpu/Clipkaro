import { LegalList, LegalPage, LegalSection } from "@/components/LegalPage";
import { LegalOperatorCard } from "@/components/LegalOperatorCard";

export default function CopyrightPage() {
  return <LegalPage title="Copyright & Rights Policy" summary="ClipKaro processes creator uploads privately by default, but users must have the rights required to upload and edit them. This page explains how to report infringement or respond to a complaint.">
    <LegalSection title="1. Your responsibility">
      <p>You may upload and process only material you own or are authorised to use. That includes the underlying video, music, artwork, logos, performances, recordings and other protected elements. ClipKaro&apos;s ability to technically process a file is not a licence to use third-party material.</p>
    </LegalSection>

    <LegalSection title="2. ClipKaro does not claim ownership of creator uploads">
      <p>Creators retain ownership of their uploaded content and outputs subject to third-party rights. ClipKaro receives only the limited processing licence described in the Terms of Service. Source uploads are not made publicly searchable by ClipKaro merely because they are uploaded for processing.</p>
    </LegalSection>

    <LegalSection title="3. Reporting alleged infringement">
      <p>If you believe content processed or made available through ClipKaro infringes your copyright or another intellectual-property right, send a clear notice to the legal/grievance contact below.</p>
      <LegalList items={[
        <>Identify the copyrighted/protected work or right you believe is infringed.</>,
        <>Identify the ClipKaro material sufficiently for us to locate it—for example a project/export identifier, account information you lawfully possess, or the relevant ClipKaro URL.</>,
        <>Provide your name, organisation (if any), email and a reliable way to contact you.</>,
        <>Explain why you believe the complained-of use is not authorised by the owner, an agent or applicable law.</>,
        <>State that the information in the notice is accurate and that you are the rights holder or authorised to act for the rights holder.</>,
        <>Provide your physical or electronic signature/name.</>,
      ]}/>
      <LegalOperatorCard />
    </LegalSection>

    <LegalSection title="4. What ClipKaro may do">
      <p>We may request more information, preserve relevant records, restrict access to stored material, suspend processing or remove content while a credible complaint is reviewed. We may notify the affected user where appropriate and lawful. Repeated or serious infringement can result in account restrictions or termination.</p>
    </LegalSection>

    <LegalSection title="5. Responding to a complaint">
      <p>If you believe material was restricted because of a mistake, contact the same legal/grievance channel with the project/export information, your contact details, the basis on which you have the necessary rights or legal permission, and any supporting evidence. We may restore access when the dispute is resolved or the available information shows restriction is no longer appropriate.</p>
    </LegalSection>

    <LegalSection title="6. False or abusive notices">
      <p>Do not knowingly submit false ownership claims, forged evidence or rights complaints intended to harass another creator. ClipKaro may reject abusive notices and take action against accounts misusing the complaint process.</p>
    </LegalSection>

    <LegalSection title="7. Applicable law">
      <p>This policy is intended to support complaints under the Copyright Act, 1957 and other applicable intellectual-property laws. It is not a substitute for a court or other competent authority, and ClipKaro may comply with valid legal orders.</p>
    </LegalSection>
  </LegalPage>;
}
