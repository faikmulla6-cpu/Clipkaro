# Local yt-dlp source import

Imported on 2026-11-05 into `yt-dlp/`, preserving all 1,235 supplied files.
Version: 2026.10.26. Declared upstream revision: `c91f8de0bfb3577894abad716eaaa01659e6bd14`.

This is a source import only; it does not change Clipkaro runtime dependencies or deployment. Existing root workflows remain unchanged; upstream workflows inside `yt-dlp/.github/` are retained as source and are not root GitHub Actions workflows.

## Security review

Gitleaks v8.30.1 scanned the complete supplied directory (12.27 MB). Its 105 findings occurred in 66 files, all verified byte-for-byte against the declared revision in the public yt-dlp/yt-dlp repository. These are published extractor constants and test fixtures, including fixture private keys. The public signing key, cookie fixtures and netrc fixtures were also verified against that revision. No additional user credentials or local environment files were identified. This scan is not a guarantee that the software is vulnerability-free.

All upstream licenses and notices are retained. Review their terms before distributing or integrating this code.

## Validation

The CLI reports version 2026.10.26. All 18 selected AES, cookie-jar and netrc unit tests passed. Git whitespace checks report existing upstream whitespace in imported source and license documents; these were preserved.
