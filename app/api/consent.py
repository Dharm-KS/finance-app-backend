from fastapi import APIRouter, status

from app.api.deps import Client, CurrentUser, DbSession
from app.schemas.common import AUTH_ERRORS, VALIDATION, ApiResponse, ErrorResponse, ok
from app.schemas.consent import ConsentCreate, ConsentListOut, ConsentOut
from app.services import consent_service

router = APIRouter(prefix="/consents", tags=["Consent"])


@router.get(
    "",
    response_model=ApiResponse[ConsentListOut],
    summary="List consents",
    description="Effective consent status per type (with the text to display) plus the full audit history.",
    responses=AUTH_ERRORS,
)
async def list_consents(user: CurrentUser, db: DbSession):
    return ok(await consent_service.get_overview(db, user), "Consents fetched successfully")


@router.post(
    "",
    response_model=ApiResponse[ConsentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Give or withdraw consent",
    description="Records an auditable consent event (IP and user-agent captured). The purpose text is "
    "taken from the server-side catalogue for the given version. Send `status: REVOKED` to withdraw.",
    responses={**AUTH_ERRORS, **VALIDATION, 400: {"model": ErrorResponse, "description": "Unsupported version"}},
)
async def create_consent(payload: ConsentCreate, user: CurrentUser, db: DbSession, client: Client):
    consent = await consent_service.record(
        db, user, consent_type=payload.consent_type, version=payload.consent_version,
        status=payload.status, client=client,
    )
    return ok(ConsentOut.model_validate(consent), "Consent recorded successfully")
