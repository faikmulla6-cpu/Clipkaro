FROM node:24-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ingestion_worker/requirements.txt /app/requirements.txt
# Install the exact upstream yt-dlp release vendored in this repository.
COPY yt-dlp /opt/yt-dlp-src
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir '/opt/yt-dlp-src[default]' \
    && /opt/venv/bin/python -c "from yt_dlp.version import __version__; assert __version__ == '2026.10.26', __version__"

RUN git clone --depth 1 --branch 2.0.0 \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil \
    && cd /opt/bgutil/server \
    && npm ci \
    && npx tsc \
    && rm -rf /opt/bgutil/.git

COPY ingestion_worker/app.py /app/app.py
COPY ingestion_worker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PATH="/opt/venv/bin:${PATH}"
ENV POT_PROVIDER_BASE_URL="http://127.0.0.1:4416"
EXPOSE 8080
CMD ["/app/entrypoint.sh"]
