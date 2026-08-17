# ClipKaro AI Quality Release

## Release decision

This build is fail-closed for speech accuracy. It no longer treats a completed ASR call as proof that a transcript is valid. Repeated tokens, collapsed word timestamps, implausible speech rates, non-speech, decoder compression loops, and incompatible scripts are rejected before clips are saved.

## Corrected failure chain

- Hindi/Urdu and uncertain English detection receives a Hindi retry.
- `small` multilingual Whisper replaces `base` as the local default.
- A stricter second decode runs when the first transcript fails quality checks.
- Only verified segments reach clip selection and caption rendering.
- Low-confidence input returns a specific error and produces zero fake suggestions.
- Model downloads use a stable writable cache, with required HTTP dependencies included.
- Frontend API connection failures now explain that the backend on port 8000 must be running.

## Verification

- Backend: 19 tests pass, including regressions for repeated “Sir”, zero-duration words, and wrong-script Hindi.
- Frontend: Next.js production compilation and TypeScript validation pass.
- Production output still requires human-labeled Hindi/Hinglish benchmark media before any claim of commercial transcription parity. Whisper confidence is not treated as ground truth.

## Recommended production upgrade

Run WhisperX alignment and speaker diarization on a GPU worker, and benchmark Hindi against AI4Bharat IndicConformer/IndicWhisper using word error rate and timestamp boundary error. Keep the local CPU pipeline as a guarded creator workflow, not an accuracy oracle.
