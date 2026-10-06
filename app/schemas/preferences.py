from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InsightTone


class PreferencesIn(BaseModel):
    """"How your twin talks to you" screen. Fields not sent keep their current value."""

    insight_tone: InsightTone | None = None
    vesting_alerts: bool | None = Field(default=None, description="Before each vest and its tax consequence")
    tax_deadline_alerts: bool | None = Field(default=None, description="Advance tax instalments and filing windows")
    weekly_digest: bool | None = Field(default=None, description="A short weekly read on what changed")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "insight_tone": "BALANCED",
                "vesting_alerts": True,
                "tax_deadline_alerts": True,
                "weekly_digest": False,
            }
        }
    )


class PreferencesOut(BaseModel):
    is_saved: bool = Field(description="False = defaults, nothing saved yet")
    insight_tone: InsightTone
    vesting_alerts: bool
    tax_deadline_alerts: bool
    weekly_digest: bool
    updated_at: datetime | None
