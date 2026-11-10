"""Contract tests for the operational API surface."""

from fastapi.testclient import TestClient

from research_agent.api.app import create_app
from research_agent.config import Settings


def _client() -> TestClient:
    settings = Settings(app_env="test", _env_file=None)  # type: ignore[call-arg]
    return TestClient(create_app(settings))


def test_healthz() -> None:
    response = _client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "env": "test"}


def test_version() -> None:
    response = _client().get("/version")

    assert response.status_code == 200
    assert response.json()["name"] == "autonomous-research-agent"
    assert response.json()["version"] == "0.1.0"


def test_openapi_schema_is_served() -> None:
    response = _client().get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Autonomous Research Agent"
