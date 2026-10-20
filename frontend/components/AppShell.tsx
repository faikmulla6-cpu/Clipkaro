"use client";
import { Activity, AlertCircle, BarChart3, Bell, CalendarDays, CircleHelp, Clapperboard, Clock3, CreditCard, FileText, FolderKanban, Home, LayoutTemplate, LogOut, Menu, Palette, Plus, Send, ServerCog, Settings, Upload, Video, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Usage, usageShortLimit, usageShortRemaining } from "@/lib/api";
import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";
import { CreditTopupDialog } from "./CreditTopupDialog";

const workspace = [["Overview","/dashboard",Home],["Upload video","/upload",Upload],["Projects","/projects",FolderKanban],["Exports","/exports",Video],["Post Karo","/post-karo",Send],["Analytics","/analytics",BarChart3],["Creator Pulse","/creator-pulse",Activity],["Content calendar","/calendar",CalendarDays]] as const;
const studio = [["Content Packs","/content-packs",FileText],["Templates","/templates",LayoutTemplate],["Brand kit","/brand",Palette]] as const;

export function AppShell({ children, title, subtitle, action }: { children: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode }) {
  const path=usePathname(); const [open,setOpen]=useState(false); const {user,loading,logout}=useAuth(); const [usage,setUsage]=useState<Usage|null>(null);
  const [purchase,setPurchase]=useState<"minutes"|"shorts"|null>(null);
  const [dismissedNotice,setDismissedNotice]=useState(false);

  useEffect(()=>{if(user) api<Usage>("/usage").then(setUsage).catch(()=>null)},[user,path]);
  useEffect(()=>{setOpen(false)},[path]);
  useEffect(()=>{
    if(!open) return;
    const previous=document.body.style.overflow;
    document.body.style.overflow="hidden";
    return ()=>{document.body.style.overflow=previous};
  },[open]);

  useEffect(() => {
    if(!user || !usage) return;
    const kind=usage.processing_minutes_remaining<=0.1?"minutes":usageShortRemaining(usage)<=0?"shorts":null;
    const key=`clipkaro-dismissed-allowance:${user.id}:${usage.period_key}:${kind}`;
    setDismissedNotice(Boolean(kind && window.localStorage.getItem(key)==="1"));
  },[user,usage]);

  if(loading || !user) return <div className="screen-loader"><div className="loader-mark">✦</div><p>Opening your studio…</p></div>;
  const nav=(items:typeof workspace|typeof studio)=>items.map(([label,href,Icon])=><Link key={href} href={href} className={path===href||path.startsWith(`${href}/`)?"active":""} onClick={()=>setOpen(false)}><Icon size={18}/><span>{label}</span></Link>);
  const minutesLeft=usage?Math.max(0,usage.processing_minutes_remaining):0;
  const legacySourceProjects=usage?.short_unit==="source_projects";
  const noticeKind=usage && minutesLeft<=0.1 ? "minutes" : usage && usageShortRemaining(usage)<=0 ? "shorts" : null;
  const noticeKey= user && usage ? `clipkaro-dismissed-allowance:${user.id}:${usage.period_key}:${noticeKind}` : "";
  const shortRemaining=usage?usageShortRemaining(usage):0;
  const shortLimit=usage?usageShortLimit(usage):0;
  const primaryLimit=shortLimit;
  // Dismissal persists between page navigations and refreshes for this billing period.
  // A successful purchase immediately clears it and refreshes the live balances.
  function closeAllowanceNotice() {
    if(noticeKey) window.localStorage.setItem(noticeKey,"1");
    setDismissedNotice(true);
  }
  function refreshPurchasedBalance() {
    if(noticeKey) window.localStorage.removeItem(noticeKey);
    setDismissedNotice(false);
    setPurchase(null);
    api<Usage>("/usage").then(setUsage).catch(()=>null);
    window.dispatchEvent(new Event("clipkaro:credits-updated"));
  }

  return <div className="app-shell">
    <aside id="workspace-navigation" className={`sidebar ${open?"sidebar-open":""}`} aria-label="Workspace navigation">
      <div className="side-top"><Logo/><button type="button" className="icon-btn mobile-only app-menu-button" onClick={()=>setOpen(false)} aria-label="Close workspace menu"><X size={20}/></button></div>
      <Link href="/upload" className="new-project"><Plus size={17}/> Create new Short</Link>
      <nav className="side-nav"><p className="nav-label">Workspace</p>{nav(workspace)}<p className="nav-label">Creator studio</p>{nav(studio)}{user.role==="admin"&&<><p className="nav-label">Internal</p><Link href="/admin" className={path==="/admin"?"active":""}><ServerCog size={18}/><span>Admin queue</span></Link></>}<p className="nav-label">Account</p><Link href="/pricing" className={path==="/pricing"?"active":""}><CreditCard size={18}/><span>Plans & billing</span></Link><Link href="/account" className={path==="/account"?"active":""}><Settings size={18}/><span>Settings</span></Link></nav>
      {noticeKind && !dismissedNotice && <aside className="ck-allowance-notice" role="status">
        <button type="button" className="ck-notice-close" aria-label="Dismiss balance warning" onClick={closeAllowanceNotice}><X size={14}/></button>
        <AlertCircle size={19} className="text-[#bb512d]"/>
        <strong>{noticeKind==="minutes"?"You've run out of Karo Minutes":"Your AI Shorts are used up"}</strong>
        <p>{noticeKind==="minutes"?`You still have ${shortRemaining} ${legacySourceProjects?"source-project slots":"AI Shorts"}. Add processing minutes whenever you're ready.`:"Your existing finished Shorts are safe. Add credits to create more."}</p>
        <button type="button" onClick={()=>setPurchase(noticeKind)} className="ck-notice-action">Add {noticeKind==="minutes"?"Karo Minutes":"AI Shorts"}</button>
      </aside>}
      <div className="side-footer"><Link href="/help"><CircleHelp size={18}/> Help centre</Link><div className="profile-chip"><div className="avatar">{user.name.slice(0,2).toUpperCase()}</div><div><b>{user.name}</b><span>{user.plan==="mini_pass"&&usage?.pass_exhausted?"mini pass expired":`${user.plan} plan`}</span></div><button className="logout-icon" title="Sign out" aria-label="Sign out" onClick={logout}><LogOut size={15}/></button></div></div>
    </aside>
    {open&&<button type="button" className="sidebar-backdrop" onClick={()=>setOpen(false)} aria-label="Close workspace navigation"/>}
    <main className="app-main">
      <header className="app-header">
        <button type="button" className="icon-btn mobile-only app-menu-button" onClick={()=>setOpen(true)} aria-label="Open workspace menu" aria-controls="workspace-navigation" aria-expanded={open}><Menu size={21}/></button>
        <div><h1>{title}</h1>{subtitle&&<p>{subtitle}</p>}</div>
        <div className="header-actions">{action}<div className="header-icon" title="No new notifications" aria-label="No new notifications"><Bell size={17}/></div><div className="status-live"><span/> Live</div></div>
      </header>
      {usage && <section aria-label="Available creation credits" className="ck-credit-ribbon">
        <div className="ck-ribbon-title"><span className="ck-ribbon-kicker">YOUR STUDIO BALANCE</span><p>More creative room, on your terms.</p></div>
        <div className="ck-balance-card ck-balance-minutes">
          <div className="ck-credit-icon"><Clock3 size={18}/></div>
          <div className="ck-balance-detail"><strong>{minutesLeft.toLocaleString(undefined,{maximumFractionDigits:1})}<small> min available</small></strong><span>Karo Minutes · ₹3 / min</span></div>
          <button type="button" onClick={()=>setPurchase("minutes")} aria-label="Add Karo Minutes">Add <Plus size={13}/></button>
        </div>
        <div className="ck-balance-card ck-balance-shorts">
          <div className="ck-credit-icon"><Clapperboard size={18}/></div>
          <div className="ck-balance-detail"><strong>{shortRemaining}<small> / {primaryLimit}</small></strong><span>{legacySourceProjects?"Source projects":"AI Shorts"} · ₹2 each</span></div>
          <button type="button" onClick={()=>setPurchase("shorts")} aria-label="Add AI Shorts">Add <Plus size={13}/></button>
        </div>
      </section>}
      <div className="page-content">{children}</div>
      {purchase && <CreditTopupDialog initial={purchase} isLegacy={Boolean(legacySourceProjects)} onClose={()=>setPurchase(null)} onSuccess={refreshPurchasedBalance}/> }
    </main>
  </div>;
}
