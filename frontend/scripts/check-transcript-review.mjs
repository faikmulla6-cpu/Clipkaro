import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Transcript Review contract failed: ${label}`);
};

const service = read("backend/app/services/transcript_review.py");
const routes = read("backend/app/api/worker_jobs.py");
const renderRoutes = read("backend/app/api/routes.py");
const database = read("backend/app/core/database.py");
const migration = read("backend/migrations/versions/20260817_01_no_vps_schema.py");
const page = read("frontend/app/projects/[id]/page.tsx");
const tests = read("backend/tests/test_transcript_review.py");

requireText(service, "def apply_corrections", "corrections must overlay source transcript segments");
requireText(service, "original_text", "original ASR text must be preserved");
requireText(service, "segment[\"words\"] = []", "corrected segments must not reuse stale ASR word text");
requireText(service, "UPDATE content_packs SET status='stale'", "Content Pack must become stale after transcript edits");
requireText(service, "def reset_correction", "creator must be able to reset to original text");
requireText(database, "CREATE TABLE IF NOT EXISTS transcript_corrections", "SQLite schema must store correction overrides");
requireText(migration, "CREATE TABLE transcript_corrections", "production baseline must store correction overrides");
requireText(routes, '@router.get("/projects/{project_id}/transcript-review")', "review fetch endpoint must exist");
requireText(routes, '@router.patch("/projects/{project_id}/transcript-review/{segment_index}")', "save correction endpoint must exist");
requireText(routes, '@router.delete("/projects/{project_id}/transcript-review/{segment_index}")', "reset correction endpoint must exist");
requireText(renderRoutes, "effective_segments_for_video", "captions/export must consume effective transcript segments");
requireText(renderRoutes, "allow_synthetic=True", "caption preview must show corrected segment text");
requireText(renderRoutes, "correction_in_clip", "rendered exports must use corrected text");
requireText(page, "function TranscriptReviewPanel", "project results must expose transcript review UI");
requireText(page, "Save correction", "inline save control must exist");
requireText(page, "Reset", "reset control must exist");
requireText(page, "videoRef.current.currentTime = segment.start", "segment jump must seek to source timestamp");
requireText(page, "Transcript changed - regenerate Content Pack", "stale Content Pack messaging must exist");
requireText(tests, "test_transcript_review_read_save_persist_caption_and_content_pack_regenerate", "main feature test must exist");
requireText(tests, "test_transcript_review_reset_restores_original_and_preserves_timestamps", "reset/timestamp test must exist");
requireText(tests, "test_transcript_review_authorization_and_malformed_requests", "authorization and malformed request test must exist");

console.log("Transcript Review contract: passed");
