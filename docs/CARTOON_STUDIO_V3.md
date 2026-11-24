# Cartoon Studio V3: directed stories

Base: e6ca3361fe52afcc2104bd7930368af9513c39df, the merge of PR 120 into the Hostinger branch.
Feature: feature/cartoon-studio-story-animation-v3-20261121.

## Reference assessment

The reference was extracted and its complete ZIP structure inspected. Sequential frames
across its 30 seconds show keyed waking/sitting poses, a close-up, a pendant memory,
and a door hold. Its mouth follows a sampled audio envelope; it has no word captions
and its standing movement is simplified. It is a benchmark, not a universal animation system.

The downloaded failed standard export holds the same small standing rig in a bedroom.
FFmpeg at -36 dB finds about 22.4 seconds of quiet, with three gaps over six seconds.
In the previous general pipeline, GLM's action sentence was discarded. Character
positions were fixed; narration, score and foley were only synthesized in the Jannat
special path. The reference path also forced 30 seconds and 16:9.

## Execution architecture

GLM returns a data-only schema_version 3 director plan. cartoon_story.py validates
stable character IDs, appearance, supported environments, props, positive action
windows, camera focus IDs, speech and sound cues. Unknown actions and dangling
references fail before rendering. No model-authored HTML, JavaScript, shell, CSS or
remote asset URLs are executed.

StoryEngine.tsx is an independently implemented ClipKaro-owned Preact/SVG biped rig
and timeline executor. Preact is a DOM renderer, not a video timeline dependency.
HyperFrames drives seekable frame time and exports through FFmpeg. There is no
Remotion dependency in the production engine.

Timed actions execute sleep/wake, sit/stand, walk/run, jump, head/gaze, blink,
wave/point/reach, emotional reactions, pickup/putdown and door open/close.
Hands use a two-bone reach solution. Low pickups bend the torso and knees while
the feet remain on the floor. Props may rest on a validated support_id table,
bed or chair. Carried objects follow the hand. Articulations remain stylized;
this is limited 2D animation, not a general physics simulation.

Camera keyframes use wide, medium, close and detail shots. Interaction windows
stay wide enough to include the hands/prop. Framing and stage geometry are
recomputed at 9:16, 16:9, 1:1 and 4:5. These are native layouts, not stretched
landscape images. A PostgreSQL migration expands the ratio CHECK constraint;
the SQLite bootstrap preserves rows when rebuilding that constraint.

## Speech, captions and audio

Every planned narration/dialogue line gets a distinct, content/voice/model-hashed
cached asset. Character voice IDs persist. The selected lead voice also narrates.
Speech scheduling uses measured audio length and shifts conflicting lines with a
200 ms gap. A line that cannot fit its scene fails rather than being cut off.
Native TTS word boundaries are preferred. Providers lacking them use ClipKaro's
existing audio ASR alignment pipeline, which may use the configured transcription
provider. Failure to align fails the job; estimated scene timestamps are not used
for V3 captions. Hinglish ASR display text is romanized; native Urdu stays RTL,
Hindi and Roman Hinglish stay LTR.

Caption phrases have their true speech span and per-word highlights. Mouth motion
uses the measured speech envelope with a simple rounded/open viseme hint, so it is
not phoneme-perfect. Only the current dialogue speaker moves their mouth.
Narration does not animate a character's lips.

Original procedural music, environmental ambience and sound cues are separate
editable WAV stems for every story, with speech ducking and edge fades.
These are deliberately simple musical/foley primitives, not a large licensed
sound library. The final MP4 is probed for ratio, duration, audio presence and
unexplained digital silence. Editable packages contain timeline, storyboard,
audio provenance, local assets and source rig files without credentials.

## Deterministic qualification

The committed fixtures cover Jannat suspense, a fox recovering a ball in a garden,
and two people finding a book and operating a door in a school/workshop.
Saved MP3s include native word timestamps and checksums. Normal qualification
never contacts GLM, OpenRouter, Edge TTS or an ASR provider.

From backend:

    python scripts/cartoon_story_v3_qualification.py --case library --ratio 4:5 --out /tmp/library-4x5

The explicit --prepare-audio flag is only for refreshing fixture speech outside
render tests. The Node test in cartoon_engine renders VNode trees at several
times and all four ratios, checks seek determinism, and tests movement/prop state.
Python tests cover schema failures, mocked GLM, missing narration, actual word
timing, speech conflicts, bounds, language direction, all 12 story/ratio
combinations and preserving SQLite data during ratio migration.

cartoon_story_v3_preflight runs a saved fixture in the deployed Modal media image
and returns engine/source fingerprints and render verification without AI calls.

## Deployment and compatibility

Legacy saved storyboards retain the existing pipeline. GLM and NVIDIA plans use V3.
Deploy the compatible backend/modal_app.py build first, then apply migration
20261122_15 to enable saved NVIDIA keys. The migration preserves existing keys.
If reverting to a backend that requires 20261121_14, downgrade the Alembic
revision before rolling back. The widened constraint and saved keys are retained.
Hostinger must merge/build this feature into
work/secure-smart-layout-v2-20261018, never main.
The authenticated /api/v1/cartoon-studio/capabilities endpoint identifies the V3 API.
The separate Modal preflight verifies the worker; a frontend page loading or a
PR merging alone does not verify the deployed worker.

## Current limits

- Fixed supported action/prop/environment vocabulary, with validation errors for unsupported actions.
- Stylized biped articulation and approximate energy/viseme lip motion.
- Arbitrary remote images, custom drawn rigs and physics are not executed from model output.
- Speech still depends on the selected external provider; non-native alignment uses existing ASR.
- A story whose generated speech cannot fit fails with an actionable timing error.
- The existing Next.js release emitted a security advisory during build. It needs a separate security upgrade.
