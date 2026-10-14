import fs from "node:fs";

const source = fs.readFileSync(new URL("../app/editor/[clipId]/page.tsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../app/pro-editor.css", import.meta.url), "utf8");

const requiredSource = [
  "MIN_SEGMENT_KEEP",
  "segmentTrimReason",
  "findSegmentTrimRange",
  "segmentTrimBounds",
  "beginSegmentTrim",
  "moveSegmentTrim",
  "finishSegmentTrim",
  "resetSelectedSegmentTrim",
  "planWithSegmentTrim",
  "mergedRemovedRanges",
  "displayTimelineSegments",
  "selectedSegmentHasTrim",
  "segment-trim-handle left",
  "segment-trim-handle right",
  "Drag yellow edges Trim",
];

const requiredCss = [
  ".segment-trim-handle",
  ".segment-trim-handle.left",
  ".segment-trim-handle.right",
  ".pro-editor-timeline.trimming",
  ".pro-editor-segment-card-actions .reset-trim",
];

const missing = [
  ...requiredSource.filter(token => !source.includes(token)).map(token => `editor:${token}`),
  ...requiredCss.filter(token => !css.includes(token)).map(token => `css:${token}`),
];

if (missing.length) {
  console.error("Professional segment trim contract failed:", missing.join(", "));
  process.exit(1);
}

console.log("Professional draggable segment trim contract passed");
