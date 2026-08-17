# ClipKaro AI v7.5 — OmniVoice Engineering Integration

## Scope

The supplied OmniVoice Studio archive was security-screened and studied as an engineering reference. ClipKaro does not import the full application or its unrelated TTS engines.

## Adopted patterns

- Token-level Levenshtein word-error-rate consensus replaces character similarity.
- Per-segment consensus now penalizes missing words, inserted filler, and repetition directly.
- FFmpeg and FFprobe candidates must execute `-version`; PATH presence is no longer treated as proof of a working Windows installation.
- Metadata probing, audio extraction, OCR frame sampling, rendering, and export validation use the validated executable paths.
- Audio extraction uses non-interactive, bounded 16 kHz mono PCM decoding suitable for ASR.
- Pipeline provenance is bumped to v7.5, forcing older transcripts through the stricter verifier.

## Intentionally rejected behavior

OmniVoice falls back to native Whisper timestamps when forced alignment fails. ClipKaro's verified-export policy does not allow this silent degradation: draft timing may remain editable, but precise-caption export must be blocked until alignment passes.

## Verification

- 41 backend tests pass.
- Python compilation passes.
- Added tests cover WER insertions, deletions, and repeated filler rejection.
- Existing language, caption layout, timestamp stabilization, rendering, OCR, provenance, and API tests remain green.

## Next integration

Add WhisperX/wav2vec2 forced alignment as an optional production worker with strict failure gating and hardware preflight. It should not be enabled by default on the user's 8 GB CPU-only Windows laptop.
