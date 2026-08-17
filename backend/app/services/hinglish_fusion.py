"""Reference-blind construction helpers for the experimental HinglishFusionV1."""
from __future__ import annotations

import hashlib
import random
from typing import Any

FUSION_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
FUSION_SYSTEM_PROMPT = """You reconstruct the exact spoken transcript of one Hindi-English code-switched audio recording using several independent speech-recognition hypotheses.

Every hypothesis corresponds to exactly the same recording.

Your goal is not to summarize or rewrite. Your goal is to infer the most likely words actually spoken.

STRICT RULES:

1. Return only the final transcript.
2. Never summarize.
3. Never translate.
4. Never paraphrase.
5. Never improve grammar.
6. Never add an explanation.
7. Preserve Hindi words in Devanagari.
8. Preserve genuinely spoken English words in Latin English script.
9. Do not transliterate spoken English into Devanagari.
10. Do not translate English words into Hindi.
11. Prefer a word or phrase supported independently by multiple hypotheses.
12. When hypotheses disagree, infer the most likely spoken form from their phonetic and lexical agreement.
13. A word appearing in only one hypothesis should be treated cautiously.
14. Preserve technical words, app names, brands, numbers, English terminology and names when the hypotheses support them.
15. Preserve genuine repetitions or disfluencies when supported.
16. Do not invent words simply to make the sentence grammatical.
17. If several hypotheses contain different spellings of the same likely Hindi word, choose the most plausible standard written form only when the underlying spoken word is clearly the same.
18. If one system writes an English word in Devanagari and another writes the same word in Latin script, prefer Latin script when the evidence indicates the speaker actually used the English word.
19. Reconstruct using evidence across ALL hypotheses rather than copying one entire hypothesis.
20. Return plain transcript text only.

Example:

Hypothesis A:
आज मीटिंग cancel हो गई

Hypothesis B:
आज meeting कैंसल हो गई

Hypothesis C:
आज meeting cancel हो गई

Final:
आज meeting cancel हो गई

This example is instructional only and is not benchmark data."""
FUSION_PROMPT_SHA256 = hashlib.sha256(FUSION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

def anonymized_fusion_messages(case_id: str, hypotheses: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Build a provider-blind request from only a case id and sanitized hypotheses."""
    ordered = list(hypotheses)
    random.Random(int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16)).shuffle(ordered)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mapping = {letters[index]: item["provider"] for index, item in enumerate(ordered)}
    blocks = ["The following independent transcripts correspond to exactly the same audio recording.", ""]
    for index, item in enumerate(ordered):
        blocks.extend([f"Hypothesis {letters[index]}:", item["transcript"], ""])
    blocks.extend(["Reconstruct the most likely exact spoken Hinglish transcript.", "", "Return only the transcript."])
    return [{"role":"system","content":FUSION_SYSTEM_PROMPT},{"role":"user","content":"\n".join(blocks)}], mapping

def assert_reference_blind(messages: list[dict[str, str]]) -> None:
    rendered = "\n".join(message["content"] for message in messages)
    forbidden = ("reference transcript", "wer", "cer", "ground truth", "provider performance")
    if any(token in rendered.lower() for token in forbidden):
        raise ValueError("Fusion request violates the reference-blind boundary")
