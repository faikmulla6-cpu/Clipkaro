# ClipKaro Behavioral Learning Strategy

## Goal

Improve clip ranking from real creator choices without turning production behavior into an uncontrolled online-learning loop.

ClipKaro records the recommendation funnel:

`generated suggestion → shown → previewed → selected/editor-opened → edited → export requested → export ready/failed → download`

The first release **collects and evaluates evidence only**. Production behavior does not automatically rewrite ranking weights.

## Why exposure context matters

A missing export is not automatically a negative label. A creator cannot reject a suggestion they never saw.

Every ranking run receives a new `generation_id`. Each suggestion snapshot preserves:

- original rank within that generation
- score and hook/clarity/value/emotion/flow breakdown
- start/end/duration
- output platform
- project language/category
- ranking source/model marker
- ClipKaro app version
- pipeline version

Reprocessing the same video creates a new generation. Historical generations stay separate until the creator deletes the project/account.

A generation starts with ranking provenance marked `pending` and becomes training-eligible only after the normal `project.processed` audit binds the actual local/Groq ranking source. This prevents an interrupted/manual ranking path with incomplete provenance from silently entering training.

## Events and label strength

The offline exporter maps evidence to an ordinal label:

| Evidence | Strength | Meaning |
| --- | ---: | --- |
| never shown / no event | `null` | censored/unobserved; **not a negative** |
| impression only | 0 | exposed but no stronger recorded intent |
| preview started | 1 | creator chose to inspect the moment |
| selected/editor opened | 2 | creator chose the clip for editing |
| meaningful edit saved | 3 | creator invested editing effort |
| export requested / ready | 4 | strong production intent |
| download receipt | 5 | strongest current completion signal |

`export_requested`, `export_ready` and `export_failed` are captured by SQLite triggers at the authoritative export lifecycle boundary. Browser telemetry cannot erase those signals.

A render failure is recorded separately and does not lower a clip's creator-intent label. If a creator requested an export, that remains strong selection evidence even when infrastructure later fails.

## Idempotency

Browser events carry a client-generated `client_event_id`. The backend stores only a SHA-256 digest of that ID and the per-page session token. The event ledger has a unique `event_key`, so retries, React rerenders and double-clicks do not multiply a single intended event and free-form browser identifiers are not retained verbatim.

Export lifecycle events use deterministic server keys based on export ID.

Repeated page visits are allowed to create new impressions because they are genuinely new exposures; rerenders inside the same page session reuse the same event ID.

## Privacy and minimisation

Behavioral-learning rows intentionally exclude:

- transcript text
- hook/title text
- uploaded media
- email/name
- IP address
- user-agent
- raw browser session/event IDs
- device fingerprint
- payment credentials

The offline JSONL export contains only ranking features/context, pseudonymous sample/generation IDs and behavior labels.

The creator's machine-readable privacy export includes their recommendation generations, suggestion snapshots and behavior events. Project/account deletion cascades the associated learning rows.

## Training workflow

1. Collect enough exposure coverage before fitting anything.
2. From the backend environment, run:

   ```bash
   cd backend
   python scripts/export_behavioral_learning.py --output behavioral-learning.jsonl
   ```

3. Reject a dataset where exposure coverage is too low, ranking provenance is still pending, or one language/category dominates badly.
4. Use only rows with `training_eligible=true`. Never infer dislike from a missing/unobserved event.
5. Split evaluation by project/generation group so the same source does not leak across train/test.
6. Start with calibration/reweighting of existing score features before attempting a new semantic model.
7. Compare candidate ranking offline against a fixed holdout using ranking metrics such as NDCG/MRR plus export/preview lift.
8. Test Hindi, Marathi, Hinglish and English separately.
9. Ship a new ranking version behind an explicit experiment/version marker.
10. Never train directly against `null` unobserved rows as negative examples.
11. Never deploy an online self-updating ranker without a separate design/security/privacy review.

## Bias / quality checks before learning

Review at minimum:

- exposure coverage rate
- training-eligible vs provenance-pending count
- signal volume by language and category
- suggestion-rank distribution
- local vs Groq ranking-source distribution
- free vs paid plan representation if plan is later added as an analysis dimension
- export failures separately from rejection (a failed render is not evidence the suggestion was poor)
- repeated-session behavior so one power user cannot dominate training
- per-generation weighting so one source with repeated page visits cannot dominate the corpus

## Current non-goals

- no foundation-model fine-tuning from creator transcripts
- no third-party advertising profile
- no cross-user personalization yet
- no real-time production weight mutation
- no treating failure to export as dislike without exposure/intent context

The first goal is trustworthy feedback data. Model changes come only after coverage and offline evaluation demonstrate that the signals are reliable.
