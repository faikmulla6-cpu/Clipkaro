"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

export function ErrorState({ title = "We could not open this page", message, retry }: {
  title?: string;
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="connection-error">
      <span><AlertTriangle size={23} /></span>
      <h2>{title}</h2>
      <p>{message}</p>
      {retry && <button className="primary-btn" onClick={retry}><RefreshCw size={15} /> Try again</button>}
      <small>Backend health: <a href="/api/v1/health" target="_blank" rel="noopener noreferrer">open diagnostic</a></small>
    </div>
  );
}
