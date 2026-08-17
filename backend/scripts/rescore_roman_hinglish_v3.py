#!/usr/bin/env python3
"""Zero-call, read-only rescore of historical Hinglish ASR transcripts under V3."""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.asr_policy_v2 import error_rate_v2, normalize_v2
from app.services.roman_hinglish_policy_v3 import (
    DEVANAGARI,
    LATIN,
    edit_counts,
    error_rate_v3,
    normalize_v3,
    policy_sha256,
    token_script_profile,
)

EXPECTED_CORPUS = "35a7c63d6c2f645fb5b73ef33c2ef1989e9462aba8048b11394d4ae83626a78b"
EXPECTED_V2 = "f58d3032436afd63e43884e4380a80bf92af887d05d1d94c4b9cdd01c6d2018a"
EXPECTED_THRESHOLD = "4f5e49ab72cebcf51c58b4f83204b1d9a29e0c607c6b19b5c324806b61f9347e"
SOURCES = {
    "sarvam": "asr-qualification-evidence/api-step4a-v2-screen/sarvam-v2-clean.json",
    "elevenlabs": "asr-qualification-evidence/api-step4a-v2-screen/elevenlabs-v2-clean.json",
    "shunya": "asr-qualification-evidence/shunya-v2-clean/shunya-v2-clean.json",
    "deepgram": "asr-qualification-evidence/api-step4a-v2-screen/deepgram-v2-clean.json",
    "groq": "asr-qualification-evidence/api-step2b-2026-08-13/groq-results.json",
    "cloudflare": "asr-qualification-evidence/api-step2b-2026-08-13/cloudflare-results.json",
    "speechmatics": "asr-qualification-evidence/api-step4a-v2-screen/speechmatics-v2-clean.json",
    "assemblyai": "asr-qualification-evidence/api-step4a-v2-screen/assemblyai-v2-clean.json",
    "gladia": "asr-qualification-evidence/api-step4a-v2-screen/gladia-v2-clean.json",
    "gnani": "asr-qualification-evidence/api-step4a-v2-screen/gnani-v2-clean-step6e-gnani-hinglish.json",
    "nvidia-parakeet": "asr-qualification-evidence/api-step4a-v2-screen/nvidia-parakeet-v2-clean.json",
}


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(quantile * len(ordered)) - 1] if ordered else math.inf


def references(case: dict) -> list[str]:
    return list((case.get("raw_references") or {"reference": case["reference"]}).values())


def best_scores(case: dict, transcript: str) -> tuple[float, float, float, float, str]:
    scored = [
        (
            error_rate_v2(reference, transcript, unit="word"),
            error_rate_v2(reference, transcript, unit="char"),
            error_rate_v3(reference, transcript, unit="word"),
            error_rate_v3(reference, transcript, unit="char"),
            reference,
        )
        for reference in references(case)
    ]
    # The V2 and V3 rates retain their respective independent frozen
    # multi-reference minimum rule.  The V3-best reference is used only for
    # post-score lexical diagnostics.
    chosen_v3 = min(scored, key=lambda item: item[2])
    return min(item[0] for item in scored), min(item[1] for item in scored), chosen_v3[2], min(item[3] for item in scored), chosen_v3[4]


def summarize(name: str, source: str, cases: dict[str, dict]) -> dict:
    raw = json.loads((ROOT / source).read_text(encoding="utf-8"))
    rows = raw.get("results", raw)
    selected = {row.get("case_id"): row for row in rows if row.get("case_id") in cases and row.get("language") == "hinglish" and row.get("scenario", "clean") == "clean"}
    metrics, edits = [], Counter()
    english_reference = english_hit = hindi_reference = hindi_hit = 0
    latin_output_cases = devanagari_output_cases = 0
    timestamp_valid = timestamp_capable = 0
    for case_id in sorted(cases):
        row = selected.get(case_id)
        if not row or not row.get("success") or not str(row.get("transcript") or "").strip():
            continue
        case, transcript = cases[case_id], str(row["transcript"])
        v2_wer, v2_cer, v3_wer, v3_cer, reference = best_scores(case, transcript)
        metrics.append({"case_id": case_id, "v2_wer": v2_wer, "v2_cer": v2_cer, "v3_wer": v3_wer, "v3_cer": v3_cer})
        edits.update(edit_counts(reference, transcript))
        # Language membership is determined from the original reference
        # script, before V3 converts both languages into Roman characters.
        # This keeps Hindi/English retention meaningful without affecting the
        # provider-independent V3 error score.
        original_reference_tokens = normalize_v2(reference).split()
        hypothesis_tokens = normalize_v3(transcript).split()
        reference_english = Counter(normalize_v3(token) for token in original_reference_tokens if LATIN.search(token))
        hypothesis_english = Counter(token for token in hypothesis_tokens if LATIN.search(token))
        reference_hindi = Counter(normalize_v3(token) for token in original_reference_tokens if DEVANAGARI.search(token))
        hypothesis_hindi = Counter(token for token in hypothesis_tokens if LATIN.search(token))
        english_reference += sum(reference_english.values()); english_hit += sum((reference_english & hypothesis_english).values())
        hindi_reference += sum(reference_hindi.values()); hindi_hit += sum((reference_hindi & hypothesis_hindi).values())
        original_tokens = normalize_v2(transcript).split()
        profile = token_script_profile(original_tokens)
        latin_output_cases += bool(profile["latin_tokens"])
        devanagari_output_cases += bool(profile["devanagari_tokens"])
        # Older screen evidence predates ``word_timestamp_count`` but still
        # records a valid production-path timestamp result.  Newer records
        # distinguish explicit zero words (for example Sarvam segments) from
        # genuine provider word timing.
        timestamp_capable += bool(row["word_timestamp_count"]) if "word_timestamp_count" in row else bool(row.get("timestamps_valid"))
        timestamp_valid += bool(row.get("timestamps_valid"))
    coverage, successful = len(selected), len(metrics)
    def mean(key: str) -> float: return round(statistics.mean(item[key] for item in metrics), 4) if metrics else math.inf
    def p90(key: str) -> float: return round(percentile([item[key] for item in metrics], 0.9), 4)
    return {
        "provider": name,
        "source": source,
        "cases_available": coverage,
        "successful_cases": successful,
        "success_rate": round(successful / 30, 4),
        "v2": {"mean_wer": mean("v2_wer"), "p90_wer": p90("v2_wer"), "mean_cer": mean("v2_cer"), "p90_cer": p90("v2_cer")},
        "v3": {"mean_wer": mean("v3_wer"), "p90_wer": p90("v3_wer"), "mean_cer": mean("v3_cer"), "p90_cer": p90("v3_cer")},
        "lexical_retention": {"hindi": round(hindi_hit / hindi_reference, 4) if hindi_reference else None, "english": round(english_hit / english_reference, 4) if english_reference else None},
        "edit_rates": {key: round(value / max(1, sum(len(normalize_v3(cases[item["case_id"]]["reference"]).split()) for item in metrics)), 4) for key, value in edits.items()},
        "historical_timestamps": {"native_word_timestamps": bool(timestamp_capable), "validity_rate": round(timestamp_valid / successful, 4) if successful else 0.0},
        "script_diagnostics": {"latin_output_case_rate": round(latin_output_cases / successful, 4) if successful else 0.0, "devanagari_output_case_rate": round(devanagari_output_cases / successful, 4) if successful else 0.0, "already_roman_output_case_rate": round(latin_output_cases / successful, 4) if successful else 0.0},
        "case_metrics": metrics,
    }


def main() -> int:
    corpus = json.loads((ROOT / "stress_corpus/corpus-lock.json").read_text(encoding="utf-8"))
    v2 = json.loads((ROOT / "asr-policy-v2.json").read_text(encoding="utf-8"))
    threshold = json.loads((ROOT / "asr-threshold-lock.json").read_text(encoding="utf-8"))
    if corpus["CORPUS_LOCK_SHA256"] != EXPECTED_CORPUS or v2["ASR_POLICY_V2_SHA256"] != EXPECTED_V2 or threshold["threshold_sha256"] != EXPECTED_THRESHOLD:
        raise RuntimeError("Immutable qualification inputs do not match; refusing rescore.")
    manifest = json.loads((ROOT / "stress_corpus/manifest.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in manifest["cases"] if case["language"] == "hinglish" and case.get("scenario") == "clean"}
    if len(cases) != 30:
        raise RuntimeError("Expected exactly 30 locked clean Hinglish cases.")
    providers = {name: summarize(name, path, cases) for name, path in SOURCES.items()}
    ranking = sorted(providers, key=lambda name: (providers[name]["v3"]["p90_wer"], providers[name]["v3"]["mean_wer"], providers[name]["v3"]["p90_cer"], providers[name]["v3"]["mean_cer"], -providers[name]["success_rate"]))
    report = {
        "scope": "zero-call offline rescore of persisted historical evidence only",
        "corpus_lock": corpus["CORPUS_LOCK_SHA256"],
        "policy_v2": v2["ASR_POLICY_V2_SHA256"],
        "threshold_lock": threshold["threshold_sha256"],
        "roman_hinglish_policy_v3": policy_sha256(),
        "providers": providers,
        "roman_text_ranking": ranking,
        "production_routing_changed": False,
    }
    output = ROOT / "asr-qualification-evidence/roman-hinglish-v3/zero-call-provider-rescore.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"policy": report["roman_hinglish_policy_v3"], "ranking": ranking}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
