from app.services.caption_styles import caption_style_catalog, get_caption_style
from app.services.rendering import _build_ass
from pathlib import Path
import pytest


def test_canonical_catalog_contains_every_creator_personality():
    assert [style["id"] for style in caption_style_catalog()] == ["kinetic", "clean", "bold", "minimal", "hindi-pop"]


def test_kinetic_style_carries_preview_and_export_requirements():
    kinetic = get_caption_style("kinetic")
    assert kinetic["text_transform"] == "uppercase"
    assert kinetic["font_weight"] >= 800
    assert kinetic["highlight_color"] == "#DFFF57"
    assert kinetic["words_per_chunk"] == 4
    assert kinetic["bottom_safe_ratio"] == .13


def test_unknown_style_fails_closed_to_canonical_kinetic():
    assert get_caption_style("not-a-style")["id"] == "kinetic"


@pytest.mark.parametrize("style_id", ["kinetic", "clean", "bold", "minimal", "hindi-pop"])
def test_each_personality_uses_the_canonical_ass_definition(tmp_path: Path, style_id: str):
    srt, ass = tmp_path / "words.srt", tmp_path / f"{style_id}.ass"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,300\nhello\n\n2\n00:00:00,350 --> 00:00:00,700\nworld\n", encoding="utf-8")
    _build_ass(srt, ass, 720, 1280, style_id, "bottom")
    content = ass.read_text(encoding="utf-8-sig")
    expected_style = "IndiaPop" if style_id == "hindi-pop" else "Studio"
    assert f"Style: {expected_style},Arial" in content
    assert f"{round(720 * get_caption_style(style_id)['font_size_width_ratio'])}," in content
    if get_caption_style(style_id)["text_transform"] == "uppercase":
        assert "HELLO" in content
    else:
        assert "hello" in content
