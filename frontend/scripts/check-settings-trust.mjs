import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const accountSource = readFileSync(resolve(here, "../app/account/page.tsx"), "utf8");
const uploadSource = readFileSync(resolve(here, "../components/UploadStudio.tsx"), "utf8");
const apiSource = readFileSync(resolve(here, "../lib/api.ts"), "utf8");

for (const label of ["Notifications", "Privacy & files", ">Security<"]) {
  if (accountSource.includes(label)) {
    throw new Error(`Settings trust check failed: non-functional UI returned: ${label}`);
  }
}

for (const required of [
  "Full name",
  "Email address",
  "Default language",
  "Timezone",
  "Default content type",
  "Private by default",
  "Save settings",
  'patchJSON<AccountSettings>("/settings", payload)',
  'name="default_language"',
  'name="timezone"',
  'name="creator_category"',
]) {
  if (!accountSource.includes(required)) {
    throw new Error(`Settings trust check failed: persisted Settings wiring is missing: ${required}`);
  }
}

for (const field of ["default_language", "timezone", "creator_category"]) {
  if (!apiSource.includes(field)) {
    throw new Error(`Settings trust check failed: AccountSettings type is missing ${field}.`);
  }
}

for (const required of [
  'api<AccountSettings>("/settings")',
  "setLanguage(saved.default_language)",
  "setCategory(saved.creator_category)",
  'form.append("language", language)',
  'form.append("category", category)',
]) {
  if (!uploadSource.includes(required)) {
    throw new Error(`Settings trust check failed: upload defaults are not consuming saved preferences: ${required}`);
  }
}

console.log("Settings persistence and trust contract passed.");
