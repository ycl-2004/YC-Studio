"""Aggregate all API route modules into one router for the FastAPI app."""

from fastapi import APIRouter

from app.api import health, index, kb
from app.core.config import get_settings

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(index.router, prefix=get_settings().api_prefix)
api_router.include_router(kb.router, prefix=get_settings().api_prefix)
