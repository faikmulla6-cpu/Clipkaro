# ClipKaro GitHub-hosted GitHub Actions runners

ClipKaro's release CI now targets `runs-on: ubuntu-24.04` on GitHub-hosted ephemeral Linux x64 machines. No self-hosted runner or permanently running Linux server is needed for routine CI. The private repository uses its GitHub Actions included minutes and can incur additional charges above its account quota; check GitHub Billing & licensing -> Actions.

## How it works

- Every job gets a fresh GitHub-managed Ubuntu 24.04 environment.
- Python 3.12 and Node 20 are provisioned explicitly via official setup actions.
- Jobs needing FFmpeg, GNU time and faketime install these with apt on the temporary runner.
- Read-only checkout, no credential persistence, same-repository PR restrictions and the trusted-base `pull_request_target` governance path remain in place.
- Release tests and actual launch-certification requirements are not bypassed. The launch job still proves the exact source SHA and must validate production Docker images and audits.
- Logs and artifacts appear under GitHub -> Actions; GitHub runners terminate after the job finishes.

## Heavy QA capacity caveat

Standard GitHub-hosted runners for **private** repos have **8 GB RAM and 14 GB SSD listed capacity**. ClipKaro's real ASR and Fresh Launch QA currently require **at least 25 GiB free disk** and an 8-GB-class machine. Those resource gates remain active. The workflows reclaim preinstalled SDK space where possible, and will fail closed if capacity remains insufficient rather than returning a misleading green result. Heavy qualification may need optimization, splitting jobs, or a paid GitHub-hosted larger runner; neither larger-runner billing nor test thresholds is changed automatically.

## Private repository cost

GitHub's included standard-runner time varies by owner plan. GitHub Free currently lists 2,000 Linux-equivalent minutes per month, with the billing period reset monthly. Avoid unnecessary 4-hour ASR/landscape manual runs if you are near the quota. Use your GitHub Billing pages to see actual balance; this repository's billing allowance is not readable here.

## Migration and rollback

Issue #91 documents moving to hosted runners. If a hosted job fails, inspect the named job and artifacts; never modify the certification result to hide a failed Docker, vulnerability, quota or media test. Older self-hosted instructions remain in SELF_HOSTED_RUNNER.md for historical reference but no active workflow selects that runner label.
