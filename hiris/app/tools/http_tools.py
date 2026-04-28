from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_DENY_HOSTNAMES = frozenset({
    "supervisor", "homeassistant", "localhost", "host.docker.internal",
})
_DENY_NETS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "100.64.0.0/10",
        "172.16.0.0/12", "192.168.0.0/16",
        "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
        "::1/128", "fe80::/10", "fc00::/7", "ff00::/8",
    )
]
_ALLOWED_SCHEMES = {"http", "https"}
_MAX_RESPONSE_BYTES = 4096
_CONNECT_TIMEOUT = 5.0
_TOTAL_TIMEOUT = 30.0

_BLOCKED_HEADERS = frozenset({
    "authorization", "x-supervisor-token", "x-ha-access",
    "x-hassio-key", "x-ingress-token",
})


@dataclass
class AllowedEndpoint:
    scheme: str
    host: str           # exact hostname or explicit IP literal
    port: int
    path_prefix: str    # must start with /
    allow_subpaths: bool = True
    follow_redirects: bool = False


class BlockedURLError(ValueError):
    pass


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _check_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    for net in _DENY_NETS:
        if ip in net:
            raise BlockedURLError(f"IP {ip} for {host!r} is in denied range {net}")
    # IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) is not caught by IPv4 network checks above;
    # extract the embedded IPv4 address and re-check it.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        _check_ip(ip.ipv4_mapped, host)


def validate_endpoint_entry(entry: dict) -> AllowedEndpoint:
    """Parse and validate an endpoint config dict. Raises ValueError on problems."""
    scheme = str(entry.get("scheme", "")).lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"scheme must be http or https, got {scheme!r}")

    host = str(entry.get("host", "")).lower().rstrip(".")
    if not host:
        raise ValueError("host is required")
    if "*" in host or "?" in host:
        raise ValueError("host wildcards are not allowed — use exact hostname or IP")
    if host in _DENY_HOSTNAMES:
        raise ValueError(f"host {host!r} is not permitted")

    # If host is an IP literal, validate it's not in a denied range
    if _is_ip_literal(host):
        try:
            _check_ip(ipaddress.ip_address(host), host)
        except BlockedURLError as exc:
            raise ValueError(str(exc)) from exc

    port = int(entry.get("port", _default_port(scheme)))

    path_prefix = str(entry.get("path_prefix", "/"))
    if not path_prefix.startswith("/"):
        raise ValueError("path_prefix must start with /")
    lower_pp = path_prefix.lower()
    if ".." in path_prefix or "%2e" in lower_pp or "%2f" in lower_pp or "\\" in path_prefix:
        raise ValueError("path_prefix contains traversal pattern")

    return AllowedEndpoint(
        scheme=scheme,
        host=host,
        port=port,
        path_prefix=path_prefix,
        allow_subpaths=bool(entry.get("allow_subpaths", True)),
        follow_redirects=bool(entry.get("follow_redirects", False)),
    )


def _match_endpoint(parsed, endpoints: list[AllowedEndpoint]) -> AllowedEndpoint | None:
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port or _default_port(scheme)
    path = parsed.path or "/"

    for ep in endpoints:
        if scheme != ep.scheme:
            continue
        if hostname != ep.host:
            continue
        if port != ep.port:
            continue
        if not path.startswith(ep.path_prefix):
            continue
        if not ep.allow_subpaths and path != ep.path_prefix:
            continue
        return ep
    return None


def _resolve_and_validate(host: str, allow_explicit_private: bool) -> str:
    """Resolve hostname, validate every resolved IP. Returns the first valid IP."""
    clean = host.lower().rstrip(".")
    if clean in _DENY_HOSTNAMES:
        raise BlockedURLError(f"hostname {host!r} is not permitted")

    try:
        infos = socket.getaddrinfo(clean, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BlockedURLError(f"DNS resolution failed for {host!r}: {exc}")

    pinned = None
    for _, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        _check_ip(ip, host)
        if ip.is_private and not allow_explicit_private:
            raise BlockedURLError(
                f"resolved IP {ip} for {host!r} is private; "
                "use an explicit IP in allowed_endpoints to permit local devices"
            )
        if pinned is None:
            pinned = str(ip)

    if pinned is None:
        raise BlockedURLError(f"no resolvable address for {host!r}")
    return pinned


def _ip_family(ip_str: str) -> int:
    ip = ipaddress.ip_address(ip_str)
    return socket.AF_INET6 if isinstance(ip, ipaddress.IPv6Address) else socket.AF_INET


class _PinnedResolver:
    """aiohttp-compatible resolver that returns a pre-validated IP, defeating DNS rebinding."""

    def __init__(self, hostname: str, ip: str) -> None:
        self._hostname = hostname
        self._ip = ip

    async def resolve(self, host: str, port: int = 0, family: int = 0) -> list[dict]:
        return [{
            "hostname": self._hostname,
            "host": self._ip,
            "port": port,
            "family": _ip_family(self._ip),
            "proto": 0,
            "flags": 0,
        }]

    async def close(self) -> None:
        pass


async def http_request(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    allowed_endpoints: list[dict] | None = None,
) -> dict[str, Any]:
    if allowed_endpoints is None:
        return {"error": "http_request not configured for this agent (set allowed_endpoints)"}

    try:
        import aiohttp
        from aiohttp import ClientTimeout, TCPConnector
    except ImportError:
        return {"error": "aiohttp not available"}

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return {"error": f"URL scheme {parsed.scheme!r} not allowed; use http or https"}
    if parsed.username or parsed.password:
        return {"error": "URLs with credentials (user:pass@host) are not allowed"}

    try:
        eps = [validate_endpoint_entry(e) for e in allowed_endpoints]
    except ValueError as exc:
        return {"error": f"Invalid endpoint configuration: {exc}"}

    ep = _match_endpoint(parsed, eps)
    if ep is None:
        return {"error": f"URL does not match any allowed endpoint for this agent"}

    hostname = (parsed.hostname or "").lower().rstrip(".")
    loop = asyncio.get_running_loop()
    try:
        pinned_ip = await loop.run_in_executor(
            None, _resolve_and_validate, hostname, _is_ip_literal(ep.host)
        )
    except BlockedURLError as exc:
        return {"error": str(exc)}

    clean_headers = {
        k: v for k, v in (headers or {}).items()
        if k.lower() not in _BLOCKED_HEADERS
    }

    timeout = ClientTimeout(connect=_CONNECT_TIMEOUT, total=_TOTAL_TIMEOUT)
    resolver = _PinnedResolver(hostname, pinned_ip)
    connector = TCPConnector(resolver=resolver)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.request(
                method.upper(),
                url,
                headers=clean_headers,
                data=body.encode("utf-8") if body else None,
                allow_redirects=False,  # redirects bypass _PinnedResolver — never follow
            ) as resp:
                raw = await resp.content.read(_MAX_RESPONSE_BYTES + 1)
                truncated = len(raw) > _MAX_RESPONSE_BYTES
                body_str = raw[:_MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
                result: dict[str, Any] = {
                    "status": resp.status,
                    "content_type": resp.content_type,
                    "body": body_str,
                }
                if truncated:
                    result["truncated"] = True
                return result
    except aiohttp.ClientError as exc:
        return {"error": f"Request failed: {exc}"}
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}


HTTP_REQUEST_TOOL_DEF: dict = {
    "name": "http_request",
    "description": (
        "Make an HTTP request to an external API or service. "
        "Only URLs matching the agent's pre-approved allowed_endpoints can be called. "
        "Returns status code, content type, and response body (capped at 4 KB). "
        "Use this for webhooks, external REST APIs, or local devices explicitly configured by the admin."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to call (must match an allowed endpoint)",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method (default: GET)",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs",
            },
            "body": {
                "type": "string",
                "description": "Optional request body as a string (e.g. JSON payload)",
            },
        },
        "required": ["url"],
    },
}
