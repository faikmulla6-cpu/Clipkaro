"""Canonical caption-personality definitions shared by preview and export."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

STYLE_PATH = Path(__file__).resolve().parents[1] / "assets" / "caption_styles.json"


@lru_cache(maxsize=1)
def caption_style_catalog() -> tuple[dict[str, Any], ...]:
    payload = json.loads(STYLE_PATH.read_text(encoding="utf-8"))
    styles = payload.get("styles")
    if not isinstance(styles, list) or not styles:
        raise RuntimeError("Caption style catalog is missing or invalid.")
    return tuple(dict(style) for style in styles if isinstance(style, dict) and style.get("id"))


def get_caption_style(style_id: str) -> dict[str, Any]:
    for style in caption_style_catalog():
        if style["id"] == style_id:
            return dict(style)
    return dict(caption_style_catalog()[0])


def public_caption_styles() -> list[dict[str, Any]]:
    """Return rendering metadata only; this catalog contains no user data or secrets."""
    return [dict(style) for style in caption_style_catalog()]
