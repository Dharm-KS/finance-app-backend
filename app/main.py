import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

DESCRIPTION = """
Backend for the AI-powered *financial friend* mobile app (MVP).

**Auth:** mobile + OTP. Call `/auth/register/*` or `/auth/login/*`, then send
`Authorization: Bearer <access_token>` on every other endpoint (use the **Authorize** button).
MVP OTP is always `123456`.

**Envelope:** success -> `{"success": true, "data": ..., "message": ...}`,
error -> `{"success": false, "message": ..., "error_code": ...}`.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/health", tags=["Health"], summary="Liveness check")
    async def health():
        return {"success": True, "data": {"status": "ok"}, "message": "OK"}

    return app


app = create_app()
