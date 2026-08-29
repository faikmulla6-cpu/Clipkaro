from pydantic import ValidationError

from app.schemas.api import ExportRequest
from app.services.render_gate import _zoom_from_keyframes


def test_zoom_defaults_off_and_preserves_old_export_payloads():
    request = ExportRequest()
    assert request.zoom == 1.0
    assert request.crop_keyframes == []


def test_zoom_is_carried_once_through_durable_crop_payload():
    request = ExportRequest(zoom=1.35, focus_x=72)
    sentinels = [item for item in request.crop_keyframes if item.zoom is not None]
    assert len(sentinels) == 1
    assert sentinels[0].zoom == 1.35
    assert sentinels[0].focus_x == 72

    # Re-hydrating the durable worker payload must not append a second marker.
    rehydrated = ExportRequest(**request.model_dump())
    sentinels = [item for item in rehydrated.crop_keyframes if item.zoom is not None]
    assert len(sentinels) == 1


def test_render_gate_extracts_zoom_without_polluting_real_tracking_keyframes():
    zoom, frames = _zoom_from_keyframes([
        {"time": 0, "focus_x": 42, "zoom": None},
        {"time": 2, "focus_x": 58, "zoom": None},
        {"time": 180, "focus_x": 58, "zoom": 1.55},
    ])
    assert zoom == 1.55
    assert frames == [
        {"time": 0, "focus_x": 42, "zoom": None},
        {"time": 2, "focus_x": 58, "zoom": None},
    ]


def test_zoom_is_bounded_to_safe_creator_range():
    for invalid in (0.95, 2.05):
        try:
            ExportRequest(zoom=invalid)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"zoom={invalid} should be rejected")
