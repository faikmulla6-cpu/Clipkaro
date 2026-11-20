# Cartoon Studio V2 — Remotion + HyperFrames Design

Status: design baseline, isolated feature branch only
Branch: `feature/cartoon-studio-remotion-pipeline-20261120`
Base: `569d8462d68931a5c3b8d3e2405a3685be0b10e3`

## 1. Reference project audit

The supplied `jannat-editable-projects.zip` contains an editable Remotion project and a HyperFrames project.

Verified source details:

- Remotion `4.0.545`; HyperFrames `0.9.72`.
- 30 seconds, 1920×1080, 30 fps, 900 frames.
- A single reusable, hand-authored SVG character rig is animated by a deterministic time-based Remotion function.
- The bedroom, lighting, props, camera framing, facial expressions, body poses and transitions are drawn/animated in the Remotion composition.
- The final HyperFrames project places the muted animation MP4 and separate narration, dialogue, score and foley audio tracks on its timeline.
- Voice is Microsoft Edge TTS `ur-PK-UzmaNeural` via the `edge-tts` Python package; narration and dialogue are separate assets.
- The TTS stream records `WordBoundary` events into `narration-words.json` and `dialogue-words.json`. Edge TTS offsets/durations are in 100-nanosecond ticks and must be converted to seconds by dividing by 10,000,000.
- A separate `lip-envelope.json` is sampled at 60 Hz from the actual dialogue audio and drives the mouth-open amount.
- Music and foley are synthesized deterministically with NumPy and retained as editable stems.
- The reference project's own SPEC and README explicitly say there are no visible subtitles/captions. The word-boundary JSON is timing metadata that can be used to build captions, but it is not itself a caption renderer.
- The sample lip movement is audio-energy based, not phoneme-perfect lip sync.

## 2. Original ClipKaro baseline at base commit 569d8462

The merged Cartoon Studio code already uses GLM 5.3 Flash through OpenRouter for structured story planning and uses HyperFrames for final rendering. It currently:

- Generates a small JSON storyboard with characters and scenes.
- Generates each scene's dialogue using the selected OpenRouter TTS model.
- Draws simple SVG character and environment templates.
- Creates scene-level dialogue cards and uses repeated mouth-scale cycles.
- Does not capture word-boundary timings.
- Does not build a Remotion animation MP4.
- Does not create independent narration, music and foley stems.

The current code is a functional MVP, but it is not the same rendering architecture as the supplied reference.

## 3. V2 target pipeline

1. **GLM Story Director** — keep GLM as the only story-planning LLM. Produce validated JSON: story bible, character identity locks, scene/shot timeline, actions, expressions, camera moves, dialogue, narration and sound cues. Never ask the LLM to emit executable Remotion/HTML/JS.
2. **Persistent Character Bible** — store immutable identity attributes (face proportions, hair, costume, palette, species, voice identity) and per-shot animation parameters separately. Reuse the same character rig across every scene and episode.
3. **Remotion Animation Renderer** — render a deterministic, data-driven 2D rig and detailed environment from storyboard JSON. Support 9:16, 16:9 and 1:1; use 30 fps initially. Build reusable body/head/arms/legs, eye/blink, brow, mouth, hair, props, lighting and camera systems. Use actual action keyframes rather than idle-only motion.
4. **Speech and timing** — create separate narration and per-speaker dialogue files. Prefer a TTS provider that returns word-boundary events. For Edge TTS, preserve the exact WordBoundary output and convert ticks to seconds. If a provider does not return alignment, use a separately validated forced-alignment step; never pretend estimated word timing is exact.
5. **Audio analysis and lip motion** — derive a 60 Hz RMS/energy envelope from the actual dialogue audio, with silence gating and per-line offsets. This improves mouth timing but must be labelled energy-driven, not phoneme-perfect.
6. **Caption compositor** — create visible subtitles from the word-timing records. Use RTL-safe Urdu rendering, punctuation-aware phrase grouping, readable safe margins and active-word highlighting. The source reference has no visible captions, so this is a deliberate ClipKaro addition.
7. **Audio stems** — keep dialogue, narration, score and foley as separate HyperFrames tracks. Generate or select music and sound effects from the scene's sound cues; normalize and limit the final mix.
8. **HyperFrames final assembly** — place the Remotion animation MP4, captions, and separate audio stems on a deterministic HyperFrames timeline; run project checks and render final MP4.
9. **QA** — inspect frames at shot boundaries and dialogue moments; verify dimensions, fps, duration, audio stream, subtitle timing/order, Urdu RTL rendering, no clipping, character identity consistency, and final output size.

## 4. Caption data contract

Canonical normalized word record:

```json
{
  "text": "خواب",
  "start_seconds": 0.398,
  "end_seconds": 0.810,
  "speaker_id": "jannat",
  "track": "dialogue",
  "source": "tts_word_boundary"
}
```

Rules:
- Keep original Urdu text exactly as generated/approved; do not rewrite it during timing.
- Convert Edge TTS `offset` and `duration` ticks using 10,000,000 ticks per second.
- When a provider reports zero duration for a boundary, derive the display end from the next boundary or a conservative bounded fallback; mark the timing source.
- Add the scene's global audio start to every local word timestamp.
- Reject negative, non-monotonic or out-of-audio-range timings.
- Phrase captions should be grouped by punctuation and line length, but each word retains its own timestamp for karaoke highlighting.
- Caption visibility is separate from dialogue-card metadata; no caption should cover a character's face.

## 5. Voice strategy

- GLM remains responsible for story planning; it is not replaced with GPT-6.
- The supplied sample's Urdu female voice is `ur-PK-UzmaNeural` from Edge TTS, not a ChatGPT voice.
- A system-voice adapter can reproduce the sample's voice and native word boundaries for Urdu. Keep the existing OpenRouter TTS adapter as an option for other languages/providers.
- Do not silently claim word-perfect captions for OpenRouter TTS unless its output has been aligned.
- Before production, verify the Microsoft Edge TTS service terms/reliability for commercial use; the Python package is a client to the service, not an Azure Speech contract.

## 6. Licensing and release gate

Remotion is source-available under its own license, not OSI open source. Current official pricing says individuals and companies of up to 3 people may qualify for its free license, including commercial automation; organizations that do not qualify need a Company License. The Automators option is listed at $0.01 per render with a $100/month minimum.

Official references:
- https://www.remotion.dev/docs/license/pricing
- https://www.remotion.dev/docs/terms
- https://www.remotion.dev/docs/license/faq

Do not deploy the Remotion-backed pipeline to production until ClipKaro's Free License eligibility or required Company License is confirmed. This branch can be used for a bounded evaluation/prototype while eligibility is checked.

## 7. Implementation phases

- **Phase A — Scene renderer integration:** per-scene Remotion MP4 rendering from GLM storyboard props, 9:16/16:9/1:1 layouts, audio-energy mouth movement and HyperFrames assembly.
- **Phase B — Caption/audio quality:** visible Urdu/English captions, native word timing, word highlight, RTL handling, caption preview and end-to-end timing tests.
- **Phase C — Reference-faithful scene templates:** detailed bedroom-drama template, memory/prop cutaways, better pose and camera choreography, persistent character bible across episodes.
- **Phase D — Audio and product controls:** separate narration/dialogue/music/foley stems, editable caption preview, voice selection, retry reuse, cost/usage display and final export.
- **Phase E — Production readiness:** license review, Modal image build, smoke render, full QA, staging deployment and only then production rollout.

## 8. Safety and rollout boundaries

- Work only on this isolated feature branch until reviewed.
- Do not modify production data or deploy this branch during development.
- Preserve existing Cartoon Studio fallback until the Remotion path passes parity and regression tests.
- Never log OpenRouter keys or speech-provider credentials.
- Keep all source prompts and storyboard text treated as untrusted data when generating markup.

### Dependency notes

- The current PyPI release found during this review is `edge-tts 7.3.1`, licensed LGPL-3.0. Include its license notice and comply with LGPL distribution requirements if it is shipped in the worker image. PyPI reference: https://pypi.org/project/edge-tts/7.3.1/
- `edge-tts` is a client library that communicates with the Microsoft Edge speech service; do not describe it as an official Azure Speech API or promise service-level reliability.

## Findings from the supplied Jannat reference project

I inspected both `jannat-urdu-drama.mp4` and every relevant source file in `jannat-editable-projects.zip`.

### What the reference actually does

- The reference video is a 30-second, 1920×1080, 30fps Remotion animation.
- `remotion/src/film.js` is a deterministic, time-seekable SVG film renderer. Its `renderFilm(t, envelope)` function draws a detailed bedroom, window/moonlight, door, bed, Jannat's character rig, facial expressions, blanket movement, memory insert, and camera changes.
- The character and room are hand-authored vector artwork. They are not generated as unrelated AI images on every frame. That is the key to consistent character identity.
- `remotion/src/Composition.tsx` calls `renderFilm` for each Remotion frame at 30fps.
- `scripts/make_voice.py` uses the Urdu voice `ur-PK-UzmaNeural` and Edge TTS `WordBoundary` events. The JSON word offsets/durations are in 100-nanosecond ticks.
- `scripts/make_audio.py` uses FFmpeg to decode the dialogue track and computes a 60Hz RMS audio-energy envelope. Remotion uses this envelope to animate the character's mouth. This is audio-energy lip movement, not phoneme-perfect visemes.
- HyperFrames is the final audio mixer. The project has separate narration, dialogue, score, and foley tracks with independent start times, durations, and levels.

### Important correction about captions

The supplied reference MP4 does **not** display visible subtitles/captions. The ZIP contains `dialogue-words.json` and `narration-words.json` timing data, which are used for speech alignment/lip animation and can also power captions. Its own review/spec files state that there are no visible captions or text overlays.

ClipKaro should retain the reference's word-timing data and add a separate subtitle layer: Urdu RTL captions, grouped into readable phrases, with optional per-word highlighting. Caption timing must come from the TTS word events when available; text-estimated timing is a clearly marked fallback.

## Current implementation status in this isolated branch

- GLM 5.3 Flash remains the story-planning model; no GPT-6 dependency was introduced.
- The generation job now renders each validated storyboard scene with Remotion's `ClipKaroScene` composition. Scene props include the environment, expression, motion, camera move, selected characters, aspect ratio, and dialogue start.
- Remotion renders a separate silent scene MP4. HyperFrames then composes those scene plates with dialogue audio and visible caption overlays, validates the project, and renders the final MP4.
- The generic Remotion rig supports 9:16, 16:9 and 1:1, ten environment types, multiple character species, basic expressions/motion, camera moves and a 60 Hz speech-energy mouth envelope.
- Added an optional `System Urdu Voice · Word-timed` TTS model using `ur-PK-UzmaNeural` / `ur-PK-AsadNeural`. Edge TTS WordBoundary ticks are normalized to seconds and used for Urdu captions; OpenRouter TTS uses explicitly marked estimated timing.
- Added bounded retries and a short pause between sequential Edge TTS requests because the external speech service did not return audio on every repeated test call.
- Added RTL-safe phrase captions, active-word highlighting, safer caption positioning and audio-energy extraction from the actual generated speech.
- The supplied Jannat bedroom/blanket/memory/door rig is now available as the dedicated `cinematic-jannat` preset; the generic Remotion styles remain separate.
- The Jannat production branch now creates separate narration, dialogue, original procedural score and bedroom-foley tracks, with native Urdu word timing and active-word captions.
- The new Remotion path has been developed on this isolated branch; it has not been merged into the working branch or deployed from this branch.

## Initial implementation snapshot — 2026-11-20 (superseded by the Jannat update below)

The first integrated Remotion + HyperFrames path is now implemented in the working branch.

### Pipeline now in code

1. **Story planning:** OpenRouter model is pinned to `z-ai/glm-5.3-flash`; no GPT-6 dependency is used.
2. **Voice:** Urdu female system voice uses `ur-PK-UzmaNeural` through the Edge speech service. Its native WordBoundary offsets are converted from 100 ns ticks to scene-relative seconds. Other TTS providers use explicitly marked estimated timing.
3. **Mouth movement:** FFmpeg decodes the speech asset to mono PCM; a smoothed 60 Hz RMS envelope is passed into Remotion to drive the speaker's mouth opening. This is speech-energy lip motion, not phoneme/viseme-level lip sync.
4. **Animation:** The `ClipKaroScene` Remotion composition renders each storyboard scene as a separate H.264 plate. It supports 9:16, 16:9 and 1:1, consistent character appearance, expression/motion/camera props, and an initial bedroom set for `home` scenes.
5. **Final composition:** HyperFrames assembles the muted Remotion plates with separate dialogue audio and RTL word-timed captions. GSAP highlights the currently spoken word. Scene-direction text is not burned into the video.
6. **Deployment packaging:** The media Docker target now copies the Remotion source/config and installs the pinned Remotion CLI with the existing HyperFrames runtime.

### Verification completed

- Python test suite: **24 passed**, with two upstream Starlette/httpx deprecation warnings.
- HyperFrames validation on the 5-second Urdu integration sample: `ok: true`, zero layout/runtime/audio findings.
- End-to-end smoke output: 1080×1920, 30 fps, H.264 video plus AAC audio, 5 seconds.
- Urdu voice smoke: 3.312-second MP3, eight native word-boundary events verified separately; the speech-energy envelope contains 199 samples.

### Not yet complete / do not assume

- The smoke render is a pipeline qualification sample, not a production episode.
- Edge TTS calls an external speech service; availability may vary. It does not use OpenRouter TTS credits.
- Word timing from non-Edge providers remains estimated unless that provider supplies alignment metadata.
- Music, foley and separate narration generation are not yet wired into the production job; the current live audio path is dialogue.
- The bedroom is the first detailed environment kit; the other environments still need richer set artwork and visual QA.
- The updated media Docker image has not yet been built or deployed. No production project or customer data was modified by this work.


## Progress update — 2026-11-20: Jannat reference preset

The supplied Jannat Remotion artwork has now been integrated as a dedicated cinematic preset on this feature branch.

### Implemented

- Imported the hand-authored Jannat SVG film renderer into `backend/cartoon_engine/remotion/src/templates/jannat/film.js` and wrapped it in a new `ClipKaroJannatCinematic` Remotion composition.
- Retained the reference's recurring character, teal outfit, moonlit bedroom, bed, window, door, camera choreography, expressions and pose changes.
- Connected the renderer to one episode-wide 60 Hz speech-energy envelope. This is audio-energy mouth movement, not phoneme-perfect visemes.
- Added the `cinematic-jannat` style to the Cartoon Studio API and UI. Selecting it locks the settings to 30 seconds, 16:9, Urdu and the built-in System Urdu word-timed voice.
- Constrained GLM story planning for this preset to exactly three 10-second scenes. The job locks all scenes to the same Jannat character, female voice and bedroom environment.
- Added a dedicated production-job branch: render one continuous 30-second Remotion episode, split it into three scene plates, then pass those plates, separate narration/dialogue, original score, bedroom foley and native Urdu word timings to HyperFrames.
- Kept the generic Remotion cartoon style as the default and retained the other styles as alternatives.
- The editable audio folder preserves narration/dialogue word-boundary JSON, voice settings, the episode lip envelope and deterministic score/foley metadata; score and foley are 48 kHz, 16-bit stereo WAV stems.

### Verification completed

- Frontend `npm run build`: completed successfully, including TypeScript and all 49 static pages.
- Focused Cartoon Studio / timing / Remotion / caption / speech / audio / score / HyperFrames / production-alignment tests: **39 passed** with two upstream Starlette/httpx deprecation warnings.
- Real Edge TTS Urdu smoke: `ur-PK-UzmaNeural` generated a 12-word narration and three dialogue tracks with 8 native WordBoundary events each; the episode lip envelope contains 1,800 samples at 60 Hz.
- Full 30-second HyperFrames smoke project: the check command exited successfully. The smoke harness did not retain an accessible per-category report after completion, so lint/runtime/layout/audio counts for this specific 30-second run remain unverified. A separate Urdu caption integration sample has a retained `check.json` with `ok: true` and zero lint, runtime, layout and audio findings.
- Final smoke MP4: H.264 1920×1080 at 30 fps, AAC audio, exactly 30 seconds, 8,153,674 bytes. The mixed audio measured -26.4 dB mean and -5.0 dB peak; no clipping was detected.
- Opening, narration, dialogue and ending frames were visually inspected. Jannat remains visually consistent, Urdu RTL captions display separately for narration and dialogue, and active-word highlighting is visible.
- Full backend suite after all current changes: **791 passed, 5 skipped, 0 failed** in 333 seconds. It reports 257 existing warnings, mainly short test JWT signing keys and Starlette/httpx deprecations; no Cartoon Studio test failed.

### Boundaries still in place

- The smoke MP4 was generated from the production Remotion and HyperFrames components/builders with real Urdu TTS and procedural score/foley. It is not evidence that a live OpenRouter GLM request and the complete queued worker job have been exercised end to end. No billable OpenRouter request was made for this smoke.
- The preset has not been deployed, merged or used to modify production/customer data. The connected Windows workstation does not have Docker installed, so the updated media/worker image has not been built.
- Separate narration, score and foley are implemented for the Jannat preset only; the generic cartoon styles still use their existing dialogue-focused audio path.
- Edge TTS is an external Microsoft Edge speech service client. Commercial-use terms, reliability and fallback policy still need review.
- **Remotion license eligibility remains a release gate.** Do not deploy the Remotion-backed pipeline until ClipKaro confirms eligibility for the applicable free license or obtains the required company license.
