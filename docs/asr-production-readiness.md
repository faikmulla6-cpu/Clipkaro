# ClipKaro ASR production-readiness qualification

This document defines what must be measured before the transcription pipeline is called production-ready for public creator traffic.

## Why normal CI is not enough

The ordinary backend CI suite runs with `TRANSCRIPTION_BACKEND=fixture`. That is correct for deterministic API/job tests, but it proves orchestration and validation logic only. It does **not** prove that faster-whisper can understand noisy Indian speech.

The acoustic qualification therefore runs the real production transcription path:

`media -> FFmpeg extraction -> faster-whisper -> auto language detection/retry -> transcript quality gate -> ASR consensus -> timestamp stabilization -> WhisperX forced alignment -> provenance`

Fixture mode is explicitly rejected by the benchmark runner.

## Launch qualification must test Auto detect

ClipKaro's default creator setting is `default_language=auto`, so a launch qualification that forces Hindi, Marathi or Hinglish would test the fallback path rather than the default product experience.

For that reason:

- official `qualification` mode refuses any corpus row whose `language_hint` is not `auto`/blank;
- Hindi, Marathi and Hinglish public-corpus builders all emit `language_hint=auto`;
- an additional hinted smoke sweep separately verifies the creator override path (`hi`, `mr`, `hinglish`).

A green hinted run cannot compensate for a red Auto-detect run.

## Required language coverage

A qualification corpus must contain at least the configured minimum number of sufficiently long cases for each family:

- Hindi (`hi`)
- Marathi (`mr`)
- genuine Hindi-English code-switching (`hinglish`)

Do not replace the Hinglish set with TTS or monolingual Hindi. The point is to test real code-switching, pronunciation and speaker variation. Qualification refuses fewer than two cases per required family even if a caller supplies a lower CLI value.

### Reproducible public speech sources

The helper scripts use/download from these sources:

1. **Google FLEURS** for Hindi and Marathi real speech. Dataset license: CC BY 4.0.
2. **MUCS 2021 Hindi-English** test set for real code-switched speech. The MUCS challenge page lists the Hindi-English test set as CC BY-SA 4.0 and exposes the OpenSLR archive.

The repository stores scripts and metadata only. Audio is downloaded at runtime and is ignored by Git. Every qualification report records the SHA-256 of each corpus case and the real-noise fixtures; if a manifest declares a case hash and the bytes differ, the benchmark fails before inference.

For launch confidence, supplement the public corpora with creator-owned recordings from the actual target market: phone microphones, cheap wired earphones, laptop mics, indoor fan/TV noise, cafés, traffic and outdoor street recordings. Never commit those recordings to Git.

## Required stress matrix

Every corpus case is tested under **all** mandatory scenarios. Qualification refuses a caller-selected subset.

| Scenario | What it probes | Launch p90 WER | Launch p90 CER | p95 RTF |
| --- | --- | ---: | ---: | ---: |
| clean | baseline model/language correctness | 0.28 | 0.18 | 1.50 |
| fast_125 | 25% faster speech | 0.38 | 0.24 | 1.50 |
| fast_145 | 45% faster speech | 0.48 | 0.30 | 1.50 |
| background_noise | moderate broadband background noise | 0.45 | 0.28 | 1.70 |
| street_noise | real environmental noise mixed with speech | 0.50 | 0.32 | 1.80 |
| phone_band | 8 kHz / telephone-band speech | 0.45 | 0.28 | 1.60 |
| low_bitrate | 24 kbps AAC compression | 0.42 | 0.27 | 1.60 |
| clipped | hard clipping / overdrive | 0.50 | 0.32 | 1.70 |
| dropouts | short packet-loss style gaps | 0.52 | 0.34 | 1.70 |
| room_echo | moderate short-room echo | 0.48 | 0.31 | 1.70 |

Additional launch gates per scenario:

- clean success rate >= 95%; degraded scenarios >= 80%
- detected language must match the expected language family in >= 80% of successful cases
- timestamp validation must pass in >= 95% of successful cases
- ASR exceptions/rejections count as failures; they are never discarded from the denominator
- every mandatory scenario must have results
- **each Hindi, Marathi and Hinglish family must independently pass the same scenario gates**; a strong language may not average away a weak one

These values live in `backend/app/services/asr_benchmark.py`. Do not lower them merely to make a red benchmark green. Threshold changes require user-facing evidence, corpus-quality evidence or a deliberate product decision.

## Real environmental-noise pack

`backend/scripts/fetch_public_asr_noise_pack.py` downloads three independent, auditable fixtures from Wikimedia Commons:

1. `traffic` — city street/traffic ambience with cars, vans and mopeds; public domain.
2. `cafe` — real café ambience with people chatting; CC0 1.0.
3. `fan` — table ventilator/fan motor and airflow; public domain.

The core launch matrix uses traffic for the mandatory `street_noise` scenario. Separate threshold-aware sweeps rerun `street_noise` with café/crowd and fan noise. Every downloaded fixture is duration-checked and SHA-256 recorded.

A manual workflow dispatch may replace the traffic fixture with another recording the operator is permitted to use, but café and fan sweeps remain independent controls.

## Hallucination / non-speech controls

Dirty speech should still be transcribed, but audio with **no speech** should fail safely rather than manufacture creator quotes. Qualification therefore also generates three 30-second negative controls:

- digital silence
- pink-noise-only audio
- tonal/non-speech audio

Each must be rejected by the existing no-speech/transcript-quality/review gates. Returning a transcript is a qualification failure. Model-download errors, crashes and unrelated runtime exceptions do **not** count as successful rejection.

## FIFO contention / resource soak

A production-quality recognizer can still be unusable if concurrent uploads overcommit RAM or bypass the FIFO queue. `backend/scripts/asr_concurrency_soak.py` launches one real Hindi, Marathi and Hinglish transcription concurrently against the production `ASR_CONCURRENCY=1` gate.

The soak must prove all of the following:

- all three real transcriptions succeed;
- at least two requests are observed queued;
- active ASR never exceeds one;
- running order is FIFO (`hi -> mr -> hinglish` for the deterministic soak input order);
- the queue drains back to zero after completion.

The Actions workflow also records GNU `/usr/bin/time -v` output and runner CPU/RAM metadata for the core, environmental, hinted and concurrency runs.

## Why both WER and CER are used

WER is useful for creator-facing transcript correction cost, but Devanagari spelling/tokenization and code-switching can make word boundaries noisy. Character error rate catches severe recognition errors without hiding behind tokenization differences. Both must pass.

## Real-time factor (RTF)

`RTF = transcription wall-clock seconds / media seconds`.

An RTF of 0.8 means one minute of media takes roughly 48 seconds of ASR wall time; 1.5 means roughly 90 seconds.

GitHub Actions RTF is useful for regressions, but **production capacity must be measured on the Hostinger/VPS class actually used for ClipKaro**. CPU model, thermal limits, RAM pressure and competing render/upload workloads materially affect faster-whisper latency.

## Build the corpus locally

From `backend/` with FFmpeg installed:

```bash
python scripts/fetch_fleurs_stress_corpus.py \
  --output-dir stress_corpus \
  --cases-per-language 3 \
  --min-seconds 40

python scripts/import_mucs_hinglish_corpus.py \
  --output-dir stress_corpus \
  --cases 3 \
  --min-seconds 40

python scripts/fetch_public_asr_noise_pack.py \
  --output-dir stress_corpus/noise
```

## Run the real production pipeline

```bash
APP_ENV=development \
TRANSCRIPTION_BACKEND=faster-whisper \
WHISPER_MODEL=medium \
WHISPER_SECONDARY_MODEL=small \
REQUIRE_ASR_CONSENSUS=true \
ALIGNMENT_BACKEND=whisperx \
REQUIRE_FORCED_ALIGNMENT=true \
AUTO_LANGUAGE_BIAS=india \
ASR_CONCURRENCY=1 \
ASR_CPU_THREADS=4 \
ASR_WORKERS=1 \
PYTHONPATH=. \
python scripts/asr_stress_benchmark.py \
  --manifest stress_corpus/manifest.json \
  --street-noise stress_corpus/noise/traffic.ogg \
  --model medium \
  --mode qualification \
  --min-cases-per-language 3 \
  --output asr-stress-report.json
```

Exit code `0` means all language coverage, per-language dirty-speech thresholds and hallucination controls passed. Exit code `2` means the benchmark ran but quality did not qualify. Exit code `3` means the benchmark itself could not run (missing corpus, fixture backend, forced hints, missing real noise, invalid media, etc.).

Smoke mode is also threshold-aware: a selected scenario returns success only when that scenario's WER/CER/RTF/success/language/timestamp gates pass. Merely avoiding an exception is not enough.

## GitHub real-verdict workflow

There are two intentional ways to launch **ASR Stress Qualification**:

1. **Actions -> ASR Stress Qualification -> Run workflow** for a manual pre-launch run. Default: 3 cases/family, 40+ seconds/case, `medium` model. A custom traffic-noise URL is optional.
2. Update `backend/asr-verdict-trigger.txt` in a pull request. This is an explicit auditable CI trigger. It uses 2 cases/family, 34+ seconds/case and the production target `medium` model. 34 seconds keeps the 1.45x fast-speech case above ClipKaro's 20-second reliable-speech floor while making an investigative PR run bounded.

The workflow performs all of the following before it can turn green:

- full Auto-detect core matrix against real traffic noise;
- silence/pink-noise/tone hallucination controls;
- café/crowd real-noise sweep;
- fan/ventilation real-noise sweep;
- explicit Hindi/Marathi/Hinglish creator-hint sweep on clean + traffic conditions;
- real-model three-request FIFO concurrency soak;
- resource/hardware evidence capture;
- JSON reports and source/noise hashes uploaded as a retained artifact.

The final workflow step fails if **any** of those four verdict groups is red.

## Pre-launch recommendation

The public-corpus run is a baseline, not the final word. Before opening paid traffic, run at least:

- 3-5 public-corpus cases per language family
- 10+ private creator recordings across multiple speakers/devices if available
- at least 3 distinct real environmental-noise recordings
- one run on the actual production VPS while no other job is active
- one run while upload/render queues are under realistic concurrent load

Record JSON reports with the release/change ticket rather than committing audio.

## What counts as production-ready

Do **not** mark the checklist item complete because the harness exists or because ordinary CI is green.

For the public-corpus evidence tier, require:

```json
{"production_ready": true}
```

from the core Auto-detect benchmark **and** green café/fan, hinted-override and concurrency reports.

For final production sign-off, also require acceptable RTF/RAM behavior on the real production VPS and representative creator-owned recordings.

## Exact-candidate and threshold-lock enforcement

A launch verdict is now valid only when the qualification is tied to an exact clean Git candidate and the quality contract is unchanged from before inference to after inference.

The source-controlled lock is `backend/asr-threshold-lock.json`. It contains the Hindi/Marathi/Hinglish coverage rules, every scenario WER/CER/RTF/success threshold, language/timestamp rates and hallucination controls. `backend/tests/test_asr_qualification_contract.py` verifies that the lock still matches the executable benchmark constants. A run records the lock SHA-256 before inference and again after every acoustic/noise/FIFO stage. The finalizer refuses to return `PASS` if those hashes differ or if the lock no longer matches its own canonical JSON.

GitHub qualification also checks that `git rev-parse HEAD == TESTED_SHA` and the tracked checkout is clean before any corpus/model work begins. This prevents a report from being attached to a different release than the code that actually ran.

## Immutable evidence bundle

Every complete run produces `backend/asr-qualification-evidence/` containing:

- `asr-qualification-evidence.json` — machine-readable final PASS / FAIL / BLOCKED verdict;
- `asr-qualification-summary.md` — human-readable scenario and per-language WER/CER/RTF summary;
- `threshold-lock-before.json` and `threshold-lock-after.json`;
- exact candidate Git SHA plus a deterministic source-tree SHA-256;
- corpus case hashes and real-noise manifest evidence;
- silence/noise/tone hallucination-control outcomes;
- café and fan real-noise sweeps;
- explicit-language fallback sweep;
- FIFO/concurrency checks and observed queue order;
- GNU `time -v` resource evidence for core, café, fan, hinted and concurrency runs;
- runner CPU/RAM/FFmpeg/Python and ASR/alignment package versions.

The final decision has three states:

- `PASS` — every mandatory quality, hallucination, environment and FIFO gate passed on an exact clean candidate with an unchanged threshold lock;
- `FAIL` — the qualification executed and one or more measured product-quality gates failed;
- `BLOCKED` — the environment/candidate/evidence was incomplete, so no product-quality conclusion is allowed.

A missing model, missing corpus, insufficient RAM, wrong Python version, unavailable network, missing exact Git SHA or incomplete resource report is `BLOCKED`, never a PASS and never silently discarded from the evidence.

## One-command self-hosted execution

On the trusted Linux `clipkaro-qa` runner, from an exact clean Git checkout:

```bash
TESTED_SHA="$(git rev-parse HEAD)" \
CASES_PER_LANGUAGE=3 \
MIN_CASE_SECONDS=40 \
WHISPER_MODEL=medium \
bash scripts/run-real-asr-qualification.sh
```

The command installs the isolated ASR/WhisperX environment, downloads the real Hindi/Marathi/Hinglish corpus and noise fixtures, executes the complete stress matrix, hallucination controls, café/fan sweeps, explicit-language path and FIFO soak, then emits/enforces the immutable evidence bundle. It intentionally refuses an unversioned extracted ZIP as a production `PASS`; exact-main qualification must run from a Git checkout.

## Environment preflight

`backend/scripts/check_asr_execution_environment.py` records a secret-free execution preflight. The production qualification requires Linux x64, an unprivileged runner account, Python 3.12, FFmpeg/FFprobe/GNU time, an 8 GB-class minimum host, at least 25 GiB free disk, outbound HTTPS/DNS for the public corpus/model sources, and—after dependency installation—the real faster-whisper/WhisperX runtime modules.

This preflight is included in the final evidence. It exists specifically to prevent an under-sized or offline machine from producing a misleading red/green ASR result.
