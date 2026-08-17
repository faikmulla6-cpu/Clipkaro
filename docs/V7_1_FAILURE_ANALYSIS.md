# v7.1 — Supplied Export Failure Analysis

## Problems verified in both exports

- The source already contains burned-in Devanagari captions.
- ClipKaro added a second caption track, creating conflicting duplicate subtitles.
- The Roman track contains inaccurate phonetic text and incomplete words.
- Several Roman captions extend outside the horizontal canvas and are visibly clipped.
- Caption coverage is intermittent despite continuous speech.
- “Hindi” incorrectly meant Devanagari output instead of the requested Roman Hinglish.
- Global transcript quality could hide a bad sentence inside an otherwise plausible transcript.
- Crop is mostly usable, but caption placement competes with the audience and existing subtitles.

## v7.1 corrections

- Native Hindi recognition is preserved for acoustic verification, while each segment and aligned word receives separate Roman-Hinglish `display_text`.
- Naturalized output includes forms such as `main`, `hoon`, `arre`, `haan`, `sahi`, `mein`, `kya`, and `karoon`.
- English code-switched words remain unchanged.
- Accuracy mode now defaults to independent `small` + `turbo` ASR consensus.
- Consensus is checked per time-overlapping segment; unverified spans are removed, and insufficient verified coverage rejects the project.
- OCR samples the lower picture area with bundled Hindi and English Tesseract data to detect existing subtitles.
- Existing subtitles trigger a Studio warning and automatically move the new Roman layer to the upper-lower safe region.
- Phrase cards remain limited to two measured lines; production timing remains aligned-word-only.
- Stable-TS-inspired timestamp cleanup enforces monotonic, minimum-duration word events only after ASR gates pass.
- WhisperX-inspired phrase splitting prefers punctuation and Hindi/English conjunction boundaries.
- Script/font-aware visual-width scoring from the caption reference reduces overflow beyond raw character counting.

## Honest boundary

Romanization converts verified Hindi words into the requested script; it cannot repair words that both recognizers hear incorrectly. Such disagreement now causes `Needs review`/no clips instead of a confident-looking false caption.
