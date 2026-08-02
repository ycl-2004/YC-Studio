"""Aggregate all API route modules into one router for the FastAPI app."""

from fastapi import APIRouter

from app.api import index

api_router = APIRouter()
api_router.include_router(index.router)
