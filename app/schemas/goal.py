from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import GoalCategory, GoalPriority, GoalStatus, GoalType
from app.schemas.common import Money, MoneyOut, PercentOut


class GoalInputs(BaseModel):
    """Extra numbers some goals are sized from. Send only the ones that goal needs."""

    property_value: Money | None = Field(default=None, description="HOME_DOWN_PAYMENT: target property value")
    education_cost_today: Money | None = Field(
        default=None, description="CHILD_EDUCATION: total course fees at today's prices"
    )
    years_to_admission: int | None = Field(default=None, ge=0, le=30, description="CHILD_EDUCATION")
    years_to_retirement: int | None = Field(
        default=None, ge=0, le=60, description="RETIREMENT_CORPUS: optional; adds inflation to the target"
    )
    health_premium_annual: Money | None = Field(
        default=None, description="SABBATICAL_RUNWAY: optional; yearly health-cover premium"
    )

    model_config = ConfigDict(extra="forbid")


class GoalCreate(BaseModel):
    goal_type: GoalType
    name: str | None = Field(default=None, min_length=1, max_length=120, description="Defaults per goal type")
    description: str | None = Field(default=None, max_length=1000)
    priority: GoalPriority | None = Field(default=None, description="Defaults per goal type")
    target_amount: Money | None = Field(
        default=None, description="Optional: calculated from the user's data when omitted (see suggestions)"
    )
    current_amount: Money | None = Field(default=None, description="Defaults to a sensible value or 0")
    target_date: date | None = None
    inputs: GoalInputs | None = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"goal_type": "EMERGENCY_FUND"}}
    )


class GoalUpdate(BaseModel):
    """Partial update."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    priority: GoalPriority | None = None
    target_amount: Money | None = None
    current_amount: Money | None = None
    target_date: date | None = None
    status: GoalStatus | None = None
    inputs: GoalInputs | None = Field(default=None, description="Replaces the stored inputs")

    model_config = ConfigDict(json_schema_extra={"example": {"current_amount": 200000, "status": "ACTIVE"}})


class GoalSelectionItem(BaseModel):
    goal_type: GoalType
    target_amount: Money | None = Field(default=None, description="Override the calculated target")
    inputs: GoalInputs | None = None


class GoalSelectionIn(BaseModel):
    """The goals screen's ticked cards. The saved goal list becomes exactly this selection."""

    goals: list[GoalSelectionItem] = Field(min_length=1)

    @field_validator("goals")
    @classmethod
    def _unique(cls, v: list[GoalSelectionItem]) -> list[GoalSelectionItem]:
        types = [g.goal_type for g in v]
        if len(types) != len(set(types)):
            raise ValueError("Each goal_type may appear only once")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "goals": [
                    {"goal_type": "EMERGENCY_FUND"},
                    {"goal_type": "EQUITY_TAX_RESERVE"},
                    {"goal_type": "RETIREMENT_CORPUS"},
                    {"goal_type": "HOME_DOWN_PAYMENT", "inputs": {"property_value": 15000000}},
                ]
            }
        }
    )


class GoalCalculation(BaseModel):
    """How the system sizes this goal from the user's current data."""

    suggested_target_amount: MoneyOut | None
    basis: str
    details: dict[str, float | int | str | None] = {}
    required_inputs: list[str] = Field(
        default=[], description="GoalInputs fields the user must supply before a target can be calculated"
    )


class GoalOut(BaseModel):
    id: int
    goal_type: GoalType
    category: GoalCategory
    name: str
    description: str | None
    priority: GoalPriority
    target_amount: MoneyOut
    current_amount: MoneyOut
    remaining_amount: MoneyOut
    progress_percent: PercentOut
    target_date: date | None
    status: GoalStatus
    is_at_risk: bool
    at_risk_reason: str | None
    inputs: dict[str, float | int | None] | None
    calculation: GoalCalculation | None
    created_at: datetime
    updated_at: datetime


class GoalListOut(BaseModel):
    goals: list[GoalOut]


class GoalSuggestionOut(BaseModel):
    goal_type: GoalType
    category: GoalCategory
    name: str
    description: str
    priority: GoalPriority
    calculation: GoalCalculation
    already_added: bool
