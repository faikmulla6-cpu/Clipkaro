import fs from "node:fs";

const source = fs.readFileSync(new URL("../app/editor/[clipId]/page.tsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../app/pro-editor.css", import.meta.url), "utf8");

const requiredSource = [
  "timelineSegments",
  "selectedSegmentIndex",
  "beginTimelineScrub",
  "moveTimelineScrub",
  "endTimelineScrub",
  "deleteSelectedSegment",
  "Split at playhead (S)",
  "Delete selected segment (Delete)",
  'event.code === "Space"',
  'key === "s"',
  'event.key === "Delete"',
  "removed_ranges",
  "split_points",
];

const requiredCss = [
  ".pro-editor-timeline-actions",
  ".pro-editor-segment-card",
  ".pro-editor-video-segment.selected",
  ".pro-editor-video-track.interactive",
];

const missing = [
  ...requiredSource.filter(token => !source.includes(token)).map(token => `editor:${token}`),
  ...requiredCss.filter(token => !css.includes(token)).map(token => `css:${token}`),
];

if (missing.length) {
  console.error("Professional timeline contract failed:", missing.join(", "));
  process.exit(1);
}

console.log("Professional timeline interaction contract passed");
