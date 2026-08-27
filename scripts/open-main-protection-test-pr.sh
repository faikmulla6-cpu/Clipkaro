#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-faikmulla6-cpu/Clipkaro}"
BRANCH="qa/main-protection-probe-$(date -u +%Y%m%d%H%M%S)"
PROBE="docs/main-protection-probe.md"

command -v gh >/dev/null || { echo "BLOCKED: gh is required"; exit 2; }
command -v git >/dev/null || { echo "BLOCKED: git is required"; exit 2; }
gh auth status >/dev/null

test -d .git || { echo "BLOCKED: run this from a Git clone, not an extracted ZIP"; exit 2; }
test "$(git branch --show-current)" = "main" || { echo "BLOCKED: start from main"; exit 2; }
git diff --quiet && git diff --cached --quiet || { echo "BLOCKED: working tree is not clean"; exit 2; }

git fetch origin main
git switch --create "$BRANCH" origin/main
cat > "$PROBE" <<EOF
# Main protection verification probe

This file exists only to verify GitHub's active \`main\` ruleset and required checks.
Created: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
git add "$PROBE"
git commit -m "test: verify main protection ruleset"
git push --set-upstream origin "$BRANCH"

PR_URL="$(gh pr create \
  --repo "$REPO" \
  --base main \
  --head "$BRANCH" \
  --title "Test main protection ruleset" \
  --body $'Closes #25\n\n## Risk\nNo product behavior changes. This PR is a protection probe only.\n\n## Validation\nExpected required checks: PR Governance, Critical Backend Invariants, Critical Frontend Contracts, Backend CI, Frontend CI.\n\n## Rollback\nClose the PR and delete the probe branch.')"

echo "Created protection test PR: $PR_URL"
echo "Waiting briefly for check registration..."
sleep 8

python scripts/configure-main-protection.py --repo "$REPO" --verify-only

# This is intentionally non-destructive: it proves the test PR exists and
# displays check rollup, but never attempts to bypass or merge the PR.
gh pr checks "$PR_URL" || true
echo
echo "PASS condition: GitHub lists all five required checks, and merge remains gated until they are green."
echo "Do NOT use a direct-push probe; active deletion/non_fast_forward/pull_request rules are verified via GitHub's rules API."
