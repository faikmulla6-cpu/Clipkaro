import fs from "node:fs";

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

const editor = read("app/editor/[clipId]/page.tsx");
const project = read("app/projects/[id]/page.tsx");
const projectList = read("app/projects/page.tsx");
const uploadForm = read("components/DirectUploadFallback.tsx");
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
  [projectList.includes('project.status === "failed" ? "Needs attention"') &&
    projectList.indexOf(') : project.status === "failed" ? (') < projectList.indexOf(') : project.video_status === "expired" ? (') &&
    projectList.includes("Needs attention · open for details"), "Failed projects must never appear as Processing or be masked by expired source status"],
  [uploadForm.includes("Plan limit exceeded") && uploadForm.includes("Check limits") && uploadForm.includes("Before you upload:"), "Upload must explain plan limits before selection and never label a blocked file as Ready"],
  [project.includes("YouTube Shorts titles and descriptions"), "Content Pack empty state must explain full output value"],
  [shell.includes("Content Packs"), "Authenticated sidebar must expose Content Packs"],
  [shell.includes("ck-credit-ribbon") && shell.includes("Karo Minutes") && shell.includes("Source projects") && shell.includes("ck-allowance-notice") && shell.includes("CreditTopupDialog"), "Relocated usage cards must offer separate top-ups and a dismissible warning"],
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
