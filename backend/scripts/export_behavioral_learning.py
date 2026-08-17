from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.database import init_db
from app.services.behavioral_learning import init_behavioral_learning, learning_rows
from app.services.behavioral_reporting import learning_diagnostics


async def run(output: Path, *, training_only: bool) -> None:
    await init_db()
    await init_behavioral_learning()
    rows = await learning_rows()
    selected = [row for row in rows if row["training_eligible"]] if training_only else rows
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary_path = output.with_suffix(".summary.json")
    summary = await learning_diagnostics()
    summary["export_mode"] = "training_only" if training_only else "all_for_audit"
    summary["rows_written"] = len(selected)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote {len(selected)} privacy-minimized suggestion rows to {output}")
    print(f"Summary: {summary_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export ClipKaro suggestion/creator-choice signals for offline ranking analysis."
    )
    parser.add_argument(
        "--output",
        default="behavioral-learning.jsonl",
        help="JSONL destination. Rows never contain transcript text, email, IP, or user-agent.",
    )
    parser.add_argument(
        "--training-only",
        action="store_true",
        help="Write only observed rows with resolved ranking provenance. Unexposed/pending rows stay out.",
    )
    args = parser.parse_args()
    asyncio.run(run(Path(args.output), training_only=args.training_only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
