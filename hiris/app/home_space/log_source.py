"""Da quale integrazione viene una voce del registro di Home Assistant.

Il registro degli errori di Home Assistant (`system_log`) nomina chi scrive col
nome del suo logger -- `homeassistant.components.hydrawise`,
`custom_components.alarmo.alarm_control_panel` -- non con l'integrazione.
Questo modulo ne ricava lo slug e un nome leggibile.

**Perche' qui e non in `mind/`.** Viveva in `mind/report.py` fino al 04/10/2026
(Tappa 3, Task 7, B-35): la storia della chat (`house_history`) la importava da
li', cioe' `home_space` dipendeva dal cervello, contro la regola che vuole la
conoscenza sotto e il cervello sopra. E' una lettura della casa, non un
giudizio del cervello: il resoconto e la rotta dello scope la chiamano da qui.

**Il nome e' quello del manifest** (B-50, F1 della Chiusura, 13/10/2026):
Home Assistant lo dichiara (`manifest/list`), e l'anagrafe lo tiene nella
tabella `manifesti` (`reader._manifest`). Fino a quel giorno era dedotto dallo
slug: misurato sulla casa il 13/10/2026, 19 integrazioni distinte nel registro
degli errori, 15 nel manifest, e per 12 di quelle 15 il nome dedotto era
diverso da quello vero.

**E il manifest conosce anche le librerie** (N151b-1, revisione del
13/10/2026): il campo `loggers` e' «a list of names that the integration's
requirements use for their getLogger calls» (developers.home-assistant.io,
`creating_integration_manifest`), e `alexa_devices` porta
`["aioamazondevices"]` (Core `2026.10.1`). Una riga scritta da una libreria e'
quindi dell'integrazione che la dichiara. Lo slug resta il ripiego per cio' che
il manifest davvero non conosce: le integrazioni non caricate (senza argomenti
`manifest/list` rende le sole caricate) e i logger che nessuna dichiara.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

#: I due prefissi con cui un logger di Home Assistant nomina l'integrazione da
#: cui viene: `homeassistant.components.hydrawise` -> «Hydrawise»,
#: `custom_components.alarmo.alarm_control_panel` -> «Alarmo». Il segmento
#: SUBITO DOPO il prefisso e' l'integrazione; quelli ancora dopo sono la
#: piattaforma dentro di lei, e non sono il suo nome.
_INTEGRATION_PREFIXES = ("homeassistant.components.", "custom_components.")

#: Il nucleo di Home Assistant quando il logger non nomina nessuna
#: integrazione (`homeassistant.helpers.entity`, misurato sulla casa vera il
#: 17/09/2026). **E' una citazione, non una resa**: il prodotto si chiama
#: cosi', e «Homeassistant.helpers.entity» non e' il nome di niente.
_CORE_LOGGER_PREFIX = "homeassistant."
_CORE_SLUG = "homeassistant"
_CORE_NAME = "Home Assistant"


def integration_slug(domain: str) -> str | None:
    """Il nome breve (**`slug`**) dell'integrazione da cui viene una voce di sistema:
    `homeassistant.components.hassio.handler` -> `hassio`,
    `custom_components.hacs.x` -> `hacs`, `frontend.js.modern.202608267` ->
    `frontend`, `homeassistant.helpers.entity` -> `homeassistant`.

    **Un segmento solo, sempre**, e da qui viene tutto il resto: e' il soggetto
    su cui la casa scrive il giudizio `impalcatura`, ed e' anche cio' che il
    nome rende leggibile. Misurato il 20/09/2026: il Supervisor ha fatto sei
    righe di primo piano in una settimana da **tre logger diversi**, e il
    frontend porta nel proprio la versione del pacchetto -- un giudizio scritto
    sul percorso intero avrebbe voluto una riga per modulo, e sarebbe scaduto
    al prossimo aggiornamento di Home Assistant.
    """
    domain = str(domain or "").strip()
    if not domain:
        return None
    for prefix in _INTEGRATION_PREFIXES:
        if domain.startswith(prefix):
            found = domain[len(prefix):].split(".")[0]
            return found or None
    if domain.startswith(_CORE_LOGGER_PREFIX):
        return _CORE_SLUG
    # Una libreria di terze parti (`aioamazondevices`, `habluetooth.scanner`)
    # non e' un'integrazione di Home Assistant, ma il primo segmento e' lo
    # stesso appiglio stabile: `habluetooth.scanner` e `habluetooth.manager`
    # sono la stessa cosa per chi legge. Il NOME e l'identificativo mostrato
    # cercano prima l'integrazione che la dichiara (`_owner`, N151b-1); il
    # giudizio `impalcatura` resta su questo slug, perche' l'elenco di
    # fabbrica (`SCAFFOLDING_INTEGRATIONS`) nomina `habluetooth`, la libreria.
    return domain.split(".")[0]


@dataclass(frozen=True)
class Manifest:
    """Cio' che il manifest delle integrazioni caricate dice a chi nomina un
    logger (B-50): **`names`**, lo slug -> il nome che Home Assistant gli da';
    **`loggers`**, il logger di una libreria -> lo slug dell'integrazione che
    lo dichiara (`loggers` del manifest, N151b-1). Vuoto senza anagrafe: ogni
    nome ripiega allora sullo slug, come prima di B-50."""
    names: Mapping[str, str] = field(default_factory=dict)
    loggers: Mapping[str, str] = field(default_factory=dict)


def manifest_of(home_space: Mapping) -> Manifest:
    """Il `Manifest` dall'anagrafe data (tabella `manifesti`, `reader._manifest`).

    **Un logger dichiarato da due integrazioni caricate non e' di nessuna
    delle due**: la riga non dice quale delle due l'abbia scritta, e
    sceglierne una sarebbe inventarlo. Quel logger ripiega sullo slug, come
    uno che nessuno dichiara."""
    rows = [row for row in home_space.get("manifesti") or []
            if isinstance(row, dict) and row.get("dominio")]
    owners: dict[str, set[str]] = {}
    for row in rows:
        for name in row.get("loggers") or []:
            owners.setdefault(name, set()).add(row["dominio"])
    return Manifest(
        names={row["dominio"]: row["nome"] for row in rows if row.get("nome")},
        loggers={name: next(iter(slugs)) for name, slugs in owners.items()
                 if len(slugs) == 1})


def _owner(domain: str, manifest: Manifest) -> str | None:
    """Lo slug dell'integrazione a cui appartiene un logger: i prefissi di Home
    Assistant prima (`integration_slug`, il logger nomina gia' la sua), poi il
    logger dichiarato piu' lungo che e' il nome intero o il suo prefisso
    seguito da un punto (`aioamazondevices.api` -> `alexa_devices`), poi lo
    slug."""
    domain = str(domain or "").strip()
    if not domain.startswith((*_INTEGRATION_PREFIXES, _CORE_LOGGER_PREFIX)):
        declared = [name for name in manifest.loggers
                    if domain == name or domain.startswith(name + ".")]
        if declared:
            return manifest.loggers[max(declared, key=len)]
    return integration_slug(domain)


def integration_name(domain: str, manifest: Manifest) -> str | None:
    """Il nome leggibile dell'integrazione da cui viene una voce di sistema.

    **Si ricava da cio' che la voce gia' porta** -- `dominio`, scritto
    dall'osservatore insieme al titolo -- e mai dall'identificativo del
    soggetto: quello e' la chiave con cui Home Assistant deduplica (logger piu'
    posizione nel sorgente), e leggerlo come un nome darebbe
    `log:...@handler.py:108` in cima alla pagina, che e' esattamente cio' che
    la pagina faceva prima del 18/09.

    Il nome e' quello del manifest (`manifest_of`), anche per una libreria che
    un'integrazione dichiara (`_owner`). Il nucleo resta «Home Assistant»
    anche se il manifest nomina `homeassistant`: un logger
    `homeassistant.helpers` e' il prodotto, non la sua integrazione «Home
    Assistant Core Integration».
    """
    slug = _owner(domain, manifest)
    if slug is None:
        return None
    if slug == _CORE_SLUG:
        return _CORE_NAME
    if slug in manifest.names:
        return manifest.names[slug]
    # Un logger che nessun manifest caricato dichiara: il suo nome intero e'
    # piu' vero di qualunque pezzo se ne possa tagliare.
    return _rendered(slug)


def _rendered(slug: str) -> str:
    """`alexa_devices` -> «Alexa devices». Una maiuscola e gli spazi: la
    minima resa che fa di un identificatore un nome, senza fingere di sapere
    come quell'integrazione si scriva davvero (`FRITZ!Box` lo sa solo HA)."""
    words = slug.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def integration_of(domain: str, manifest: Manifest) -> tuple[str, str] | None:
    """`(nome, identificativo)` dell'integrazione da cui viene un dominio di
    registro, o `None` se non se ne ricava nessuno.

    Le stesse regole di `integration_name`, con lo stesso proprietario
    (`_owner`): la riga di una libreria porta l'identificativo
    dell'integrazione che la dichiara, e il filtro per integrazione della
    storia degli errori la ritrova. La usa la rotta dello scope per
    raggruppare i soggetti tecnici, e il primo piano del resoconto
    (`mind/report.py`) usa le stesse, cosi' le due schede della stessa pagina
    dicono lo stesso nome per lo stesso logger.
    """
    identifier = _owner(domain, manifest)
    if not identifier:
        return None
    return integration_name(domain, manifest), identifier
