from fastapi import APIRouter

from app.api import (
    advisor,
    aggregator,
    auth,
    consent,
    credit,
    dashboard,
    equity,
    financial,
    goals,
    onboarding,
    preferences,
    risk,
)

api_router = APIRouter()
for module in (
    auth, onboarding, consent, credit, financial, equity, risk, goals, preferences, dashboard, aggregator, advisor,
):
    api_router.include_router(module.router)
