from pydantic import ValidationError

from app.schemas.api import ExportRequest
from app.services.render_gate import _render_controls_from_keyframes, _zoom_from_keyframes


def test_default_export_carries_creator_framing_intent_without_public_crop_frames():
    request = ExportRequest()
    assert request.zoom == 1.0
    controls = [item for item in request.crop_keyframes if item.zoom is not None or item.preserve_source_captions is not None]
    assert len(controls) == 1
    assert controls[0].zoom == 1.0
    assert controls[0].preserve_source_captions is False


def test_zoom_is_carried_once_through_durable_crop_payload():
    request = ExportRequest(zoom=1.35, focus_x=72)
    controls = [item for item in request.crop_keyframes if item.zoom is not None or item.preserve_source_captions is not None]
    assert len(controls) == 1
    assert controls[0].zoom == 1.35
    assert controls[0].focus_x == 72
    assert controls[0].preserve_source_captions is False

    rehydrated = ExportRequest(**request.model_dump())
    controls = [item for item in rehydrated.crop_keyframes if item.zoom is not None or item.preserve_source_captions is not None]
    assert len(controls) == 1


def test_render_gate_extracts_controls_without_polluting_real_tracking_keyframes():
    zoom, preserve, frames = _render_controls_from_keyframes([
        {"time": 0, "focus_x": 42, "zoom": None, "preserve_source_captions": None},
        {"time": 2, "focus_x": 58, "zoom": None, "preserve_source_captions": None},
        {"time": 180, "focus_x": 58, "zoom": 1.55, "preserve_source_captions": False},
    ])
    assert zoom == 1.55
    assert preserve is False
    assert frames == [
        {"time": 0, "focus_x": 42, "zoom": None, "preserve_source_captions": None},
        {"time": 2, "focus_x": 58, "zoom": None, "preserve_source_captions": None},
    ]
    legacy_zoom, legacy_frames = _zoom_from_keyframes([
        {"time": 180, "focus_x": 50, "zoom": 1.25, "preserve_source_captions": True},
    ])
    assert legacy_zoom == 1.25
    assert legacy_frames == []


def test_preserve_source_caption_choice_survives_durable_rehydration():
    request = ExportRequest(preserve_source_captions=True, zoom=1.7)
    rehydrated = ExportRequest(**request.model_dump())
    zoom, preserve, frames = _render_controls_from_keyframes([item.model_dump() for item in rehydrated.crop_keyframes])
    assert zoom == 1.7
    assert preserve is True
    assert frames == []


def test_zoom_is_bounded_to_safe_creator_range():
    for invalid in (0.95, 2.05):
        try:
            ExportRequest(zoom=invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"zoom={invalid} should be rejected")
