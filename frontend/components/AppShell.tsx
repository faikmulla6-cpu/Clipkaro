"use client";
import { Activity, BarChart3, Bell, CalendarDays, CircleHelp, CreditCard, FileText, FolderKanban, Home, LayoutTemplate, LogOut, Menu, Palette, Plus, ServerCog, Settings, Upload, Video, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, Usage } from "@/lib/api";
import { useAuth } from "./AuthProvider";
import { Logo } from "./Logo";

const workspace = [["Overview","/dashboard",Home],["Upload video","/upload",Upload],["Projects","/projects",FolderKanban],["Exports","/exports",Video],["Analytics","/analytics",BarChart3],["Creator Pulse","/creator-pulse",Activity],["Content calendar","/calendar",CalendarDays]] as const;
const studio = [["Content Packs","/content-packs",FileText],["Templates","/templates",LayoutTemplate],["Brand kit","/brand",Palette]] as const;

export function AppShell({ children, title, subtitle, action }: { children: React.ReactNode; title: string; subtitle?: string; action?: React.ReactNode }) {
  const path=usePathname(); const [open,setOpen]=useState(false); const {user,loading,logout}=useAuth(); const [usage,setUsage]=useState<Usage|null>(null);

  useEffect(()=>{if(user) api<Usage>("/usage").then(setUsage).catch(()=>null)},[user,path]);
  useEffect(()=>{setOpen(false)},[path]);
  useEffect(()=>{
    if(!open) return;
    const previous=document.body.style.overflow;
    document.body.style.overflow="hidden";
    return ()=>{document.body.style.overflow=previous};
  },[open]);

  if(loading || !user) return <div className="screen-loader"><div className="loader-mark">✦</div><p>Opening your studio…</p></div>;
  const nav=(items:typeof workspace|typeof studio)=>items.map(([label,href,Icon])=><Link key={href} href={href} className={path===href||path.startsWith(`${href}/`)?"active":""} onClick={()=>setOpen(false)}><Icon size={18}/><span>{label}</span></Link>);

  return <div className="app-shell">
    <aside id="workspace-navigation" className={`sidebar ${open?"sidebar-open":""}`} aria-label="Workspace navigation">
      <div className="side-top"><Logo/><button type="button" className="icon-btn mobile-only app-menu-button" onClick={()=>setOpen(false)} aria-label="Close workspace menu"><X size={20}/></button></div>
      <Link href="/upload" className="new-project"><Plus size={17}/> Create new Short</Link>
      <nav className="side-nav"><p className="nav-label">Workspace</p>{nav(workspace)}<p className="nav-label">Creator studio</p>{nav(studio)}{user.role==="admin"&&<><p className="nav-label">Internal</p><Link href="/admin" className={path==="/admin"?"active":""}><ServerCog size={18}/><span>Admin queue</span></Link></>}<p className="nav-label">Account</p><Link href="/pricing" className={path==="/pricing"?"active":""}><CreditCard size={18}/><span>Plans & billing</span></Link><Link href="/account" className={path==="/account"?"active":""}><Settings size={18}/><span>Settings</span></Link></nav>
      <div className="usage-card"><div className="usage-row"><span>Karo Minutes</span><b>{usage?`${Math.round(usage.source_minutes)} / ${Math.round(usage.processing_minutes_limit)}`:"—"}</b></div><div className="progress"><span style={{width:`${usage&&usage.processing_minutes_limit?Math.min(usage.source_minutes/usage.processing_minutes_limit*100,100):0}%`}}/></div><p>{usage?`${usage.exports_remaining} Shorts left · ${Math.round(usage.processing_minutes_remaining)} min remaining`:"Loading usage…"}</p><Link href="/pricing">View plans & billing</Link></div>
      <div className="side-footer"><Link href="/help"><CircleHelp size={18}/> Help centre</Link><div className="profile-chip"><div className="avatar">{user.name.slice(0,2).toUpperCase()}</div><div><b>{user.name}</b><span>{user.plan} plan</span></div><button className="logout-icon" title="Sign out" aria-label="Sign out" onClick={logout}><LogOut size={15}/></button></div></div>
    </aside>
    {open&&<button type="button" className="sidebar-backdrop" onClick={()=>setOpen(false)} aria-label="Close workspace navigation"/>}
    <main className="app-main">
      <header className="app-header">
        <button type="button" className="icon-btn mobile-only app-menu-button" onClick={()=>setOpen(true)} aria-label="Open workspace menu" aria-controls="workspace-navigation" aria-expanded={open}><Menu size={21}/></button>
        <div><h1>{title}</h1>{subtitle&&<p>{subtitle}</p>}</div>
        <div className="header-actions">{action}<div className="header-icon" title="No new notifications" aria-label="No new notifications"><Bell size={17}/></div><div className="status-live"><span/> Live</div></div>
      </header>
      <div className="page-content">{children}</div>
    </main>
  </div>;
}
