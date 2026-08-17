# Controlled ElevenLabs Roman Hinglish promotion

This is an opt-in Hinglish-only route, not a replacement for Hindi, Marathi, or
the default Groq to Cloudflare API ASR path.  It is practically validated for
caption/export QA but **failed the frozen strict Roman ASR benchmark P90 gates**.

Default (safe rollback / no public activation):

```ini
HINGLISH_ASR_PROVIDER=legacy
ROMAN_HINGLISH_ENABLED=false
```

Internal staged enablement requires the private worker environment to contain
`ELEVENLABS_API_KEY`, then set:

```ini
HINGLISH_ASR_PROVIDER=elevenlabs
ROMAN_HINGLISH_ENABLED=true
ROMAN_HINGLISH_POLICY=v3
ROMAN_HINGLISH_DISPLAY_POLICY=v1
```

Restart the media worker and inspect `/api/v1/system/preflight`.  The route is
only selected for `hinglish` / `roman_hinglish` job metadata.  ElevenLabs Scribe
v2 preserves native word timing, then V3 and Display V1 set only caption
`display_text`; original text and timestamps remain intact.  Operational
failures (timeout, rate limit, 5xx, connectivity, malformed/empty response)
use the existing Groq then Cloudflare route.  Authentication/configuration
errors fail clearly and do not spend fallback quota.

Rollback is immediate: set `HINGLISH_ASR_PROVIDER=legacy`, restart/redeploy.
No code deletion, GitHub synchronization, VPS, GPU, WhisperX, or local Whisper
runtime is involved.  Source videos with burned-in captions can still visually
show both their source subtitle layer and ClipKaro's one caption layer; this is
a source-content limitation, not an internal duplicate overlay.
