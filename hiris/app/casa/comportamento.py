"""Cosa la casa fa gia' da sola: il corpo delle automazioni e degli script.

Il file dice cosa c'e' SCRITTO; lo stato dice cosa ESISTE davvero. Le due cose
non coincidono, e la differenza e' informazione: le automazioni scritte a mano
non stanno in `automations.yaml` — vivono nei pacchetti o in cartelle incluse —
e di quelle HIRIS conosce il nome e non il corpo. Deve saperlo e dirlo, invece
di credere che non esistano o che siano vuote.

Senza tutto questo la Legge I resta sulla carta: HIRIS proporrebbe
un'automazione per una cosa che la casa gia' fa, e non potrebbe mai dire la
frase piu' utile che esista — «non serve, ce l'hai gia', si chiama cosi'».
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .anagrafe import domain_of
from .lettura_yaml import load_file

logger = logging.getLogger(__name__)

_AUTOMATIONS = "automations.yaml"
_SCRIPT = "scripts.yaml"

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


def compose(automation_yaml, script_yaml, states: list[dict]) -> tuple[list[dict], list[str]]:
    """Incrocia i file con lo stato e produce l'elenco del comportamento.

    `automation_yaml`/`script_yaml` a `None` significano «non ho letto il
    file»: le voci vive restano, marcate `solo_stato`. Una lista vuota
    significa invece «il file c'e' e non contiene niente», ed e' un fatto
    diverso.

    Restituisce `(entries, problems)`. `problems` e' un elenco di frasi in
    italiano leggibile su cio' che NON si e' potuto concludere con certezza
    — id duplicati, script vuoti, file mal formati. Un silenzio non
    dichiarato e' indistinguibile da un'assenza di problemi: se questi casi
    non finissero qui, il chiamante li scambierebbe per dati buoni.
    """
    problems: list[str] = []
    automation_yaml = automation_yaml or []

    # Un trattino residuo in coda ("- id: '1'\n  alias: X\n-\n") o un valore
    # scalare al posto di una mappa sono entrambi YAML VALIDO: il parser non
    # solleva, quindi `file_non_letti` resterebbe vuoto e il guasto sarebbe
    # invisibile finche' non arriva qui sotto e fa esplodere `.get()` su
    # `None` o su una stringa. Si scarta PRIMA di tutto il resto — id,
    # conteggi, aggancio allo stato — cosi' nessuno di quei passaggi vede mai
    # una voce che non e' un dizionario.
    valid_automations: list[dict] = []
    for index, v in enumerate(automation_yaml):
        if not isinstance(v, dict):
            problems.append(
                f"{_AUTOMATIONS}: voce #{index + 1} non e' un dizionario "
                f"(trovato {type(v).__name__}) — scartata"
            )
            continue
        valid_automations.append(v)
    automation_yaml = valid_automations

    # Un id usato da piu' voci non e' una chiave: prima si conta, poi si
    # decide chi entra nella mappa. Tenerla "l'ultima vince" (il bug
    # originale) marcherebbe come "file" — dato certo — l'entita' viva che
    # per caso corrisponde all'id duplicato, con il corpo sbagliato.
    id_counts: dict[str, int] = {}
    for v in automation_yaml:
        if v.get("id") is not None:
            key = str(v.get("id"))
            id_counts[key] = id_counts.get(key, 0) + 1
    ambiguous = {key for key, n in id_counts.items() if n > 1}
    for key in sorted(ambiguous):
        problems.append(f"{_AUTOMATIONS}: id {key} usato da {id_counts[key]} voci")

    by_automation_id: dict[str, dict] = {}
    without_id: list[dict] = []
    for v in automation_yaml:
        raw_id = v.get("id")
        if raw_id is None:
            # Scritta a mano, senza passare dall'interfaccia: non si puo'
            # agganciare a nessuna entita' viva, ma non per questo sparisce.
            without_id.append(v)
            continue
        key = str(raw_id)
        if key not in ambiguous:
            by_automation_id[key] = v

    if script_yaml is None:
        scripts_by_key: dict = {}
    elif isinstance(script_yaml, dict):
        scripts_by_key = dict(script_yaml)
    else:
        # Abitudine presa da automations.yaml: scripts.yaml scritto come
        # lista. `dict(script_yaml)` non solleva subito e produce un
        # dizionario spurio; l'errore arriverebbe piu' tardi, incoerente.
        scripts_by_key = {}
        problems.append(
            f"{_SCRIPT}: atteso un dizionario di script, trovato un oggetto di tipo "
            f"{type(script_yaml).__name__} — nessuno script letto dal file"
        )

    # Stessa difesa della lista sopra, per gli script: la chiave e' una mappa
    # attesa (`saluta:\n  alias: ...`), ma niente nello YAML impedisce
    # `saluta: 'ciao'` — uno scalare al posto della mappa. Prima si scartano i
    # valori che non sono ne' `None` (assente-e-nullo, gia' gestito) ne' un
    # dizionario, cosi' il `.get("alias")` piu' sotto non vede mai altro.
    valid_scripts: dict = {}
    for key, value in scripts_by_key.items():
        if value is None:
            problems.append(f"{_SCRIPT}: script '{key}' presente nel file ma vuoto")
            valid_scripts[key] = None
        elif isinstance(value, dict):
            valid_scripts[key] = value
        else:
            problems.append(
                f"{_SCRIPT}: script '{key}' non e' un dizionario "
                f"(trovato {type(value).__name__}) — scartato"
            )
    scripts_by_key = valid_scripts

    entries: list[dict] = []
    seen_automations: set[str] = set()
    seen_scripts: set[str] = set()

    for state in states:
        entity_id = state.get("entity_id", "")
        domain, _, object_id = entity_id.partition(".")
        attributes = state.get("attributes") or {}
        name = attributes.get("friendly_name") or object_id

        if domain == "automation":
            # `None` e' l'unica assenza: un id intero `0` (numerazione a
            # mano da zero) e' un id vero, non un id mancante.
            attribute_id = attributes.get("id")
            key = str(attribute_id) if attribute_id is not None else ""
            if key and key in ambiguous:
                entries.append({
                    "id": entity_id, "tipo": "automazione", "nome": name,
                    "corpo": None, "origine": "ambiguo", "id_reale": True,
                })
                continue
            body = by_automation_id.get(key) if key else None
            if body is not None:
                seen_automations.add(key)
            entries.append({
                "id": entity_id, "tipo": "automazione", "nome": name,
                "corpo": body, "origine": "file" if body is not None else "solo_stato",
                "id_reale": True,
            })
        elif domain == "script":
            body = scripts_by_key.get(object_id, _ABSENT)
            if body is not _ABSENT:
                # Conosciuta anche se vuota: non deve ripresentarsi come
                # solo_file piu' sotto.
                seen_scripts.add(object_id)
            else:
                body = None
            entries.append({
                "id": entity_id, "tipo": "script", "nome": name,
                "corpo": body, "origine": "file" if body is not None else "solo_stato",
                "id_reale": True,
            })

    # Cio' che sta nel file e non nello stato e' scritto ma NON caricato:
    # un'automazione disabilitata all'origine, o una configurazione con un
    # errore. E' un fatto sulla casa, e va visto invece che scartato.
    for key, body in by_automation_id.items():
        if key not in seen_automations:
            entries.append({
                "id": f"automation.__non_caricata_{key}", "tipo": "automazione",
                "nome": body.get("alias") or key, "corpo": body,
                # Questo id e' sintetico (combacia comunque con la forma
                # dominio.oggetto di un entity_id vero — vedi _ENTITY_ID_RE):
                # senza questo campo un consumatore lo passerebbe a un
                # servizio come se l'entita' esistesse davvero.
                "origine": "solo_file", "id_reale": False,
            })
    for index, body in enumerate(without_id):
        name = body.get("alias") or f"automazione senza id #{index + 1}"
        entries.append({
            "id": f"automation.__senza_id_{index}", "tipo": "automazione",
            "nome": name, "corpo": body, "origine": "solo_file", "id_reale": False,
        })
        problems.append(
            f"{_AUTOMATIONS}: automazione '{name}' senza id, non collegabile a nessuna entita'"
        )
    for key, body in scripts_by_key.items():
        if key not in seen_scripts:
            # Id sintetico prefissato, simmetrico a quello delle automazioni
            # sopra: due rami dello stesso codice non devono avere due
            # convenzioni diverse per «scritto ma non caricato».
            entries.append({
                "id": f"script.__non_caricato_{key}", "tipo": "script",
                "nome": (body or {}).get("alias") or key, "corpo": body,
                "origine": "solo_file", "id_reale": False,
            })

    return entries, problems


async def reread(client, store, ha_folder: Path | None) -> dict:
    """Rilegge i due file e li incrocia con lo stato, poi sostituisce.

    Restituisce
    `{"conteggi": {...}, "senza_corpo": n, "file_non_letti": {...}, "problemi": [...]}`.
    `senza_corpo` non e' un dettaglio: dice quante automazioni HIRIS vede senza
    poter dire cosa fanno, ed e' l'unica misura onesta di quanto sa davvero.

    `file_non_letti` mappa il nome del file alla RAGIONE per cui non e' stato
    letto: `"assente"` (il file non esiste, va creato) oppure
    `"illeggibile: <motivo>"` (il file c'e' ed e' rotto, va riparato). Le due
    cose chiedono interventi opposti, e un elenco unico dei "mancanti" le
    rendeva indistinguibili.
    """
    automations = script = None
    unloaded: dict[str, str] = {}
    if ha_folder is not None:
        for name, attribute in ((_AUTOMATIONS, "automazioni"), (_SCRIPT, "script")):
            try:
                content = load_file(ha_folder / name)
            except Exception as exc:
                logger.warning("%s non leggibile: %s", name, exc)
                content = None
                unloaded[name] = f"illeggibile: {exc}"
            else:
                if content is None:
                    unloaded[name] = "assente"
            if attribute == "automazioni":
                automations = content
            else:
                script = content
    else:
        unloaded = {_AUTOMATIONS: "assente", _SCRIPT: "assente"}

    # `[]` significa «tutte»: e' la convenzione di HAClient.get_states, che
    # richiede l'argomento. Gli altri sei chiamanti fanno cosi'.
    states = await client.get_states([]) or []

    # Guardia sulla gamba dello stato, stessa forma di quella dell'anagrafe
    # (anagrafe.ricostruisci, anagrafe.py:40-43): se lo stato NON porta
    # nessuna entita' automation.*/script.* mentre i file ne contengono, non
    # e' un fatto sulla casa — e' quasi certamente Home Assistant ripartito
    # senza avere ancora caricato le automazioni (riavvio, safe mode dopo un
    # configuration.yaml rotto). `/api/states` risponde 200: e' un successo,
    # non un errore, e senza questa guardia sarebbe indistinguibile da una
    # casa che ha DAVVERO cancellato tutte le sue automazioni. Sostituire
    # comunque trasformerebbe ogni automazione viva in "solo_file" — scritta
    # ma NON caricata: qualcosa non va — un'affermazione positiva e FALSA, e
    # farebbe sparire del tutto quelle scritte a mano (solo_stato). Una
    # replica vecchia e dichiarata stantia e' meglio di una fresca e falsa.
    behavior_domains = {"automation", "script"}
    state_has_behavior = any(
        domain_of(s.get("entity_id", "")) in behavior_domains for s in states
    )
    files_have_entries = bool(automations) or bool(script)
    if not state_has_behavior and files_have_entries:
        message = (
            "nessuna entita' automation.*/script.* nello stato mentre i file "
            "ne contengono voci: Home Assistant probabilmente non ha ancora "
            "caricato le automazioni (riavvio, safe mode) — comportamento NON "
            "sostituito, mantenuta la replica precedente"
        )
        logger.warning("comportamento: %s", message)
        current_entries = store.behavior()
        current_counts: dict[str, int] = {}
        for v in current_entries:
            current_counts[v["tipo"]] = current_counts.get(v["tipo"], 0) + 1
        return {
            "conteggi": current_counts,
            "senza_corpo": sum(1 for v in current_entries if v["corpo"] is None),
            "file_non_letti": unloaded, "problemi": [message],
        }

    entries, problems = compose(automations, script, states)
    store.replace_behavior(entries, problems=problems, unloaded_files=unloaded)

    counts: dict[str, int] = {}
    for v in entries:
        counts[v["tipo"]] = counts.get(v["tipo"], 0) + 1
    without_body = sum(1 for v in entries if v["corpo"] is None)
    if without_body:
        logger.info("comportamento: %d voci di cui %d senza corpo", len(entries), without_body)
    if problems:
        logger.warning("comportamento: %d problemi nella lettura: %s", len(problems), problems)
    return {
        "conteggi": counts, "senza_corpo": without_body,
        "file_non_letti": unloaded, "problemi": problems,
    }


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
