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

# Native media tools required by the serverless Cloud Run Job. This stage does
# NOT install local Whisper/WhisperX: production ASR stays API-first.
FROM runtime-base AS media-base
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libass9 tesseract-ocr fonts-noto-core fonts-liberation2 clamav \
    && rm -rf /var/lib/apt/lists/*
COPY assets ./assets
RUN chown -R 10001:10001 /app
USER 10001:10001

# Production Cloud Run Job executes exactly one JOB_ID and exits. It owns
# scanning, FFmpeg, captions, rendering and provider API calls without a VPS.
FROM media-base AS media
CMD ["python", "-m", "app.media_job"]

# Legacy/local-ASR worker target retained only for deliberate qualification.
# It starts from runtime-base so WhisperX/alignment dependencies stay out of
# the production API/media image lineage unless this target is built directly.
FROM runtime-base AS worker
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libass9 tesseract-ocr fonts-noto-core fonts-liberation2 clamav \
    && rm -rf /var/lib/apt/lists/*
COPY assets ./assets
COPY requirements-alignment.txt .
RUN python -m pip install --no-cache-dir -r requirements-alignment.txt \
    && python -m pip check
RUN chown -R 10001:10001 /app
USER 10001:10001
CMD ["python", "-m", "app.worker"]

# Keep API as the default target so local/dev docker builds remain lightweight.
FROM runtime-base AS api
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["python", "-m", "app.cloudrun_api"]
