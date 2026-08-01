"""API index endpoint."""

from fastapi import APIRouter

from ycstudio.core.config import get_settings

router = APIRouter()


@router.get("/", tags=["system"], summary="Describe the API")
async def api_index() -> dict[str, str]:
    """Return a stable, dependency-free API entry point."""

    return {"name": get_settings().app_name}
