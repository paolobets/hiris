"""Cosa la casa fa gia' da sola: il corpo delle automazioni e degli script.

**La fonte e' Home Assistant, non il file** (dal 10/09/2026). Prima si leggevano
`automations.yaml` e `scripts.yaml`, e il prodotto dichiarava il proprio punto
cieco: *«le automazioni scritte a mano non stanno in automations.yaml -- vivono
nei pacchetti o in cartelle incluse -- e di quelle HIRIS conosce il nome e non
il corpo»*. Il comando `automation/config` torna `raw_config` dell'ENTITA',
quindi quel punto cieco si chiude: qualunque sia l'origine, il corpo arriva.

**Cosa si perde, ed e' dichiarato.** Il file diceva cosa c'e' SCRITTO, lo stato
dice cosa ESISTE. Un'automazione scritta e rotta -- che Home Assistant non ha
caricato -- prima si vedeva (`solo_file`), adesso no: HIRIS conosce cio' che HA
ha caricato, e HA quella la segnala per conto suo. Con la fonte sono usciti i
tre valori di `origine` (`file`/`solo_stato`/`solo_file`), `id_reale` (ogni id
e' ora un `entity_id` vero) e le tre ragioni di `file_non_letti`.

**Cosa resta, e cambia soggetto**: la dichiarazione di punto cieco. Non e' piu'
«questo FILE non l'ho letto» ma «di QUESTA automazione non conosco il corpo, e
per questa ragione» -- piu' precisa, e alla fonte giusta.

**I segreti si oscurano al confine** (`redaction.SecretSeal`): il YAML che HA
restituisce e' gia' risolto, mentre il lettore di file non risolveva `!secret`
affatto. Se `secrets.yaml` non si legge, il corpo **non si archivia** e lo si
dichiara: non si pubblica cio' che non si e' potuto controllare.

Senza tutto questo la Legge I resta sulla carta: HIRIS proporrebbe
un'automazione per una cosa che la casa gia' fa, e non potrebbe mai dire la
frase piu' utile che esista -- «non serve, ce l'hai gia', si chiama cosi'».
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .reader import clean_name
from .redaction import SecretSeal
from .topology import domain_of

logger = logging.getLogger(__name__)

#: Il file dei segreti: l'unica cosa che HIRIS legge ancora dal disco di
#: Home Assistant, perche' e' la dichiarazione del proprietario su cosa
#: sia segreto -- e nessuna API la espone.
_SECRETS = "secrets.yaml"

# Le RAGIONI di `file_non_letti` (`reread()`, sotto). Pubbliche perche' chi
# consuma quella mappa per decidere se dichiarare un punto cieco
# (`tools.py::ToolDispatcher._blind_spots`) deve poter distinguere i due
# generi senza duplicare la stringa letterale -- ri-review sul Task 2
# «rifiutare e importare», secondo giro di correzioni: la stessa forma del
# fianco gia' chiuso su `_blind_spots` (guasto di adesso vs limite stabile),
# un livello piu' sotto.
#
# Un file davvero assente (la cartella e' raggiungibile, il file no) non
# nasconde NIENTE: non c'e' contenuto scritto da poter mancare, quindi non
# e' un punto cieco per `search` -- va creato, non riparato.
FILE_GENUINELY_ABSENT = "assente"

# Quando la cartella di configurazione di Home Assistant stessa non e'
# raggiungibile (`ha_folder is None`, sotto): i due file POTREBBERO esserci,
# HIRIS non ha potuto nemmeno controllare. E' un guasto DI ADESSO -- il
# Supervisor puo' non aver ancora montato la cartella (`server.py::
# behavior_sentinel` la ricerca a ogni giro apposta per questo), non
# un'assenza -- misurato che confonderlo con `FILE_GENUINELY_ABSENT` spegne
# `nulla_riconosciuto` per SEMPRE su questa casa, con un motivo che dice
# "cio' che c'e' scritto li' dentro potrebbe esistere lo stesso" di un file
# che il codice non ha nemmeno guardato.
FOLDER_UNREACHABLE = "cartella non raggiungibile"

# entity_id canonico (dominio.oggetto). Qui serve a RICONOSCERE, dentro una
# configurazione di plancia, quali stringhe sono un entity_id.
#
# NON e' «la stessa forma usata da ha_client» e non va tenuta allineata a
# quella: e' la stessa espressione oggi e per caso, ma le due hanno esigenze
# CONTRAPPOSTE. Quella di `proxy/ha_client` e' una GUARDIA -- rifiuta un
# entity_id ostile prima di comporlo in un URL -- e vuole essere il piu'
# STRETTA possibile. Questa vuole essere abbastanza LARGA da riconoscere
# tutto, o le entita' di una plancia spariscono dall'archivio.
#
# Il commento di prima diceva «stessa forma usata da ha_client», e quella frase
# era un invito: chi avesse allargato questa per far comparire una plancia
# incompleta avrebbe potuto «riallineare» anche l'altra, allentando la guardia
# contro l'iniezione senza che nessun test lo dicesse. Allargare QUESTA e'
# libero; allargare quella e' una decisione di sicurezza, e va presa sapendolo.
# DOPPIONE DICHIARATO: due esigenze contrapposte, non due copie --
#   una guardia contro l'iniezione (stretta) e un riconoscitore
#   (largo). Allinearle sarebbe una falla, non una pulizia.
_ENTITY_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$")

# Sentinella per distinguere «la chiave non c'e'» da «la chiave c'e' e vale
# None» in `scripts_by_key.get(...)`. Con `None` come default le due cose
# sono indistinguibili, e uno scripts.yaml a meta' modifica (chiave presente,
# valore nullo) faceva emettere lo stesso script due volte: una `solo_stato`
# (perche' "sembrava" senza corpo) e una `solo_file` (perche' "sembrava" mai
# vista) — fino a un UNIQUE constraint failed che fa fallire l'intero
# aggiornamento del comportamento.
_ABSENT = object()


#: I due domini che portano un comportamento. Le scene non entrano in questa
#: fetta: `scene/config` esiste, ma il vocabolario di `tipo` ha due valori e
#: allargarlo tocca la pagina, il nucleo e le ricerche -- si fa quando serve,
#: non "gia' che ci siamo".
_BEHAVIOR_DOMAINS = {"automation": "automazione", "script": "script"}

#: Le due ragioni per cui un corpo puo' mancare. Sono due, non una: la prima e'
#: un guasto di adesso (Home Assistant non ha risposto per quella voce), la
#: seconda una scelta nostra (non si pubblica cio' che non si e' potuto
#: controllare contro i segreti). Chiedono cose opposte -- riprovare, oppure
#: sistemare `secrets.yaml` -- e chi legge deve poterle distinguere.
BODY_NOT_READ = "configurazione non letta da Home Assistant"
SECRETS_UNCHECKABLE = "segreti non controllabili: il corpo non si archivia"


async def reread(client, home_space, ha_folder: Path | None) -> dict:
    """Rilegge il comportamento da Home Assistant e lo consegna all'anagrafe.

    Restituisce `{"conteggi": {...}, "senza_corpo": n, "corpi_non_letti":
    {...}, "problemi": [...]}`. `senza_corpo` non e' un dettaglio: dice di
    quante automazioni HIRIS vede il nome senza poter dire cosa fanno, ed e'
    l'unica misura onesta di quanto sa davvero. **Adesso e' derivato da
    `corpi_non_letti`**, non contato a parte: due campi per lo stesso fatto
    sono due campi che possono divergere.

    **La guardia dello stato resta, e cambia termine di paragone.** Se lo stato
    non porta nessuna entita' `automation.*`/`script.*` mentre la replica
    precedente ne aveva, non e' un fatto sulla casa: e' quasi certamente Home
    Assistant ripartito senza aver ancora caricato le automazioni (riavvio,
    safe mode dopo un `configuration.yaml` rotto). `get_states` risponde lo
    stesso -- e' un successo, non un errore -- e sostituire trasformerebbe
    dodici automazioni vive in zero. Una replica vecchia e dichiarata stantia
    e' meglio di una vuota e falsa.
    """
    # `[]` significa «tutte»: e' la convenzione di `HAClient.get_states`.
    states = await client.get_states([]) or []
    behavior_states = [s for s in states
                       if domain_of(s.get("entity_id", "")) in _BEHAVIOR_DOMAINS]

    if not behavior_states and home_space.behavior():
        message = (
            "nessuna entita' automation.*/script.* nello stato mentre la replica "
            "precedente ne aveva: Home Assistant probabilmente non ha ancora "
            "caricato le automazioni (riavvio, safe mode) - comportamento NON "
            "sostituito, mantenuta la replica precedente"
        )
        logger.warning("comportamento: %s", message)
        current = home_space.behavior()
        counts: dict[str, int] = {}
        for v in current:
            counts[v["tipo"]] = counts.get(v["tipo"], 0) + 1
        unread = home_space.unread_bodies()
        return {"conteggi": counts, "senza_corpo": len(unread),
                "corpi_non_letti": unread, "problemi": [message]}

    seal = (SecretSeal.from_file(ha_folder / _SECRETS) if ha_folder is not None
            else SecretSeal({}, readable=False))
    report = await client.behavior_configs([s["entity_id"] for s in behavior_states])
    configs = report.get("configurazioni") or {}
    failure = report.get("errore")

    entries: list[dict] = []
    unread: dict[str, str] = {}
    problems: list[str] = []
    if behavior_states and not seal.readable:
        problems.append(
            "«" + _SECRETS + "» non letto: i corpi non si archiviano, perche' un "
            "segreto risolto da Home Assistant finirebbe in chiaro nell'archivio "
            "e nel contesto del modello")
    for state in behavior_states:
        entity_id = state["entity_id"]
        body = configs.get(entity_id)
        if body is None:
            unread[entity_id] = failure or BODY_NOT_READ
        elif not seal.readable:
            unread[entity_id] = SECRETS_UNCHECKABLE
            body = None
        else:
            body = seal.redact(body)
        entries.append({
            "id": entity_id,
            "tipo": _BEHAVIOR_DOMAINS[domain_of(entity_id)],
            # Il nome amichevole e' quello che Home Assistant mostra: la
            # sanificazione sta dove sta sempre, al confine (`clean_name`).
            "nome": clean_name((state.get("attributes") or {}).get("friendly_name")),
            "corpo": body,
        })

    home_space.hold_behavior(entries, problems=problems, unread_bodies=unread)

    counts = {}
    for v in entries:
        counts[v["tipo"]] = counts.get(v["tipo"], 0) + 1
    if unread:
        logger.info("comportamento: %d voci di cui %d senza corpo",
                    len(entries), len(unread))
    return {"conteggi": counts, "senza_corpo": len(unread),
            "corpi_non_letti": unread, "problemi": problems}


def _entities_in(config) -> list[str]:
    """Le entita' nominate in una configurazione di plancia: ogni valore che
    somiglia a un entity_id (dominio.oggetto), trovato nelle chiavi `entity`
    e `entities`, in tutto l'albero della config (viste, card, card
    annidate). E' una passeggiata ricorsiva: non esiste uno schema fisso
    delle card di Lovelace da rispettare — le card custom inventano le
    proprie chiavi — quindi si cerca la FORMA (quelle due chiavi), non un
    tipo di card particolare.

    Serve a rispondere «questa entita' la vedi gia' in Cucina» invece di
    riproporla: e' il senso di leggere le plance."""
    found: set[str] = set()

    def _add_if_entity(value) -> None:
        if isinstance(value, str) and _ENTITY_ID_RE.match(value):
            found.add(value)

    def _walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("entity", "entities"):
                    if isinstance(value, list):
                        for item in value:
                            _add_if_entity(item)
                    else:
                        _add_if_entity(value)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(config)
    return sorted(found)


async def reread_dashboards(client, store) -> dict:
    """Rilegge le plance da HA (compresa la predefinita) e sostituisce.

    Se NESSUNA plancia risulta leggibile (`config` a `None` su tutte, o
    l'elenco stesso vuoto) NON si sostituisce: stessa regola dell'anagrafe
    (`anagrafe.rebuild`) — una replica vecchia e dichiarata e' meglio
    di una vuota e falsa. Una plancia leggibile e una in modalita' YAML
    convivono invece senza problemi: quella YAML resta con `config` a
    `None`, visibile in `non_disponibili`, le altre si aggiornano.

    Stessa regola anche quando e' l'ELENCO stesso a non arrivare (timeout su
    `lovelace/dashboards/list`): la predefinita si legge da un'altra
    connessione e puo' risultare leggibile da sola, ma sostituire in quel
    caso rimpiazzerebbe la replica con la sola predefinita — le plance
    aggiuntive sparirebbero senza nemmeno finire fra i non disponibili,
    perche' l'elenco che le nominerebbe non e' mai arrivato.

    Restituisce `{"conteggi": {"plance": n}, "non_disponibili": [...]}`.
    """
    dashboards, unavailable = await client.read_dashboards()
    # L'elenco stesso ("lovelace/dashboards/list") puo' fallire (timeout,
    # disconnessione) mentre la config della predefinita si legge lo stesso —
    # e' un'altra connessione WS. Senza distinguere questo caso, `plance`
    # conterrebbe la sola predefinita leggibile: la guardia sotto ("nessuna
    # leggibile") non scatterebbe, e la replica verrebbe sostituita con la
    # sola predefinita — Cucina, Camera, Tablet sparirebbero senza finire
    # nemmeno fra i non disponibili, perche' l'elenco non li ha mai nominati.
    list_failed = any(nd.split(":", 1)[0] == "elenco" for nd in unavailable)
    readable = [p for p in dashboards if p.get("config") is not None]
    if not readable or list_failed:
        logger.warning(
            "plance: %s (non disponibili: %s) — replica precedente conservata",
            "elenco delle plance non arrivato" if list_failed else "nessuna leggibile",
            unavailable)
        return {"conteggi": {"plance": 0}, "non_disponibili": unavailable}

    entries = [{**p, "entita": _entities_in(p.get("config"))} for p in dashboards]
    store.replace_dashboards(entries, unavailable=unavailable)
    if unavailable:
        logger.info("plance: %d lette, %d non disponibili (%s)",
                    len(entries), len(unavailable), unavailable)
    return {"conteggi": {"plance": len(entries)}, "non_disponibili": unavailable}
