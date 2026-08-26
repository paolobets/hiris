"""Cosa l'osservatore guarda comunque, qualunque cosa dica l'obiettivo.

**Il pavimento non e' una lista scritta a mano.** Si deriva da cio' che Home
Assistant dichiara gia' su ogni entita' -- dominio, classe del dispositivo,
classe dello stato -- perche' una lista a mano invecchia col primo dispositivo
nuovo e nessuno se ne accorge.

**Perche' esiste un pavimento.** Il prompt dell'obiettivo decide cosa entra
nelle osservazioni, quindi e' un punto singolo che puo' ACCECARE l'osservatore
-- e cio' che non e' stato osservato non esiste piu': riscrivere il prompt fra
tre mesi non fa ricomparire i tre mesi mancanti. Il pavimento e' cio' che il
prompt non puo' togliere. Sopra di esso allarga; sotto, mai.
"""
from __future__ import annotations

GAMBE = ("chi c'e'", "comfort", "dispersione", "consumo", "buono stato")

# Le classi che Home Assistant dichiara, raggruppate per gamba dell'obiettivo.
# I nomi sono quelli veri di HA, non nostri.
_PRESENZA = frozenset({"presence", "occupancy", "motion"})
_APERTURA = frozenset({"door", "window", "opening", "garage_door"})
_COMFORT = frozenset({"temperature", "humidity"})
_CONSUMO = frozenset({"energy", "power", "gas", "water"})


def _testo(valore) -> str:
    """Un attributo di Home Assistant -> stringa confrontabile.

    Gli attributi arrivano da fuori: possono mancare, essere `None`, o avere un
    tipo inatteso. Un'eccezione qui fermerebbe l'osservatore su un evento solo,
    e l'osservatore gira per sempre.
    """
    return valore.strip() if isinstance(valore, str) else ""


def gamba(entity_id: str, attributi: dict | None) -> str | None:
    """A quale gamba dell'obiettivo serve questa entita', o `None`.

    L'obiettivo e' «ottimizzare la casa e renderla confortevole», e ha tre
    gambe -- efficiente, confortevole, in buono stato -- che qui diventano
    cinque domande: chi c'e', che aria si respira, cosa disperde, cosa consuma,
    cosa si sta rompendo.
    """
    attributi = attributi if isinstance(attributi, dict) else {}
    dominio = str(entity_id).split(".")[0]
    classe = _testo(attributi.get("device_class"))
    classe_stato = _testo(attributi.get("state_class"))

    if dominio == "person":
        return "chi c'e'"
    if dominio == "device_tracker":
        # MISURATO il 26/08/2026: 65 dei 73 tracker di questa casa sono
        # `router` -- l'NVR, Alexa, un Echo, una TV, una lampada. Dicono «questo
        # apparecchio e' connesso al wifi», non «c'e' qualcuno in casa». I 4
        # `gps` sono i telefoni, e sono le fonti dietro le due `person`.
        # Non e' volume (i 65 fanno 114 cambi al giorno, lo zero per cento):
        # e' che non significano niente per l'obiettivo.
        return "chi c'e'" if _testo(attributi.get("source_type")) == "gps" else None
    if dominio == "climate":
        return "comfort"
    if dominio == "cover":
        return "dispersione"
    if dominio == "binary_sensor":
        if classe in _PRESENZA:
            return "chi c'e'"
        if classe in _APERTURA:
            return "dispersione"
        return None
    if dominio == "sensor":
        if classe in _COMFORT:
            return "comfort"
        if classe == "battery":
            # `battery` e' `diagnostic`, e le entita' di servizio sono 604 su
            # 1226 in questa casa. Il filtro e' per CLASSE, non per categoria:
            # escludere `diagnostic` in blocco toglierebbe «buono stato».
            return "buono stato"
        if classe in _CONSUMO or classe_stato == "total_increasing":
            return "consumo"
    return None


def nel_pavimento(entity_id: str, attributi: dict | None) -> bool:
    """Se questa entita' si osserva comunque. Derivata da `gamba`, mai
    riscritta: due risposte alla stessa domanda divergono, e la prima a
    divergere e' quella che nessuno guarda."""
    return gamba(entity_id, attributi) is not None
