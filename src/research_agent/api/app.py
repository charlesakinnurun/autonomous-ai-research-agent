"""FastAPI application factory."""

from fastapi import FastAPI

from research_agent import __version__
from research_agent.api.schemas import HealthResponse, VersionResponse
from research_agent.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app.

    Injecting ``settings`` keeps tests free of global environment state.
    """
    resolved = settings if settings is not None else get_settings()

    app = FastAPI(
        title="Autonomous Research Agent",
        version=__version__,
        summary="Evidence-first research runs with claim-level citations.",
        license_info={"name": "MIT"},
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["ops"], summary="Liveness probe")
    async def healthz() -> HealthResponse:
        # Liveness only: no DB, no external calls. Readiness arrives in Phase 2.
        return HealthResponse(version=__version__, env=resolved.app_env)

    @app.get("/version", response_model=VersionResponse, tags=["ops"])
    async def version() -> VersionResponse:
        return VersionResponse(version=__version__)

    return app


app = create_app()
