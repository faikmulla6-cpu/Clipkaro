from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.behavioral_learning import learning_rows, learning_summary


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _bucket(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key) if row.get(key) is not None else "unknown")].append(row)
    result: dict[str, dict[str, Any]] = {}
    for value, items in sorted(grouped.items()):
        observed = [row for row in items if row["observed"]]
        eligible = [row for row in items if row["training_eligible"]]
        previewed = [row for row in items if row["events"].get("preview_started")]
        selected = [row for row in items if row["events"].get("selected")]
        exported = [row for row in items if (row["label_strength"] or 0) >= 4]
        downloaded = [row for row in items if row["events"].get("downloaded")]
        result[value] = {
            "suggestions": len(items),
            "observed": len(observed),
            "training_eligible": len(eligible),
            "coverage_rate": _rate(len(observed), len(items)),
            "preview_rate_per_observed": _rate(len(previewed), len(observed)),
            "selection_rate_per_observed": _rate(len(selected), len(observed)),
            "export_intent_rate_per_observed": _rate(len(exported), len(observed)),
            "download_rate_per_observed": _rate(len(downloaded), len(observed)),
        }
    return result


async def learning_diagnostics() -> dict[str, Any]:
    """Privacy-minimized coverage diagnostics; never returns creator/content identity."""
    rows = await learning_rows()
    summary = await learning_summary()
    training_rows = [row for row in rows if row["training_eligible"]]
    summary["label_distribution"] = {
        str(label): sum(1 for row in training_rows if row["label_strength"] == label)
        for label in range(0, 6)
    }
    summary["by_rank"] = _bucket(rows, "suggestion_rank")
    summary["by_language"] = _bucket(rows, "language")
    summary["by_category"] = _bucket(rows, "category")
    summary["by_ranking_source"] = _bucket(rows, "ranking_source")
    summary["by_pipeline_version"] = _bucket(rows, "pipeline_version")
    return summary
