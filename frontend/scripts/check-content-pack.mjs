import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Content Pack contract failed: ${label}`);
};

const service = read("backend/app/services/content_pack.py");
const database = read("backend/app/core/database.py");
const migration = read("backend/migrations/versions/20260817_01_no_vps_schema.py");
const routes = read("backend/app/api/worker_jobs.py");
const page = read("frontend/app/projects/[id]/page.tsx");
const tests = read("backend/tests/test_content_pack.py");

requireText(service, "def generate_content_pack", "backend generator must be isolated and testable");
requireText(service, "def validate_content_pack", "malformed provider output must be rejected");
requireText(service, "FORBIDDEN_CLICHES", "generic AI phrasing guard must remain explicit");
requireText(service, "Not recommended for this clip", "irrelevant platform suppression must be supported");
requireText(database, "CREATE TABLE IF NOT EXISTS content_packs", "SQLite schema must persist generated packs");
requireText(migration, "CREATE TABLE content_packs", "production baseline must persist generated packs");
requireText(routes, '@router.get("/projects/{project_id}/content-pack")', "read endpoint must exist");
requireText(routes, '@router.post("/projects/{project_id}/content-pack"', "create endpoint must exist");
requireText(routes, "p.user_id=?", "content pack context must enforce project ownership");
requireText(routes, "status='ready'", "ready packs must be idempotently reused");
requireText(page, "function ContentPackPanel", "project results must render the Content Pack");
requireText(page, "/content-pack", "frontend must call the Content Pack API");
requireText(page, "navigator.clipboard.writeText", "copy buttons must be wired");
requireText(page, "PackageCheck", "Content Pack UI must have a distinct project-results affordance");
requireText(tests, "test_content_pack_generation_success_persists_and_is_idempotent", "success and idempotency test must exist");
requireText(tests, "test_content_pack_authorization_is_project_scoped", "authorization test must exist");
requireText(tests, "test_provider_failure_is_recoverable_and_persisted", "provider failure test must exist");
requireText(tests, "test_hinglish_content_pack_preserves_tone", "Hinglish tone test must exist");
requireText(tests, "test_irrelevant_linkedin_is_suppressed_for_pure_comedy", "irrelevant LinkedIn suppression test must exist");

console.log("Content Pack contract: passed");
