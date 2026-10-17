# Karo Smart Layouts

## Product contract
The Clipkaro Short editor has a Frame > Karo Smart Layouts selector.
- Auto Director: choose based on visible speakers and mouth/audio evidence.
- Dual Stack: two individually cropped speaker panels, separated by a caption band.
- Speaker Focus: one speaker fills the vertical frame; transition eases over about 0.4 seconds, with a minimum hold to prevent rapid switching.
- Classic: preserve the existing manual crop and zoom.

The editor now **changes the live canvas when a layout is selected**, without using an export credit. Classic is the safe default; Dual Stack and Auto Director immediately show two synchronized, muted/non-muted speaker panels and a middle caption band, while Speaker Focus displays a portrait crop. This instant preview is a **layout composition guide**, not a claim that browser CSS has analyzed the faces. The actual export samples and analyzes the original frames (on the private CPU media worker) and adapts separately for each scene. When a shot has fewer than two real visible faces, Dual Stack deliberately becomes a safe single-speaker portrait; if no face can be located it retains the full source width against a blurred backing. This prevents fake duplicates and left/right seams. The selector is supported on 9:16 only; choosing Smart Layout opts out of the incompatible Preserve burned-in source captions toggle.

## Implementation
- backend/app/services/karo_smart_layouts.py: CPU video/face sampling, speech attribution, composition and safe fallback.
- backend/app/services/render_gate.py: precompose new layout before existing caption, hook, Smart Edit and export logic.
- backend/app/schemas/api.py: validated layout_mode.
- backend/app/api/routes.py and backend/app/media_job.py: identical export modes for normal and Modal durable workers.
- backend/modal_app.py: OpenCV and numpy **only** in the CPU media image.
- frontend/app/editor/[clipId]/page.tsx: Frame-mode selector.
- backend/tests/test_karo_smart_layouts.py: independent behavioral and actual FFmpeg render checks.

The pipeline never reconstructs missing people. Each camera shot is analyzed independently (with a bounded sample count and a maximum of 24 FFmpeg scene compositions). True Dual Stack is reserved for scenes with two separated, co-visible faces in most samples. Single-face scenes are focused as one portrait, and no-face scenes use a full-width safe fit, preserving original content without an incorrect face crop. All per-scene FFmpeg parts get square-pixel aspect ratio before concatenation. A technical FFmpeg error is surfaced as an error rather than silently substituting a different export. The encoder uses 1080x1920 for 1080p purchases. This is still an OpenCV frontal-face detector, not a complete side-profile/occlusion model; its accuracy must be evaluated on a variety of real podcasts.

## Sources and future work
Design draws on MIT-licensed OpenShorts source: openshorts-main/openshorts-main/split_layout.py, active_speaker.py, reframe_v2.py and layout_ranges.py. It reimplements the relevant ideas using Clipkaro's own API and FFmpeg rendering, including per-person mouth normalization, hold decisions and middle captions.

See https://ffmpeg.org/ffmpeg-filters.html for crop, fps, scale and vstack.

Potential future improvement: a private on-demand rendered preview with real per-scene face analysis, instead of the current immediate geometry guide. Browser preview uses only the authenticated source URL; the renderer processes in an isolated Modal media worker with the same project permissions/validated storage keys as the existing export job. No face/audio data is sent to new third-party APIs. Audio diarization alone cannot associate a voice reliably with a visible face.

## Validation checklist
1. Synthetic Dual Stack and Speaker Focus FFmpeg export (automated).
2. Portrait input, missing/occluded face, 3+ people, long podcast, actual two-person dialogue, overlapping speech and background music (real video tests still needed).
3. Final 720p/1080p MP4 caption centering, existing watermark and Smart Edit timeline.
4. Modal deployment smoke test and Hostinger frontend release.
