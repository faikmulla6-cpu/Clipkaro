# ClipKaro Cartoon Engine

The first release creates deterministic, editable 2D cartoon scenes with SVG character rigs, GSAP motion and HyperFrames rendering. Each scene is a native HyperFrames subcomposition with its own timeline; the root composition sequences scenes and dialogue audio. GLM produces validated storyboard JSON only; it never writes executable HTML or JavaScript. OpenRouter BYOK supplies story planning and per-character TTS. Kokoro 82M is the low-cost default for Hindi/English; choose a broader multilingual model when needed. FFmpeg converts audio, validates and muxes the final MP4.

## Runtime

- Node.js 22+
- HyperFrames 0.9.70 (Apache-2.0)
- GSAP 3.15.0
- Chromium + FFmpeg/FFprobe
- Python worker calls the pinned HyperFrames CLI from the isolated media job.

## Agent skills

Codex instructions are in AGENTS.md and Claude Code instructions are in CLAUDE.md. The matching upstream HyperFrames skills are installed under the repository's .agents/skills and .claude/skills directories.

## Security model

- User provider keys are encrypted at rest with the existing dedicated POST_KARO_ENCRYPTION_KEY, using a Cartoon Studio-specific encryption context.
- Keys are decrypted server-side for OpenRouter model discovery in the API and for story/TTS generation in the isolated media job. They are never returned to the browser, placed in job payloads or written to logs.
- The LLM returns a constrained JSON storyboard. The renderer allow-lists species, colours, environments, motions and expressions; no model-generated code is executed.
- Reference videos are quarantined, malware-scanned in the media worker, sampled to a few frames for style analysis, then deleted.
- AI inference and TTS are billed by the user's OpenRouter account. ClipKaro does not fall back to a platform-owned key.

## MVP limits

The first beta supports original 2D cartoon animation, 15/30/45/60 second durations, 9:16/16:9/1:1, Hindi/Hinglish/English/Marathi story text, optional reference video analysis and stable voice presets per character. It is not a text-to-video model and does not promise photorealistic or Pixar-style 3D animation.
