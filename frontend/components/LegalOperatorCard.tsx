"use client";

import { api } from "@/lib/api";
import { LegalConfig } from "@/lib/legal";
import { CSSProperties, useEffect, useState } from "react";

export function LegalOperatorCard() {
  const [config, setConfig] = useState<LegalConfig | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api<LegalConfig>("/legal/config").then(setConfig).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return <div style={warning}>Operator details could not be loaded. Paid checkout should not be used until this page loads correctly.</div>;
  }
  if (!config) return <div style={muted}>Loading operator details…</div>;
  if (!config.paid_launch_ready) {
    return <div style={warning}>
      <b>Paid launch is not legally configured yet.</b><br/>
      ClipKaro keeps paid checkout disabled until the operator identity, customer-care and grievance particulars are configured on the production server.
    </div>;
  }

  return <div style={card}>
    <div><span style={label}>Operator</span><b>{config.operator_name}</b></div>
    <div><span style={label}>Principal address</span><span>{config.operator_address}</span></div>
    <div><span style={label}>Customer care</span><span><a href={`mailto:${config.customer_care_email}`}>{config.customer_care_email}</a>{config.customer_care_phone ? ` · ${config.customer_care_phone}` : ""}</span></div>
    <div><span style={label}>Privacy contact</span><a href={`mailto:${config.privacy_email}`}>{config.privacy_email}</a></div>
    <div><span style={label}>Grievance Officer</span><span>{config.grievance_officer_name} · <a href={`mailto:${config.grievance_email}`}>{config.grievance_email}</a>{config.grievance_phone ? ` · ${config.grievance_phone}` : ""}</span></div>
    {config.gstin && <div><span style={label}>GSTIN</span><span>{config.gstin}</span></div>}
    {config.pan && <div><span style={label}>PAN</span><span>{config.pan}</span></div>}
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
const warning: CSSProperties = { padding: 18, border: "1px solid #e6a23c", borderRadius: 14, background: "#fff8e8", color: "#5d430f", lineHeight: 1.55 };
const muted: CSSProperties = { padding: 16, color: "#66736d" };
