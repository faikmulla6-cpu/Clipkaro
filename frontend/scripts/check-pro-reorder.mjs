import fs from "node:fs";

const source = fs.readFileSync(new URL("../app/editor/[clipId]/page.tsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../app/pro-editor.css", import.meta.url), "utf8");
const backend = fs.readFileSync(new URL("../../backend/app/services/smart_edit.py", import.meta.url), "utf8");

const requiredSource = [
  "segment_order",
  "validSegmentOrder",
  "timelineLayout",
  "visualTimelineLayout",
  "visualRemovedRanges",
  "sourceRelativeToOutput",
  "outputToSourceRelative",
  "sourceRelativeToVisual",
  "visualToSourceRelative",
  "timelineCaptionBlocks",
  "orderedAllSourceWords",
  "reorderSegment",
  "moveSelectedSegment",
  "beginSegmentReorder",
  "overSegmentReorder",
  "finishSegmentReorder",
  "segment-reorder-grip",
  "GripVertical",
  "reordering",
];

const requiredCss = [
  ".segment-reorder-grip",
  ".pro-editor-video-segment.dragging",
  ".pro-editor-video-segment.drop-target",
  ".pro-editor-timeline.reordering",
  ".pro-editor-segment-card-actions .reorder-step",
];

const requiredBackend = [
  "segment_order",
  "plan_reorders_segments",
  "def kept_ranges",
  "for segment_index in normal[\"segment_order\"]",
];

const missing = [
  ...requiredSource.filter(token => !source.includes(token)).map(token => `editor:${token}`),
  ...requiredCss.filter(token => !css.includes(token)).map(token => `css:${token}`),
  ...requiredBackend.filter(token => !backend.includes(token)).map(token => `backend:${token}`),
];

const trackedAdvance = source.indexOf("if (!video.paused && trackedPiece && relative >= trackedPiece.sourceEnd - .015)");
const sourceRecovery = source.indexOf("pieces.findIndex(piece => relative >= piece.sourceStart - .02 && relative <= piece.sourceEnd + .02)");
if (trackedAdvance < 0 || sourceRecovery < 0 || trackedAdvance > sourceRecovery) {
  missing.push("editor:edited-order playback must advance before source-time recovery");
}

if (missing.length) {
  console.error("Professional segment reorder contract failed:", missing.join(", "));
  process.exit(1);
}

console.log("Professional drag/reorder segment contract passed");
