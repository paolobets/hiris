from __future__ import annotations


def resolve_owner(request) -> str:
    """Owner = HA user id dagli header ingress, altrimenti 'home' (condiviso)."""
    uid = request.headers.get("X-Remote-User-Id", "").strip()
    return uid or "home"
