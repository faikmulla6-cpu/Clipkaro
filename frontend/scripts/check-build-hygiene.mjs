import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const pkg = JSON.parse(read("frontend/package.json"));
const lock = JSON.parse(read("frontend/package-lock.json"));
const packages = lock.packages || {};

const compare = (a, b) => {
  const pa = String(a).split(".").map(Number);
  const pb = String(b).split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const delta = (pa[i] || 0) - (pb[i] || 0);
    if (delta) return delta;
  }
  return 0;
};
const requireAtLeast = (name, actual, minimum) => {
  if (!actual || compare(actual, minimum) < 0) {
    throw new Error(`Build hygiene failed: ${name}=${actual || "missing"}, minimum=${minimum}`);
  }
};

const rootLock = packages[""] || {};
const nextPkg = packages["node_modules/next"] || {};
if (pkg.dependencies?.next !== "16.3.3") {
  throw new Error(`Build hygiene failed: Next.js must be pinned to 16.3.3, found ${pkg.dependencies?.next || "missing"}`);
}
if (rootLock.dependencies?.next !== pkg.dependencies.next || nextPkg.version !== pkg.dependencies.next) {
  throw new Error("Build hygiene failed: package.json/package-lock Next.js versions are not identical");
}
requireAtLeast("postcss", packages["node_modules/postcss"]?.version, "8.5.23");
requireAtLeast("nanoid", packages["node_modules/nanoid"]?.version, "3.3.18");
requireAtLeast("sharp", packages["node_modules/sharp"]?.version, "0.35.0");

for (const key of [
  "node_modules/@next/swc-linux-x64-gnu",
  "node_modules/@next/swc-linux-x64-musl",
  "node_modules/@img/sharp-linux-x64",
  "node_modules/@img/sharp-libvips-linux-x64",
  "node_modules/@img/sharp-linuxmusl-x64",
  "node_modules/@img/sharp-libvips-linuxmusl-x64",
]) {
  const item = packages[key] || {};
  if (!String(item.integrity || "").startsWith("sha512-")) {
    throw new Error(`Build hygiene failed: lockfile integrity missing for ${key}`);
  }
}

const nextEnv = read("frontend/next-env.d.ts");
if (!nextEnv.includes('import "./.next/types/routes.d.ts";') || nextEnv.includes(".next/dev/types")) {
  throw new Error("Build hygiene failed: next-env.d.ts is not in deterministic production-build form");
}
const gitignore = read(".gitignore");
if (!gitignore.split(/\r?\n/).includes("*.tsbuildinfo")) {
  throw new Error("Build hygiene failed: generated TypeScript build info is not ignored");
}
if (fs.existsSync(path.join(root, "frontend/tsconfig.tsbuildinfo"))) {
  throw new Error("Build hygiene failed: generated frontend/tsconfig.tsbuildinfo is tracked in release source");
}

console.log("Frontend build hygiene contract: passed");
