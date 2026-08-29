from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from app.core.database import execute, fetch_all, fetch_one, run_in_transaction
from app.services.india_quality import review_signal, transcript_review_summary
from app.services.jobs import utcnow


REASON_LABELS = {
    "low_word_confidence": "Low speech confidence",
    "short_uncertain_segment": "Suspiciously short segment",
    "repeated_token_review": "Possible repeated words",
    "mixed_language_review": "Mixed-language segment - check spelling",
    "timestamp_collapse": "Timestamp looks collapsed",
    "phonetic_spelling_review": "Possible phonetic spelling - check wording",
    "review_required": "Needs transcript review",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _segment_key(segment: dict[str, Any], index: int) -> str:
    if segment.get("id"):
        return str(segment["id"])
    return f"{index}:{float(segment.get('start', 0)):.3f}:{float(segment.get('end', 0)):.3f}"


def _effective_text(segment: dict[str, Any]) -> str:
    return str(segment.get("corrected_text") or segment.get("display_text") or segment.get("text") or "").strip()


def _text_for_clip(segments: list[dict[str, Any]], start: float, end: float) -> str:
    return _normalize(" ".join(
        _effective_text(segment)
        for segment in segments
        if float(segment.get("end", 0)) > start and float(segment.get("start", 0)) < end
    ))


def apply_corrections(segments: list[dict[str, Any]], corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    effective = copy.deepcopy(segments)
    by_key = {str(row.get("segment_key")): row for row in corrections if row.get("status") in {"corrected", "reviewed"}}
    for index, segment in enumerate(effective):
        key = _segment_key(segment, index)
        row = by_key.get(key)
        if not row:
            continue
        segment["original_text"] = row.get("original_text") or segment.get("text") or ""
        segment["review_state"] = row.get("status") or "corrected"
        if row.get("status") == "corrected":
            corrected = str(row.get("corrected_text") or "").strip()
            segment["corrected_text"] = corrected
            segment["text"] = corrected
            segment["display_text"] = corrected
            segment["words"] = []
        else:
            segment["reviewed_at"] = row.get("updated_at")
    return effective


def review_payload(transcript: dict[str, Any], corrections: list[dict[str, Any]]) -> dict[str, Any]:
    language = str(transcript.get("language") or "auto")
    source_segments = json.loads(transcript.get("segments_json") or "[]")
    effective_segments = apply_corrections(source_segments, corrections)
    corrected_keys = {str(row.get("segment_key")) for row in corrections if row.get("status") == "corrected"}
    reviewed_keys = {str(row.get("segment_key")) for row in corrections if row.get("status") == "reviewed"}
    items = []
    flagged_count = corrected_count = reviewed_count = remaining_count = 0
    for index, source in enumerate(source_segments):
        signal = review_signal(source, language)
        key = _segment_key(source, index)
        corrected = key in corrected_keys
        reviewed = key in reviewed_keys
        flagged = bool(signal["review_suggested"])
        if flagged:
            flagged_count += 1
        if corrected:
            corrected_count += 1
        if reviewed:
            reviewed_count += 1
        state = "corrected" if corrected else "reviewed" if reviewed else "needs_review" if flagged else "clean"
        if flagged and state == "needs_review":
            remaining_count += 1
        if flagged or corrected or reviewed:
            items.append({
                "index": index,
                "segment_key": key,
                "start": float(source.get("start", 0)),
                "end": float(source.get("end", 0)),
                "original_text": str(source.get("text") or ""),
                "text": _effective_text(effective_segments[index]),
                "state": state,
                "flagged": flagged,
                "reasons": [REASON_LABELS.get(reason, reason.replace("_", " ").title()) for reason in signal["review_reasons"]],
            })
    items.sort(key=lambda item: (0 if item["state"] == "needs_review" else 1, item["start"]))
    summary = transcript_review_summary(source_segments, language)
    return {
        "language": language,
        "summary": {
            "flagged": flagged_count or summary["review_segment_count"],
            "corrected": corrected_count,
            "reviewed": reviewed_count,
            "remaining": remaining_count,
        },
        "segments": items,
    }


async def latest_transcript(video_id: str) -> dict[str, Any] | None:
    return await fetch_one(
        "SELECT * FROM transcripts WHERE video_id=? ORDER BY created_at DESC LIMIT 1",
        (video_id,),
    )


async def effective_segments_for_video(video_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    transcript = await latest_transcript(video_id)
    if not transcript:
        return None, []
    corrections = await fetch_all("SELECT * FROM transcript_corrections WHERE transcript_id=?", (transcript["id"],))
    return transcript, apply_corrections(json.loads(transcript["segments_json"] or "[]"), corrections)


async def update_clip_transcripts(video_id: str, segments: list[dict[str, Any]]) -> None:
    clips = await fetch_all("SELECT id,start_time,end_time FROM clips WHERE video_id=? AND status<>'superseded'", (video_id,))
    for clip in clips:
        text = _text_for_clip(segments, float(clip["start_time"]), float(clip["end_time"]))
        await execute("UPDATE clips SET transcript_text=?,updated_at=? WHERE id=?", (text, utcnow(), clip["id"]))


async def save_correction(project_id: str, user_id: str, segment_index: int, text: str) -> dict[str, Any]:
    corrected = _normalize(text)
    if not corrected:
        raise ValueError("Correction text is required.")
    project = await fetch_one(
        """SELECT p.id,v.id video_id FROM projects p JOIN videos v ON v.project_id=p.id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user_id),
    )
    if not project:
        raise PermissionError("Project not found.")
    transcript = await latest_transcript(project["video_id"])
    if not transcript:
        raise LookupError("Transcript not found.")
    source_segments = json.loads(transcript["segments_json"] or "[]")
    if segment_index < 0 or segment_index >= len(source_segments):
        raise IndexError("Transcript segment not found.")
    source = source_segments[segment_index]
    key = _segment_key(source, segment_index)
    now = utcnow()

    async def _write(db) -> None:
        await db.execute(
            """INSERT INTO transcript_corrections(
                 id,transcript_id,project_id,video_id,segment_index,segment_key,original_text,corrected_text,status,created_at,updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'corrected', ?, ?)
               ON CONFLICT(transcript_id,segment_key) DO UPDATE SET
                 corrected_text=excluded.corrected_text,status='corrected',updated_at=excluded.updated_at""",
            (
                str(uuid.uuid4()), transcript["id"], project_id, project["video_id"], segment_index,
                key, str(source.get("text") or ""), corrected, now, now,
            ),
        )
        await db.execute(
            "UPDATE content_packs SET status='stale',updated_at=? WHERE project_id=? AND status='ready'",
            (now, project_id),
        )

    await run_in_transaction(_write, mode="IMMEDIATE", operation_name="save transcript correction")
    _, effective = await effective_segments_for_video(project["video_id"])
    await update_clip_transcripts(project["video_id"], effective)
    return {"status": "corrected", "segment_index": segment_index, "text": corrected}


async def reset_correction(project_id: str, user_id: str, segment_index: int) -> dict[str, Any]:
    project = await fetch_one(
        """SELECT p.id,v.id video_id FROM projects p JOIN videos v ON v.project_id=p.id
           WHERE p.id=? AND p.user_id=?""",
        (project_id, user_id),
    )
    if not project:
        raise PermissionError("Project not found.")
    transcript = await latest_transcript(project["video_id"])
    if not transcript:
        raise LookupError("Transcript not found.")
    source_segments = json.loads(transcript["segments_json"] or "[]")
    if segment_index < 0 or segment_index >= len(source_segments):
        raise IndexError("Transcript segment not found.")
    key = _segment_key(source_segments[segment_index], segment_index)
    now = utcnow()

    async def _write(db) -> None:
        await db.execute(
            "DELETE FROM transcript_corrections WHERE transcript_id=? AND segment_key=?",
            (transcript["id"], key),
        )
        await db.execute(
            "UPDATE content_packs SET status='stale',updated_at=? WHERE project_id=? AND status='ready'",
            (now, project_id),
        )

    await run_in_transaction(_write, mode="IMMEDIATE", operation_name="reset transcript correction")
    _, effective = await effective_segments_for_video(project["video_id"])
    await update_clip_transcripts(project["video_id"], effective)
    return {"status": "reset", "segment_index": segment_index, "text": str(source_segments[segment_index].get("text") or "")}
