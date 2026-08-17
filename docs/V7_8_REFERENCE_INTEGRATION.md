# ClipKaro AI v7.8 — Reference Repository Integration

## Reference reviewed

`SamurAIGPT/AI-Youtube-Shorts-Generator` was reviewed because the uploaded archive
arrived as a zero-byte file. Its upstream repository is MIT licensed.

## Adopted concepts

- Content-type and speech-density profiling.
- Duration targets that change for dense tutorials versus slower stories.
- Strong-hook validation at the actual clip opening.
- Score-first overlap suppression using measured overlap rather than rejecting
  every clip that touches another candidate.
- Multilingual virality categories: curiosity, warnings, revelations, opinion,
  emotion, practical value, and story payoff.

## Improved beyond the reference

- Hindi and Hinglish signals work in Roman and Devanagari scripts.
- Ranking remains deterministic and local; it does not require MuAPI, OpenAI,
  Gemini, or an LLM-generated score.
- Transcript timestamps and words remain protected by ClipKaro's ASR consensus,
  hallucination, alignment, and provenance gates.
- Candidate boundaries still come exclusively from verified transcript segments.
- Incomplete endings, filler openings, and hooks appearing late in a clip receive
  explicit penalties.

## Deliberately not copied

- `base` Whisper defaults, because they are too weak for launch-quality Hindi.
- Paid MuAPI dependencies and external video-processing custody.
- LLM scores treated as objective truth.
- Basic OpenCV face crops where ClipKaro's bounded keyframe renderer is safer.
- YouTube downloading without a rights/ownership workflow.

## Verification

- Python compilation passed.
- Direct Hindi/Hinglish ranking test passed with the opening `Sabse badi galti
  kya hai pata hai?` selected first and hook score 98.
- Density classification and overlap-ratio boundary tests passed.
- The full dependency-backed suite could not be reinstalled during this pass due
  an execution quota limit; v7.7's 41-test baseline had passed immediately before
  these isolated ranking changes.
