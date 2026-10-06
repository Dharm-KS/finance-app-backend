from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RiskTolerance
from app.schemas.common import ORMModel, Percent, PercentOut


class RiskProfileIn(BaseModel):
    risk_tolerance: RiskTolerance
    max_drawdown_percent: Percent = Field(description="0-100: largest temporary portfolio fall the user can hold through")
    single_stock_limit_percent: Percent = Field(description="0-100: max share of net worth in a single stock")
    planning_horizon_years: int = Field(ge=1, le=50)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "risk_tolerance": "BALANCED",
                "max_drawdown_percent": 18,
                "single_stock_limit_percent": 35,
                "planning_horizon_years": 10,
            }
        }
    )


class RiskProfileOut(ORMModel):
    risk_tolerance: RiskTolerance
    max_drawdown_percent: PercentOut
    single_stock_limit_percent: PercentOut
    planning_horizon_years: int
    created_at: datetime
    updated_at: datetime
