# ClipKaro Remotion scene renderer

This is the Remotion layer used by the Cartoon Studio generation job.

## Generic scene composition

- Entry point: `src/index.ts`
- Composition ID: `ClipKaroScene`
- Main scene component: `src/CartoonScene.tsx`
- Input: one validated GLM storyboard scene, its character records, aspect ratio, dialogue start time, and a 60 Hz speech-energy envelope.
- Output: a silent MP4 scene plate. The backend renders one plate per storyboard scene.
- Final assembly: HyperFrames combines the scene plates with timed captions and the scene dialogue audio.

Supported output ratios: 9:16, 16:9, and 1:1.

The reusable generic rig is data-driven and supports several environments, human and animal character species, basic expressions, simple movement, camera motion, and audio-energy mouth animation.

## Jannat cinematic reference preset

- Composition ID: `ClipKaroJannatCinematic`
- Component: `src/JannatCinematic.tsx`
- Reference renderer: `src/templates/jannat/film.js`
- Input props: `durationSeconds: 30` and `episodeLipEnvelope` (1,800 samples at 60 Hz).
- Output: one continuous 30-second, 1920×1080 cinematic animation, split by the backend into three 10-second scene plates.
- The imported hand-authored SVG rig retains Jannat's consistent face, long dark hair, teal outfit, moonlit bedroom, bed, window, door, camera choreography and pose changes.
- The first scene includes the wake-up sequence, the middle scene the door/memory beat, and the final scene Jannat standing toward the door.

For this preset, the backend adds separate Urdu narration and dialogue tracks, a deterministic original D-minor suspense score, and procedural bedroom foley. Native Edge TTS word timings drive RTL captions and active-word highlighting. The same 60 Hz dialogue-energy envelope drives the Jannat mouth animation; it is energy-based lip motion, not phoneme-perfect visemes.

## Local sample

Run a generic sample from `backend/cartoon_engine`:

```powershell
npm ci
npm run remotion:render
```

The production worker invokes the generic composition per scene for other styles. For the Jannat preset it renders the continuous cinematic composition once, then splits it into three plates. Do not replace the HyperFrames final-mix stage: it owns captions, independent audio tracks, validation, and the final MP4.

## Release gates

- Confirm the applicable Remotion license eligibility before deploying the Remotion-backed pipeline.
- Review Edge TTS service terms, availability and fallback behavior before commercial rollout.
