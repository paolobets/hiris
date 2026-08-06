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


def componi(automazioni_yaml, script_yaml, stati: list[dict]) -> list[dict]:
    """Incrocia i file con lo stato e produce l'elenco del comportamento.

    `automazioni_yaml`/`script_yaml` a `None` significano «non ho letto il
    file»: le voci vive restano, marcate `solo_stato`. Una lista vuota
    significa invece «il file c'e' e non contiene niente», ed e' un fatto
    diverso.
    """
    per_id_automazione = {
        str(v.get("id")): v for v in (automazioni_yaml or []) if v.get("id") is not None
    }
    script_per_chiave = dict(script_yaml or {})

    voci: list[dict] = []
    visti_automazione: set[str] = set()
    visti_script: set[str] = set()

    for stato in stati:
        entity_id = stato.get("entity_id", "")
        dominio, _, object_id = entity_id.partition(".")
        attributi = stato.get("attributes") or {}
        nome = attributi.get("friendly_name") or object_id

        if dominio == "automation":
            chiave = str(attributi.get("id") or "")
            corpo = per_id_automazione.get(chiave)
            if corpo is not None:
                visti_automazione.add(chiave)
            voci.append({
                "id": entity_id, "tipo": "automazione", "nome": nome,
                "corpo": corpo, "origine": "file" if corpo is not None else "solo_stato",
            })
        elif dominio == "script":
            corpo = script_per_chiave.get(object_id)
            if corpo is not None:
                visti_script.add(object_id)
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
    for chiave, corpo in script_per_chiave.items():
        if chiave not in visti_script:
            voci.append({
                "id": f"script.{chiave}", "tipo": "script",
                "nome": (corpo or {}).get("alias") or chiave, "corpo": corpo,
                "origine": "solo_file",
            })

    return voci


async def rileggi(client, archivio, cartella_ha: Path | None) -> dict:
    """Rilegge i due file e li incrocia con lo stato, poi sostituisce.

    Restituisce `{"conteggi": {...}, "senza_corpo": n, "file_mancanti": [...]}`.
    `senza_corpo` non e' un dettaglio: dice quante automazioni HIRIS vede senza
    poter dire cosa fanno, ed e' l'unica misura onesta di quanto sa davvero.
    """
    automazioni = script = None
    mancanti: list[str] = []
    if cartella_ha is not None:
        for nome, attributo in ((_AUTOMAZIONI, "automazioni"), (_SCRIPT, "script")):
            try:
                contenuto = carica_file(cartella_ha / nome)
            except Exception as exc:
                logger.warning("%s non leggibile: %s", nome, exc)
                contenuto = None
            if contenuto is None:
                mancanti.append(nome)
            if attributo == "automazioni":
                automazioni = contenuto
            else:
                script = contenuto
    else:
        mancanti = [_AUTOMAZIONI, _SCRIPT]

    stati = await client.get_states()
    voci = componi(automazioni, script, stati or [])
    archivio.sostituisci_comportamento(voci)

    conteggi: dict[str, int] = {}
    for v in voci:
        conteggi[v["tipo"]] = conteggi.get(v["tipo"], 0) + 1
    senza_corpo = sum(1 for v in voci if v["corpo"] is None)
    if senza_corpo:
        logger.info("comportamento: %d voci di cui %d senza corpo", len(voci), senza_corpo)
    return {"conteggi": conteggi, "senza_corpo": senza_corpo, "file_mancanti": mancanti}
