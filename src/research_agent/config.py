"""Application configuration.

All runtime configuration enters through this module. No other module should
read ``os.environ`` directly: it makes tests and replays non-deterministic.

Provider limits, prices, and routing live in ``config/providers.yaml`` (not
here) because free-tier limits change without notice and must be verifiable.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

AppEnv = Literal["local", "test", "staging", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMMode = Literal["live", "record", "replay"]


class Settings(BaseSettings):
    """Typed, environment-driven settings.

    Budget fields are hard caps enforced by the graph runtime, not hints.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    app_env: AppEnv = "local"
    log_level: LogLevel = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_auth_token: SecretStr = Field(default=SecretStr("dev-local-token"))
    llm_mode: LLMMode = "replay"

    # Storage
    database_url: str = "postgresql+psycopg://research:research@localhost:5432/research"
    cache_dir: Path = Path(".cache/research-agent")

    # Embeddings (local ONNX; no API cost)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = Field(default=384, gt=0, le=4096)

    # Config files
    providers_config_path: Path = Path("config/providers.yaml")
    budgets_config_path: Path = Path("config/budgets.yaml")
    retrieval_config_path: Path = Path("config/retrieval.yaml")

    # Free-tier LLM providers (keys are read by the router, not by nodes)
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    cerebras_api_key: SecretStr | None = None
    mistral_api_key: SecretStr | None = None
    ollama_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434/v1"

    # Search
    searxng_url: str = "http://localhost:8080"
    searxng_engines: str = ""
    search_user_agent: str = "autonomous-research-agent/0.1 (local research; contact: local)"

    # Hard per-run budgets (mirrors config/budgets.yaml defaults)
    max_steps: int = Field(default=40, gt=0)
    max_tool_calls: int = Field(default=25, gt=0)
    max_total_tokens: int = Field(default=100_000, gt=0)
    max_cost_usd: float = Field(default=0.0, ge=0)
    max_wall_clock_seconds: int = Field(default=600, gt=0)
    max_research_loops: int = Field(default=2, ge=0)
    max_revision_loops: int = Field(default=2, ge=0)

    # Human-in-the-loop
    approval_ttl_seconds: int = Field(default=86_400, gt=0)
    approval_required_memory_write: bool = True
    approval_required_export: bool = True
    approval_required_over_budget: bool = True

    # Observability (OTLP exporter optional; no paid tracing service)
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""

    @property
    def langgraph_database_url(self) -> str:
        """Plain psycopg URL for LangGraph's Postgres saver.

        SQLAlchemy URLs carry a driver suffix (``postgresql+psycopg://``) which
        psycopg's own connection helper does not parse.
        """
        url = make_url(self.database_url).set(drivername="postgresql")
        return url.render_as_string(hide_password=False)

    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy URL for Alembic's synchronous migration engine."""
        return self.database_url

    def ensure_cache_dir(self) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.cache_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Tests that mutate the environment must call ``get_settings.cache_clear()``.
    """
    return Settings()
