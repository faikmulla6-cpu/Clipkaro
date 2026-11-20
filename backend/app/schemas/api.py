from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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
    cartoon_studio_access_override: bool = False


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
    edit_plan: dict | None = None


class TranscriptCorrectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class CropKeyframe(BaseModel):
    time: float = Field(ge=0, le=180)
    focus_x: float = Field(ge=0, le=100)
    # Internal render-control fields share the already-durable keyframe payload
    # and are removed by render_gate before crop tracking sees real keyframes.
    zoom: float | None = Field(default=None, ge=1.0, le=2.0)
    preserve_source_captions: bool | None = None


class ExportRequest(BaseModel):
    resolution: str = Field(default="720p", pattern="^(720p|1080p)$")
    aspect_ratio: str = Field(default="9:16", pattern="^(9:16|1:1|4:5)$")
    caption_style: str = Field(default="kinetic", pattern="^(kinetic|clean|bold|minimal|hindi-pop)$")
    layout_mode: str = Field(default="classic", pattern="^(classic|auto|dual_stack|speaker_focus)$")
    hook_text: str | None = Field(default=None, max_length=120)
    hook_enabled: bool = True
    watermark: bool = True
    brand_kit_id: str | None = None
    focus_x: float = Field(default=50, ge=0, le=100)
    zoom: float = Field(default=1.0, ge=1.0, le=2.0)
    crop_keyframes: list[CropKeyframe] = Field(default_factory=list, max_length=120)
    caption_position: str = Field(default="bottom", pattern="^(bottom|above|center)$")
    # Caption composition is normalized to percentages so Creator Studio preview
    # coordinates remain resolution-independent at render time. caption_y stays
    # optional so existing preset-based exports retain their exact layout.
    caption_x: float = Field(default=50.0, ge=0, le=100)
    caption_y: float | None = Field(default=None, ge=0, le=100)
    caption_scale: float = Field(default=1.0, ge=0.65, le=1.60)
    caption_alignment: str = Field(default="center", pattern="^(left|center|right)$")
    preserve_source_captions: bool = False
    india_quality_mode: bool = False
    caption_language_style: str = Field(default="auto", pattern="^(auto|roman_hinglish|original)$")

    def resolved_hook_text(self, fallback: str | None) -> str:
        """Return the creator-authoritative opening hook for the renderer."""
        if not self.hook_enabled:
            return ""
        return str(self.hook_text or fallback or "")

    @model_validator(mode="after")
    def carry_render_controls(self):
        # Do not silently ignore a requested Smart Layout because the caller
        # combined it with incompatible canvas/caption-preservation settings.
        if self.layout_mode != "classic":
            if self.aspect_ratio != "9:16":
                raise ValueError("Karo Smart Layouts require a 9:16 canvas.")
            if self.preserve_source_captions:
                raise ValueError("Choose Classic to preserve burned-in source captions; Smart Layout uses new captions.")
        # Existing API and durable-worker paths already persist crop_keyframes.
        # One internal marker keeps zoom and the explicit preserve toggle intact
        # across both execution paths without changing public crop semantics.
        has_control = any(
            item.zoom is not None or item.preserve_source_captions is not None
            for item in self.crop_keyframes
        )
        if not has_control:
            self.crop_keyframes.append(CropKeyframe(
                time=180,
                focus_x=self.focus_x,
                zoom=self.zoom,
                preserve_source_captions=self.preserve_source_captions,
            ))
        return self


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
    shorts_used: int = 0
    shorts_limit: int = 0
    shorts_remaining: int = 0
    pass_exhausted: bool = False
    unlimited_exports: bool = False
    source_minutes: float
    processing_minutes_limit: float = 0
    processing_minutes_remaining: float = 0
    source_minutes_per_short: float | None = None
    source_video_limit_minutes: float = 15
    purchased_minutes_remaining: float = 0
    purchased_shorts_remaining: int = 0
    short_unit: str = "source_projects"
    plan_price_paise: int = 0
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
