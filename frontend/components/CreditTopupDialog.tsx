"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, CreditCard, Loader2, Minus, Plus, ShieldCheck, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { api, postJSON } from "@/lib/api";

type Kind = "minutes" | "shorts";
type Quote = { eligible: boolean; minutes_max: number; shorts_max: number; minutes_min: number; minutes_paise: number; short_paise: number; purchased_minutes_left: number; purchased_shorts_left: number };
type Checkout = { key_id: string; order_id: string; amount: number; currency: string; name: string; description: string; prefill?: { name: string; email: string } };
type Payment = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string };
type Verification = { verified: boolean; pending?: boolean };
type RazorpayInstance = { open: () => void; on?: (event: string, handler: (value: { error?: { description?: string } }) => void) => void };
type RazorpayWindow = Window & { Razorpay?: new (options: Record<string, unknown>) => RazorpayInstance };

const SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";
let scriptPromise: Promise<void> | null = null;
function loadCheckout(): Promise<void> {
  if ((window as RazorpayWindow).Razorpay) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    let settled = false;
    const timeout = window.setTimeout(() => finish(new Error("Razorpay took too long to load. Check your connection and retry.")), 15000);
    function finish(error?: Error) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      if (error) { scriptPromise = null; script.remove(); reject(error); }
      else resolve();
    }
    script.onload = () => (window as RazorpayWindow).Razorpay ? finish() : finish(new Error("Secure checkout failed to initialize."));
    script.onerror = () => finish(new Error("Unable to load Razorpay. Please check your internet connection."));
    document.head.appendChild(script);
  });
  return scriptPromise;
}

function Quantity({ label, helper, value, min, max, step, onChange }: { label: string; helper: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) {
  return <div className="flex flex-col gap-3 rounded-2xl border border-[#dfe9de] bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
    <div><p className="text-[13px] font-extrabold text-[#153a2a]">{label}</p><p className="mt-1 text-[11px] text-[#6a7a70]">{helper}</p></div>
    <div className="flex items-center gap-2 self-end sm:self-auto">
      <button type="button" aria-label={`Remove ${label}`} disabled={value===0} onClick={() => onChange(value<=min?0:value-step)} className="grid h-9 w-9 place-items-center rounded-xl border border-[#dce7da] text-[#174532] transition hover:border-[#a2bbaa] hover:bg-[#f3f8ef] disabled:opacity-35"><Minus size={15}/></button>
      <input aria-label={`${label} quantity`} type="number" inputMode="numeric" min="0" max={max} step="1" value={value} onBlur={()=>{if(value>0&&value<min)onChange(min);}} onChange={e=>{
        if(e.target.value==="") { onChange(0); return; }
        const next = Number(e.target.value);
        if(Number.isInteger(next) && next>=0) onChange(Math.min(max,next));
      }} className="h-10 w-16 rounded-xl border border-[#e0e8de] bg-[#f8faf6] text-center text-[17px] font-black tabular-nums text-[#143d2b] outline-none focus:border-[#1d7150]" />
      <button type="button" aria-label={`Add ${label}`} disabled={value>=max} onClick={() => onChange(Math.min(max,value===0?min:value+step))} className="grid h-9 w-9 place-items-center rounded-xl bg-[#176044] text-white transition hover:bg-[#0f4c36] disabled:opacity-35"><Plus size={15}/></button>
    </div>
  </div>;
}

export function CreditTopupDialog({ initial, isLegacy, onClose, onSuccess }: { initial: Kind; isLegacy: boolean; onClose: () => void; onSuccess: () => void }) {
  const [quote,setQuote] = useState<Quote|null>(null);
  const [minutes,setMinutes] = useState(initial==="minutes"?10:0);
  const [shorts,setShorts] = useState(initial==="shorts"?1:0);
  const [loading,setLoading] = useState(true);
  const [submitting,setSubmitting] = useState(false);
  const [error,setError] = useState("");
  const [message,setMessage] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    headingRef.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    document.addEventListener("keydown", handler);
    return () => { document.body.style.overflow=previous; document.removeEventListener("keydown", handler); };
  }, [submitting,onClose]);
  useEffect(() => {
    let live = true;
    api<Quote>("/credits/quote").then(q=>{ if(live) { setQuote(q); setMinutes(v=>Math.min(v,q.minutes_max));setShorts(v=>Math.min(v,q.shorts_max)); } })
      .catch(e=>{if(live)setError(e instanceof Error?e.message:"Could not load your purchase limits.");})
      .finally(()=>{if(live)setLoading(false);});
    return ()=>{live=false;};
  },[]);
  const total = useMemo(()=>minutes*3 + shorts*2,[minutes,shorts]);
  const eligible = quote?.eligible && total>0 && (!minutes||(minutes>=10&&minutes<=quote.minutes_max)) && shorts<=quote.shorts_max;

  async function purchase() {
    if(!eligible || submitting) return;
    setSubmitting(true);setError("");setMessage("");
    try {
      await loadCheckout();
      const order = await postJSON<Checkout>("/credits/checkout",{minutes,shorts});
      if(order.currency!=="INR" || order.amount!==total*100 || !order.order_id || !order.key_id) {
        throw new Error("The checkout amount did not match your selection. You have not been charged.");
      }
      const Constructor = (window as RazorpayWindow).Razorpay;
      if(!Constructor) throw new Error("Razorpay is unavailable. Please retry.");
      let verifying = false;
      const instance = new Constructor({
        key:order.key_id, order_id:order.order_id,amount:order.amount,currency:order.currency,
        name:order.name,description:order.description,prefill:order.prefill,theme:{ color:"#165f43" },
        modal:{ backdropclose:false,ondismiss:()=>{if(!verifying){setSubmitting(false);setMessage("Checkout closed. No credits were added.");}} },
        handler:async(payment:Payment)=>{
          verifying=true;
          setMessage("Confirming your payment securely…");
          try {
            const result=await postJSON<Verification>("/credits/verify",payment);
            if(result.verified) { onSuccess(); return; }
            setMessage("Your payment is awaiting capture. We will update your credits after confirmation.");
          } catch(e) {
            setError((e instanceof Error?e.message:"Unable to verify payment.")+" If you were charged, do not pay again yet. Your payment will be reconciled automatically.");
          } finally {setSubmitting(false);}
        },
      });
      instance.on?.("payment.failed",(event)=>{setSubmitting(false);setError(event.error?.description||"Payment failed. No credits were added. Please try again.");});
      instance.open();
    } catch(e) {
      setError(e instanceof Error?e.message:"Unable to start secure checkout. Please try again.");
      setSubmitting(false);
    }
  }

  return <div role="presentation" className="fixed inset-0 z-[120] flex items-center justify-center bg-[#05180fe0] px-3 py-6 backdrop-blur-[6px] motion-safe:animate-[creditOverlay_.2s_ease-out]" onMouseDown={e=>{if(e.target===e.currentTarget&&!submitting)onClose();}}>
    <section role="dialog" aria-modal="true" aria-labelledby="credit-dialog-title" className="relative max-h-[95vh] w-full max-w-[490px] overflow-y-auto rounded-[28px] border border-white/50 bg-[#f8faf5] p-5 shadow-[0_30px_100px_rgba(3,28,13,.36)] sm:p-7 motion-safe:animate-[creditPanel_.28s_cubic-bezier(.2,.9,.2,1)]">
      <div className="flex justify-between gap-4"><div><div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-[#e8f4e4] px-2.5 py-1 text-[10px] font-black uppercase tracking-[.08em] text-[#216b49]"><Sparkles size={13}/> Creator balance</div><h2 ref={headingRef} tabIndex={-1} id="credit-dialog-title" className="text-[23px] font-black tracking-[-.9px] text-[#122d22] outline-none">Add to your balance</h2><p className="mt-1 text-[12px] text-[#6b7970]">Only pay for the credits you need.</p></div><button aria-label="Close" disabled={submitting} onClick={onClose} className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-[#dde8d8] text-[#4e6054] transition hover:bg-white disabled:opacity-40"><X size={17}/></button></div>
      <div className="mt-6 space-y-3">
        {loading?<div className="flex items-center gap-2 py-8 text-xs text-[#607269]"><Loader2 size={16} className="animate-spin"/> Checking your plan…</div>:quote?.eligible?<>
          <Quantity label="Karo Minutes" helper={`₹3 per minute · min 10 · max ${quote.minutes_max}`} value={minutes} min={10} max={quote.minutes_max} step={1} onChange={setMinutes}/>
          <Quantity label={isLegacy?"Source project credits":"AI Shorts"} helper={`₹2 each · max ${quote.shorts_max} per purchase${isLegacy?" · legacy project slots":""}`} value={shorts} min={1} max={quote.shorts_max} step={1} onChange={setShorts}/>
        </>:<div className="rounded-xl bg-[#fff4d8] p-4 text-[12px] text-[#795518]">Top-ups require a Creator, Growth, Pro or Agency subscription. <Link className="font-extrabold underline" href="/pricing" onClick={onClose}>View plans</Link></div>}
      </div>
      <div className="mt-5 rounded-2xl bg-[#153e2b] px-4 py-4 text-white">
        <div className="flex items-center justify-between gap-3"><div><p className="text-[11px] text-[#bdd4c3]">One-time payment</p><p className="mt-1 text-[10px] text-[#bdd4c3]">{minutes} minutes + {shorts} {isLegacy?"project slots":"AI Shorts"}</p></div><div className="text-[31px] font-black tracking-[-1px] tabular-nums">₹{total.toLocaleString("en-IN")}</div></div>
      </div>
      {error&&<p role="alert" className="mt-3 rounded-xl border border-[#f1c9bf] bg-[#fff1ec] p-3 text-[12px] text-[#a13b30]">{error}</p>}
      {message&&<p role="status" className="mt-3 rounded-xl border border-[#badfcc] bg-[#f0f9f1] p-3 text-[12px] text-[#215b3d]">{message}</p>}
      <button onClick={()=>void purchase()} disabled={!eligible || loading || submitting} className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-[#dfff57] text-[13px] font-black text-[#133a2a] shadow-[0_10px_26px_rgba(63,143,51,.12)] transition hover:-translate-y-0.5 hover:bg-[#d3f64d] disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:translate-y-0">
        {submitting?<><Loader2 size={16} className="animate-spin"/> Secure checkout…</>:<><CreditCard size={16}/> Pay ₹{total.toLocaleString("en-IN")} securely <ArrowRight size={16}/></>}
      </button>
      <div className="mt-4 flex items-start justify-center gap-1.5 text-[10px] leading-4 text-[#758478]"><ShieldCheck size={15} className="shrink-0 text-[#2d8051]"/><span>Razorpay protected · Credits added only after confirmed payment · Unused purchased credits carry forward</span></div>
      {isLegacy&&<p className="mt-2 text-center text-[10px] text-[#738072]">Your existing plan counts source projects rather than finished Shorts. Its purchased rights stay unchanged.</p>}
    </section>
  </div>;
}
