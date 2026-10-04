import fs from "node:fs";

const editor = fs.readFileSync(new URL("../app/editor/[clipId]/page.tsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

for (const token of [
  "Smart Edit V1", "Clean Speech", "splitAtPlayhead", "undoEdit", "redoEdit",
  "edit_plan: editPlan", "source_words", "timeline-removal", "rangeContains",
]) {
  if (!editor.includes(token)) throw new Error(`Smart Edit contract is missing: ${token}`);
}
for (const token of [".smart-transcript", ".smart-word.removed", ".pause-block", ".timeline-split"]) {
  if (!css.includes(token)) throw new Error(`Smart Edit style is missing: ${token}`);
}
console.log("Smart Edit frontend contract passed");
