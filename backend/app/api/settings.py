import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.behavioral_learning import router as behavioral_router
from app.api.legal import router as legal_router
from app.core.config import get_settings
from app.core.database import fetch_one, run_in_transaction
from app.services.auth import current_user
from app.services.behavioral_learning import init_behavioral_learning
from app.services.behavioral_triggers import init_behavioral_triggers
from app.services.legal import init_legal_compliance


router = APIRouter()

DEFAULT_LANGUAGE = "auto"
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_CREATOR_CATEGORY = "auto"
ALLOWED_LANGUAGES = {"auto", "en", "hi", "hinglish", "mr"}
ALLOWED_TIMEZONES = {
    "Asia/Kolkata", "UTC", "Asia/Dubai", "Asia/Singapore",
    "Europe/London", "America/New_York", "America/Los_Angeles",
}
ALLOWED_CREATOR_CATEGORIES = {
    "auto", "education", "podcast", "business", "motivation", "spiritual", "local-business",
}


class AccountSettingsOut(BaseModel):
    name: str
    email: str
    default_language: str = DEFAULT_LANGUAGE
    timezone: str = DEFAULT_TIMEZONE
    creator_category: str = DEFAULT_CREATOR_CATEGORY


class AccountSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=60)
    default_language: str | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    creator_category: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least 2 characters.")
        return cleaned

    @field_validator("default_language")
    @classmethod
    def valid_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_LANGUAGES:
            raise ValueError("Choose a supported default language.")
        return value

    @field_validator("creator_category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_CREATOR_CATEGORIES:
            raise ValueError("Choose a supported creator category.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in ALLOWED_TIMEZONES:
            raise ValueError("Choose a supported timezone.")
        return value


async def init_user_preferences() -> None:
    """Create creator preferences and bounded product-compliance side stores."""
    settings = get_settings()
    if settings.normalized_database_backend == "postgres":
        return
    async def create(db) -> None:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
              user_id TEXT PRIMARY KEY,
              default_language TEXT NOT NULL DEFAULT 'auto',
              timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
              creator_category TEXT NOT NULL DEFAULT 'auto',
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
    await run_in_transaction(create, operation_name="user preferences schema")
    await init_legal_compliance()
    await init_behavioral_learning()
    await init_behavioral_triggers()


async def _read_settings(user: dict) -> AccountSettingsOut:
    row = await fetch_one(
        "SELECT default_language,timezone,creator_category FROM user_preferences WHERE user_id=?",
        (user["id"],),
    )
    return AccountSettingsOut(
        name=user["name"],
        email=user["email"],
        default_language=row["default_language"] if row else DEFAULT_LANGUAGE,
        timezone=row["timezone"] if row else DEFAULT_TIMEZONE,
        creator_category=row["creator_category"] if row else DEFAULT_CREATOR_CATEGORY,
    )


@router.get("/settings", response_model=AccountSettingsOut)
async def get_account_settings(user: dict = Depends(current_user)) -> AccountSettingsOut:
    return await _read_settings(user)


@router.patch("/settings", response_model=AccountSettingsOut)
async def update_account_settings(
    body: AccountSettingsPatch,
    user: dict = Depends(current_user),
) -> AccountSettingsOut:
    timestamp = datetime.now(timezone.utc).isoformat()
    changed = sorted(body.model_fields_set)
    result: dict[str, str] = {}
    async def save(db) -> None:
            # Serialize the read/merge/write sequence. This prevents two tabs
            # saving different partial fields from overwriting one another.
            user_cursor = await db.execute("SELECT name,email FROM users WHERE id=?", (user["id"],))
            fresh_user = await user_cursor.fetchone()
            if not fresh_user:
                raise HTTPException(401, "Account not found.")

            pref_cursor = await db.execute(
                "SELECT default_language,timezone,creator_category FROM user_preferences WHERE user_id=?",
                (user["id"],),
            )
            pref = await pref_cursor.fetchone()

            current_language = pref["default_language"] if pref else DEFAULT_LANGUAGE
            current_timezone = pref["timezone"] if pref else DEFAULT_TIMEZONE
            current_category = pref["creator_category"] if pref else DEFAULT_CREATOR_CATEGORY

            name = body.name if body.name is not None else fresh_user["name"]
            language = body.default_language if body.default_language is not None else current_language
            timezone_name = body.timezone if body.timezone is not None else current_timezone
            category = body.creator_category if body.creator_category is not None else current_category

            await db.execute(
                "UPDATE users SET name=?,onboarding_complete=1,updated_at=? WHERE id=?",
                (name, timestamp, user["id"]),
            )
            await db.execute(
                """
                INSERT INTO user_preferences(
                  user_id,default_language,timezone,creator_category,created_at,updated_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                  default_language=excluded.default_language,
                  timezone=excluded.timezone,
                  creator_category=excluded.creator_category,
                  updated_at=excluded.updated_at
                """,
                (user["id"], language, timezone_name, category, timestamp, timestamp),
            )
            await db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), user["id"], "account.settings_updated", "user", user["id"],
                    json.dumps({"fields": changed}), timestamp,
                ),
            )
            result.update(name=name, email=fresh_user["email"], language=language, timezone=timezone_name, category=category)

    await run_in_transaction(save, operation_name="update account settings")

    return AccountSettingsOut(
        name=result["name"],
        email=result["email"],
        default_language=result["language"],
        timezone=result["timezone"],
        creator_category=result["category"],
    )


# Main already mounts the settings router. Nest bounded public/account APIs here
# to avoid duplicate route registration and keep startup ownership in one module.
router.include_router(legal_router)
router.include_router(behavioral_router)
