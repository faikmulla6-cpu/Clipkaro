import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const analyticsPath = path.join(root, "app", "analytics", "page.tsx");
const source = fs.readFileSync(analyticsPath, "utf8");

function requireText(text, reason) {
  if (!source.includes(text)) {
    throw new Error(`Analytics trust check failed: ${reason}`);
  }
}

function forbid(pattern, reason) {
  if (pattern.test(source)) {
    throw new Error(`Analytics trust check failed: ${reason}`);
  }
}

forbid(/\[\s*0\s*,\s*1\s*,\s*0\s*,\s*2\s*,\s*1\s*,\s*3\s*,\s*2\s*\]/, "the legacy manufactured activity series is still present");
forbid(/18\s*\+\s*[^\n]*\*\s*22/, "bar height still uses the old manufactured baseline formula");

requireText('api<AnalyticsData>("/analytics")', "analytics summary must come from the backend API");
requireText('api<ExportHistory[]>("/exports")', "historical export semantics must be reconciled with the real export history API");
requireText('item.status === "ready" || item.status === "expired"', "completed history must include expired downloads without counting failed exports");
requireText('setError(', "API failures must have an explicit error state");
requireText('setLoading(', "loading must be distinct from empty analytics");
requireText('"Historical exports"', "the export total must be labelled as historical rather than current-plan usage");
requireText('"Includes expired downloads"', "expired download files must remain visible as historical completed exports");
requireText('data.activity.some((item) => item.exports > 0)', "the chart must be gated by real export activity");
requireText('(item.exports / maxExports) * 100', "bar heights must be scaled from real export counts");
requireText('item.exports === 0 ? 0', "zero exports must render as a zero-height bar");
requireText('Completed export history', "the chart must state that it represents completed export history");
requireText('Plan-period usage resets with billing rules', "current plan usage must be explicitly separated from historical exports");

console.log("Analytics trust contract passed: historical completed exports and current plan usage remain distinct and no activity is manufactured.");
