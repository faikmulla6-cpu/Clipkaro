# ClipKaro zero-cost self-hosted GitHub Actions runner

## Purpose

ClipKaro's required CI and launch-qualification jobs target exactly:

```yaml
runs-on: [self-hosted, linux, x64, clipkaro-qa]
```

GitHub supplies the default `self-hosted`, OS and architecture labels; the ClipKaro machine must also carry the custom `clipkaro-qa` label. Keep this runner repository-scoped and dedicated to the private ClipKaro repository.

## Security boundary

A self-hosted runner executes repository workflow code on your machine. Treat it as production-adjacent infrastructure:

- keep the ClipKaro repository private while using this persistent runner;
- use a dedicated Linux machine/VM or production-class VPS, not a personal daily-use desktop;
- run the runner service as a dedicated non-root user;
- do not store unrelated SSH keys, browser profiles, wallets, cloud credentials or personal files on the runner account;
- Docker access is powerful. Give it only to the dedicated runner account and do not expose the Docker socket over TCP;
- the workflows use read-only repository permissions and `persist-credentials: false` on checkout;
- PR jobs are restricted to branches from this same repository. Fork PRs are intentionally not executed on the persistent self-hosted runner;
- do not add repository secrets to pull-request workflows unless a later security review explicitly requires them;
- keep the OS, Docker Engine and the GitHub Actions runner updated.

## Exact host contract

Required:

- Linux x86_64 (`x64`)
- dedicated non-root service account
- Git
- Bash
- Python **3.12** plus `venv`
- Node.js **20.x** and npm
- FFmpeg + FFprobe
- Docker Engine with the **Compose v2** plugin; runner user can execute `docker info` without sudo
- GNU `/usr/bin/time`
- `curl`
- outbound HTTPS/DNS access for GitHub Actions, PyPI, npm, Docker registries, Hugging Face/model downloads and the public QA media/corpora used by the qualification jobs
- **8 GB-class RAM hard minimum** (>=7400 MiB visible) for heavyweight ASR/launch QA; **12+ GiB recommended**
- **25 GiB free disk hard minimum** for heavyweight QA; **40+ GiB recommended**

The workflow-level validator is:

```bash
bash scripts/check-self-hosted-runner.sh --profile launch
```

Do not bypass that check to make a red runner appear healthy.

## Register the runner

1. In GitHub open the private repository → **Settings → Actions → Runners → New self-hosted runner**.
2. Select **Linux** and **x64**.
3. On the trusted Linux host, create/login to the dedicated runner account and use the download/configuration commands GitHub generates on that page. The registration token is short-lived; never commit it.
4. When running `config.sh`, add the custom label `clipkaro-qa`. For example, preserve GitHub's generated URL/token and add:

```bash
./config.sh --url https://github.com/faikmulla6-cpu/Clipkaro --token <SHORT_LIVED_TOKEN> --labels clipkaro-qa
```

5. Install/start it as a service using the service commands shown by GitHub for the downloaded runner package.
6. Back in **Settings → Actions → Runners**, verify the runner is **Idle/Online** and has all four effective labels: `self-hosted`, `Linux`, `X64`, `clipkaro-qa`.

Do not use `--no-default-labels`; the workflows intentionally require GitHub's OS/architecture labels in addition to the custom label.

## One-time host verification

Run from a ClipKaro checkout as the runner user:

```bash
bash scripts/check-self-hosted-runner.sh --profile launch
```

Then verify Docker permissions without sudo:

```bash
docker info
docker compose version
```

If either requires `sudo`, fix the runner account configuration before enabling jobs. Do not run the Actions service itself as root.

## Workflow profiles

The same validator is used with narrower profiles so simple jobs do not depend on unnecessary tools:

- `governance` — Git + Python only
- `ci-backend` / `critical-backend` — Python + FFmpeg
- `ci-frontend` / `critical-frontend` — Node/npm + Docker/Compose
- `landscape` — Python + FFmpeg + GNU time
- `asr` — Python + FFmpeg + GNU time + curl + heavy-host resource floor
- `launch` — full Python/Node/FFmpeg/Docker/Compose resource contract

Python dependencies are installed into a per-job `.venv-ci`; workflows do not pip-install packages into the runner's global Python environment.

## Runner maintenance

At least monthly, and before every public launch certification:

```bash
sudo apt update
sudo apt upgrade
# update Docker using the installation method chosen for the host
bash scripts/check-self-hosted-runner.sh --profile launch
```

Also verify the GitHub runner shows **Online** and is not waiting for a forced runner software update.

The workflows remove their temporary virtual environments, npm `node_modules`, real-media QA corpora/evidence, and tagged ClipKaro Docker images after runs. Public model/cache data may be retained only where a workflow explicitly uses a cache.

## Recovery / replacement

If the machine is compromised, lost, reused, or no longer dedicated:

1. Remove the runner in GitHub Settings immediately.
2. Stop/delete the local runner service and `_work` directory.
3. Rotate any repository/deployment credential that was ever exposed to a workflow on that host.
4. Provision a clean machine and register it again with the `clipkaro-qa` label.

Never clone a preconfigured runner VM containing its `.runner` credentials to create another runner.

### Real ASR launch qualification

After the runner passes `bash scripts/check-self-hosted-runner.sh --profile asr`, run the exact-candidate qualification with `bash scripts/run-real-asr-qualification.sh`. The run is threshold-locked and returns only PASS, FAIL or BLOCKED with immutable WER/CER/RTF, hallucination, FIFO and resource evidence. Do not qualify from an extracted ZIP; use the exact clean Git candidate so the report has a verifiable SHA.


### Real landscape launch qualification

After the runner passes:

```bash
bash scripts/check-self-hosted-runner.sh --profile landscape
```

the exact candidate can execute the locked 10-real-clip × 3-policy qualification with:

```bash
export TESTED_SHA="$(git rev-parse HEAD)"
bash scripts/run-real-landscape-qualification.sh
```

The qualification additionally checks Python 3.12, non-root execution, FFmpeg/FFprobe,
OpenCV, free disk/RAM, and access to the real Wikimedia source corpus. If the runner
cannot reach Wikimedia, pre-download the five locked real files to a private host
directory and set `LANDSCAPE_SOURCE_DIR=/path/to/cache`; the same input filenames,
case windows, thresholds and evidence rules still apply.

Never substitute synthetic media for this release gate. Synthetic framing fixtures are
useful regression tests, but only the exact 30-export real-media matrix can produce a
landscape qualification `PASS`.
