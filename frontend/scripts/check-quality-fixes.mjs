import fs from "node:fs";

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

const editor = read("app/editor/[clipId]/page.tsx");
const project = read("app/projects/[id]/page.tsx");
const shell = read("components/AppShell.tsx");
const upload = read("components/UploadStudio.tsx");
const pricing = read("app/pricing/PricingExperience.tsx");
const css = read("app/quality-fixes.css");

const requirements = [
  [editor.includes("Video zoom:"), "Creator Studio must expose the video zoom control"],
  [editor.includes("zoom,"), "Export request must carry zoom to the backend"],
  [editor.includes("export-drawer-close"), "Completed export drawer must be dismissible"],
  [project.includes("Generate Content Pack"), "Project results must expose Content Pack generation"],
  [project.includes("No Content Pack yet"), "Missing Content Pack must render a normal empty state"],
  [project.includes("YouTube Shorts titles and descriptions"), "Content Pack empty state must explain full output value"],
  [shell.includes("Content Packs"), "Authenticated sidebar must expose Content Packs"],
  [shell.includes("Karo Minutes left") && shell.includes("AI Shorts left") && shell.includes("source_video_limit_minutes") && shell.includes("unlimited re-exports of finished Shorts"), "Usage card must show separate minute and Short credits with truthful render rights"],
  [upload.includes("No AI Short credits left for new finished Shorts.") && upload.includes("Existing Shorts can still be edited") && upload.includes("No Karo Minutes left for a new source.") && upload.includes("Open projects"), "Upload screen must differentiate Short capacity from source minutes"],
  [pricing.includes('planFeatureMinutes("mini_pass")') && pricing.includes("5 unique finished AI Shorts") && pricing.includes("Existing Mini Pass purchases retain") && pricing.includes("Unlimited re-exports") && pricing.includes("30 days"), "Mini Pass pricing must state 25 total minutes and 5 finished Shorts, honoring legacy purchases"],
  [css.includes(".side-nav{flex:1;min-height:0;overflow-y:auto"), "Sidebar navigation must remain scrollable on short screens"],
];

const failed = requirements.filter(([ok]) => !ok);
if (failed.length) {
  for (const [, message] of failed) console.error(`FAIL: ${message}`);
  process.exit(1);
}

console.log("Creator Studio quality-fix contracts passed.");
