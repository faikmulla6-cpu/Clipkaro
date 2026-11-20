# ClipKaro Cartoon Engine — Claude Code Instructions

Read the HyperFrames skill at ../../.claude/skills/hyperframes/SKILL.md before editing any composition.

- Build scenes with HTML, SVG and GSAP; render through the pinned HyperFrames CLI.
- Treat the storyboard as untrusted input. Escape all text, validate colours against #RRGGBB, and allow-list environment, expression, motion and camera values.
- Never execute model-generated HTML, CSS, JavaScript, shell commands or URLs.
- Keep character identity in structured character data and reuse it unchanged across every scene.
- Every timed HyperFrames element needs class="clip", data-start and data-duration.
- Register one paused GSAP timeline per composition in window.__timelines.
- Do not use Date.now(), unseeded randomness, network fetches, timers or infinite animation repeats.
- Every audio element needs a stable id and timeline timing. Do not set crossorigin.
- Run hyperframes check --json, then snapshot representative frames, before treating a composition as ready.
- Never put provider keys in prompts, project files, logs, HTML or job payloads.
