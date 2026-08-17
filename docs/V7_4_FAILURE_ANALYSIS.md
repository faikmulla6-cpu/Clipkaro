# ClipKaro AI v7.4 — Caption Replacement and Hindi Accuracy

## Evidence from `clipkaro-short(6).mp4`

- The 36.24-second export is technically valid H.264/AAC at 720×1280 and 25 fps.
- The source contains a large burned lower caption that is horizontally truncated after 9:16 cropping.
- ClipKaro added a second, smaller kinetic caption layer, creating visible duplication.
- Roman-Hinglish output contains phonetic decoding errors such as `ieenjheenairim` and `tumahanee`; these are transcription errors, not merely font or layout defects.

## Corrective architecture

- OCR now returns the source caption band, not only a Boolean result.
- The renderer masks only the platform-unsafe lower band before it draws the verified caption layer.
- The mask is clamped to the lower 24%–6% of the frame so signage or detected text higher in the picture cannot create an oversized panel.
- Hindi accuracy mode now uses `medium` as the primary model instead of `small`.
- Hindi/Hinglish decoding receives a non-content-bearing language prompt and common English technical hotwords.
- Pipeline provenance is bumped to v7.4, automatically invalidating and rebuilding every older transcript.

## Verification

- 39 backend tests pass.
- Python application compilation passes.
- The supplied export's subtitle OCR detection passes with 100% sampled-frame confidence.
- A direct render test confirms that the old lower caption is suppressed before replacement captions are composited.
