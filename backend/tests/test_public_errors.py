from app.services.public_errors import safe_export_failure, safe_project_failure


def test_project_error_does_not_expose_provider_or_machine_path():
    raw = RuntimeError(r"Groq request failed token=secret at C:\\Users\\dev\\Downloads\\private.mp4")
    message = safe_project_failure(raw)
    assert "Groq" not in message
    assert "Users" not in message
    assert "secret" not in message
    assert message == "Transcription is temporarily unavailable for this video. Please retry shortly."


def test_export_error_does_not_expose_ffmpeg_stderr_or_machine_path():
    raw = RuntimeError(r"ffmpeg C:\\Users\\dev\\video.mp4 failed: internal stderr")
    message = safe_export_failure(raw)
    assert "Users" not in message
    assert "stderr" not in message
    assert message == "ClipKaro could not render this Short. Please retry the export."


def test_known_user_actionable_messages_remain_specific():
    assert "20–90 second moments" in safe_project_failure(ValueError("We found speech, but no complete 20–90 second moments."))
    assert "source video" in safe_export_failure(RuntimeError("The source video is unavailable in ClipKaro private storage.")).lower()
