from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ClipKaro AI"
    app_env: str = "development"
    # Creator access to the internal/manual analysis endpoint is fail-closed.
    # Tests are allowed automatically; local development must opt in explicitly.
    allow_manual_analysis_in_development: bool = False
    api_prefix: str = "/api/v1"
    secret_key: str = "development-only-change-me"
    access_token_minutes: int = 10080
    database_backend: str = "sqlite"
    database_url: str = ""
    postgres_pool_min_size: int = 0
    postgres_pool_max_size: int = 4
    postgres_statement_cache_size: int = 0
    postgres_command_timeout_seconds: float = 30.0
    database_path: Path = Path("./storage/clipkaro.db")
    # SQLite waits briefly for a writer before returning SQLITE_BUSY, then the
    # database layer retries the whole operation/transaction with backoff.
    sqlite_busy_timeout_ms: int = 5000
    sqlite_lock_max_attempts: int = 4
    sqlite_lock_retry_base_ms: int = 50
    storage_root: Path = Path("./storage")
    storage_backend: str = "local"
    gcs_bucket: str = ""
    gcs_upload_url_ttl_seconds: int = 900
    gcs_download_url_ttl_seconds: int = 300
    gcs_signing_service_account: str = ""
    max_upload_mb: int = 500
    max_video_minutes: int = 15
    file_expiry_hours: int = 24
    whisper_model: str = "medium"
    whisper_fallback_model: str = "small"
    whisper_secondary_model: str = "small"
    require_asr_consensus: bool = True
    hindi_caption_script: str = "roman"
    model_cache_dir: Path = Path("./storage/models")
    transcription_backend: str = "faster-whisper"
    # API is the production default. Local faster-whisper/WhisperX remain only
    # for qualification and explicit ASR_MODE=local deployments.
    asr_mode: str = "api"
    asr_primary_provider: str = "groq"
    asr_fallback_provider: str = "cloudflare"
    groq_asr_model: str = "whisper-large-v3"
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_asr_model: str = "@cf/openai/whisper-large-v3-turbo"
    # Candidate bake-off credentials. These adapters are intentionally not part
    # of production provider routing until a separately qualified promotion.
    elevenlabs_api_key: str = ""
    # Optional ordered key pool for the controlled Hinglish route.  Rotation is
    # limited to genuine ElevenLabs rate-limit/quota responses; malformed and
    # authentication requests must fail closed instead.
    elevenlabs_api_keys: str = ""
    # Controlled, Hinglish-only promotion.  Keep this legacy by default: an
    # operator must explicitly opt in before ElevenLabs is selected for jobs.
    hinglish_asr_provider: str = "legacy"
    roman_hinglish_enabled: bool = False
    roman_hinglish_policy: str = "v3"
    roman_hinglish_display_policy: str = "v1"
    hinglish_stage1_enabled: bool = False
    hinglish_stage1_user_ids: str = ""
    deepgram_api_key: str = ""
    sarvam_api_key: str = ""
    speechmatics_api_key: str = ""
    trelis_router_api_key: str = ""
    assemblyai_api_key: str = ""
    gladia_api_key: str = ""
    gemini_api_key: str = ""
    shunyalabs_api_key: str = ""
    nvidia_api_key: str = ""
    # Candidate-only Gnani Prisma v2.5 credential.  It is deliberately not
    # consumed by the production Groq -> Cloudflare routing.
    gnani_api_key: str = ""
    asr_provider_timeout_seconds: float = 45.0
    # Scribe v2 supports large uploads, but its own batch guidance recommends
    # five-minute pieces for large media.  This is deliberately scoped to the
    # opted-in Hinglish candidate route; Groq/Cloudflare retain their existing
    # API bounds and retry policy.
    elevenlabs_asr_chunk_seconds: int = 300
    elevenlabs_asr_timeout_seconds: float = 120.0
    asr_provider_max_attempts: int = 2
    asr_api_max_audio_minutes: int = 60
    asr_api_max_chunk_mb: int = 24
    asr_api_max_chunks: int = 24
    asr_chunk_seconds: int = 600
    asr_chunk_overlap_seconds: int = 2
    alignment_backend: str = "native"
    require_forced_alignment: bool = False
    transcription_fixture_path: Path = Path("./sample_data/e2e_segments.json")
    auto_language_bias: str = "india"
    cors_origins: str = "http://localhost:3000"
    seed_demo_user: bool = False
    demo_email: str = "demo@clipkaro.ai"
    demo_password: str = "ClipKaro123!"
    render_concurrency: int = 1
    # Production uses the durable worker queue so the internet-facing API only
    # validates/enqueues work. Development/tests keep BackgroundTasks for a fast,
    # deterministic local loop. Supported values: background, worker.
    job_execution_mode: str = "background"
    job_backend: str = "local"
    gcp_project_id: str = ""
    gcp_region: str = ""
    cloud_run_media_job_name: str = ""
    cloud_run_job_timeout_seconds: float = 15.0
    job_claim_stale_seconds: int = 1800
    worker_poll_seconds: float = 0.75
    # Worker liveness is persisted in SQLite so the API can distinguish an idle
    # healthy worker from a dead container without sharing process memory.
    worker_heartbeat_seconds: float = 5.0
    worker_stale_after_seconds: float = 30.0
    worker_provider_probe_seconds: float = 300.0
    # External production-preflight probes are bounded and never return provider
    # response bodies or credential material to clients.
    preflight_network_timeout_seconds: float = 8.0
    # Number of source videos allowed inside the memory-heavy ASR pipeline at
    # once. This is intentionally separate from ASR_WORKERS, which controls
    # faster-whisper's internal workers for a single model instance.
    asr_concurrency: int = 1
    asr_cpu_threads: int = 4
    asr_workers: int = 1

    # Identity security. JWTs are merely signed handles to persisted sessions;
    # logout, logout-all and password reset revoke server-side state immediately.
    password_reset_token_minutes: int = 30
    password_reset_resend_cooldown_seconds: int = 60
    password_reset_max_sends_per_hour: int = 5

    # Uploads are quarantined on disk and scanned before project/job creation.
    # Production enables this and talks to the ClamAV sidecar over its private
    # Docker network. Development can leave CLAMAV_HOST empty to skip scanning.
    upload_scan_required: bool = False
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0
    clamav_chunk_kb: int = 256

    # Bound external media processes so malformed media cannot run forever or
    # create unbounded FFmpeg thread pressure inside the isolated worker.
    media_process_timeout_seconds: int = 1800
    media_ffmpeg_threads: int = 2

    # Email ownership is required before creator accounts may spend AI compute.
    # Existing accounts are migrated as verified once; new accounts start
    # unverified and unlock processing only after consuming a one-time token.
    email_verification_required: bool = True
    # Resend is the server-only transactional email provider.  FRONTEND_URL is
    # deliberately configurable so a later domain migration needs no code edit.
    resend_api_key: str = ""
    email_from: str = ""
    frontend_url: str = "http://localhost:3000"
    resend_timeout_seconds: float = 15.0
    # Preferred explicit name for new deployments. Zero preserves compatibility
    # with the previously shipped EMAIL_VERIFICATION_TOKEN_MINUTES setting.
    email_verification_token_ttl_minutes: int = 0
    app_public_url: str = "http://localhost:3000"
    email_verification_token_minutes: int = 60
    email_verification_resend_cooldown_seconds: int = 60
    email_verification_max_sends_per_hour: int = 5
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "ClipKaro AI"
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = 15.0

    # Public legal identity. These are not secrets: they are intentionally
    # published on ClipKaro's Legal Notice and used as a fail-closed paid-launch
    # gate. Production checkout is disabled until all required particulars are
    # real values rather than placeholders.
    legal_operator_name: str = ""
    legal_operator_address: str = ""
    legal_contact_email: str = ""
    privacy_contact_email: str = ""
    customer_care_email: str = ""
    customer_care_phone: str = ""
    grievance_officer_name: str = ""
    grievance_email: str = ""
    grievance_phone: str = ""
    legal_gstin: str = ""
    legal_pan: str = ""

    # Groq is an optional semantic reranker. Local deterministic ranking remains
    # the fail-safe so a provider outage or rate limit never breaks clip creation.
    groq_ranking_enabled: bool = True
    groq_ranking_model: str = "openai/gpt-oss-120b"
    groq_ranking_fallback_model: str = "openai/gpt-oss-20b"
    groq_ranking_timeout_seconds: float = 18.0
    groq_ranking_candidates: int = 16
    # Prefer GROQ_API_KEYS for deployment. Individual slots make migration from
    # multiple existing keys explicit without ever committing their values.
    groq_api_keys: str = ""
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_key_5: str = ""

    # Operational guard: keep false until provider credentials have been rotated
    # after any exposure/export and installed only in the private VPS environment.
    production_credentials_rotated: bool = False

    # Razorpay mode: test or live. Must match the configured key type.
    # Production live checkout always requires complete legal configuration.
    # Local development can explicitly opt into LIVE checkout for merchant-side
    # integration testing; this flag never relaxes staging/production gates.
    razorpay_mode: str = "test"
    allow_live_razorpay_in_development: bool = False
    razorpay_webhook_secret: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def normalized_razorpay_mode(self) -> str:
        mode = self.razorpay_mode.strip().lower()
        if mode not in {"test", "live"}:
            raise RuntimeError("RAZORPAY_MODE must be 'test' or 'live'.")
        return mode

    @property
    def normalized_database_backend(self) -> str:
        backend = self.database_backend.strip().lower()
        if backend not in {"sqlite", "postgres"}:
            raise RuntimeError("DATABASE_BACKEND must be 'sqlite' or 'postgres'.")
        return backend

    @property
    def normalized_storage_backend(self) -> str:
        backend = self.storage_backend.strip().lower()
        if backend not in {"local", "gcs"}:
            raise RuntimeError("STORAGE_BACKEND must be 'local' or 'gcs'.")
        return backend

    @property
    def normalized_job_backend(self) -> str:
        backend = self.job_backend.strip().lower()
        if backend not in {"local", "cloud_run_job"}:
            raise RuntimeError("JOB_BACKEND must be 'local' or 'cloud_run_job'.")
        return backend

    @property
    def production_serverless_mode(self) -> bool:
        return (
            self.app_env.strip().lower() == "production"
            and self.normalized_database_backend == "postgres"
            and self.normalized_storage_backend == "gcs"
            and self.normalized_job_backend == "cloud_run_job"
        )

    @property
    def razorpay_key_is_test(self) -> bool:
        key = self.razorpay_key_id.strip()
        return key.startswith("rzp_test_") or key.startswith("rzp_test")

    @property
    def razorpay_key_is_live(self) -> bool:
        key = self.razorpay_key_id.strip()
        return key.startswith("rzp_live_") or key.startswith("rzp_live")

    @property
    def razorpay_mode_key_consistent(self) -> bool:
        """Validate that RAZORPAY_MODE matches the configured key type."""
        if not self.razorpay_key_id.strip():
            return True  # No key configured, can't validate
        if self.normalized_razorpay_mode == "test":
            return self.razorpay_key_is_test
        return self.razorpay_key_is_live

    @property
    def upload_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.storage_root / "exports"

    @property
    def temp_dir(self) -> Path:
        """Writable storage-backed temp space for large multipart/media work.

        Production containers are read-only and keep /tmp intentionally small.
        Starlette/Python may spool multipart uploads before application-level size
        validation, so TMPDIR points here in production to avoid rejecting a
        legitimate near-limit upload solely because the container tmpfs filled.
        """
        return self.storage_root / "tmp"

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def groq_keys(self) -> list[str]:
        values = [item.strip() for item in self.groq_api_keys.split(",") if item.strip()]
        values.extend(
            item.strip()
            for item in (
                self.groq_api_key_1, self.groq_api_key_2, self.groq_api_key_3,
                self.groq_api_key_4, self.groq_api_key_5,
            )
            if item.strip()
        )
        # Keep configured order while removing accidental duplicates.
        return list(dict.fromkeys(values))

    @property
    def elevenlabs_keys(self) -> list[str]:
        """Ordered private key pool, including the legacy comma-separated form."""
        configured = self.elevenlabs_api_keys or self.elevenlabs_api_key
        values = [item.strip() for item in configured.split(",") if item.strip()]
        return list(dict.fromkeys(values))

    @property
    def groq_ranking_models(self) -> list[str]:
        return list(dict.fromkeys(
            model.strip() for model in (self.groq_ranking_model, self.groq_ranking_fallback_model)
            if model.strip()
        ))

    @property
    def normalized_asr_mode(self) -> str:
        mode = self.asr_mode.strip().lower()
        if mode not in {"api", "local"}:
            raise RuntimeError("ASR_MODE must be either 'api' or 'local'.")
        return mode

    @property
    def normalized_asr_primary_provider(self) -> str:
        provider = self.asr_primary_provider.strip().lower()
        if provider not in {"groq", "cloudflare"}:
            raise RuntimeError("ASR_PRIMARY_PROVIDER must be 'groq' or 'cloudflare'.")
        return provider

    @property
    def normalized_asr_fallback_provider(self) -> str:
        provider = self.asr_fallback_provider.strip().lower()
        if provider not in {"", "none", "cloudflare"}:
            raise RuntimeError("ASR_FALLBACK_PROVIDER must be 'cloudflare' or empty.")
        return provider

    @property
    def normalized_hinglish_asr_provider(self) -> str:
        provider = self.hinglish_asr_provider.strip().lower()
        if provider not in {"legacy", "elevenlabs"}:
            raise RuntimeError("HINGLISH_ASR_PROVIDER must be 'legacy' or 'elevenlabs'.")
        return provider

    @property
    def hinglish_roman_pipeline_enabled(self) -> bool:
        return (
            self.normalized_hinglish_asr_provider == "elevenlabs"
            and self.roman_hinglish_enabled
            and self.roman_hinglish_policy.strip().lower() == "v3"
            and self.roman_hinglish_display_policy.strip().lower() == "v1"
        )

    @property
    def hinglish_stage1_ids(self) -> frozenset[str]:
        """Exact server-side IDs only; malformed/empty values fail closed."""
        values = [item.strip() for item in self.hinglish_stage1_user_ids.split(",") if item.strip()]
        return frozenset(value for value in values if value.replace("-", "").isalnum())

    def stage1_hinglish_eligible(self, language_hint: str, authenticated_user_id: str | None) -> bool:
        return bool(
            self.hinglish_stage1_enabled
            and authenticated_user_id
            and language_hint.strip().lower().replace("-", "_") in {"hinglish", "roman_hinglish"}
            and authenticated_user_id in self.hinglish_stage1_ids
        )

    @property
    def effective_require_asr_consensus(self) -> bool:
        """Consensus is a legacy local-ASR quality gate, not an API retry trigger."""
        return self.require_asr_consensus if self.normalized_asr_mode == "local" else False

    @property
    def effective_require_forced_alignment(self) -> bool:
        """Provider word timestamps are authoritative in API mode; WhisperX stays local-only."""
        return self.require_forced_alignment if self.normalized_asr_mode == "local" else False


@lru_cache
def get_settings() -> Settings:
    return Settings()
