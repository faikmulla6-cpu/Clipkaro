# ClipKaro `main` Protection

## Required server-side rule

The source repository contains an exact GitHub repository-ruleset payload at
`.github/main-protection-ruleset.json`.

It targets only `refs/heads/main` and is intentionally **Active** with **no bypass actors**.

The rule requires:

- pull requests before `main` can be updated;
- all review conversations resolved;
- strict/up-to-date required status checks;
- `PR Governance`;
- `Critical Backend Invariants`;
- `Critical Frontend Contracts`;
- `Backend CI`;
- `Frontend CI`;
- deletion blocked;
- non-fast-forward / force pushes blocked.

No second-person approval count is required because this is currently a solo-owner repository.
The PR boundary and mandatory automated checks are still enforced.

## One-command configuration

Do **not** place a PAT in this repository or in chat.

On an administrator-controlled machine:

```bash
gh auth login
python scripts/configure-main-protection.py
```

The GitHub identity used by `gh` must have repository **Administration: write**.
The script never prints or stores the auth token. It creates the ruleset if absent,
or updates the existing `ClipKaro main protection` ruleset in place.

Dry-run:

```bash
python scripts/configure-main-protection.py --dry-run
```

Read-only verification:

```bash
python scripts/configure-main-protection.py --verify-only
python scripts/verify-main-protection.py
```

## Test PR verification

After the ruleset exists and the `clipkaro-qa` self-hosted runner is online:

```bash
bash scripts/open-main-protection-test-pr.sh
```

The script:

1. starts from a clean, up-to-date `main`;
2. creates a throwaway `qa/main-protection-probe-*` branch;
3. adds one harmless documentation probe;
4. opens a PR linked to issue #25;
5. verifies GitHub's active rules for `main`;
6. displays the PR check rollup;
7. **never merges the PR and never attempts a direct push to `main`**.

A valid test PR must show all five required checks. The PR remains gated until all
five are successful and its branch is current with `main`.

Direct-push, force-push, and deletion behavior are verified non-destructively
through GitHub's active-rules API. We intentionally do not perform an unsafe
push merely to see whether it succeeds.

## Important deployment ordering

Do not activate required checks whose workflow jobs cannot run. In the current
ClipKaro launch plan, first register the trusted Linux runner carrying:

```text
self-hosted
linux
x64
clipkaro-qa
```

Then push the self-hosted workflow changes, let each required check run at least
once, and activate this ruleset. GitHub notes that required checks must have
completed successfully in the repository recently to be selectable/usable as
required checks.

## If GitHub rejects ruleset creation

Private-repository rulesets/branch protection availability depends on the GitHub
plan, and the API credential must have `Administration: write`. A 403/404 from
the installer is a configuration/plan blocker, not evidence that `main` is
protected.
