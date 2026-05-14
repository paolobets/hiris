# Security Policy

## Supported Versions

HIRIS is distributed as a Home Assistant add-on. Only the **latest released version** receives security fixes.

| Version | Supported |
| ------- | --------- |
| Latest release (see [Releases](https://github.com/paolobets/hiris/releases)) | ✅ |
| Older versions | ❌ |

## Reporting a Vulnerability

**Please do NOT open public GitHub issues for security vulnerabilities.**

If you believe you have found a security issue in HIRIS (for example: token leakage, prompt injection that exfiltrates data, ingress auth bypass, RCE through agent actions, MQTT or HA call_service abuse, etc.), report it privately:

- **Email:** paolo.bets@gmail.com
- **Subject prefix:** `[HIRIS SECURITY]`
- Include: affected version, reproduction steps, impact assessment, and any logs (with secrets redacted).

You should receive an acknowledgement within **5 business days**. Coordinated disclosure: a fix is typically released before public disclosure.

## Scope

In scope:
- The HIRIS add-on container (`hiris/app/` Python code).
- The Lovelace card (`hiris/app/static/`).
- The internal HTTP API and the proxy paths consumed by other add-ons.

Out of scope:
- Vulnerabilities in upstream models (Anthropic / OpenAI / OpenRouter / Ollama). Report those to the upstream vendor.
- Vulnerabilities in Home Assistant Core or Supervisor. Report those upstream.
- Issues that require an attacker with administrative HA access — HIRIS trusts users with HA admin.

## Hardening notes for self-hosters

- Keep `internal_token` set in the add-on config; do not expose port 8099 outside the `hassio` Docker network unless `debug_expose_port` is intentionally enabled.
- Rotate API keys regularly.
- The default ingress flow assumes Supervisor-mediated auth. If you reverse-proxy directly, add your own authentication layer.
