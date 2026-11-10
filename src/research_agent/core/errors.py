"""Typed error hierarchy.

Every error that crosses a module boundary is a subclass of
``ResearchAgentError`` with a stable ``code`` and a ``retryable`` flag. Nodes
and API handlers translate these into structured events instead of leaking
provider-specific exceptions.
"""

from __future__ import annotations

from typing import Any


class ResearchAgentError(Exception):
    """Base class for all application errors."""

    code = "internal_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class ConfigurationError(ResearchAgentError):
    code = "configuration_error"


class ValidationError(ResearchAgentError):
    code = "validation_error"


class SecurityError(ResearchAgentError):
    code = "security_error"


class BudgetExceeded(ResearchAgentError):
    code = "budget_exceeded"


class CacheError(ResearchAgentError):
    code = "cache_error"


class CacheMissError(CacheError):
    code = "cache_miss"


class ToolError(ResearchAgentError):
    code = "tool_error"


class ToolTimeout(ToolError):
    code = "tool_timeout"
    retryable = True


class ToolRateLimited(ToolError):
    code = "tool_rate_limited"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class ToolServerError(ToolError):
    code = "tool_server_error"
    retryable = True


class ToolResponseError(ToolError):
    code = "tool_response_error"


class ProviderError(ToolError):
    code = "provider_error"


class ProviderRateLimited(ProviderError):
    code = "provider_rate_limited"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class ProviderServerError(ProviderError):
    code = "provider_server_error"
    retryable = True


class QuotaExceeded(ResearchAgentError):
    code = "quota_exceeded"


class ApprovalRequired(ResearchAgentError):
    code = "approval_required"
