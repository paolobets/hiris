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

GAMBE = ("chi c'e'", "comfort", "dispersione", "consumo", "buono stato", "sicurezza")

# Le classi che Home Assistant dichiara, raggruppate per gamba dell'obiettivo.
# I nomi sono quelli veri di HA, non nostri.
_PRESENZA = frozenset({"presence", "occupancy", "motion"})
_APERTURA = frozenset({"door", "window", "opening", "garage_door"})
_COMFORT = frozenset({"temperature", "humidity"})
# Qualita' dell'aria: il docstring di `gamba` promette «che aria si respira»,
# non solo temperatura e umidita'. `carbon_monoxide` NON e' qui: e' una
# concentrazione di un gas letale, non comfort -- vedi `_SICUREZZA_SENSORE`.
_QUALITA_ARIA = frozenset({
    "carbon_dioxide", "pm1", "pm10", "pm25",
    "volatile_organic_compounds", "volatile_organic_compounds_parts",
    "nitrogen_dioxide", "nitrogen_monoxide", "nitrous_oxide", "ozone",
    "sulphur_dioxide",
})
_CONSUMO = frozenset({"energy", "power", "gas", "water"})

# La sesta gamba, aggiunta il 26/08/2026 dalla review del primo task: la
# prima stesura non conteneva gli allarmi -- ne' fumo, ne' gas, ne'
# monossido, ne' allagamento, ne' serrature, ne' pannello dell'allarme --
# ed era il buco peggiore possibile, sulla categoria di dati che conta piu'
# di tutte (docs/design/2026-08-26-l-osservatore.md §4).
#
# Il vocabolario gemello vive in `casa/nucleo.py::_DOMINI_EVENTO` e
# `_CLASSI_EVENTO`, verificato sulla documentazione di Home Assistant il
# 16/08/2026. Qui NON e' importato, e' RICOPIATO: `nucleo.py` risponde a
# «cosa e' notevole ADESSO» (un evento da annunciare), questo modulo
# risponde a «cosa si osserva SEMPRE» (cosa entra nel pavimento) -- due
# domande diverse i cui elenchi possono divergere in futuro per ragioni
# proprie. Chi tocca uno dei due elenchi guardi anche l'altro.
_DOMINI_SICUREZZA = frozenset({"lock", "alarm_control_panel"})
_SICUREZZA_BINARIA = frozenset({
    "smoke", "gas", "carbon_monoxide", "moisture", "safety", "tamper",
    "problem", "heat", "cold",
})
# Trappola gia' documentata nel prodotto: la classe si chiama
# `carbon_monoxide`, NON `co`. E trappola nuova: `gas` compare anche qui
# sopra (`_SICUREZZA_BINARIA`) ma e' un'altra entita' -- il rilevatore di
# fuga su `binary_sensor`, non il contatore su `sensor` (resta `_CONSUMO`).
# Il ramo per dominio in `gamba()` le separa gia': un controllo per sola
# classe le fonderebbe.
_SICUREZZA_SENSORE = frozenset({"carbon_monoxide"})


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
    sei domande: chi c'e', che aria si respira, cosa disperde, cosa consuma,
    cosa si sta rompendo, cosa minaccia la sicurezza.
    """
    attributi = attributi if isinstance(attributi, dict) else {}
    dominio = str(entity_id).split(".")[0]
    classe = _testo(attributi.get("device_class"))
    classe_stato = _testo(attributi.get("state_class"))

    if dominio == "person":
        return "chi c'e'"
    if dominio in _DOMINI_SICUREZZA:
        return "sicurezza"
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
        if classe in _SICUREZZA_BINARIA:
            return "sicurezza"
        return None
    if dominio == "sensor":
        if classe in _COMFORT or classe in _QUALITA_ARIA:
            return "comfort"
        if classe in _SICUREZZA_SENSORE:
            return "sicurezza"
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
