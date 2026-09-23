from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def test_serverless_export_is_published_only_after_durable_storage() -> None:
    source = (BACKEND_ROOT / "app" / "media_job.py").read_text(encoding="utf-8")

    render_pos = source.index("await render_short_limited(")
    durable_verify_pos = source.index("verified = await storage.stat(output_key)")
    ready_pos = source.index("SET output_path=?,object_generation=?,status='ready',progress=100,error=NULL")
    completed_pos = source.index('"Your Short is ready to download", "completed"')

    assert render_pos < durable_verify_pos < ready_pos < completed_pos
    assert "project_routes._render_export(" not in source


def test_creator_caption_position_is_authoritative_in_preview_and_render() -> None:
    worker = (BACKEND_ROOT / "app" / "media_job.py").read_text(encoding="utf-8")
    editor = (REPO_ROOT / "frontend" / "app" / "editor" / "[clipId]" / "page.tsx").read_text(encoding="utf-8")

    assert "request.caption_position" in worker
    assert "effective_position" not in worker
    assert 'const positionClass = captionY === null ? `position-${captionPosition}` : "caption-custom-position";' in editor
    assert "caption_position: captionPosition" in editor
    assert "caption_y: captionY" in editor
    assert "effectiveCaptionPosition" not in editor


def test_durable_media_worker_forwards_caption_composition() -> None:
    worker = (BACKEND_ROOT / "app" / "media_job.py").read_text(encoding="utf-8")
    for field in ("caption_x", "caption_y", "caption_scale", "caption_alignment"):
        assert f"{field}=request.{field}" in worker


def test_postgres_claim_locks_only_the_jobs_side_of_outer_join() -> None:
    jobs = (BACKEND_ROOT / "app" / "services" / "jobs.py").read_text(encoding="utf-8")
    assert 'suffix = " FOR UPDATE OF j"' in jobs
