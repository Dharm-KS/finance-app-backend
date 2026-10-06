"""Consent capture. Consents are append-only so every grant/revoke is auditable."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ErrorCode
from app.core.time import utcnow
from app.models.consent import Consent
from app.models.enums import ConsentStatus, ConsentType
from app.models.user import User
from app.services import onboarding_service
from app.services.otp_service import ClientInfo


@dataclass(frozen=True)
class ConsentDefinition:
    latest_version: str
    required_for: str
    purposes: dict[str, str]  # version -> exact text shown to the user


# The server owns the consent text: the client only says which type/version it displayed,
# and we record the exact purpose text for that version.
CONSENT_CATALOG: dict[ConsentType, ConsentDefinition] = {
    ConsentType.CREDIT_REPORT: ConsentDefinition(
        latest_version="v1",
        required_for="Fetching your credit report and score from a credit bureau",
        purposes={
            "v1": "I authorise the app to obtain my credit information report and credit score from "
            "credit information companies (such as CIBIL) to show me my credit health and to personalise "
            "my financial insights. This consent is valid until I withdraw it."
        },
    ),
    ConsentType.FINANCIAL_ANALYSIS: ConsentDefinition(
        latest_version="v1",
        required_for="Generating personalised financial insights",
        purposes={
            "v1": "I agree that the app may analyse the financial information I provide or authorise, "
            "to generate personalised insights, risk analysis and goal recommendations."
        },
    ),
    ConsentType.DATA_PROCESSING: ConsentDefinition(
        latest_version="v1",
        required_for="Storing and processing your data",
        purposes={
            "v1": "I agree to the storage and processing of my personal and financial data as described "
            "in the Privacy Policy."
        },
    ),
}


async def list_history(db: AsyncSession, user: User) -> list[Consent]:
    stmt = (
        select(Consent)
        .where(Consent.user_id == user.id)
        .order_by(Consent.created_at.desc(), Consent.id.desc())
    )
    return list((await db.execute(stmt)).scalars())


async def get_overview(db: AsyncSession, user: User) -> dict:
    history = await list_history(db, user)
    latest: dict[ConsentType, Consent] = {}
    for c in history:  # newest first
        latest.setdefault(c.consent_type, c)
    current = []
    for ctype, definition in CONSENT_CATALOG.items():
        c = latest.get(ctype)
        current.append(
            {
                "consent_type": ctype,
                "status": c.status if c else None,
                "consent_version": c.consent_version if c else None,
                "latest_version": definition.latest_version,
                "consented_at": c.consented_at if c else None,
                "required_for": definition.required_for,
                "purpose": definition.purposes[definition.latest_version],
            }
        )
    return {"current": current, "history": history}


async def record(
    db: AsyncSession, user: User, *, consent_type: ConsentType, version: str, status: ConsentStatus, client: ClientInfo
) -> Consent:
    definition = CONSENT_CATALOG[consent_type]
    purpose = definition.purposes.get(version)
    if purpose is None:
        raise AppError(
            400,
            f"Unsupported consent version '{version}'. Latest is '{definition.latest_version}'.",
            ErrorCode.CONSENT_VERSION_UNSUPPORTED,
        )
    consent = Consent(
        user_id=user.id,
        consent_type=consent_type,
        consent_version=version,
        purpose=purpose,
        status=status,
        consented_at=utcnow(),
        ip_address=client.ip_address,
        user_agent=(client.user_agent or "")[:255] or None,
    )
    db.add(consent)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    return consent


async def has_active_consent(db: AsyncSession, user: User, consent_type: ConsentType) -> bool:
    status = (
        await db.execute(
            select(Consent.status)
            .where(Consent.user_id == user.id, Consent.consent_type == consent_type)
            .order_by(Consent.created_at.desc(), Consent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return status == ConsentStatus.GRANTED
