"use client";

import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";
import { AccountSettings, api, patchJSON, postJSON } from "@/lib/api";
import { AlertCircle, Check, Download, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

const TIMEZONES = [
  ["Asia/Kolkata", "India Standard Time"],
  ["UTC", "UTC"],
  ["Asia/Dubai", "Dubai"],
  ["Asia/Singapore", "Singapore"],
  ["Europe/London", "London"],
  ["America/New_York", "New York"],
  ["America/Los_Angeles", "Los Angeles"],
] as const;

export default function Account() {
  const { refresh } = useAuth();
  const [settings, setSettings] = useState<AccountSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [privacyBusy, setPrivacyBusy] = useState("");
  const [privacyNotice, setPrivacyNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<AccountSettings>("/settings")
      .then(setSettings)
      .catch((err) => setError(err instanceof Error ? err.message : "Settings could not be loaded."));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || !settings) return;

    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") || "").trim();
    if (name.length < 2) {
      setError("Enter a name with at least 2 characters.");
      return;
    }

    const payload = {
      name,
      default_language: String(data.get("default_language") || "auto"),
      timezone: String(data.get("timezone") || "Asia/Kolkata"),
      creator_category: String(data.get("creator_category") || "auto"),
    };

    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const updated = await patchJSON<AccountSettings>("/settings", payload);
      setSettings(updated);
      await refresh();
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Settings could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function downloadPrivacyExport() {
    setPrivacyBusy("export");
    setPrivacyNotice("");
    setError("");
    try {
      const payload = await api<Record<string, unknown>>("/privacy/export");
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `clipkaro-personal-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setPrivacyNotice("Your machine-readable personal-data export was downloaded to this device.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not prepare your privacy export.");
    } finally {
      setPrivacyBusy("");
    }
  }

  async function requestDeletion() {
    const confirmed = window.confirm("Record an account deletion request? If you have a recurring subscription, cancel it in Plans & billing so future renewals are stopped before account closure.");
    if (!confirmed) return;
    setPrivacyBusy("deletion");
    setPrivacyNotice("");
    setError("");
    try {
      const result = await postJSON<{ message: string; requires_billing_action: boolean }>("/privacy/requests", {
        kind: "deletion",
        details: "Account deletion requested from Settings.",
      });
      setPrivacyNotice(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the deletion request.");
    } finally {
      setPrivacyBusy("");
    }
  }

  if (!settings) {
    return (
      <AppShell title="Settings" subtitle="Manage your profile and creator defaults.">
        <div className="screen-loader inline">
          <Loader2 className="spin" size={24} />
          <p>{error || "Loading your settings…"}</p>
        </div>
      </AppShell>
    );
  }

  const timezoneOptions = TIMEZONES.some(([value]) => value === settings.timezone)
    ? TIMEZONES
    : ([[settings.timezone, settings.timezone], ...TIMEZONES] as readonly (readonly [string, string])[]);

  return (
    <AppShell
      title="Settings"
      subtitle="Manage your profile, creator defaults and privacy requests."
    >
      <div className="account-settings">
        <form className="settings-panel" onSubmit={submit} key={`${settings.name}:${settings.default_language}:${settings.timezone}:${settings.creator_category}`}>
          <div className="panel-head">
            <div>
              <h3>Profile & creator defaults</h3>
              <p className="panel-subtitle">Every editable field below is saved to your account.</p>
            </div>
            {saved && (
              <span className="ready-pill" role="status">
                <Check size={11} /> Saved
              </span>
            )}
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="account-name">Full name</label>
              <input id="account-name" name="name" defaultValue={settings.name} autoComplete="name" maxLength={60} required />
            </div>
            <div className="field">
              <label htmlFor="account-email">Email address</label>
              <input id="account-email" value={settings.email} type="email" autoComplete="email" disabled aria-describedby="account-email-help" />
              <small id="account-email-help" className="field-help">Your sign-in email is read-only for now. Use the privacy/grievance channel for an email correction request.</small>
            </div>
          </div>

          <div className="form-row">
            <div className="field">
              <label htmlFor="default-language">Default language</label>
              <select id="default-language" name="default_language" defaultValue={settings.default_language}>
                <option value="auto">Auto detect</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option><option value="en">English</option><option value="mr">Marathi</option>
              </select>
              <small className="field-help">Preselected when you start a new upload.</small>
            </div>
            <div className="field">
              <label htmlFor="timezone">Timezone</label>
              <select id="timezone" name="timezone" defaultValue={settings.timezone}>
                {timezoneOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
              <small className="field-help">Stored as an IANA timezone for schedules and local timestamps.</small>
            </div>
          </div>

          <div className="field">
            <label htmlFor="creator-category">Default content type</label>
            <select id="creator-category" name="creator_category" defaultValue={settings.creator_category}>
              <option value="auto">Let AI decide</option><option value="education">Education</option><option value="podcast">Podcast</option><option value="business">Business</option><option value="motivation">Motivation</option><option value="spiritual">Spiritual</option><option value="local-business">Local business</option>
            </select>
            <small className="field-help">Preselected for new projects; you can still change it per upload.</small>
          </div>

          <div className="privacy-card">
            <ShieldCheck />
            <div>
              <b>Private by default</b>
              <p>Source videos and exports expire automatically. Derived project/transcript records can remain as explained in the <Link href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Notice</Link>. Other creators cannot access your project IDs, media, clips, or downloads.</p>
            </div>
          </div>

          {error && <div className="error-banner settings-error" role="alert"><AlertCircle size={18}/><span>{error}</span></div>}
          {privacyNotice && <div className="success-banner" role="status"><span>{privacyNotice}</span></div>}

          <div className="settings-actions">
            <button className="primary-btn" type="submit" disabled={saving}>
              {saving ? <Loader2 className="spin" size={16}/> : <Check size={16}/>} {saving ? "Saving settings…" : "Save settings"}
            </button>
          </div>
        </form>

        <div className="settings-panel" style={{ marginTop: 20 }}>
          <div className="panel-head"><div><h3>Privacy controls</h3><p className="panel-subtitle">Access your data or record a privacy-rights request without emailing support first.</p></div></div>
          <div className="privacy-card">
            <Download />
            <div><b>Download my personal data</b><p>Creates a JSON export of your account, project/transcript metadata, usage, billing references and legal/privacy records. Password hashes, server file paths and secrets are excluded.</p></div>
            <button type="button" className="secondary-btn" disabled={!!privacyBusy} onClick={downloadPrivacyExport}>{privacyBusy === "export" ? <Loader2 className="spin" size={14}/> : <Download size={14}/>} Download data</button>
          </div>
          <div className="privacy-card" style={{ marginTop: 14 }}>
            <Trash2 />
            <div><b>Request account deletion</b><p>Records a deletion request for review of billing, legal and security retention obligations. If a recurring plan is active, first schedule cancellation in <Link href="/pricing">Plans & billing</Link> so account closure cannot leave future renewals behind.</p></div>
            <button type="button" className="secondary-btn" disabled={!!privacyBusy} onClick={requestDeletion}>{privacyBusy === "deletion" ? <Loader2 className="spin" size={14}/> : <Trash2 size={14}/>} Request deletion</button>
          </div>
          <p className="field-help" style={{ marginTop: 14 }}>For correction, access questions or a grievance, use the privacy and Grievance Officer details in the <Link href="/legal-notice" target="_blank" rel="noopener noreferrer">Legal Notice</Link>.</p>
        </div>
      </div>
    </AppShell>
  );
}
