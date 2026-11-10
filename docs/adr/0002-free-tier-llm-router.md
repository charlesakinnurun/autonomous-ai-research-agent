# ADR-0002: Provider-Agnostic LLM Router with a Postgres Quota Tracker

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 0
- **Deciders:** Project owner

## Context

The project must run at $0 using free-tier APIs (Groq, Gemini, optional OpenRouter/Cerebras/Mistral) with a local Ollama fallback. Free tiers differ in:

- rate limits (RPM, RPD, TPM, TPD) that change without notice;
- model IDs and capabilities (JSON mode, tool calling, context length);
- reliability and error shapes;
- data-retention policies.

We need one call interface, deterministic fallback, per-provider limit enforcement, record/replay, and durable quota state across restarts. The hard requirement is that limits are **configuration**, not code.

## Decision

Build a thin **OpenAI-compatible client + router** with:

1. Provider adapters that supply base URL, auth, model aliases, capabilities, and limits.
2. A capability filter (context length, JSON schema, tools, streaming).
3. A quota/rate check backed by Postgres (`quota_usage`, `quota_reservations`).
4. Deterministic provider selection by priority and headroom, with health/cooldown state.
5. Retry with exponential backoff + jitter on 429/5xx; no retry on most 4xx.
6. Fallback chain: Groq → Gemini → Ollama (configurable).
7. A content-addressed cache with `record` / `replay` / `live` modes.
8. Per-call usage accounting (tokens in/out, latency, cache hit, provider, model).

LiteLLM is not used as the router in v0.1, though it remains the top alternative.

## Consequences

**Positive**

- Full control of quota accounting, fallback, and replay determinism.
- One place to add a provider (adapter + config).
- Quota state survives restarts; benchmark collection can pause/resume.
- No hidden paid dependency or telemetry.

**Negative**

- We own retry/fallback edge cases and provider quirks.
- More code than adopting LiteLLM.
- Provider-specific features (e.g., native JSON schema) need per-adapter handling.
- Free-tier limits require manual verification.

**Mitigations**

- Keep adapters tiny and contract-tested.
- Record provider/model/version per call.
- Add a provider smoke script.
- Revisit LiteLLM if maintenance exceeds ~1 day/month.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| LiteLLM router | Good coverage, but quota tracking, replay, and deterministic selection still need a wrapper; extra dependency and abstraction |
| Direct SDKs per provider | Duplicated retry/usage/cache logic; hard to compare fairly |
| OpenRouter only | Single point of failure; free pool is congested; still need fallback |
| Ollama only | Zero quota risk but weaker quality; insufficient for a credible benchmark |
| Paid APIs | Violates the $0 constraint |

## Verification

- Adapter contract tests with recorded responses.
- Quota tests: reserve, commit, release, exhaust, reset, fallback.
- Replay test with zero network.
- Provider smoke script (manual, live).
- Grep test: no hardcoded limits in `src/`.

## References

- `docs/DESIGN.md` §5.10
- `docs/QUOTA_PLAN.md`
- `docs/RISKS.md` R-02, R-16
