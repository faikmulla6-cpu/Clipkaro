# Karo Smart Layouts

## Product contract
The Clipkaro Short editor has a Frame > Karo Smart Layouts selector.
- Auto Director: choose based on visible speakers and mouth/audio evidence.
- Dual Stack: two individually cropped speaker panels, separated by a caption band.
- Speaker Focus: one speaker fills the vertical frame; transition eases over about 0.4 seconds, with a minimum hold to prevent rapid switching.
- Classic: preserve the existing manual crop and zoom.

The browser preview currently shows the original source. The new layout appears in the **exported 9:16 MP4**, not the editor's browser video element. The API defaults to Classic for older clients; the editor selects Auto Director.

## Implementation
- backend/app/services/karo_smart_layouts.py: CPU video/face sampling, speech attribution, composition and safe fallback.
- backend/app/services/render_gate.py: precompose new layout before existing caption, hook, Smart Edit and export logic.
- backend/app/schemas/api.py: validated layout_mode.
- backend/app/api/routes.py and backend/app/media_job.py: identical export modes for normal and Modal durable workers.
- backend/modal_app.py: OpenCV and numpy **only** in the CPU media image.
- frontend/app/editor/[clipId]/page.tsx: Frame-mode selector.
- backend/tests/test_karo_smart_layouts.py: independent behavioral and actual FFmpeg render checks.

The pipeline never reconstructs missing people. It needs two clearly separated, co-visible faces in a landscape source. If confidence is insufficient, it returns to Classic. Preserving original burned-in subtitles also opts out of Smart Layout. This version uses OpenCV frontal-face detection, not a comprehensive multiview speaker model; real podcast validation is required.

## Sources and future work
Design draws on MIT-licensed OpenShorts source: openshorts-main/openshorts-main/split_layout.py, active_speaker.py, reframe_v2.py and layout_ranges.py. It reimplements the relevant ideas using Clipkaro's own API and FFmpeg rendering, including per-person mouth normalization, hold decisions and middle captions.

See https://ffmpeg.org/ffmpeg-filters.html for crop, fps, scale and vstack.

Later improvements could include MediaPipe face tracking, optional pyannote diarization and an actual in-editor rendered preview. Audio diarization alone cannot associate a voice reliably with a visible face. No third-party speech API or GPU is required for this initial layout pipeline.

## Validation checklist
1. Synthetic Dual Stack and Speaker Focus FFmpeg export (automated).
2. Portrait input, missing/occluded face, 3+ people, long podcast, actual two-person dialogue, overlapping speech and background music (real video tests still needed).
3. Final 720p/1080p MP4 caption centering, existing watermark and Smart Edit timeline.
4. Modal deployment smoke test and Hostinger frontend release.
