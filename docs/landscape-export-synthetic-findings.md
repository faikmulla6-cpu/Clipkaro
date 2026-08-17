# Landscape Export QA — adversarial fallback findings

## Status

This document records an **independent deterministic fallback run** performed while GitHub-hosted Actions jobs for PR #17 were failing before runner step 1. It is useful engineering evidence, but it is **not the final real-footage launch verdict**. The source-controlled Wikimedia Commons qualification in `landscape-export-qa.yml` still has to execute successfully before the checklist can be closed.

## 30-export fallback matrix

Ten deterministic 1280×720 podcast/interview compositions were rendered through the same production crop geometry used by `render_short()`:

1. centred static speaker
2. left static speaker
3. right static speaker
4. left seated drift
5. right seated drift
6. speaker pacing across the frame
7. two-person layout, left participant framed as primary
8. two-person layout, right participant framed as primary
9. two-person active-speaker handoff from one side to the other
10. hard opposite-side camera/speaker handoff

Every layout was rendered with three policies:

- default centred crop
- best possible single manual `focus_x`
- time-varying focus keyframes passed through the existing production smoother

That produced exactly **30 actual portrait H.264 exports** with a mixture of 720p and 1080p outputs.

## Export correctness result

**30 / 30 exports validated successfully.**

The fallback run therefore found no basic FFmpeg/export-format defect in the landscape→portrait path. The risk is framing policy, not whether the renderer can produce a playable portrait file.

## Framing result

| Layout | Default centre | Best single manual focus | Existing dynamic keyframes |
| --- | --- | --- | --- |
| centred static | PASS | PASS | PASS |
| left static | FAIL | PASS | PASS |
| right static | FAIL | PASS | PASS |
| left seated drift | FAIL | PASS | PASS |
| right seated drift | FAIL | PASS | PASS |
| pacing across frame | FAIL | FAIL | PASS |
| two-person, left primary | FAIL | PASS | PASS |
| two-person, right primary | FAIL | PASS | PASS |
| two-person handoff | FAIL | FAIL | FAIL |
| hard camera/speaker handoff | FAIL | FAIL | FAIL |

Aggregate adversarial rates:

- best single manual focus: **7 / 10 (70%)**
- existing time-varying keyframe path: **8 / 10 (80%)**
- valid renders: **30 / 30 (100%)**

The synthetic matrix is deliberately adversarial and must not be treated as a prevalence estimate for real creator podcasts. It is meant to expose classes of failure that a happy-path sample can miss.

## Important engineering finding: tracking alone is not the whole fix

`crop_tracking.smooth_crop_keyframes()` caps horizontal focus movement at **18 focus points per second**. That behaviour is desirable for normal continuous movement because it prevents nauseating crop snapping.

It is not correct for a genuine shot boundary or hard speaker handoff where the visual subject jumps from the far left to the far right in one edit. In that case the current smoother intentionally takes time to travel across the frame, leaving the new subject badly cropped after the cut.

Therefore a future automatic reframe system should not be described as only "face tracking". A robust system needs at least two motion modes:

1. **continuous-shot tracking** — smooth face/subject motion to avoid jitter and snapping
2. **scene-cut/hard-handoff reframing** — allow an immediate focus reset when a verified shot boundary changes the composition

For multi-face podcasts, a third problem remains: deciding **which** visible face is the active speaker. Largest-face detection is only a framing proxy and must not be mistaken for active-speaker diarization.

## Product interpretation before the real-footage run

The fallback evidence supports these provisional conclusions:

- A single manual focus control is genuinely useful. It repaired every static off-centre and modest seated-drift layout in this matrix.
- A single manual focus is not enough for large in-shot movement or alternating opposite-side speakers.
- Time-varying focus fixes continuous cross-frame movement.
- The existing time-varying smoother still fails abrupt opposite-side shot/speaker changes without scene-cut semantics.
- Consequently, implementing a face detector alone would not close the complete landscape-podcast reframing problem.

The final launch decision must still come from the real Wikimedia interview qualification because it measures how often these failure classes occur in representative footage. The source-controlled verdict thresholds remain unchanged:

- manual focus can be considered sufficient for now only when it passes at least 85% of reliably scored real cases and dynamic-only rescue stays below 20%
- automatic tracking becomes launch-critical when manual success is below 80% or at least 25% of real cases require time-varying reframing
- a high multi-face rate independently triggers an active-speaker tracking follow-up

## Current checklist state

`[◐] Landscape Export QA — 30-export adversarial fallback complete; real-footage qualification still required.`
