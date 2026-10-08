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
from pathlib import Path

from ..proxy.entity_cache import unreadable_inventory_error
from .ha_vocabulary import LINK_NAME, domain_of, is_entity_id
from .redaction import SecretSeal

logger = logging.getLogger(__name__)

#: Il file dei segreti: l'unica cosa che HIRIS legge ancora dal disco di
#: Home Assistant, perche' e' la dichiarazione del proprietario su cosa
#: sia segreto -- e nessuna API la espone.
_SECRETS = "secrets.yaml"

#: I due domini che portano un comportamento. Le scene non entrano in questa
#: fetta: `scene/config` esiste, ma il vocabolario di `tipo` ha due valori e
#: allargarlo tocca la pagina, il nucleo e le ricerche -- si fa quando serve,
#: non "gia' che ci siamo".
#:
#: Il nome italiano di ognuno e' quello della tabella dei legami di Home
#: Assistant (`ha_vocabulary.LINK_NAME`), che lo scriveva gia': si chiede a
#: lei (B-23, Tappa 3, Task 7, 04/10/2026), non si riscrive.
BEHAVIOR_DOMAINS = {domain: LINK_NAME[domain] for domain in ("automation", "script")}

#: Le due ragioni per cui un corpo puo' mancare. Sono due, non una: la prima e'
#: un guasto di adesso (Home Assistant non ha risposto per quella voce), la
#: seconda una scelta nostra (non si pubblica cio' che non si e' potuto
#: controllare contro i segreti). Chiedono cose opposte -- riprovare, oppure
#: sistemare `secrets.yaml` -- e chi legge deve poterle distinguere.
BODY_NOT_READ = "configurazione non letta da Home Assistant"
SECRETS_UNCHECKABLE = "segreti non controllabili: il corpo non si archivia"

#: Perche' la guardia dello stato conserva la replica (`reread`): e' il segno
#: che arriva al nucleo (`HomeSpace.keep_behavior`, G-16).
BEHAVIOR_NOT_LOADED = ("Home Assistant non ha nello stato nessuna automazione "
                       "ne' script: probabilmente non li ha ancora caricati "
                       "(riavvio, safe mode)")


def automation_active(entity_id: str, row: dict | None) -> bool | None:
    """Se un'automazione e' attiva, dalla sua riga nello specchio; `None`
    quando non lo si puo' dire.

    `attiva` (24/09/2026). Lo stato arrivava fin dentro la rilettura e veniva
    buttato via: una scelta del proprietario -- ho disabilitato questa
    automazione -- e un guasto diventavano indistinguibili. Misurato sulla
    casa vera: HIRIS segnalava «Gestione antimosche ferma da undici giorni»
    come anomalia, e il proprietario ha risposto che e' giusto, l'ha spenta
    lui. Un allarme su una cosa voluta e' il rumore sano che seppellisce la
    rotta.

    **Si chiede allo specchio quando la voce si legge** (A-12, Tappa 2), non
    si copia nella voce alla rilettura: lo specchio cambia al primo evento, la
    rilettura del comportamento ogni cinque minuti, e la copia diceva accesa
    per cinque minuti un'automazione appena spenta.

    **Solo per le automazioni.** Per un'automazione `off` vuol dire
    DISABILITATA; per uno script vuol dire «non sta girando in questo
    istante», che e' vero quasi sempre. Lo stesso campo per i due insegnerebbe
    al modello a leggere ogni script fermo come spento.

    Solo `on`/`off`: `unavailable` o `unknown` non sono una scelta del
    proprietario, e dire «attiva: false» li spaccerebbe per tale. Una riga che
    lo specchio non ha e' un «non lo so».
    """
    if domain_of(entity_id) != "automation" or row is None:
        return None
    state = row.get("state")
    if state not in ("on", "off"):
        return None
    return state == "on"


async def reread(client, mirror, home_space, ha_folder: Path | None) -> None:
    """Rilegge il comportamento da Home Assistant e lo consegna all'anagrafe.

    **Non restituisce niente** (trovato 5 della Tappa 3, 04/10/2026): fino a
    quel giorno restituiva conteggi per tipo, `senza_corpo`, i corpi non letti
    e i problemi, e l'unico chiamante di produzione (`server.watch_behavior`)
    li buttava. Cio' che serve vive nell'anagrafe, dove questa funzione lo
    consegna (`hold_behavior`): chi vuole sapere quali corpi mancano e perche'
    lo chiede a `home_space.unread_bodies()`, i problemi a
    `behavior_problems()`. Erano due copie dei conteggi di B-39 senza lettori.

    **La guardia dello stato resta, e cambia termine di paragone.** Se lo stato
    non porta nessuna entita' `automation.*`/`script.*` mentre la replica
    precedente ne aveva, non e' un fatto sulla casa: e' quasi certamente Home
    Assistant ripartito senza aver ancora caricato le automazioni (riavvio,
    safe mode dopo un `configuration.yaml` rotto). `get_states` risponde lo
    stesso -- e' un successo, non un errore -- e sostituire trasformerebbe
    dodici automazioni vive in zero. Una replica vecchia e dichiarata stantia
    e' meglio di una vuota e falsa.

    **Quali automazioni e script ci sono, lo dice lo specchio** (`mirror`,
    A-03, 03/10/2026): fino a quel giorno si rileggeva da Home Assistant
    l'intera casa (`GET /api/states`, centinaia di entita') per tenerne lo
    stato e il nome di una ventina -- cose che lo specchio sa gia', aggiornate
    a ogni evento. Da Home Assistant si chiede solo cio' che lo specchio non
    porta: il corpo (`behavior_configs`).

    **Lo specchio si legge quando ha finito di rileggersi** (S-31, Tappa 8):
    alla riconnessione la rilettura dello specchio e questa partono dallo
    stesso evento, e fino all'08/10/2026 questa leggeva la casa di prima della
    caduta se l'altra non era finita (`EntityCache.settled`).
    """
    # Lo specchio si legge quando ha finito di rileggersi (S-31): alla
    # riconnessione la sua rilettura e questa partono insieme.
    await mirror.settled()
    failure = unreadable_inventory_error(mirror)
    if failure is not None:
        # Uno specchio che non si legge non e' una casa senza automazioni: la
        # rilettura si ferma e la replica resta quella di prima -- chi chiama
        # (`server.watch_behavior`) lo registra, e la replica lo dice.
        home_space.keep_behavior(failure["error"])
        raise RuntimeError(failure["error"])
    behavior_states = [s for s in mirror.all_states()
                       if domain_of(s.get("id", "")) in BEHAVIOR_DOMAINS]

    if not behavior_states and home_space.behavior():
        message = (
            "nessuna entita' automation.*/script.* nello stato mentre la replica "
            "precedente ne aveva: Home Assistant probabilmente non ha ancora "
            "caricato le automazioni (riavvio, safe mode) - comportamento NON "
            "sostituito, mantenuta la replica precedente"
        )
        logger.warning("comportamento: %s", message)
        home_space.keep_behavior(BEHAVIOR_NOT_LOADED)
        return

    seal = (SecretSeal.from_file(ha_folder / _SECRETS) if ha_folder is not None
            else SecretSeal({}, readable=False))
    report = await client.behavior_configs([s["id"] for s in behavior_states])
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
        entity_id = state["id"]
        body = configs.get(entity_id)
        if body is None:
            unread[entity_id] = (failure or (report.get("non_letti") or {}).get(entity_id)
                                 or BODY_NOT_READ)
        elif not seal.readable:
            unread[entity_id] = SECRETS_UNCHECKABLE
            body = None
        else:
            body = seal.redact(body)
        entry = {
            "id": entity_id,
            "tipo": BEHAVIOR_DOMAINS[domain_of(entity_id)],
            # Il nome amichevole e' quello che Home Assistant mostra, gia'
            # sanificato al confine dallo specchio (`_to_minimal`). La sua
            # stringa vuota e' «senza nome», e qui si e' sempre scritto `None`.
            "nome": state.get("name") or None,
            "corpo": body,
        }
        entries.append(entry)

    home_space.hold_behavior(entries, problems=problems, unread_bodies=unread)
    if unread:
        logger.info("comportamento: %d voci di cui %d senza corpo",
                    len(entries), len(unread))


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
        if is_entity_id(value):
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


async def reread_dashboards(client, home_space) -> dict:
    """Rilegge le plance da HA (compresa la predefinita) e sostituisce.

    Se NESSUNA plancia risulta leggibile (`config` a `None` su tutte, o
    l'elenco stesso vuoto) NON si sostituisce: stessa regola dell'anagrafe
    (`topology.rebuild`) — una replica vecchia e dichiarata e' meglio
    di una vuota e falsa. Una plancia leggibile e una in modalita' YAML
    convivono invece senza problemi: quella YAML resta con `config` a
    `None`, visibile in `non_disponibili`, le altre si aggiornano.

    Stessa regola anche quando e' l'ELENCO stesso a non arrivare (timeout su
    `lovelace/dashboards/list`): la predefinita si legge con un'altra
    richiesta e puo' risultare leggibile da sola, ma sostituire in quel
    caso rimpiazzerebbe la replica con la sola predefinita — le plance
    aggiuntive sparirebbero senza nemmeno finire fra i non disponibili,
    perche' l'elenco che le nominerebbe non e' mai arrivato.

    Restituisce `{"conteggi": {"plance": n}, "non_disponibili": [...]}`.
    """
    dashboards, unavailable = await client.read_dashboards()
    # L'elenco stesso ("lovelace/dashboards/list") puo' fallire (timeout,
    # disconnessione) mentre la config della predefinita si legge lo stesso —
    # e' un'altra richiesta. Senza distinguere questo caso, `dashboards`
    # conterrebbe la sola predefinita leggibile: la guardia sotto ("nessuna
    # leggibile") non scatterebbe, e la replica verrebbe sostituita con la
    # sola predefinita — Cucina, Camera, Tablet sparirebbero senza finire
    # nemmeno fra i non disponibili, perche' l'elenco non li ha mai nominati.
    list_failed = any(nd.split(":", 1)[0] == "elenco" for nd in unavailable)
    readable = [p for p in dashboards if p.get("config") is not None]
    if not readable or list_failed:
        reason = ("elenco delle plance non arrivato" if list_failed
                  else "nessuna plancia leggibile")
        logger.warning("plance: %s (non disponibili: %s) — replica precedente conservata",
                       reason, unavailable)
        home_space.keep_dashboards(reason, unavailable=unavailable)
        return {"conteggi": {"plance": 0}, "non_disponibili": unavailable}

    # **La forma e' quella dell'anagrafe, non quella di Home Assistant.** Le
    # chiavi inglesi (`url_path`, `title`, `mode`) sono il vocabolario del
    # sistema esterno e si traducono al confine, come ogni altra cosa che entra:
    # chi legge le plance conosce
    # `percorso`/`titolo`/`modalita`, e una seconda forma sarebbe la
    # stessa cosa detta in due modi (fondamenta 3).
    entries = [{"percorso": p.get("url_path"), "titolo": p.get("title"),
                "modalita": p.get("mode"), "config": p.get("config"),
                "entita": _entities_in(p.get("config"))}
               for p in dashboards]
    home_space.hold_dashboards(entries, unavailable=unavailable)
    if unavailable:
        logger.info("plance: %d lette, %d non disponibili (%s)",
                    len(entries), len(unavailable), unavailable)
    return {"conteggi": {"plance": len(entries)}, "non_disponibili": unavailable}
