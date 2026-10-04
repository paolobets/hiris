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

**Il nome e' dedotto dallo slug**, non letto dal manifest dell'integrazione:
e' la voce B-50 del registro, che la Tappa 3 cambia al Task 5 dopo aver letto
la fonte di Home Assistant.
"""
from __future__ import annotations

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
    # sono la stessa cosa per chi legge.
    return domain.split(".")[0]


def integration_name(domain: str) -> str | None:
    """Il nome leggibile dell'integrazione da cui viene una voce di sistema.

    **Si ricava da cio' che la voce gia' porta** -- `dominio`, scritto
    dall'osservatore insieme al titolo -- e mai dall'identificativo del
    soggetto: quello e' la chiave con cui Home Assistant deduplica (logger piu'
    posizione nel sorgente), e leggerlo come un nome darebbe
    `log:...@handler.py:108` in cima alla pagina, che e' esattamente cio' che
    la pagina faceva prima del 18/09.
    """
    slug = integration_slug(domain)
    if slug is None:
        return None
    if slug == _CORE_SLUG:
        return _CORE_NAME
    # Una libreria di terze parti (`aioamazondevices`) non e' un'integrazione e
    # il suo nome intero e' piu' vero di qualunque pezzo se ne possa tagliare:
    # per lei il `slug` E' il nome.
    return _rendered(slug)


def _rendered(slug: str) -> str:
    """`alexa_devices` -> «Alexa devices». Una maiuscola e gli spazi: la
    minima resa che fa di un identificatore un nome, senza fingere di sapere
    come quell'integrazione si scriva davvero (`FRITZ!Box` lo sa solo HA)."""
    words = slug.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def integration_of(domain: str) -> tuple[str, str] | None:
    """`(nome, identificativo)` dell'integrazione da cui viene un dominio di
    registro, o `None` se non se ne ricava nessuno.

    Le due regole insieme (`integration_name`, `integration_slug`): la usa
    la rotta dello scope per raggruppare i soggetti tecnici, e il primo piano
    del resoconto (`mind/report.py`) usa le stesse, cosi' le due schede della
    stessa pagina dicono lo stesso nome per lo stesso logger.
    """
    identifier = integration_slug(domain)
    if not identifier:
        return None
    return integration_name(domain), identifier
