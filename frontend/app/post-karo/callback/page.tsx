"use client";

import { AppShell } from "@/components/AppShell";
import { postJSON } from "@/lib/api";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

function PostKaroCallbackPageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const started = useRef(false);
  const [error, setError] = useState("");
  const returnExport = search.get("return_export") || "";
  const oauthError = search.get("error") || "";

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (oauthError) {
      setError("The social account was not connected. You can try again from Post Karo whenever you are ready.");
      return;
    }
    void (async () => {
      try {
        await postJSON("/post-karo/accounts/sync", {});
        const suffix = returnExport ? "?export=" + encodeURIComponent(returnExport) + "&connected=1" : "?connected=1";
        router.replace("/post-karo" + suffix);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "ClipKaro could not finish this social connection.");
      }
    })();
  }, [oauthError, returnExport, router]);

  return <AppShell title="Post Karo" subtitle="Finishing your secure social connection.">
    <div className="empty-state">
      <div className="empty-icon">{error ? <span>!</span> : <Loader2 className="spin"/>}</div>
      <h3>{error ? "Connection needs attention" : "Finishing your connection…"}</h3>
      <p>{error || "ClipKaro is checking the account Zernio just authorised. You will return to Post Karo automatically."}</p>
      {error && <button className="primary-btn" onClick={() => router.replace(returnExport ? "/post-karo?export=" + encodeURIComponent(returnExport) : "/post-karo")}><CheckCircle2 size={15}/> Back to Post Karo</button>}
    </div>
  </AppShell>;
}


export default function PostKaroCallbackPage() {
  return <Suspense fallback={<AppShell title="Post Karo" subtitle="Finishing your secure social connection."><div className="screen-loader inline"><Loader2 className="spin"/><p>Finishing your connection…</p></div></AppShell>}><PostKaroCallbackPageInner/></Suspense>;
}
