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
from pathlib import Path

from .lettura_yaml import carica_file

logger = logging.getLogger(__name__)

_AUTOMAZIONI = "automations.yaml"
_SCRIPT = "scripts.yaml"

# Sentinella per distinguere «la chiave non c'e'» da «la chiave c'e' e vale
# None» in `script_per_chiave.get(...)`. Con `None` come default le due cose
# sono indistinguibili, e uno scripts.yaml a meta' modifica (chiave presente,
# valore nullo) faceva emettere lo stesso script due volte: una `solo_stato`
# (perche' "sembrava" senza corpo) e una `solo_file` (perche' "sembrava" mai
# vista) — fino a un UNIQUE constraint failed che fa fallire l'intero
# aggiornamento del comportamento.
_ASSENTE = object()


def componi(automazioni_yaml, script_yaml, stati: list[dict]) -> tuple[list[dict], list[str]]:
    """Incrocia i file con lo stato e produce l'elenco del comportamento.

    `automazioni_yaml`/`script_yaml` a `None` significano «non ho letto il
    file»: le voci vive restano, marcate `solo_stato`. Una lista vuota
    significa invece «il file c'e' e non contiene niente», ed e' un fatto
    diverso.

    Restituisce `(voci, problemi)`. `problemi` e' un elenco di frasi in
    italiano leggibile su cio' che NON si e' potuto concludere con certezza
    — id duplicati, script vuoti, file mal formati. Un silenzio non
    dichiarato e' indistinguibile da un'assenza di problemi: se questi casi
    non finissero qui, il chiamante li scambierebbe per dati buoni.
    """
    problemi: list[str] = []
    automazioni_yaml = automazioni_yaml or []

    # Un id usato da piu' voci non e' una chiave: prima si conta, poi si
    # decide chi entra nella mappa. Tenerla "l'ultima vince" (il bug
    # originale) marcherebbe come "file" — dato certo — l'entita' viva che
    # per caso corrisponde all'id duplicato, con il corpo sbagliato.
    conteggio_id: dict[str, int] = {}
    for v in automazioni_yaml:
        if v.get("id") is not None:
            chiave = str(v.get("id"))
            conteggio_id[chiave] = conteggio_id.get(chiave, 0) + 1
    ambigui = {chiave for chiave, n in conteggio_id.items() if n > 1}
    for chiave in sorted(ambigui):
        problemi.append(f"{_AUTOMAZIONI}: id {chiave} usato da {conteggio_id[chiave]} voci")

    per_id_automazione: dict[str, dict] = {}
    senza_id: list[dict] = []
    for v in automazioni_yaml:
        id_grezzo = v.get("id")
        if id_grezzo is None:
            # Scritta a mano, senza passare dall'interfaccia: non si puo'
            # agganciare a nessuna entita' viva, ma non per questo sparisce.
            senza_id.append(v)
            continue
        chiave = str(id_grezzo)
        if chiave not in ambigui:
            per_id_automazione[chiave] = v

    if script_yaml is None:
        script_per_chiave: dict = {}
    elif isinstance(script_yaml, dict):
        script_per_chiave = dict(script_yaml)
    else:
        # Abitudine presa da automations.yaml: scripts.yaml scritto come
        # lista. `dict(script_yaml)` non solleva subito e produce un
        # dizionario spurio; l'errore arriverebbe piu' tardi, incoerente.
        script_per_chiave = {}
        problemi.append(
            f"{_SCRIPT}: atteso un dizionario di script, trovato un oggetto di tipo "
            f"{type(script_yaml).__name__} — nessuno script letto dal file"
        )

    for chiave, valore in script_per_chiave.items():
        if valore is None:
            problemi.append(f"{_SCRIPT}: script '{chiave}' presente nel file ma vuoto")

    voci: list[dict] = []
    visti_automazione: set[str] = set()
    visti_script: set[str] = set()

    for stato in stati:
        entity_id = stato.get("entity_id", "")
        dominio, _, object_id = entity_id.partition(".")
        attributi = stato.get("attributes") or {}
        nome = attributi.get("friendly_name") or object_id

        if dominio == "automation":
            # `None` e' l'unica assenza: un id intero `0` (numerazione a
            # mano da zero) e' un id vero, non un id mancante.
            id_attributo = attributi.get("id")
            chiave = str(id_attributo) if id_attributo is not None else ""
            if chiave and chiave in ambigui:
                voci.append({
                    "id": entity_id, "tipo": "automazione", "nome": nome,
                    "corpo": None, "origine": "ambiguo",
                })
                continue
            corpo = per_id_automazione.get(chiave) if chiave else None
            if corpo is not None:
                visti_automazione.add(chiave)
            voci.append({
                "id": entity_id, "tipo": "automazione", "nome": nome,
                "corpo": corpo, "origine": "file" if corpo is not None else "solo_stato",
            })
        elif dominio == "script":
            corpo = script_per_chiave.get(object_id, _ASSENTE)
            if corpo is not _ASSENTE:
                # Conosciuta anche se vuota: non deve ripresentarsi come
                # solo_file piu' sotto.
                visti_script.add(object_id)
            else:
                corpo = None
            voci.append({
                "id": entity_id, "tipo": "script", "nome": nome,
                "corpo": corpo, "origine": "file" if corpo is not None else "solo_stato",
            })

    # Cio' che sta nel file e non nello stato e' scritto ma NON caricato:
    # un'automazione disabilitata all'origine, o una configurazione con un
    # errore. E' un fatto sulla casa, e va visto invece che scartato.
    for chiave, corpo in per_id_automazione.items():
        if chiave not in visti_automazione:
            voci.append({
                "id": f"automation.__non_caricata_{chiave}", "tipo": "automazione",
                "nome": corpo.get("alias") or chiave, "corpo": corpo,
                "origine": "solo_file",
            })
    for indice, corpo in enumerate(senza_id):
        nome = corpo.get("alias") or f"automazione senza id #{indice + 1}"
        voci.append({
            "id": f"automation.__senza_id_{indice}", "tipo": "automazione",
            "nome": nome, "corpo": corpo, "origine": "solo_file",
        })
        problemi.append(
            f"{_AUTOMAZIONI}: automazione '{nome}' senza id, non collegabile a nessuna entita'"
        )
    for chiave, corpo in script_per_chiave.items():
        if chiave not in visti_script:
            # Id sintetico prefissato, simmetrico a quello delle automazioni
            # sopra: due rami dello stesso codice non devono avere due
            # convenzioni diverse per «scritto ma non caricato».
            voci.append({
                "id": f"script.__non_caricato_{chiave}", "tipo": "script",
                "nome": (corpo or {}).get("alias") or chiave, "corpo": corpo,
                "origine": "solo_file",
            })

    return voci, problemi


async def rileggi(client, archivio, cartella_ha: Path | None) -> dict:
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
    automazioni = script = None
    non_letti: dict[str, str] = {}
    if cartella_ha is not None:
        for nome, attributo in ((_AUTOMAZIONI, "automazioni"), (_SCRIPT, "script")):
            try:
                contenuto = carica_file(cartella_ha / nome)
            except Exception as exc:
                logger.warning("%s non leggibile: %s", nome, exc)
                contenuto = None
                non_letti[nome] = f"illeggibile: {exc}"
            else:
                if contenuto is None:
                    non_letti[nome] = "assente"
            if attributo == "automazioni":
                automazioni = contenuto
            else:
                script = contenuto
    else:
        non_letti = {_AUTOMAZIONI: "assente", _SCRIPT: "assente"}

    stati = await client.get_states()
    voci, problemi = componi(automazioni, script, stati or [])
    archivio.sostituisci_comportamento(voci)

    conteggi: dict[str, int] = {}
    for v in voci:
        conteggi[v["tipo"]] = conteggi.get(v["tipo"], 0) + 1
    senza_corpo = sum(1 for v in voci if v["corpo"] is None)
    if senza_corpo:
        logger.info("comportamento: %d voci di cui %d senza corpo", len(voci), senza_corpo)
    if problemi:
        logger.warning("comportamento: %d problemi nella lettura: %s", len(problemi), problemi)
    return {
        "conteggi": conteggi, "senza_corpo": senza_corpo,
        "file_non_letti": non_letti, "problemi": problemi,
    }
