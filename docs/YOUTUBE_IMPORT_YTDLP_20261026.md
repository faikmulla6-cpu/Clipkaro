# YouTube import: yt-dlp 2026.10.26 rollout

This change integrates the `yt-dlp/` source that is checked into the repository. It does **not** change ClipKaro's account, quota, source-size, or SSRF protections.

## What changed

- The Modal media image installs `yt-dlp[default,deno]==2026.10.26`, matching `yt-dlp/yt_dlp/version.py`.
- The dedicated ingestion-worker Docker image builds `yt-dlp[default]` **from the checked-in `yt-dlp/` tree**, rather than the older 2026.8.19 PyPI release.
- The existing Node 24 and PO-token-provider configuration of the separate worker stays in place.
- Direct imports surface the original-file fallback even if YouTube's bot check appears during the download phase rather than during metadata extraction.

## Important limitation

A newer extractor and JavaScript runtime improve compatibility, but cannot guarantee YouTube accepts requests from a datacenter IP. The historical error `Sign in to confirm you're not a bot` is a server-side rejection, not a bad URL. Do not weaken URL allowlists, supply creators' browser cookies, or attempt to bypass the platform's access restrictions. Original-file upload should remain available for videos the creator has permission to process.

## Deploy safely

1. Run the tests from `backend/`:

   ```sh
   python -m pytest -q tests/test_youtube_import.py tests/test_youtube_worker_client.py
   ```

2. For the existing Modal native mode, review the new requirements lock and deploy through the established reviewed release process from `backend/`. **This pull request does not deploy Modal.**
3. To build the dedicated ingestion worker using the newly pushed source, run from the **repository root**:

   ```sh
   docker build -f ingestion_worker/Dockerfile -t clipkaro-youtube-ingestion:2026.10.26 .
   ```

4. If a compliant external ingestion-worker service is already deployed and reachable over HTTPS, configure the Modal production secret with `YOUTUBE_INGESTION_PROVIDER=worker`, `YOUTUBE_INGESTION_WORKER_URL`, and `YOUTUBE_INGESTION_WORKER_SECRET` (a random secret of at least 32 characters). Do **not** enable worker mode without its endpoint and credentials. The existing production default remains `native`.
5. Using an authorized test video within a test plan's limits, verify: metadata lookup, bounded download, ClamAV scan, project readiness, no credits deducted on failure, original-file fallback, and no private URL or token in logs.

## Measure outcomes

Monitor `import_youtube` jobs by **distinct user**, error stage, provider, and result. Previous production data had 38 failed imports out of 40; do not call this fixed until a representative post-deployment sample succeeds. If YouTube still rejects the request, switch users to authorized original-file upload and inspect provider/egress health rather than silently retrying indefinitely.
