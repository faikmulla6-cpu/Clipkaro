import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const must = (condition, message) => { if (!condition) throw new Error(`Behavioral-learning contract failed: ${message}`); };

const service = read("backend/app/services/behavioral_learning.py");
const reporting = read("backend/app/services/behavioral_reporting.py");
const triggers = read("backend/app/services/behavioral_triggers.py");
const api = read("backend/app/api/behavioral_learning.py");
const settings = read("backend/app/api/settings.py");
const worker = read("backend/app/worker.py");
const privacyApi = read("backend/app/api/legal.py");
const exporter = read("backend/scripts/export_behavioral_learning.py");
const projectPage = read("frontend/app/projects/[id]/page.tsx");
const editor = read("frontend/app/editor/[clipId]/page.tsx");
const exportsPage = read("frontend/app/exports/page.tsx");
const client = read("frontend/lib/behavior.ts");
const privacy = read("frontend/app/privacy/page.tsx");
const docs = read("docs/BEHAVIORAL_LEARNING.md");

for (const table of ["recommendation_generations", "clip_suggestion_snapshots", "clip_behavior_events"]) {
  must(service.includes(table), `${table} schema is missing`);
}
for (const event of ["impression", "preview_started", "selected", "edited", "export_requested", "export_ready", "export_failed", "downloaded"]) {
  must(service.includes(`\"${event}\"`) || service.includes(`'${event}'`), `${event} event is missing`);
}
for (const trigger of [
  "trg_learning_capture_clip_suggestion",
  "trg_learning_capture_ranking_source",
  "trg_learning_export_requested",
  "trg_learning_export_ready",
  "trg_learning_export_failed",
]) must(triggers.includes(trigger), `${trigger} is missing`);

must(settings.includes("init_behavioral_learning()") && settings.includes("init_behavioral_triggers()"), "API startup does not initialize learning schema/triggers");
must(worker.includes("init_behavioral_learning()") && worker.includes("init_behavioral_triggers()"), "isolated worker startup can miss export outcome triggers");
must(settings.includes("router.include_router(behavioral_router)"), "behavior API is not mounted");
must(api.includes('router.post("/clips/{clip_id}/behavior"'), "clip behavior endpoint is missing");
must(api.includes('router.post("/exports/{export_id}/download-event"'), "download receipt endpoint is missing");
must(api.includes("ConfigDict(extra=\"forbid\")"), "behavior API must reject arbitrary payload fields");
must(reporting.includes("async def learning_diagnostics"), "privacy-minimized learning coverage reporting is missing");
must(!api.includes('router.get("/admin/'), "behavior API must not expose a customer-role admin surface");
must(privacyApi.includes('"behavioral_learning"'), "privacy export does not include learning data");

must(projectPage.includes("IntersectionObserver") && projectPage.includes("intersectionRatio >= 0.5"), "impressions are not viewport-qualified");
must(projectPage.includes('"impression"') && projectPage.includes('"preview_started"'), "project suggestions do not track exposure and preview");
must(
  projectPage.indexOf("await ref.current.play()") < projectPage.indexOf('trackClipBehavior(clip.id, "preview_started"'),
  "project preview is recorded before video playback succeeds",
);
must(editor.includes('"selected"') && editor.includes('"edited"'), "editor does not track selection/edit intent");
must(
  editor.indexOf("await video.play()") < editor.indexOf('trackClipBehavior(clip.id, "preview_started"'),
  "editor preview is recorded before video playback succeeds",
);
must(editor.includes("recordDownload(exportId)"), "download receipt is not wired from completed editor export");
const exportsDownloadWired =
  exportsPage.includes("recordDownload(item.id)") ||
  exportsPage.includes("recordDownload(x.id)") ||
  (exportsPage.includes("recordDownload(exportId)") && exportsPage.includes("downloadExport(item.id)"));
must(exportsDownloadWired, "download receipt is not wired from exports library");
must(client.includes("keepalive: true"), "download receipt can be cancelled by navigation");
must(client.includes("void recordDownload(exportId)") && !client.includes("await recordDownload(exportId)"), "download navigation must not wait for telemetry");
must(client.includes("Behavioral telemetry must never block creator actions"), "client telemetry failure boundary is missing");
must(service.includes("hashlib.sha256") && service.includes("session_digest"), "raw browser event/session identifiers are not hashed before storage");

must(service.includes('"label_strength": positive_strength'), "offline labels are missing");
must(service.includes('"eligible_negative": positive_strength == 0 and provenance_ready'), "negative examples are not gated on exposure + provenance");
must(service.includes('"observed": observed'), "unobserved rows are not distinguished");
must(service.includes('"training_eligible": observed and provenance_ready'), "training rows are not provenance-gated");
must(exporter.includes("--training-only") && exporter.includes('row["training_eligible"]'), "offline exporter cannot safely select training-eligible rows");
for (const forbidden of ["email", "user_agent", "ip_address", "transcript_text"]) {
  must(!exporter.includes(`row[\"${forbidden}\"]`), `offline exporter should not emit ${forbidden}`);
}
for (const dimension of ["by_rank", "by_language", "by_category", "by_ranking_source", "by_pipeline_version"]) {
  must(reporting.includes(`summary[\"${dimension}\"]`), `${dimension} coverage diagnostics are missing`);
}

must(privacy.includes("privacy-minimized recommendation signals"), "privacy notice does not disclose ranking learning");
must(docs.includes("never shown / no event") && docs.includes("not a negative"), "learning documentation does not protect censored examples");
must(docs.includes("does not automatically rewrite ranking weights"), "online-learning non-goal is not documented");
must(docs.includes("training_eligible=true"), "offline training provenance gate is not documented");

console.log("Behavioral-learning trust contract passed.");
