"""API response/request schemas.

Phase 0 exposes only operational endpoints. Run, approval, and report schemas
land in Phase 2 alongside the persistence layer.
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness response. Deliberately does not touch the database."""

    status: Literal["ok"] = "ok"
    version: str
    env: str


class VersionResponse(BaseModel):
    name: Literal["autonomous-research-agent"] = "autonomous-research-agent"
    version: str
