from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ConsentStatus, ConsentType
from app.schemas.common import ORMModel


class ConsentCreate(BaseModel):
    consent_type: ConsentType
    consent_version: str = Field(min_length=1, max_length=20, examples=["v1"])
    status: ConsentStatus = Field(
        default=ConsentStatus.GRANTED, description="GRANTED to give consent, REVOKED to withdraw it"
    )

    model_config = ConfigDict(json_schema_extra={"example": {"consent_type": "CREDIT_REPORT", "consent_version": "v1"}})


class ConsentOut(ORMModel):
    id: int
    consent_type: ConsentType
    consent_version: str
    purpose: str
    status: ConsentStatus
    consented_at: datetime
    created_at: datetime


class ConsentStatusItem(BaseModel):
    consent_type: ConsentType
    status: ConsentStatus | None = Field(description="Latest status, or null if never given")
    consent_version: str | None
    latest_version: str
    consented_at: datetime | None
    required_for: str
    purpose: str


class ConsentListOut(BaseModel):
    current: list[ConsentStatusItem] = Field(description="Effective consent per type")
    history: list[ConsentOut] = Field(description="Full audit trail, newest first")
