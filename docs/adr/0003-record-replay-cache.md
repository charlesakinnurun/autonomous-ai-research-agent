# ADR-0003: Record/Replay Cache for Every External Call

- **Status:** Accepted
- **Date:** 2026-11-07
- **Phase:** 1 (design in Phase 0)
- **Deciders:** Project owner

## Context

The benchmark must be reproducible, cheap, and CI-safe. Free-tier APIs are rate-limited, nondeterministic, and can change models. Search results and web pages change daily. Without a cache, every eval is a different experiment and CI cannot run without secrets.

The cache must cover LLM calls, search queries, page fetches, and PDF parses. It must support three modes:

- `record`: call live, store the response.
- `replay`: read only; fail on miss.
- `live`: call live, bypass the cache (or write-through for debugging).

## Decision

Use a **content-addressed filesystem cache** with JSON envelopes, plus a `CacheMode` enum.

```text
.cache/research-agent/
  llm/<sha256>.json
  search/<sha256>.json
  fetch/<sha256>.json
  pdf/<sha256>.json
```

Cache key:

```text
sha256(
  tool_name + tool_version +
  normalized_request +
  relevant_config (model, temperature, max_tokens, prompt_version)
)
```

Envelope:

```json
{
  "key": "...",
  "tool": "llm.chat",
  "version": "1",
  "request": {...},
  "response": {...},
  "provider": "groq",
  "model": "llama-3.3-70b-versatile",
  "recorded_at": "2026-11-07T12:00:00Z",
  "latency_ms": 812,
  "usage": {"tokens_in": 1200, "tokens_out": 300},
  "content_hash": "sha256:..."
}
```

Rules:

- Replay mode performs **zero** network calls; a miss raises `CacheMissError` and fails CI.
- Record mode writes to a staging directory, not directly to committed fixtures.
- Committed benchmark cassettes live under `evals/cassettes/<dataset_version>/`; they are reviewed and promoted deliberately.
- Secrets are never stored; request headers are excluded from the envelope.
- LLM cache keys include the prompt hash and model; search keys include normalized query + engine; fetch keys include URL + user agent + parser version.
- Cache entries are immutable. A parser or prompt change produces a new key.
- Add a `manifest.json` per cassette bundle with hashes and tool versions.

## Consequences

**Positive**

- CI runs with no secrets and no live calls.
- Evals are deterministic and cheap.
- Debugging can replay exact provider responses.
- Benchmark snapshots are explicit, reviewable artifacts.

**Negative**

- Disk usage grows; needs pruning.
- Bad cache keys cause false hits; needs discipline and tests.
- Recorded responses can hide provider drift.
- Sensitive data could leak into cassettes if not scrubbed.

**Mitigations**

- Content hashing + key-version tests.
- `scripts/scan_cassettes.py` for key/email/PII patterns.
- Periodic replay-vs-live spot checks.
- Prune local cache; keep benchmark cassettes immutable.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| VCR.py / pytest-recording | Test-oriented; not a runtime cache for the app or benchmark |
| Redis cache | Extra service; less transparent for committed fixtures |
| Database cache only | Harder to review/diff; filesystem is better for cassettes |
| No cache | Non-reproducible, quota-heavy, CI requires secrets |

## Verification

- Record → replay round-trip test.
- Replay miss fails hard.
- Cache key changes when prompt/model/parser version changes.
- Secret scanner test.
- Benchmark replay in CI with network disabled.

## References

- `docs/QUOTA_PLAN.md`
- `docs/EVAL_PLAN.md` §2.4
- `docs/RISKS.md` R-20
