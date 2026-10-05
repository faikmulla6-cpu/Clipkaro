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
  [shell.includes("Karo Minutes left") && shell.includes("Shorts left") && shell.includes("min processed"), "Usage card must distinguish remaining minutes from processed minutes"],
  [upload.includes("No Karo Minutes left for a new source.") && upload.includes("Open projects"), "Upload screen must explain that remaining Short exports can still be used"],
  [pricing.includes("25 total source-processing minutes") && pricing.includes("Up to 5 Short exports") && pricing.includes("max 30 days"), "Mini Pass pricing must separate processing minutes, Short exports, and source retention"],
  [css.includes(".side-nav{flex:1;min-height:0;overflow-y:auto"), "Sidebar navigation must remain scrollable on short screens"],
];

const failed = requirements.filter(([ok]) => !ok);
if (failed.length) {
  for (const [, message] of failed) console.error(`FAIL: ${message}`);
  process.exit(1);
}

console.log("Creator Studio quality-fix contracts passed.");
