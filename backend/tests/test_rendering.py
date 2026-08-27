from pathlib import Path
from app.services.rendering import _build_ass, create_edited_srt, create_srt, format_srt_time, subtitle_ass_filter, timed_words
from app.services.video import probe_metadata
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
    monkeypatch.setattr("app.services.video.find_media_tool", lambda _: None)
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


def test_export_renderer_keeps_source_burned_subtitles_unchanged():
    source = Path(__file__).resolve().parents[1] / "app" / "services" / "rendering.py"
    assert "source_caption_mask_filter" not in source.read_text(encoding="utf-8")


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
