from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # Optional at the schema layer so legacy/test fixtures remain usable. The
    # production signup route requires both fields and records the versioned
    # acceptance before issuing a creator session.
    accept_legal: bool = False
    legal_version: str | None = Field(default=None, min_length=8, max_length=40)

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        if not any(c.isupper() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain an uppercase letter and a number.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    plan: str
    role: str
    onboarding_complete: bool = False


class AuthOut(BaseModel):
    user: UserOut
    token_type: str = "cookie"


class ProjectOut(BaseModel):
    id: str
    title: str
    status: str
    progress: int = 0
    stage: str = "created"
    video_id: str | None = None
    job_id: str | None = None
    created_at: str
    updated_at: str | None = None


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=30)


class Segment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)


class AnalyseRequest(BaseModel):
    segments: list[Segment] | None = None
    language: str = "auto"


class ScoreBreakdown(BaseModel):
    hook: float
    clarity: float
    value: float
    emotion: float
    flow: float


class ClipOut(BaseModel):
    id: str
    start_time: float
    end_time: float
    hook: str
    title: str
    reason: str
    transcript_text: str = ""
    score: float
    score_breakdown: dict = {}
    platform: str
    status: str = "suggested"


class ClipPatch(BaseModel):
    start_time: float | None = Field(default=None, ge=0)
    end_time: float | None = Field(default=None, gt=0)
    hook: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    transcript_text: str | None = Field(default=None, max_length=10000)


class TranscriptCorrectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class CropKeyframe(BaseModel):
    time: float = Field(ge=0, le=180)
    focus_x: float = Field(ge=0, le=100)


class ExportRequest(BaseModel):
    resolution: str = Field(default="720p", pattern="^(720p|1080p)$")
    aspect_ratio: str = Field(default="9:16", pattern="^(9:16|1:1|4:5)$")
    caption_style: str = Field(default="kinetic", pattern="^(kinetic|clean|bold|minimal|hindi-pop)$")
    hook_text: str | None = Field(default=None, max_length=120)
    watermark: bool = True
    brand_kit_id: str | None = None
    focus_x: float = Field(default=50, ge=0, le=100)
    zoom: float = Field(default=1.0, ge=1.0, le=2.0)
    crop_keyframes: list[CropKeyframe] = Field(default_factory=list, max_length=120)
    caption_position: str = Field(default="bottom", pattern="^(bottom|above|center)$")
    preserve_source_captions: bool = False
    india_quality_mode: bool = False
    caption_language_style: str = Field(default="auto", pattern="^(auto|roman_hinglish|original)$")


class ExportOut(BaseModel):
    id: str
    job_id: str | None = None
    status: str
    progress: int = 0
    download_url: str | None = None
    expires_at: str


class UsageOut(BaseModel):
    plan: str
    exports_used: int
    exports_limit: int
    exports_remaining: int
    source_minutes: float
    processing_minutes_limit: float = 0
    processing_minutes_remaining: float = 0
    period_key: str = ""


class BrandKitRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    primary_color: str = Field(pattern="^#[0-9A-Fa-f]{6}$")
    # Retained for backwards-compatible stored rows. Caption personalities have
    # their own frozen palette/font rules, so launch Brand Kits expose only
    # settings that are actually rendered: wordmark, primary colour and preset.
    accent_color: str = Field(default="#165F43", pattern="^#[0-9A-Fa-f]{6}$")
    font_family: str = Field(default="Inter", max_length=60)
    logo_text: str = Field(default="", max_length=40)
    caption_preset: str = Field(default="kinetic", pattern="^(kinetic|clean|bold|minimal|hindi-pop)$")
    is_default: bool = False


class ScheduleRequest(BaseModel):
    export_id: str
    platform: str = Field(pattern="^(youtube|instagram|tiktok|linkedin)$")
    caption: str = Field(max_length=2200)
    hashtags: str = Field(default="", max_length=500)
    scheduled_for: datetime
