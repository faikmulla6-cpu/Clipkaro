# Reference repository audit

The user supplied Stable-TS, WhisperX, and ai-video-captions as technical references. ClipKaro did not copy their complete frameworks or present optional GPU features as locally available.

## Integrated concepts

- **Stable-TS (MIT):** post-verification monotonic timestamp stabilization, minimum word duration, small-overlap midpoint correction, and refusal to invent missing words.
- **WhisperX (BSD-2-Clause):** aligned-word-only production contract; time-overlap-based independent transcript verification; punctuation/conjunction-aware subtitle segmentation.
- **ai-video-captions (MIT):** script/font-aware layout reasoning, visual character-width estimation, deterministic ASS safety, and bundled-font validation.

The resulting modules are ClipKaro-specific implementations designed for faster-whisper output and the 8 GB laptop profile. Full Stable-TS/WhisperX installation remains an optional production-worker upgrade because their PyTorch/alignment/diarization stacks materially increase memory, model, and deployment requirements.

## Repositories

- Stable-TS: `jianfch/stable-ts`, MIT License.
- WhisperX: `m-bain/whisperX`, BSD 2-Clause License.
- ai-video-captions: supplied repository, MIT License (AutoShorts, 2026).

No source files from these repositories are redistributed in the ClipKaro package. Their licenses and architecture were reviewed before implementing compatible concepts.
