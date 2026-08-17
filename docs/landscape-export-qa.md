# Landscape Export QA decision gate

## Product question

This qualification answers one narrow launch question:

> When ClipKaro turns a normal 16:9 interview/podcast into a 9:16 Short, is the existing single manual horizontal focus control good enough for now, or do we need automatic time-varying reframing before launch?

The test does **not** assume that a successful FFmpeg encode means the framing is usable.

## Why landscape input is difficult

A 16:9, 1280×720 source exported to 9:16 retains only about 405 source pixels horizontally at any instant. In other words, a portrait Short sees only ~31.6% of the original landscape width. A centered crop can therefore remove an off-centre guest completely even when the source video itself looks normal.

ClipKaro currently supports:

- `focus_x`: one horizontal focus value for the entire clip
- optional time-varying `crop_keyframes`
- smoothing of supplied keyframes before the FFmpeg crop expression is built

`crop_tracking.py` does not currently detect faces, scene cuts, or active speakers. It only smooths focus observations it is given.

## The 30-export qualification

The heavyweight workflow downloads five compact Creative-Commons interview recordings from Wikimedia Commons at runtime. The repository stores only source-page references; third-party media is not committed.

Two deterministic 8-second landscape windows are taken from each source, producing 10 test clips. Each clip is exported three times through the production `render_short()` implementation:

1. **Center** — current default `focus_x=50`
2. **Manual** — the best single `focus_x` that could be selected for the entire clip
3. **Dynamic** — time-varying focus keyframes derived from sampled primary-face positions and passed through ClipKaro's current production smoother

That produces exactly **30 real H.264/AAC portrait exports**. The matrix deliberately mixes 720p and 1080p outputs.

The workflow saves all 30 MP4s, the JSON evidence report, a Markdown summary, and GNU `time -v` resource evidence as a 30-day Actions artifact.

## Face/framing score

OpenCV is installed only in the heavyweight QA workflow. It is not added to ClipKaro's production dependency set.

Each normalized landscape test clip is sampled across time. The largest detected face is treated as the **primary framing target**. For every sampled frame the scorer measures:

- percentage of the primary face retained by the portrait crop
- distance of the face centre from the crop centre
- whether the frame contains multiple detected faces
- how far the ideal focus point moves during the clip

A sampled frame passes when at least 90% of the target face remains visible and the face remains inside the central framing region. A case passes when at least 90% of scored frames pass, average face visibility is at least 94%, and p10 visibility is at least 80%.

The best static manual focus is selected by exhaustive search across `focus_x=0..100`; this intentionally gives manual focus its strongest possible result rather than testing an arbitrary slider position.

## Decision contract

The verdict is source-controlled so the result cannot be reinterpreted after seeing the numbers.

### Manual focus sufficient for now

Requires:

- at least 8 reliably face-scored real cases
- best single manual focus passes at least 85% of cases
- fewer than 20% of cases are failures that only dynamic focus rescues

If the current dynamic tracker itself scores below 90% while manual focus still satisfies those thresholds, the result becomes `manual_focus_sufficient_but_auto_tracking_not_qualified`. Manual focus remains a valid first-release fallback, but the dynamic implementation cannot be presented as production-ready.

### Automatic face tracking is critical

When the current dynamic policy itself is reliable (at least 90% case pass rate), automatic face tracking becomes launch-critical when either:

- best single manual focus passes fewer than 80% of representative cases, or
- at least 25% of representative cases fail with the best manual focus but pass with time-varying focus

That means a creator cannot reliably repair common landscape podcast clips with one manual focus position. Automatic tracking or a manual keyframe/timeline workflow becomes a launch-level requirement.

### Face tracking alone is insufficient

If at least 8 real cases are measured reliably but the current time-varying focus policy passes fewer than 90% of them **and** manual focus is not sufficient, the valid product verdict is:

`automatic_reframe_needs_scene_cut_or_speaker_logic`

This is not benchmark failure. It means simple smoothed face positions do not solve the actual footage. Common causes include:

- hard camera cuts from one side of the frame to the other
- abrupt active-speaker handoffs in two-person podcasts
- multi-face ambiguity
- detector instability around shot boundaries

A robust future reframer therefore needs separate continuous-shot smoothing and scene-cut-aware focus resets; multi-face footage may additionally need active-speaker evidence.

### Guardrail state

Results between the manual-sufficient and tracking-critical boundaries return `manual_focus_sufficient_with_guardrails`. Manual focus remains viable for the first release, but clips with substantial movement or multiple faces should receive an explicit editor warning/review path.

## Multi-face limitation

The largest face is a framing proxy, **not active-speaker diarization**. A two-person podcast may contain two visible faces while the speaking person alternates. The report therefore publishes `multi_face_sample_rate` separately and recommends a future active-speaker tracking evaluation when at least 20% of sampled frames are multi-face.

This prevents a face detector from being mistaken for a complete speaker-aware reframing system.

## Manual-reframe trust contract

The first-release fallback is only trustworthy if the editor and downloaded MP4 use the same focus semantics. Normal CI therefore verifies that:

- Creator Studio still exposes the `Manual reframe` slider over the full 0..100 range
- the browser preview uses `object-fit: cover`
- the selected value drives `object-position`
- the export summary discloses the selected focus percentage
- the same value is submitted as backend `focus_x`
- the backend still validates 0..100 and the renderer still uses that value in its horizontal crop expression

This prevents a UI refactor from making manual focus appear functional while the exported crop behaves differently.

## Failure semantics

The qualification fails closed only when the **evidence itself** is incomplete or invalid, for example:

- fewer than 30 exports are produced
- any generated export fails H.264/dimension/duration validation
- fewer than 8 of the 10 source clips have reliable face detections

A red product result is not infrastructure failure. `automatic_face_tracking_is_critical` and `automatic_reframe_needs_scene_cut_or_speaker_logic` are both legitimate outcomes and must remain visible in the evidence report rather than being converted into generic CI failure.

## Local execution

Install FFmpeg/FFprobe, backend development dependencies, and `opencv-python-headless`, then from `backend/` run:

```bash
python scripts/landscape_export_qa.py --output-dir landscape_qa --cases 10 --clip-seconds 8 --samples 12
```

The normal CI suite tests crop geometry, verdict logic, abrupt-handoff handling, and the manual-reframe trust contract without downloading videos or requiring OpenCV. The dedicated `Landscape Export QA` workflow performs the expensive real-media run.


## Exact-candidate evidence discipline

The launch qualification is now an exact-candidate gate rather than a best-effort visual smoke test.

Every trustworthy run must:

- execute from a clean Git checkout
- record `TESTED_SHA` and prove `git rev-parse HEAD` matches it
- record the source-controlled threshold contract before the first real export
- record the same threshold contract again after the run
- keep the before/after SHA-256 identical
- produce exactly 10 real normalized cases
- produce exactly one `center`, `manual`, and `dynamic` export for every case
- validate exactly 30 H.264/AAC outputs
- retain at least 8 reliably face-scored cases
- preserve the real product verdict even when that verdict says automatic reframing is required

The qualification execution decision and product decision are deliberately separate:

- `PASS` means the evidence is complete and trustworthy.
- `FAIL` means the qualification ran but the evidence contract was violated.
- `BLOCKED` means the host/source environment prevented a valid run before a product verdict existed.

A `PASS` does **not** mean manual reframing passed. For example,
`automatic_face_tracking_is_critical` is a valid product verdict from a successful qualification.

The frozen contract lives at:

```text
backend/landscape-threshold-lock.json
```

The current contract fixes:

- 10 real cases
- 3 policies per case
- 30 exports
- 8-second windows
- 12 face samples per case
- 60% minimum detection coverage
- 6 minimum detected observations per scored case
- 8 minimum reliably scored cases
- frame/case visibility and centering thresholds
- manual-vs-dynamic product decision thresholds
- H.264 + AAC output validation

Changing any of those values is a new qualification contract and must happen before looking at a new run.

## Real-media acquisition

The default runner downloads the five locked Wikimedia interview files and creates two deterministic windows from each source.

For a network-restricted but trusted qualification host, operators can pre-download the same five real files into one private directory and run:

```bash
LANDSCAPE_SOURCE_DIR=/srv/clipkaro-landscape-sources \
  bash scripts/run-real-landscape-qualification.sh
```

The directory must contain these exact filenames:

```text
Interview_with_Janno_Loide.webm
Rwicinterview2.webm
Rwicinterview3.webm
Erik_Gudbranson_interview.webm
Friedel_Wikipedia_Public_Policy_Initiative_interview_clip.webm
```

The report records the actual SHA-256 and byte size of each input, whether it came from the runtime download path or an operator-supplied real-media cache, and the exact normalized source window used. The real media itself remains outside Git.

For GitHub Actions, the same cache can be selected without committing a host path by defining the non-secret repository variable `LANDSCAPE_SOURCE_DIR` to that directory on the trusted self-hosted runner. Leave the variable unset to use runtime Wikimedia downloads.

## Evidence bundle

A successful run creates:

```text
backend/landscape_qa/landscape-export-qa-report.json
backend/landscape_qa/landscape-export-qa-summary.md
backend/landscape_qa/exports/*.mp4
backend/landscape-qualification-evidence/landscape-qualification-evidence.json
backend/landscape-qualification-evidence/landscape-qualification-summary.md
backend/landscape-qualification-evidence/threshold-lock-before.json
backend/landscape-qualification-evidence/threshold-lock-after.json
backend/landscape-execution-preflight.json
backend/landscape-runner-hardware.txt
backend/landscape-qa-resource.txt
```

The JSON report records per-case detection coverage, focus span, multi-face samples,
manual focus, dynamic keyframes, framing scores, per-export resolution/codec/duration/size,
render time, and output SHA-256.

The final evidence summary records:

- exact tested SHA
- threshold lock integrity
- 30/30 export completion
- center/manual/dynamic case pass rates
- dynamic-only rescue rate
- multi-face sampled-frame rate
- multi-face case IDs
- the final manual-vs-automatic-reframe product verdict
- GNU `time -v` resource evidence

## One-command production qualification

On the trusted `clipkaro-qa` Linux runner, after the backend QA dependencies and
`opencv-python-headless` are installed:

```bash
export TESTED_SHA="$(git rev-parse HEAD)"
bash scripts/run-real-landscape-qualification.sh
```

The command fails closed unless the final evidence decision is `PASS`.

## Current sandbox diagnostic attempt

The extracted ZIP was also executed in the ChatGPT sandbox to verify failure semantics.
No real product verdict was manufactured.

That attempt recorded `BLOCKED` because the environment was not a valid exact-candidate
qualification host:

- extracted ZIP, not a Git checkout
- Python 3.13 instead of the required Python 3.12 runner
- process running as root rather than the dedicated unprivileged runner account
- no outbound DNS/HTTPS access to the Wikimedia real-media sources
- approximately 5.9 GiB visible RAM (usable for development, below the recommended 8 GB-class repeatability target)

The threshold SHA remained identical before and after the attempt. The diagnostic record is
included in this delivered ZIP under `backend/landscape-qualification-evidence/`.
It is evidence that the run was blocked, **not** evidence about manual or automatic reframing quality.
