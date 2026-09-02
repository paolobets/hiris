"""Cosa l'osservatore guarda comunque, qualunque cosa dica l'obiettivo.

**Il pavimento non e' una lista scritta a mano.** Si deriva da cio' che Home
Assistant dichiara gia' su ogni entita' -- dominio, classe del dispositivo
(`device_class`), `source_type` -- perche' una lista a mano invecchia col
primo dispositivo nuovo e nessuno se ne accorge. **Non `state_class`**
(correzione di parole della review, mandato «il bilancio dell'energia»,
punto 7, 27/08/2026): dopo la correzione del 27/08 (vedi il docstring di
`aspect` sotto), questa funzione non la legge piu' per decidere nessuna
gamba -- resta grezzo conservato nell'archivio (`cervello/archivio.py`),
non un criterio del pavimento.

**Perche' esiste un pavimento.** Il prompt dell'obiettivo decide cosa entra
nelle osservazioni, quindi e' un punto singolo che puo' ACCECARE l'osservatore
-- e cio' che non e' stato osservato non esiste piu': riscrivere il prompt fra
tre mesi non fa ricomparire i tre mesi mancanti. Il pavimento e' cio' che il
prompt non puo' togliere. Sopra di esso allarga; sotto, mai.
"""
from __future__ import annotations

ASPECTS = ("chi c'e'", "comfort", "dispersione", "energia", "buono stato", "sicurezza")

# Le classi che Home Assistant dichiara, raggruppate per gamba dell'obiettivo.
# I nomi sono quelli veri di HA, non nostri.
_PRESENZA = frozenset({"presence", "occupancy", "motion"})
_APERTURA = frozenset({"door", "window", "opening", "garage_door"})
_COMFORT = frozenset({"temperature", "humidity"})
# Qualita' dell'aria: il docstring di `aspect` promette «che aria si respira»,
# non solo temperatura e umidita'. `carbon_monoxide` NON e' qui: e' una
# concentrazione di un gas letale, non comfort -- vedi `_SICUREZZA_SENSORE`.
_QUALITA_ARIA = frozenset({
    "carbon_dioxide", "pm1", "pm10", "pm25",
    "volatile_organic_compounds", "volatile_organic_compounds_parts",
    "nitrogen_dioxide", "nitrogen_monoxide", "nitrous_oxide", "ozone",
    "sulphur_dioxide",
})
# NON tradotta in `_ENERGY` (corretto durante la review del Task 6): "energia"
# e' una delle sei ASPECTS (`chi c'e'`, comfort, dispersione, **energia**,
# buono stato, sicurezza) -- un valore di dominio rinviato dal glossario,
# esattamente come "sicurezza" nelle costanti gemelle qui sotto
# (`_SICUREZZA_BINARIA`, `_SICUREZZA_SENSORE`, `_DOMINI_SICUREZZA`). La
# REGOLA, applicabile a tutte e sette le costanti di questo file che
# raggruppano classi Home Assistant per gamba: il nome della costante resta
# italiano quando CONTIENE il nome esatto di un valore di dominio rinviato
# (`presenza`, `comfort`, `sicurezza`, `energia`...), a prescindere da quanto
# "ovvia" sembri la traduzione -- tradurne una e non le altre (`_ENERGIA` ->
# `_ENERGY` accanto a `_SICUREZZA_SENSORE` invariata) sarebbe la stessa
# incoerenza che questa fetta esiste per chiudere, dal lato sbagliato.
_ENERGIA = frozenset({"energy", "power", "gas", "water"})

# DEBITO DICHIARATO il 26/08/2026, CHIUSO A LIVELLO DI EPISODIO il
# 27/08/2026 (mandato «le direzioni dell'energia» -- misurato sulla casa
# vera, vedi `CLAUDE.md`, «Su Home Assistant non si ipotizza mai»): Home
# Assistant usa `device_class: energy` (e `power`) sia per l'energia
# PRODOTTA da un impianto fotovoltaico sia per quella PRELEVATA dalla rete
# -- la classe da sola non separa le due direzioni, e indovinarle dal NOME
# del sensore ("prodotta", "esportata") si romperebbe sul prossimo
# inverter. Su questa casa l'inverter con accumulo ha 17 entita': il
# pavimento ne cattura 16, di cui **15 finiscono in questa gamba** (energia
# e potenza prodotta, esportata, importata, autoconsumata, consumata,
# carica e scarica) perche' sono tutte `energy`/`power`; la sedicesima e'
# la percentuale di carica (`battery`) e va in "buono stato".
#
# **Questa GAMBA resta un'unica "energia"** -- vera per tutti e 15 i
# sensori, produzione compresa, e il mandato vieta esplicitamente di
# sdoppiarla («la direzione e' DENTRO l'episodio, non e' una gamba nuova»).
# La distinzione vera vive ora un livello sopra, nel CORPO di ogni episodio
# di energia (`cervello/oggetti.py::aggregate_day`, parametro `direzioni`):
# `HAClient.energy_directions()` legge due fonti, sulla stessa connessione
# --
#
# - **dichiarata** (`energy/get_prefs`, la dashboard Energia dell'utente):
#   vince sempre. Forma misurata sul vivo il 27/08/2026, tre sorgenti --
#     grid    -> `stat_energy_from` = ..._energia_importata_oggi -> prelievo
#                `stat_energy_to`   = ..._energia_esportata_oggi -> immissione
#     solar   -> `stat_energy_from` = ..._energia_prodotta_oggi  -> produzione
#                `stat_rate`        = ..._potenza_prodotta        -> produzione
#     battery -> `stat_energy_from` = ..._energia_scarica_oggi   -> scarica
#                `stat_energy_to`   = ..._energia_carica_oggi    -> carica
#   **Trappola di forma, misurata il 26/08 e ri-confermata il 27/08:** la
#   sorgente `grid` porta i suoi due sensori in campi SCALARI
#   (`stat_energy_from`/`stat_energy_to`), non in liste di flussi -- uno
#   script che si aspetta liste legge una configurazione piena come vuota.
#   Copre 6 delle 17 entita' di questa casa.
# - **dedotta** (`translation_key` del registro entita'): si applica SOLO
#   dove la dichiarata tace. Vera ma specifica dell'integrazione
#   (`zcsazzurro`, su questa casa) -- un altro inverter usera' chiavi sue.
#   Copre tutte le 14 entita' direzionali di questa integrazione.
#
# Un episodio senza `direzione` resta possibile (nessuna delle due fonti la
# sa dire per quel sensore): il campo non c'e' -- non una "sconosciuta"
# travestita da dato.

# La sesta gamba, aggiunta il 26/08/2026 dalla review del primo task: la
# prima stesura non conteneva gli allarmi -- ne' fumo, ne' gas, ne'
# monossido, ne' allagamento, ne' serrature, ne' pannello dell'allarme --
# ed era il buco peggiore possibile, sulla categoria di dati che conta piu'
# di tutte (docs/design/2026-08-26-l-osservatore.md §4).
#
# Il vocabolario gemello vive in `casa/nucleo.py::_EVENT_DOMAINS` e
# `_EVENT_CLASSES`. La prima e' un giudizio del prodotto, misurato
# sull'impianto, con gli stati verificati il 20/08/2026; la seconda e'
# verificata sulla documentazione di Home Assistant il 16/08/2026. Qui NON
# e' importato, e' RICOPIATO: `nucleo.py` risponde a
# «cosa e' notevole ADESSO» (un evento da annunciare), questo modulo
# risponde a «cosa si osserva SEMPRE» (cosa entra nel pavimento) -- due
# domande diverse i cui elenchi possono divergere in futuro per ragioni
# proprie. Chi tocca uno dei due elenchi guardi anche l'altro.
_DOMINI_SICUREZZA = frozenset({"lock", "alarm_control_panel", "siren"})
_SICUREZZA_BINARIA = frozenset({
    "smoke", "gas", "carbon_monoxide", "moisture", "safety", "tamper",
    "problem", "heat", "cold",
})
# Trappola gia' documentata nel prodotto: la classe si chiama
# `carbon_monoxide`, NON `co`. E trappola nuova: `gas` compare anche qui
# sopra (`_SICUREZZA_BINARIA`) ma e' un'altra entita' -- il rilevatore di
# fuga su `binary_sensor`, non il contatore su `sensor` (resta `_ENERGIA`).
# Il ramo per dominio in `aspect()` le separa gia': un controllo per sola
# classe le fonderebbe.
_SICUREZZA_SENSORE = frozenset({"carbon_monoxide"})


def _text(value) -> str:
    """Un attributo di Home Assistant -> stringa confrontabile.

    Gli attributi arrivano da fuori: possono mancare, essere `None`, o avere un
    tipo inatteso. Un'eccezione qui fermerebbe l'osservatore su un evento solo,
    e l'osservatore gira per sempre.
    """
    return value.strip() if isinstance(value, str) else ""


def aspect(entity_id: str, attributes: dict | None) -> str | None:
    """A quale gamba dell'obiettivo serve questa entita', o `None`.

    L'obiettivo e' «ottimizzare la casa e renderla confortevole», e ha tre
    gambe -- efficiente, confortevole, in buono stato -- che qui diventano
    sei domande: chi c'e', che aria si respira, cosa disperde, quanta
    energia si muove, cosa si sta rompendo, cosa minaccia la sicurezza.

    **"Quanta energia si muove" e non "cosa consuma"** (correzione del
    26/08/2026): questa gamba cattura energia PRODOTTA e PRELEVATA nella
    stessa classe HA (`energy`/`power`, vedi `_ENERGIA` sopra), e "consuma"
    affermerebbe il contrario per una buona meta' dei 15 sensori che un
    impianto fotovoltaico con accumulo porta in questa gamba.

    **`state_class: total_increasing` da solo NON basta piu' per "energia"**
    (correzione del 27/08/2026, mandato «il bilancio dell'energia», punto 5
    -- misurato sulla casa vera lo stesso giorno). Prima di questa correzione
    un contatore sempre-crescente qualunque finiva qui: `sensor.
    betarena_gb_inviati`/`_gb_ricevuti` -- i gigabyte del router, `device_
    class: data_size` -- erano archiviati come energia e producevano un
    episodio di energia ogni notte. Non e' restringere il pavimento (che il
    prompt non puo' fare): e' smettere di DERIVARE una classe che Home
    Assistant non dichiara. Un contatore che aumenta e basta non e' energia:
    e' la forma di molte cose (dati di rete, litri, richieste HTTP...), e
    solo `_ENERGIA` sopra -- classi dichiarate -- dice quali di quelle sono
    davvero energia.
    """
    attributes = attributes if isinstance(attributes, dict) else {}
    domain = str(entity_id).split(".")[0]
    device_class = _text(attributes.get("device_class"))

    if domain == "person":
        return "chi c'e'"
    if domain in _DOMINI_SICUREZZA:
        return "sicurezza"
    if domain == "device_tracker":
        # MISURATO il 26/08/2026: 65 dei 73 tracker di questa casa sono
        # `router` -- l'NVR, Alexa, un Echo, una TV, una lampada. Dicono «questo
        # apparecchio e' connesso al wifi», non «c'e' qualcuno in casa». I 4
        # `gps` sono i telefoni, e sono le fonti dietro le due `person`.
        # Non e' volume (i 65 fanno 114 cambi al giorno, lo zero per cento):
        # e' che non significano niente per l'obiettivo.
        return "chi c'e'" if _text(attributes.get("source_type")) == "gps" else None
    if domain == "climate":
        return "comfort"
    if domain == "cover":
        return "dispersione"
    if domain == "binary_sensor":
        if device_class in _PRESENZA:
            return "chi c'e'"
        if device_class in _APERTURA:
            return "dispersione"
        if device_class in _SICUREZZA_BINARIA:
            return "sicurezza"
        return None
    if domain == "sensor":
        if device_class in _COMFORT or device_class in _QUALITA_ARIA:
            return "comfort"
        if device_class in _SICUREZZA_SENSORE:
            return "sicurezza"
        if device_class == "battery":
            # `battery` e' `diagnostic`, e le entita' di servizio sono 604 su
            # 1226 in questa casa. Il filtro e' per CLASSE, non per categoria:
            # escludere `diagnostic` in blocco toglierebbe «buono stato».
            return "buono stato"
        if device_class in _ENERGIA:
            return "energia"
    return None


def in_baseline(entity_id: str, attributes: dict | None) -> bool:
    """Se questa entita' si osserva comunque. Derivata da `aspect`, mai
    riscritta: due risposte alla stessa domanda divergono, e la prima a
    divergere e' quella che nessuno guarda."""
    return aspect(entity_id, attributes) is not None
