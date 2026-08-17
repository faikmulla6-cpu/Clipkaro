FROM python:3.12-slim AS runtime-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr fonts-noto-core fonts-liberation2 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 clipkaro \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin clipkaro

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY assets ./assets
RUN mkdir -p /app/storage/uploads /app/storage/exports /app/storage/models \
    && chown -R 10001:10001 /app /home/clipkaro

# Heavy alignment dependencies belong only in the isolated media worker.
FROM runtime-base AS worker
COPY requirements-alignment.txt .
RUN python -m pip install --no-cache-dir -r requirements-alignment.txt \
    && python -m pip check
USER 10001:10001
CMD ["python", "-m", "app.worker"]

# Keep API as the default target so local/dev docker builds remain lightweight.
FROM runtime-base AS api
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
