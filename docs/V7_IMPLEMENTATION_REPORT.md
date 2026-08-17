# ClipKaro AI v7 — Verified Captions Implementation

## Implemented

- Pluggable secondary Whisper model with independent transcript-agreement scoring.
- Optional fail-closed `REQUIRE_ASR_CONSENSUS`; missing or disagreeing secondary ASR creates no clips.
- ASR model/provider/agreement provenance stored with segments.
- Production export uses only real aligned word timestamps; uniform synthetic timing is disabled.
- Phrase-aware caption cards using punctuation, pauses, duration, word count, and character limits.
- Maximum two lines, 32-character target, reading-speed checks, and safe-area margins.
- The captions API returns the exact cards used by FFmpeg; the Studio preview consumes those cards.
- Bundled OFL Noto Sans Devanagari for deterministic Hindi rendering on Windows and Linux.
- Bounded, time-varying crop keyframes and FFmpeg interpolation instead of static-only focus.
- Complete render validation remains mandatory before an export is marked ready.

## Capability boundary

AI4Bharat IndicWhisper/IndicConformer, WhisperX alignment, pyannote diarization, and automatic face-to-speaker association require production model workers and model assets. v7 provides the verification/layout/crop contracts needed for those workers but does not pretend that local `faster-whisper` is those systems. Configure a genuinely independent `WHISPER_SECONDARY_MODEL` and enable consensus for accuracy-first deployments.

## Quality verification

- 27 backend tests cover API behavior, ASR hallucination gates, transcript agreement, phrase wrapping, invalid timing removal, crop smoothing, rendering, security, and language detection.
- Next.js production build and TypeScript validation pass.
- A real FFmpeg H.264/AAC render was generated from the supplied short with Devanagari hook/captions, two-line wrapping, karaoke highlighting, and animated crop; full probe validation passed.
