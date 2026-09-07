"""Come Home Assistant rende uno stato, e da dove viene la tabella.

**Lo stato si RENDE alla lettura, non si salva.** E' l'opposto della regola
del nome amichevole (`mind/store.py`, colonna `friendly_name`), e non e'
un'incoerenza -- sono due cose di natura diversa:

- il nome puo' SPARIRE con l'entita', quindi si scrive quando lo si sa;
- lo stato non sparisce mai (`heat` e' il fatto, ed e' quello che
  `mind/facts.py` confronta con `_RESTING`/`_UNKNOWN` per aprire e chiudere
  gli episodi), mentre la sua TRADUZIONE migliora: una voce che oggi manca
  domani c'e'. Renderla alla lettura fa arrivare i miglioramenti anche alle
  righe vecchie; congelarla in colonna li perde per sempre. E la lingua e'
  una preferenza MUTABILE della casa (`hass.config.language`): congelare la
  resa congelerebbe anche quella, e chi cambia lingua vedrebbe meta'
  archivio nella vecchia.

**Nessun vocabolario nostro.** Home Assistant PUBBLICA le traduzioni degli
stati e sono consumabili da un add-on: un comando WebSocket solo,
`frontend/get_translations` con `category: "entity_component"`, senza
`@require_admin` (`homeassistant/components/frontend/__init__.py:1007-1019`
al tag `2026.9.1`). Misurato dal vivo su questa casa il 07/09/2026:
**801 chiavi, 53 domini, 65 KB, 13 ms**.

**L'ordine dei gradini non e' un'interpretazione.** E' quello di
`homeassistant/helpers/translation.py:459-491` (`async_translate_state`) al
tag `2026.9.1`, e il frontend di HA usa lo STESSO ordine
(`src/common/entity/compute_state_display.ts:274-292` @ `20260826.6`, col
commento «We don't know! Return the raw state.»). E' l'unico algoritmo che
HA ha.
"""
from __future__ import annotations

import asyncio
import logging

from ..home_space.ha_vocabulary import UNAVAILABLE_LABEL, UNKNOWN_LABEL

logger = logging.getLogger(__name__)

# La categoria che porta le traduzioni degli stati per DOMINIO. Non e' quella
# che il nome suggerisce: `category: "state"` risponde con zero chiavi
# (misurato dal vivo, 07/09/2026), e `category: "entity"` (134 KB) copre solo
# le entita' con un `translation_key` proprio -- il primo gradino qui sotto.
STATE_TRANSLATIONS_CATEGORY = "entity_component"

# Gli stati che Home Assistant NON traduce mai: `async_translate_state` li
# restituisce tali e quali PRIMA di ogni altro gradino
# (`homeassistant/helpers/translation.py:469-470`), e il frontend li rende da
# un bundle proprio che il backend non pubblica
# (`compute_state_display.ts:94-101`). Sono l'unico buco che tocca a noi
# riempire, ed e' un buco di HA, non nostro: le due etichette vivono nel
# vocabolario, accanto alle spiegazioni lunghe che gia' ci stavano.
_OUR_LABELS = {"unavailable": UNAVAILABLE_LABEL, "unknown": UNKNOWN_LABEL}


def state_translation(state, *, domain, device_class=None, platform=None,
                      translation_key=None, component_resources,
                      entity_resources=None) -> str | None:
    """La resa di `state`, o `None` quando nessun gradino risponde.

    Trascrizione di `async_translate_state`
    (`homeassistant/helpers/translation.py:459-491`, tag `2026.9.1`), quattro
    gradini nell'ordine esatto:

    1. `component.{platform}.entity.{domain}.{translation_key}.state.{state}`
       nelle risorse di `category: "entity"` (`:472-478`);
    2. `component.{domain}.entity_component.{device_class}.state.{state}`
       (`:480-486`);
    3. `component.{domain}.entity_component._.state.{state}` (`:487-489`);
    4. nessuna traduzione (`:491`).

    **Due scostamenti dichiarati dal sorgente di HA, ed entrambi hanno un
    perche' che vale piu' della fedelta' letterale.**

    **a. Il quarto gradino torna `None`, non il grezzo.** HA a `:491` fa
    `return state`, e chi lo chiama non puo' piu' distinguere «tradotto» da
    «non traducibile» senza confrontare due stringhe. Qui il buco lo dichiara
    la FONTE, non lo indovina chi consuma: e' la stessa disciplina per cui
    `read_registries` distingue un registro vuoto da un registro caduto, e la
    stessa che rende possibile dire al proprietario «le traduzioni non si sono
    potute leggere» invece di «questo stato non ha traduzione» -- due fatti
    diversi che non devono produrre la stessa risposta. Il grezzo resta cio'
    che il lettore vede: e' una DECISIONE di chi rende (il confine dell'API
    non emette nessun campo, e la pagina mostra `stato`), non un dato.

    **b. `unavailable` e `unknown` prendono le NOSTRE etichette.** HA a
    `:469-470` li restituisce grezzi, prima di ogni gradino, e il suo frontend
    li rende da un bundle proprio che il backend non pubblica: per un add-on
    quel buco non e' colmabile da HA. Le due etichette stanno in
    `home_space/ha_vocabulary.py` (accanto a `UNAVAILABLE_MEANING`/
    `UNKNOWN_MEANING`, che gia' c'erano), e sono in italiano FISSO -- vedi il
    limite dichiarato li'.

    `component_resources` e' obbligatorio ed e' il dizionario piatto di
    `category: "entity_component"`; `entity_resources` (`category: "entity"`)
    e' facoltativo, e senza di esso il primo gradino non puo' rispondere --
    cade sul secondo, che e' esattamente cio' che HA fa quando la cache di
    quella categoria e' vuota.
    """
    if not isinstance(state, str) or not state:
        return None
    our_label = _OUR_LABELS.get(state)
    if our_label is not None:
        return our_label
    if not isinstance(domain, str) or not domain:
        return None
    if platform and translation_key and isinstance(entity_resources, dict):
        key = (f"component.{platform}.entity.{domain}."
               f"{translation_key}.state.{state}")
        if key in entity_resources:
            return entity_resources[key]
    if not isinstance(component_resources, dict):
        return None
    if device_class:
        key = f"component.{domain}.entity_component.{device_class}.state.{state}"
        if key in component_resources:
            return component_resources[key]
    key = f"component.{domain}.entity_component._.state.{state}"
    if key in component_resources:
        return component_resources[key]
    return None


class StateTranslations:
    """La tabella delle traduzioni, letta da Home Assistant e tenuta in cache.

    **Si rilegge quando cambia `versione_ha` o `lingua`**, le due cose che
    HIRIS gia' distilla da `Config.as_dict()` in
    `home_space.topology.reference_frame()` -- non una seconda idea di
    "versione della casa" o di "lingua della casa", le stesse. Fra un cambio e
    l'altro la lettura costa zero: 801 chiavi restano in memoria.

    **Non entra nel batch di `read_registries`.** Quel metodo dichiara nel
    proprio docstring che «una funzione che restituisce registri restituisce
    registri», ed e' la ragione per cui nemmeno `get_config` ci sta dentro.
    Un comando suo, su una connessione sua, 13 ms.

    **Risponde SEMPRE con un esito etichettato**, mai con un dizionario vuoto
    che chi legge deve interpretare: `{"lette": True, "lingua": ..., "risorse":
    {...}}` oppure `{"lette": False, "motivo": "..."}`. Le traduzioni non
    lette e uno stato senza traduzione sono due fatti diversi, e chi PRODUCE
    il motivo deve etichettarlo -- non chi lo consuma indovinarlo.
    """

    def __init__(self, client, *, category: str = STATE_TRANSLATIONS_CATEGORY) -> None:
        self._client = client
        self._category = category
        self._key: tuple[str | None, str | None] | None = None
        self._resources: dict | None = None
        self._lock = asyncio.Lock()

    async def read(self, *, ha_version, language) -> dict:
        """L'esito etichettato per questa coppia `(versione_ha, lingua)`.

        Senza `lingua` non si legge affatto, e non si indovina un `"en"`:
        `frontend/get_translations` vuole la lingua come parametro
        OBBLIGATORIO (`frontend/__init__.py:1007-1015`), e sceglierne una noi
        vorrebbe dire rendere la pagina in una lingua che il proprietario non
        ha chiesto. Il motivo lo dice l'esito.

        Un guasto NON invalida la cache buona di prima: se una lettura fallisce
        ma la coppia e' ancora quella gia' letta, si continua a rendere con la
        tabella che si ha. Una tabella che c'e' e' meglio di un vuoto
        dichiarato fresco -- e' la stessa scelta di `topology.rebuild()`.
        """
        key = (ha_version, language)
        if not language:
            return {"lette": False,
                    "motivo": "la lingua della casa non e' nota: l’anagrafe non ha "
                              "ancora letto il sistema di riferimento di Home Assistant"}
        async with self._lock:
            # Il controllo della cache sta DENTRO il lock, e ce n'e' uno solo.
            # Fuori sarebbe stato piu' veloce (chi ha gia' la tabella non
            # aspetta nessuno), ma allora ne servirebbero DUE -- lo stesso
            # confronto e lo stesso ritorno scritti due volte, e quello fuori
            # non lo puo' pinnare nessuna prova: toglierlo lascia il
            # comportamento identico, perche' quello dentro fa gia' lo stesso
            # lavoro. Un doppione che nessuna mutazione puo' vedere rosso e' il
            # peggiore dei doppioni. Il lock qui non e' conteso (due letture
            # della pagina in parallelo sono il caso raro) e serve comunque:
            # senza, due letture simultanee farebbero due chiamate identiche a
            # Home Assistant.
            if self._resources is not None and self._key == key:
                return {"lette": True, "lingua": language, "risorse": self._resources}
            report = await self._client.get_translations(language, category=self._category)
            if "risorse" not in report:
                reason = report.get("errore") or "motivo non dichiarato"
                logger.debug("traduzioni degli stati non lette (%s): %s", language, reason)
                return {"lette": False, "motivo": reason}
            self._resources = report["risorse"]
            self._key = key
            logger.info("traduzioni degli stati lette da Home Assistant: %d chiavi (%s, HA %s)",
                        len(self._resources), language, ha_version)
        return {"lette": True, "lingua": language, "risorse": self._resources}
