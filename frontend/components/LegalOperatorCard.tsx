"use client";

import { api } from "@/lib/api";
import { LegalConfig, TRUST_PROFILE } from "@/lib/legal";
import { CSSProperties, useEffect, useState } from "react";

export function LegalOperatorCard() {
  const [config, setConfig] = useState<LegalConfig | null>(null);
  const [failed, setFailed] = useState(false);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let active = true;
    const slowTimer = window.setTimeout(() => {
      if (active) setSlow(true);
    }, 4_000);

    api<LegalConfig>("/legal/config").then((result) => {
      if (!active) return;
      setConfig(result);
      setFailed(false);
      setSlow(false);
    }).catch(() => {
      if (active) setFailed(true);
    }).finally(() => window.clearTimeout(slowTimer));

    return () => {
      active = false;
      window.clearTimeout(slowTimer);
    };
  }, []);

  if ((failed || slow) && !config) return <FallbackOperatorCard failed={failed} />;
  if (!config) return <div style={muted}>Loading public operator and support details…</div>;

  return <div style={card}>
    {config.paid_launch_ready ? <div style={noticeInline}>
      <b>Production paid checkout is enabled.</b><br/>
      Operator identity, principal address, customer-care and grievance particulars are configured for the live service.
    </div> : <div style={warningInline}>
      <b>Paid launch details are incomplete.</b><br/>
      Checkout remains disabled until operator identity, customer-care and grievance particulars are configured on the production server.
    </div>}
    <div><span style={label}>Service</span><b>{config.service_name || "ClipKaro AI"}</b></div>
    {config.operator_name && <div><span style={label}>Operator</span><b>{config.operator_name}</b></div>}
    {config.operator_address && <div><span style={label}>Principal address</span><span>{config.operator_address}</span></div>}
    <div><span style={label}>Customer care</span><span>{config.customer_care_email ? <a href={`mailto:${config.customer_care_email}`}>{config.customer_care_email}</a> : "Customer-care email not configured"}{config.customer_care_phone ? ` · ${config.customer_care_phone}` : ""}</span></div>
    <div><span style={label}>Privacy contact</span>{config.privacy_email ? <a href={`mailto:${config.privacy_email}`}>{config.privacy_email}</a> : <span>Privacy email not configured</span>}</div>
    <div><span style={label}>Grievance Officer</span><span>{config.grievance_officer_name || "Not configured"}{config.grievance_email ? <> · <a href={`mailto:${config.grievance_email}`}>{config.grievance_email}</a></> : " · grievance email not configured"}{config.grievance_phone ? ` · ${config.grievance_phone}` : ""}</span></div>
    {config.gstin && <div><span style={label}>GSTIN</span><span>{config.gstin}</span></div>}
    {config.pan && <div><span style={label}>PAN</span><span>{config.pan}</span></div>}
  </div>;
}

function FallbackOperatorCard({ failed }: { failed: boolean }) {
  return <div style={card}>
    <div style={failed ? warningInline : noticeInline}>
      <b>{failed ? "Official operator details are temporarily unavailable." : "Official operator details are taking longer than expected."}</b><br/>
      Public support channels are shown below. Live checkout eligibility is enforced server-side using the configured production legal particulars.
    </div>
    <div><span style={label}>Service</span><b>{TRUST_PROFILE.serviceName}</b></div>
    <div><span style={label}>Built by</span><b>{TRUST_PROFILE.founderName}, {TRUST_PROFILE.founderTitle}</b></div>
    <div><span style={label}>Website</span><a href={TRUST_PROFILE.website}>{TRUST_PROFILE.website}</a></div>
    <div><span style={label}>Customer care</span><a href={`mailto:${TRUST_PROFILE.supportEmail}`}>{TRUST_PROFILE.supportEmail}</a></div>
    <div><span style={label}>Privacy contact</span><a href={`mailto:${TRUST_PROFILE.privacyEmail}`}>{TRUST_PROFILE.privacyEmail}</a></div>
    <div><span style={label}>Legal notices</span><a href={`mailto:${TRUST_PROFILE.legalEmail}`}>{TRUST_PROFILE.legalEmail}</a></div>
    <div><span style={label}>Grievance email</span><a href={`mailto:${TRUST_PROFILE.grievanceEmail}`}>{TRUST_PROFILE.grievanceEmail}</a></div>
    <div><span style={label}>Response expectation</span><span>{TRUST_PROFILE.supportExpectation}</span></div>
    <div><span style={label}>Media deletion and retention</span><span>{TRUST_PROFILE.mediaRetention} {TRUST_PROFILE.deletionSummary}</span></div>
  </div>;
}

const card: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 20,
  border: "1px solid #d9dfd7",
  borderRadius: 16,
  background: "#f7faf6",
  color: "#1f2b25",
};
const label: CSSProperties = { display: "block", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em", color: "#5f6f66", marginBottom: 3 };
const warningInline: CSSProperties = { padding: 14, border: "1px solid #e6a23c", borderRadius: 12, background: "#fff8e8", color: "#5d430f", lineHeight: 1.55 };
const noticeInline: CSSProperties = { padding: 14, border: "1px solid #b9d5c7", borderRadius: 12, background: "#effaf3", color: "#1e5d3e", lineHeight: 1.55 };
const muted: CSSProperties = { padding: 16, color: "#66736d" };
