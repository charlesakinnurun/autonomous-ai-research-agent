"""Role-based provider routing with fallback."""

from __future__ import annotations

from research_agent.config import Settings
from research_agent.core.errors import ProviderError, QuotaExceeded, ToolError
from research_agent.llm.client import LLMClient
from research_agent.llm.provider_config import ProvidersConfig
from research_agent.llm.quota import QuotaTracker
from research_agent.models.tools import LLMRequest, LLMResponse

FALLBACK_ERRORS = (ProviderError, QuotaExceeded, ToolError)


class LLMRouter:
    """Resolve a role to an ordered provider list and fall back on retryable errors."""

    def __init__(
        self,
        *,
        config: ProvidersConfig,
        settings: Settings,
        clients: dict[str, LLMClient],
        quota: QuotaTracker | None = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self.clients = clients
        self.quota = quota

    async def chat(self, request: LLMRequest, *, role: str = "planner") -> LLMResponse:
        errors: list[str] = []
        for provider_name in self._providers_for_role(role):
            client = self.clients.get(provider_name)
            if client is None:
                continue
            try:
                return await client.chat(request)
            except FALLBACK_ERRORS as exc:
                errors.append(f"{provider_name}:{exc.code}")
                continue
        if errors:
            raise ProviderError(
                f"all providers failed for role {role}",
                details={"attempts": ",".join(errors)},
            )
        raise ProviderError(f"no enabled provider available for role {role}")

    def _providers_for_role(self, role: str) -> list[str]:
        configured = self.config.routing.roles.for_role(role)
        candidates = configured or self.config.routing.fallback_order
        out: list[str] = []
        for name in candidates:
            provider = self.config.providers.get(name)
            if provider is not None and provider.enabled and name in self.clients:
                out.append(name)
        return out

    async def aclose(self) -> None:
        for client in self.clients.values():
            await client.aclose()
