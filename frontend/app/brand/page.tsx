"use client";
import { Check, Palette, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { useAuth } from "@/components/AuthProvider";
import { api, deleteJSON, postJSON } from "@/lib/api";

type Kit = {
  id: string;
  name: string;
  primary_color: string;
  accent_color: string;
  font_family: string;
  logo_text?: string | null;
  caption_preset: string;
  is_default: boolean;
};

const BRAND_KIT_PLANS = new Set(["creator", "growth", "pro", "agency"]);

export default function Brand() {
  const { user } = useAuth();
  const [kits, setKits] = useState<Kit[]>([]);
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const canUseBrandKit = BRAND_KIT_PLANS.has(String(user?.plan || "free").toLowerCase());

  const load = async () => {
    const result = await api<Kit[]>("/brand-kits");
    setKits(Array.isArray(result) ? result : []);
  };
  useEffect(() => { void load().catch((err) => setError(err instanceof Error ? err.message : "Could not load brand kits.")); }, []);

  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canUseBrandKit) {
      setError("Brand Kit is available on Creator, Growth, Pro and Agency plans.");
      return;
    }
    setError("");
    const d = new FormData(e.currentTarget);
    try {
      await postJSON("/brand-kits", {
        name: d.get("name"),
        primary_color: d.get("primary"),
        accent_color: "#165F43",
        font_family: "Inter",
        logo_text: d.get("logo"),
        caption_preset: d.get("preset"),
        is_default: kits.length === 0,
      });
      setShow(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create brand kit");
    }
  }

  async function remove(kit: Kit) {
    if (!window.confirm(`Delete “${kit.name}”? This does not change already-rendered videos.`)) return;
    setBusy(kit.id);
    setError("");
    try {
      await deleteJSON(`/brand-kits/${kit.id}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete brand kit.");
    } finally {
      setBusy("");
    }
  }

  return <AppShell title="Brand kit" subtitle="Make every export recognisably yours." action={<button className="primary-btn small" disabled={!canUseBrandKit} title={canUseBrandKit ? "Create a new brand kit" : "Available on Creator, Growth, Pro and Agency plans"} onClick={() => canUseBrandKit && setShow(!show)}><Plus size={14}/>New kit</button>}>
    <div className="brand-hero"><div><span className="eyebrow"><Palette size={12}/> BRAND CONSISTENCY</span><h2>Set it once. Stay recognisable everywhere.</h2><p>Save your wordmark, brand color and caption personality, then apply the kit directly in Creator Studio.</p></div><div className="brand-preview"><div className="brand-video"><span className="brand-wordmark">YOUR BRAND</span><div className="brand-caption">MAKE EVERY<br/><em>SECOND COUNT</em></div></div></div></div>
    {!canUseBrandKit && <div className="billing-manage"><div><b>Brand Kit starts on Creator</b><span>Your current plan can preview the feature. Creating reusable wordmarks, brand colors and caption presets is available on Creator, Growth, Pro and Agency.</span></div><Link href="/pricing" className="secondary-btn">View eligible plans</Link></div>}
    {show && canUseBrandKit && <form className="brand-form" onSubmit={create}><div className="field"><label>Kit name</label><input name="name" placeholder="My creator brand" required/></div><div className="field"><label>Wordmark</label><input name="logo" placeholder="FAIK CREATES" maxLength={40}/></div><div className="field"><label>Primary color</label><input name="primary" type="color" defaultValue="#DFFF57"/></div><div className="field"><label>Caption personality</label><select name="preset" defaultValue="kinetic"><option value="kinetic">Kinetic</option><option value="clean">Clean</option><option value="bold">Bold</option><option value="minimal">Minimal</option><option value="hindi-pop">India Pop</option></select></div><button className="primary-btn">Save brand kit</button></form>}
    {error && <div className="error-banner"><span>{error}</span></div>}
    <div className="section-line"><h3>Your brand kits</h3></div>
    {kits.length ? <div className="brand-grid">{kits.map(k => <article className="brand-card" key={k.id}><div className="brand-colors"><span style={{background:k.primary_color}}/><span style={{background:k.accent_color}}/></div><div><div className="ready-row"><h3>{k.name}</h3>{k.is_default ? <span className="ready-pill"><Check size={11}/>Default</span> : null}</div><p>{k.logo_text || "No wordmark"} · {k.caption_preset}</p></div><button className="icon-btn" title={`Delete ${k.name}`} aria-label={`Delete ${k.name}`} disabled={busy === k.id} onClick={() => void remove(k)}><Trash2 size={15}/></button></article>)}</div> : <div className="empty-state compact"><div className="empty-icon"><Palette/></div><h3>{canUseBrandKit ? "Create your first brand kit" : "Brand Kit is not included in your current plan"}</h3><p>{canUseBrandKit ? "Save reusable wordmarks, brand colors and caption presets." : "Upgrade to Creator, Growth, Pro or Agency to create and reuse Brand Kits."}</p></div>}
  </AppShell>;
}
