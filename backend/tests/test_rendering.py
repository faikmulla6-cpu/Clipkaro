from pathlib import Path
from app.services.rendering import (
    _base_video_filters, _build_ass, _scaled_caption_max_chars, align_edited_words,
    create_edited_srt, create_srt, format_srt_time, subtitle_ass_filter, timed_words,
)
from app.services.video import probe_metadata
from app.schemas.api import ExportRequest
from pydantic import ValidationError
import pytest


def test_srt_time_format():
    assert format_srt_time(65.432) == "00:01:05,432"


def test_create_srt_clips_timestamps(tmp_path: Path):
    path = tmp_path / "captions.srt"
    segments = [{"start": 10, "end": 14, "text": "First line"}, {"start": 14, "end": 20, "text": "Second line"}]
    create_srt(segments, 12, 18, path)
    assert path.read_text() == ""


def test_production_does_not_invent_word_timestamps():
    segments = [{"start": 10, "end": 14, "text": "First line"}]
    assert timed_words(segments, 10, 14) == []
    assert len(timed_words(segments, 10, 14, allow_synthetic=True)) == 2


@pytest.mark.asyncio
async def test_missing_ffmpeg_returns_actionable_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.services.video.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="FFmpeg and FFprobe were not found"):
        await probe_metadata(tmp_path / "video.mp4")


def test_word_timestamps_are_preserved_exactly(tmp_path: Path):
    path = tmp_path / "words.srt"
    segments = [{"start": 5, "end": 7, "text": "hello world", "words": [
        {"start": 5.125, "end": 5.510, "text": "hello"},
        {"start": 5.720, "end": 6.140, "text": "world"},
    ]}]
    create_srt(segments, 5, 7, path)
    content = path.read_text()
    assert "00:00:00,125 --> 00:00:00,510" in content
    assert "00:00:00,720 --> 00:00:01,140" in content


def test_native_word_boundary_tolerance_is_limited_to_50ms():
    within = [{"start": 0, "end": 1, "text": "x", "words": [{"start": -.04, "end": .4, "text": "x"}]}]
    outside = [{"start": 0, "end": 1, "text": "x", "words": [{"start": -.051, "end": .4, "text": "x"}]}]
    assert len(timed_words(within, 0, 1)) == 1
    assert timed_words(outside, 0, 1) == []


def test_corrected_words_keep_reference_audio_anchors(tmp_path: Path):
    path = tmp_path / "corrected.srt"
    reference = [{"start": 10.1, "end": 10.4, "text": "their"},
                 {"start": 10.7, "end": 11.0, "text": "product"}]
    create_edited_srt("the product", 2, path, reference, 10)
    content = path.read_text()
    assert "00:00:00,100 --> 00:00:00,400" in content
    assert "00:00:00,700 --> 00:00:01,000" in content


def test_ass_contains_active_word_events(tmp_path: Path):
    srt, ass = tmp_path / "words.srt", tmp_path / "words.ass"
    srt.write_text("1\n00:00:00,100 --> 00:00:00,400\nHello\n\n2\n00:00:00,500 --> 00:00:00,900\nworld\n")
    _build_ass(srt, ass, 720, 1280, "kinetic", "bottom")
    content = ass.read_text(encoding="utf-8-sig")
    # Studio-style positioned rendering redraws every visible word for each
    # active-word state; it is deliberately not one generic karaoke event.
    assert content.count("Dialogue:") == 4
    assert "HELLO" in content and "WORLD" in content
    assert "\\1c&H0057FFDF" in content
    assert "Style: Studio,Arial" in content


def test_caption_scale_changes_font_size_and_custom_position(tmp_path: Path):
    srt = tmp_path / "caption-size.srt"
    base_ass = tmp_path / "base.ass"
    scaled_ass = tmp_path / "scaled.ass"
    srt.write_text("1\n00:00:00,100 --> 00:00:00,800\nHello\n", encoding="utf-8")

    _build_ass(srt, base_ass, 720, 1280, "kinetic", "bottom")
    _build_ass(
        srt, scaled_ass, 720, 1280, "kinetic", "bottom",
        caption_x=30, caption_y=25, caption_scale=1.4,
    )

    base_style = next(line for line in base_ass.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Style: Studio"))
    scaled = scaled_ass.read_text(encoding="utf-8-sig")
    scaled_style = next(line for line in scaled.splitlines() if line.startswith("Style: Studio"))
    assert int(scaled_style.split(",")[2]) > int(base_style.split(",")[2])
    assert "\\pos(216,320)" in scaled


def test_caption_alignment_changes_multiline_word_positions(tmp_path: Path):
    srt = tmp_path / "caption-align.srt"
    left_ass = tmp_path / "left.ass"
    right_ass = tmp_path / "right.ass"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:00,300\ncreator\n\n"
        "2\n00:00:00,350 --> 00:00:00,650\nworkflow\n\n"
        "3\n00:00:00,700 --> 00:00:01,000\ncaption\n\n"
        "4\n00:00:01,050 --> 00:00:01,350\ncontrols\n",
        encoding="utf-8",
    )
    _build_ass(srt, left_ass, 720, 1280, "kinetic", "bottom", caption_alignment="left")
    _build_ass(srt, right_ass, 720, 1280, "kinetic", "bottom", caption_alignment="right")
    left = left_ass.read_text(encoding="utf-8-sig")
    right = right_ass.read_text(encoding="utf-8-sig")
    assert "\\an5\\pos(" in left and "\\an5\\pos(" in right
    assert left != right


def test_larger_caption_scale_reduces_safe_text_width():
    style = {"max_line_width": 30}
    assert _scaled_caption_max_chars(style, .65) > _scaled_caption_max_chars(style, 1.0)
    assert _scaled_caption_max_chars(style, 1.0) > _scaled_caption_max_chars(style, 1.6)


def test_export_request_bounds_caption_composition():
    request = ExportRequest(caption_x=0, caption_y=100, caption_scale=.65, caption_alignment="left")
    assert request.caption_x == 0 and request.caption_y == 100 and request.caption_scale == .65
    assert request.caption_alignment == "left"
    with pytest.raises(ValidationError):
        ExportRequest(caption_x=-.1)
    with pytest.raises(ValidationError):
        ExportRequest(caption_y=100.1)
    with pytest.raises(ValidationError):
        ExportRequest(caption_scale=1.61)
    with pytest.raises(ValidationError):
        ExportRequest(caption_alignment="justify")


def test_india_pop_ass_uses_real_rounded_active_word_pill_and_short_cards(tmp_path: Path):
    srt, ass = tmp_path / "words.srt", tmp_path / "india-pop.ass"
    srt.write_text(
        "1\n00:00:00,100 --> 00:00:00,400\nKya\n\n"
        "2\n00:00:00,500 --> 00:00:00,900\nhai\n\n"
        "3\n00:00:01,000 --> 00:00:01,400\npolice\n\n"
        "4\n00:00:01,500 --> 00:00:01,900\nboli\n",
        encoding="utf-8",
    )
    _build_ass(srt, ass, 720, 1280, "hindi-pop", "bottom")
    content = ass.read_text(encoding="utf-8-sig")
    assert "Style: IndiaPop,Arial" in content
    assert "\\p1" in content  # vector background, not a colour-only karaoke approximation
    assert "\\1c&H003857FF" in content  # orange/red active-word pill
    assert "\\1c&H005BF0FF" in content  # yellow active word text
    assert "KYA" in content and "HAI" in content
    # Four words with a three-word style limit produce two visual cards.
    assert content.count("\\p1") == 4


@pytest.mark.parametrize("style_id,marker", [
    ("kinetic", "&H0057FFDF"), ("clean", "&H0057FFDF"),
    ("bold", "&H00324DFF"), ("minimal", "&H0057FFDF"),
])
def test_studio_personalities_use_positioned_visual_layers(tmp_path: Path, style_id: str, marker: str):
    srt, ass = tmp_path / "words.srt", tmp_path / f"{style_id}.ass"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,300\nhello\n\n2\n00:00:00,350 --> 00:00:00,700\nworld\n", encoding="utf-8")
    _build_ass(srt, ass, 720, 1280, style_id, "bottom")
    content = ass.read_text(encoding="utf-8-sig")
    assert "Style: Studio,Arial" in content
    assert "\\an5\\pos(" in content
    assert marker in content
    if style_id in {"clean", "bold", "minimal"}:
        assert "\\p1" in content


def test_export_renderer_preserves_full_frame_when_source_has_burned_subtitles():
    filters = _base_video_filters(720, 1280, "0.500", source_caption_band=.82)
    assert "scale=720:1280:force_original_aspect_ratio=decrease" in filters
    assert "pad=720:1280:(ow-iw)/2:(oh-ih)/2" in filters
    assert not any(item.startswith("crop=") for item in filters)


def test_export_renderer_crops_normally_without_source_burned_subtitles():
    filters = _base_video_filters(720, 1280, "0.500")
    assert "scale=720:1280:force_original_aspect_ratio=increase" in filters
    assert "crop=720:1280:(iw-720)*0.500:(ih-1280)/2" in filters


def test_ass_filter_uses_escaped_absolute_windows_and_linux_paths():
    windows = subtitle_ass_filter("C:\\temp captions\\late clip.ass", "C:\\fonts dir")
    linux = subtitle_ass_filter("/tmp/caption output/clip.ass", "/opt/fonts")
    assert "C\\:/temp captions/late clip.ass" in windows
    assert "C\\:/fonts dir" in windows
    assert "filename='/tmp/caption output/clip.ass'" in linux


@pytest.mark.parametrize("clip_start", [0, 126.25, 912.75])
def test_clip_local_srt_offsets_work_for_early_middle_and_late_clips(tmp_path: Path, clip_start: float):
    path = tmp_path / "caption temp" / "clip.srt"
    path.parent.mkdir()
    segments = [{"start": clip_start + .10, "end": clip_start + .45, "text": "raw", "words": [
        {"start": clip_start + .10, "end": clip_start + .45, "text": "raw", "display_text": "roman"}
    ]}]
    create_srt(segments, clip_start, clip_start + 1, path)
    assert "00:00:00,100 --> 00:00:00,450" in path.read_text()
    assert "roman" in path.read_text()


def test_corrected_alignment_preserves_speech_region_identity():
    reference = [
        {"start": 10.10, "end": 10.40, "text": "hello", "confidence": .9, "speech_region_id": 4, "speech_aligned": True},
        {"start": 11.10, "end": 11.40, "text": "world", "confidence": .9, "speech_region_id": 5, "speech_aligned": True},
    ]
    aligned = align_edited_words("hello world", 2.0, reference, 10.0)
    assert aligned[0]["speech_region_id"] == 4
    assert aligned[1]["speech_region_id"] == 5


def test_corrected_caption_alignment_preserves_reference_silence():
    reference = [
        {"start": 10.10, "end": 10.40, "text": "hello", "confidence": .9},
        {"start": 11.10, "end": 11.40, "text": "world", "confidence": .9},
    ]
    aligned = align_edited_words("hello world", 2.0, reference, 10.0)
    assert aligned[0]["start"] == pytest.approx(.10)
    assert aligned[0]["end"] == pytest.approx(.40)
    assert aligned[1]["start"] == pytest.approx(1.10)
    assert aligned[1]["end"] == pytest.approx(1.40)


def test_ass_does_not_bridge_real_silence_between_caption_cards(tmp_path: Path):
    srt, ass = tmp_path / "pause.srt", tmp_path / "pause.ass"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:00,300\nhello\n\n"
        "2\n00:00:00,900 --> 00:00:01,200\nworld\n",
        encoding="utf-8",
    )
    _build_ass(srt, ass, 720, 1280, "kinetic", "bottom")
    dialogue = [line for line in ass.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]
    assert dialogue
    assert all(
        not (",0:00:00.30," in line and ",0:00:00.90," in line)
        for line in dialogue
    )
    assert any(",0:00:00.00,0:00:00.30," in line for line in dialogue)
    assert any(",0:00:00.90,0:00:01.20," in line for line in dialogue)


def test_ass_caps_interword_hold_inside_one_card(tmp_path: Path):
    srt, ass = tmp_path / "short-pause.srt", tmp_path / "short-pause.ass"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:00,300\nhello\n\n"
        "2\n00:00:00,500 --> 00:00:00,800\nworld\n",
        encoding="utf-8",
    )
    _build_ass(srt, ass, 720, 1280, "kinetic", "bottom")
    dialogue = [line for line in ass.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]
    assert any(",0:00:00.00,0:00:00.36," in line for line in dialogue)
    assert all(",0:00:00.00,0:00:00.50," not in line for line in dialogue)
