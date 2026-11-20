# Pin the video renderer's Node runtime and dependencies independently from the
# Python API image. HyperFrames and its headless browser are installed at build
# time; a customer render never downloads packages or browsers at runtime.
FROM node:22-bookworm-slim AS cartoon-runtime
WORKDIR /opt/cartoon-engine
COPY cartoon_engine/package.json cartoon_engine/package-lock.json ./
COPY cartoon_engine/animation ./animation
RUN npm ci --omit=dev --no-audit --no-fund \
    && npm run build \
    && ./node_modules/.bin/hyperframes browser ensure

FROM python:3.12-slim AS runtime-base

RUN groupadd --gid 10001 clipkaro \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin clipkaro

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN mkdir -p /app/storage/uploads /app/storage/exports /app/storage/models \
    && chown -R 10001:10001 /app /home/clipkaro

# Native media tools plus the pinned HyperFrames runtime are
# required by the isolated Cloud Run Job. The API image stays small.
FROM runtime-base AS media-base
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg libass9 tesseract-ocr clamav \
       fonts-noto-core fonts-noto-cjk fonts-noto-color-emoji fonts-liberation2 \
       fontconfig libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
       libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
       libxrandr2 libgbm1 libasound2 libx11-xcb1 libxss1 libxtst6 libgtk-3-0 \
       libpango-1.0-0 libcairo2 libfontconfig1 libfreetype6 libxshmfence1 \
       libvulkan1 libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY assets ./assets
COPY cartoon_engine/package.json ./cartoon_engine/package.json
COPY --from=cartoon-runtime /opt/cartoon-engine/dist/animation.js ./cartoon_engine/dist/animation.js
COPY --from=cartoon-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=cartoon-runtime /opt/cartoon-engine/node_modules ./cartoon_engine/node_modules
COPY --from=cartoon-runtime /root/.cache/hyperframes /home/clipkaro/.cache/hyperframes
RUN set -eu; \
    mkdir -p /app/cartoon_engine /home/clipkaro/.cache/hyperframes; \
    shell="$(find /home/clipkaro/.cache/hyperframes -type f -name 'chrome-headless-shell' -perm /111 | head -n 1)"; \
    test -n "$shell"; \
    printf '%s\n' "$shell" > /etc/hyperframes-headless-shell-path; \
    chown -R 10001:10001 /app /home/clipkaro
ENV HOME=/home/clipkaro
ENV HYPERFRAMES_CACHE_DIR=/home/clipkaro/.cache/hyperframes
USER 10001:10001

# Production Cloud Run Job executes exactly one JOB_ID and exits. It owns
# scanning, FFmpeg, captions, animation, voice synchronization and uploads.
FROM media-base AS media
CMD ["python", "-m", "app.media_job"]

# Legacy/local-ASR worker target retained only for deliberate qualification.
# It inherits the same renderer so local worker-mode cartoon jobs work too.
FROM media-base AS worker
USER root
COPY requirements-local-asr.txt .
COPY requirements-alignment.txt .
RUN python -m pip install --no-cache-dir -r requirements-alignment.txt \
    && python -m pip check \
    && chown -R 10001:10001 /app
USER 10001:10001
CMD ["python", "-m", "app.worker"]

# Keep API as the default target so local/dev docker builds remain lightweight.
FROM runtime-base AS api
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["python", "-m", "app.cloudrun_api"]
