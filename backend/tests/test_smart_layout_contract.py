"""Smart Layout request safety: caller can never silently receive a different format."""
import pytest
from pydantic import ValidationError
from app.schemas.api import ExportRequest


@pytest.mark.parametrize("mode", ["auto", "dual_stack", "speaker_focus"])
def test_paid_smart_layout_supported_in_portrait(mode):
    request = ExportRequest(layout_mode=mode, aspect_ratio="9:16", resolution="1080p")
    assert request.layout_mode == mode
    assert request.resolution == "1080p"


@pytest.mark.parametrize("mode", ["auto", "dual_stack", "speaker_focus"])
@pytest.mark.parametrize("ratio", ["4:5", "1:1"])
def test_smart_layout_refuses_non_portrait_canvas(mode, ratio):
    with pytest.raises(ValidationError, match="require a 9:16"):
        ExportRequest(layout_mode=mode, aspect_ratio=ratio)


@pytest.mark.parametrize("mode", ["auto", "dual_stack", "speaker_focus"])
def test_smart_layout_refuses_incompatible_original_subtitles(mode):
    with pytest.raises(ValidationError, match="preserve burned-in"):
        ExportRequest(layout_mode=mode, preserve_source_captions=True)


def test_classic_preserves_original_subtitles_and_manual_zoom():
    result = ExportRequest(layout_mode="classic",preserve_source_captions=True,
                           aspect_ratio="1:1",zoom=1.5,focus_x=30.)
    assert result.preserve_source_captions
    assert result.zoom == 1.5
    assert result.focus_x == 30.
