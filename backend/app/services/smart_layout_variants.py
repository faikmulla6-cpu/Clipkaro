"""Derive all three Smart Layout choices from ONE private face-analysis pass.

Do not rerun the source detector every time the user changes a dropdown.
This module has no storage, HTTP, database or payment dependencies.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.services.smart_layout_contract import from_media_plan

SUPPORTED_MODES = ("auto", "dual_stack", "speaker_focus")


def all_layout_variants(auto_plan: Any, *, source_start: float,
                        duration: float) -> dict[str, dict[str, Any]]:
    """Turn an Auto Director evidence plan into three distinct render plans.

    The existing analyzer stores centers only when a face is actually
    visible. This preserves the no-duplicate rule during solo camera cuts.
    """
    if getattr(auto_plan, "mode", None) != "auto":
        raise ValueError("Only an Auto Director evidence plan can seed variants")

    result: dict[str, dict[str, Any]] = {}
    for choice in SUPPORTED_MODES:
        scenes = []
        for scene in getattr(auto_plan, "segments", ()):
            # A genuinely co-visible pair remains pair evidence regardless of
            # whether Auto Director selected focus or split for this scene.
            pair = (
                getattr(scene, "mode", None) in {"dual_stack", "speaker_focus"}
                and len(getattr(scene, "centers", ())) == 2
            )
            # Dual Stack can use weaker-but-stable two-face evidence in an
            # uninterrupted wide shot. Auto Director never changes its layout.
            wide_pair = tuple(getattr(scene, "pair_centers", ()))
            if choice == "dual_stack" and (pair or len(wide_pair) == 2):
                centers = scene.centers if pair else wide_pair
                derived = replace(scene, mode="dual_stack", centers=centers, switches=())
            elif pair and choice == "speaker_focus":
                derived = replace(scene, mode="speaker_focus")
            elif getattr(scene, "mode", None) == "dual_stack":
                # Auto Director may choose Dual Stack while still recording
                # mouth-motion votes. Those votes cannot be applied to split
                # scenes; they belong only in Speaker Focus.
                derived = replace(scene, switches=())
            else:
                derived = scene
            scenes.append(derived)

        plan = replace(auto_plan, mode=choice, segments=tuple(scenes))
        result[choice] = from_media_plan(
            plan, source_start=source_start, duration=duration)
    return result


def all_variants_match_source(variants: dict[str, dict[str, Any]]) -> bool:
    """No mode may describe a different source clip or timeline."""
    if set(variants) != set(SUPPORTED_MODES):
        return False
    identity = None
    for mode in SUPPORTED_MODES:
        data = variants.get(mode, {})
        if data.get("requested_mode") != mode or data.get("version") != 2:
            return False
        current = tuple(data.get(key) for key in (
            "version", "source_width", "source_height", "source_start",
            "duration", "preview_width", "preview_height"))
        if identity is None:
            identity = current
        if identity != current:
            return False
    return True
