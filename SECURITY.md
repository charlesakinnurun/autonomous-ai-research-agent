# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Development (pre-release) |

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting or contact the maintainer directly. Include:

- affected version/commit,
- reproduction steps,
- impact (data exposure, SSRF, prompt injection, etc.),
- suggested fix if known.

## Security model (v0.1)

- Single-tenant, laptop-only deployment.
- Bearer-token auth stub; not production authentication.
- Retrieved web content is **untrusted data**. It must never cause tool execution, URL fetches, or shell commands.
- SSRF protections: scheme allowlist, DNS/IP checks, redirect re-checks, private IP block, response byte caps.
- Secrets are read from environment variables, never logged, never written to cassettes.
- Free-tier providers may train on prompts: use public data only.
- Memory writes and report exports are approval-gated by default.

## Out of scope for v0.1

- Multi-tenant isolation.
- OAuth/OIDC, RBAC, audit-grade identity.
- Internet-facing deployment.
- Malware analysis of downloaded files.
- OCR sandboxing.

See `docs/DESIGN.md` §5.13 and `docs/RISKS.md` for the full threat model.
