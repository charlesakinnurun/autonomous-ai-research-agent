"""Provider configuration loaded from YAML.

Limits are data, not code. A missing/unknown provider fails closed instead of
silently using a default quota.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator

from research_agent.config import Settings
from research_agent.core.runtime import load_yaml
from research_agent.models.common import FrozenModel, QuotaLimits


class ModelAliases(FrozenModel):
    default: str = Field(min_length=1)
    fast: str = Field(min_length=1)


class ProviderCapabilities(FrozenModel):
    json_mode: bool = False
    tools: bool = False
    streaming: bool = True
    context_window: int = Field(default=8192, gt=0)


class ProviderPricing(FrozenModel):
    """Shadow pricing for comparability. Free tiers normally set both to 0."""

    input_usd_per_mtok: float = Field(default=0.0, ge=0)
    output_usd_per_mtok: float = Field(default=0.0, ge=0)


class ProviderConfig(FrozenModel):
    enabled: bool = True
    kind: Literal["openai_compatible"] = "openai_compatible"
    base_url: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    priority: int = Field(default=100, ge=0)
    verified: str | None = None
    models: ModelAliases
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    # Required on purpose: an omitted limit must fail closed, not become unlimited.
    limits: QuotaLimits
    pricing: ProviderPricing = Field(default_factory=ProviderPricing)

    def api_key(self, settings: Settings) -> str | None:
        """Read the key through Settings (never ``os.environ`` in nodes)."""
        mapping: dict[str, SecretStr | None] = {
            "GROQ_API_KEY": settings.groq_api_key,
            "GEMINI_API_KEY": settings.gemini_api_key,
            "OPENROUTER_API_KEY": settings.openrouter_api_key,
            "CEREBRAS_API_KEY": settings.cerebras_api_key,
            "MISTRAL_API_KEY": settings.mistral_api_key,
            "OLLAMA_API_KEY": settings.ollama_api_key,
        }
        value = mapping.get(self.api_key_env)
        if value is None:
            return None
        return value.get_secret_value()

    def base_url_for(self, settings: Settings) -> str:
        if self.api_key_env == "OLLAMA_API_KEY" and settings.ollama_base_url:
            return settings.ollama_base_url.rstrip("/")
        return self.base_url.rstrip("/")


class RoleRouting(FrozenModel):
    planner: list[str] = Field(default_factory=list)
    writer: list[str] = Field(default_factory=list)
    verifier: list[str] = Field(default_factory=list)
    extractor: list[str] = Field(default_factory=list)
    critic: list[str] = Field(default_factory=list)
    judge: list[str] = Field(default_factory=list)

    def for_role(self, role: str) -> list[str]:
        value = getattr(self, role, None)
        if value is None:
            raise KeyError(f"unknown role: {role}")
        return list(value)


class RoutingConfig(FrozenModel):
    fallback_order: list[str] = Field(default_factory=list)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_base_seconds: float = Field(default=1.0, gt=0)
    retry_max_seconds: float = Field(default=30.0, gt=0)
    request_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    roles: RoleRouting = Field(default_factory=RoleRouting)
    allow_local_fallback_for_interactive: bool = True
    allow_local_fallback_for_benchmark: bool = False


class ProvidersConfig(FrozenModel):
    version: int = Field(default=1, ge=1)
    verified_at: str | None = None
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    providers: dict[str, ProviderConfig]

    @model_validator(mode="after")
    def _routing_references_exist(self) -> ProvidersConfig:
        known = set(self.providers)
        for name in self.routing.fallback_order:
            if name not in known:
                raise ValueError(f"fallback_order references unknown provider: {name}")
        for role_name in (
            "planner",
            "writer",
            "verifier",
            "extractor",
            "critic",
            "judge",
        ):
            for name in self.routing.roles.for_role(role_name):
                if name not in known:
                    raise ValueError(f"role {role_name} references unknown provider: {name}")
        return self

    def enabled(self) -> dict[str, ProviderConfig]:
        return {name: config for name, config in self.providers.items() if config.enabled}

    def provider(self, name: str) -> ProviderConfig:
        try:
            return self.providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {name}") from exc


def load_providers_config(path: Path) -> ProvidersConfig:
    return ProvidersConfig.model_validate(load_yaml(path))


def default_providers_config(settings: Settings) -> ProvidersConfig:
    """Load the configured file, with a clear error if it is missing."""
    path = settings.providers_config_path
    if not path.exists() and path.name == "providers.yaml":
        example = path.with_name("providers.example.yaml")
        raise FileNotFoundError(
            f"{path} not found; copy {example} to {path} and verify limits in each provider console"
        )
    return load_providers_config(path)
