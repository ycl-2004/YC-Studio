"""Response contracts for liveness and readiness endpoints."""

from typing import Literal

from pydantic import BaseModel, Field

DependencyStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Minimal dependency-free liveness response."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Availability of every dependency required to serve traffic."""

    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus]
    failed_dependencies: list[str] = Field(default_factory=list)
