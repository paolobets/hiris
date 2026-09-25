"""Il filo: la conversazione di UN soggetto da UN ingresso.

Spec `docs/design/2026-09-25-le-chat-divise.md` §2. Un modulo solo perche'
cinque punti devono calcolarlo nello stesso modo -- la chat, il poll, la coda,
la rotta MCP, l'officina -- e due calcoli dello stesso filo sono due fili.

«Ingresso» e non «canale»: canale in questo codice e' gia' il servizio
firmato (`api/canali.py`) e la strada del modello (`misura_turno`).
"""
from __future__ import annotations

from dataclasses import dataclass

_INGRESSO_PER_VIA = {"ingress": "pannello", "canale": "firma", "no_token": "sviluppo"}


@dataclass(frozen=True)
class Filo:
    subject_key: str
    entry_point: str


def chiave_soggetto(soggetto: dict | None) -> str:
    """`specie:id` -- mai il nome, che cambia. `-` quando l'id non c'e'."""
    s = soggetto or {}
    return f"{s.get('specie') or 'nessuno'}:{s.get('id') or '-'}"


def ingresso_da(auth_via: str | None) -> str:
    return _INGRESSO_PER_VIA.get(auth_via or "", "interno")


def filo_da(soggetto: dict | None, auth_via: str | None) -> Filo:
    return Filo(chiave_soggetto(soggetto), ingresso_da(auth_via))


def della_richiesta(request) -> Filo:
    return filo_da(request.get("soggetto"), request.get("auth_via"))


def in_contesto(filo: Filo) -> dict:
    return {"subject_key": filo.subject_key, "entry_point": filo.entry_point}


def da_contesto(d: dict | None) -> Filo | None:
    if not d or not d.get("subject_key") or not d.get("entry_point"):
        return None
    return Filo(d["subject_key"], d["entry_point"])
