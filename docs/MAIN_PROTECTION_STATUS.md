# Main Protection Status

**Source-controlled protection contract:** PASS

**GitHub server-side ruleset:** NOT YET INSTALLED

Reason: the connected GitHub tool available in this session does not expose
repository Rulesets / Branch Protection write operations. GitHub requires
repository `Administration: write` to create/update a repository ruleset.

Run on an admin-controlled machine:

```bash
gh auth login
python scripts/configure-main-protection.py
python scripts/configure-main-protection.py --verify-only
bash scripts/open-main-protection-test-pr.sh
```

Do not mark issue #25 complete until both verification commands pass against GitHub.
