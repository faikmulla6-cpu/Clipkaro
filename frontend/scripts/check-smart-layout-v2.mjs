/** Lightweight Node 24+ contract check, without React, private media or exports. */
import assert from "node:assert/strict";
import {
  parseSmartLayoutPlan, findScene, focusRectAt, paintSmartLayoutFrame, dualStackCoverageSeconds,
  dualStackCropsAt,
} from "../lib/smart-layout-timeline.ts";

const fixture = {
  version: 2,
  requested_mode: "auto",
  source_width: 1280,
  source_height: 720,
  source_start: 523.46,
  duration: 8,
  preview_width: 360,
  preview_height: 640,
  scenes: [
    { start: 0, end: 3, layout: "dual_stack",
      crops: [[100, 40, 590, 460], [620, 70, 590, 460]],
      switches: [], caption_zone: "middle" },
    { start: 3, end: 5, layout: "single",
      crops: [[560, 10, 404, 700]],
      switches: [], caption_zone: "bottom" },
    { start: 5, end: 8, layout: "wide",
      crops: [[0, 0, 1280, 720]],
      switches: [], caption_zone: "bottom" },
  ],
};
const parsed = parseSmartLayoutPlan(fixture);
assert.ok(parsed, "valid layout timeline must parse");
assert.equal(dualStackCoverageSeconds(parsed), 3, "only genuine paired scenes count as Dual Stack");
assert.equal(dualStackCoverageSeconds({ ...parsed, scenes: parsed.scenes.slice(1) }), 0,
             "solo and wide scenes cannot be advertised as dual-video coverage");
assert.equal(findScene(parsed, 524)?.layout, "dual_stack");
assert.equal(findScene(parsed, 526.7)?.layout, "single");
assert.equal(findScene(parsed, 529)?.layout, "wide");
assert.equal(findScene(parsed, 531.46)?.layout, "wide", "last exact frame is included");
assert.equal(findScene(parsed, 532)?.layout, undefined);

const cloned = () => JSON.parse(JSON.stringify(fixture));
for (const malicious of [NaN, Infinity, -Infinity, -1]) {
  const p = cloned(); p.scenes[0].crops[0][0] = malicious;
  assert.equal(parseSmartLayoutPlan(p), null, "unbounded crop rejected");
}
for (const kind of ["single", "wide"]) {
  const p = cloned(); p.scenes[0].layout = kind;
  assert.equal(parseSmartLayoutPlan(p), null, "an unexpected duplicate panel rejected");
}
{
  const p = cloned(); p.scenes[1].start = 3.5;
  assert.equal(parseSmartLayoutPlan(p), null, "gap cannot become a blank frame");
}
{
  const p = cloned(); p.scenes[0].crops[1] = [...p.scenes[0].crops[0]];
  assert.equal(parseSmartLayoutPlan(p), null, "same person must not be duplicated");
}
{
  const p = cloned(); p.scenes[0].caption_zone = "bottom";
  assert.equal(parseSmartLayoutPlan(p), null, "caption zone must match scene layout");
}
{
  const p = cloned(); p.scenes[0].switches = [[2, 2]];
  assert.equal(parseSmartLayoutPlan(p), null, "a nonexistent third speaker is forbidden");
}

{
  const p = cloned();
  p.scenes[0].switches = [[0, 0], [1.5, 1]];
  const switching = parseSmartLayoutPlan(p);
  assert.ok(switching, "verified Dual Stack switches are valid");
  assert.deepEqual(dualStackCropsAt(switching.scenes[0], 1), p.scenes[0].crops);
  assert.deepEqual(dualStackCropsAt(switching.scenes[0], 2), [
    p.scenes[0].crops[1], p.scenes[0].crops[0],
  ], "active speaker goes above the listener");
  const { ctx, commands } = fakeCanvas();
  assert.equal(paintSmartLayoutFrame(ctx, { readyState: 4 }, switching, 525.46), true);
  const draws = commands.filter(c => c[0] === "draw");
  assert.deepEqual(draws[0].slice(1, 5), p.scenes[0].crops[1]);
  assert.deepEqual(draws[1].slice(1, 5), p.scenes[0].crops[0]);
}

const focusScene = {
  start: 0, end: 4, layout: "speaker_focus",
  crops: [[0, 20, 404, 700], [860, 20, 404, 700]],
  switches: [[0, 0], [2, 1]], caption_zone: "bottom",
};
const focus = { ...cloned(), duration: 4, scenes: [focusScene], requested_mode: "speaker_focus" };
assert.ok(parseSmartLayoutPlan(focus));
assert.equal(focusRectAt(focusScene, 1.5)[0], 0);
assert.ok(focusRectAt(focusScene, 2)[0] > 400 && focusRectAt(focusScene, 2)[0] < 500,
          "speaker focus must ease across the actual face centers");
assert.equal(focusRectAt(focusScene, 2.4)[0], 860);

const elevatedFocus = {
  ...focusScene,
  crops: [[0, 0, 404, 700], [860, 18, 404, 700]],
};
assert.deepEqual(focusRectAt(elevatedFocus, 1), [0, 0, 404, 700]);
const halfway = focusRectAt(elevatedFocus, 2);
assert.ok(halfway[0] > 400 && halfway[0] < 500);
assert.ok(halfway[1] > 8 && halfway[1] < 10,
          "Speaker Focus must animate x and y identically to FFmpeg");
assert.deepEqual(focusRectAt(elevatedFocus, 2.4), [860, 18, 404, 700]);
const lateFirstSwitch = {
  ...elevatedFocus,
  switches: [[1.5, 1]],
};
assert.deepEqual(focusRectAt(lateFirstSwitch, .5), [0, 0, 404, 700],
  "No confirmed speaker change must preserve the initial frame, not jump to a future speaker");
assert.deepEqual(focusRectAt(lateFirstSwitch, 2.0), [860, 18, 404, 700]);

function fakeCanvas() {
  const commands = [];
  const ctx = {
    canvas: { width: 360, height: 640 },
    save() { commands.push(["save"]); },
    restore() { commands.push(["restore"]); },
    clearRect(...coords) { commands.push(["clear", ...coords]); },
    drawImage(_v, ...coords) { commands.push(["draw", ...coords]); },
    fillRect(...coords) { commands.push(["fill", ...coords]); },
    filter: "none", fillStyle: "",
  };
  return { ctx, commands };
}
const video = { readyState: 4, videoWidth: 1280, videoHeight: 720 };
{
  const { ctx, commands } = fakeCanvas();
  assert.equal(paintSmartLayoutFrame(ctx, video, parsed, 524), true);
  const draws = commands.filter(c => c[0] === "draw");
  assert.equal(draws.length, 2, "dual stack draws two separately cropped regions");
  assert.notDeepEqual(draws[0].slice(1, 5), draws[1].slice(1, 5));
  assert.equal(commands.filter(c => c[0] === "fill").length, 1, "caption band has its own space");
}
{
  const { ctx, commands } = fakeCanvas();
  assert.equal(paintSmartLayoutFrame(ctx, video, parsed, 526.7), true);
  assert.equal(commands.filter(c => c[0] === "draw").length, 1,
               "one visible face must produce exactly one panel");
}
{
  const { ctx, commands } = fakeCanvas();
  assert.equal(paintSmartLayoutFrame(ctx, video, parsed, 529), true);
  assert.equal(commands.filter(c => c[0] === "draw").length, 2,
               "wide scene draws a safety background and full source content");
}

console.log("Smart Layout v2 contract and canvas geometry: passed");
