"""L'anagrafe: i registri grezzi di Home Assistant diventano LA CASA.

Quattro livelli di gerarchia — piano → area → dispositivo → entita' — dove
HIRIS ne conosceva uno solo. Il significato non si deduce e non si compra: e'
gia' dichiarato dall'utente in Home Assistant.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ricostruisci(client, archivio) -> dict:
    """Rilegge tutti i registri da HA e sostituisce l'anagrafe.

    Restituisce `{"conteggi": {...}, "non_disponibili": [...]}`.

    I conteggi servono a chi guarda: se domani sono la meta' di ieri, e'
    successo qualcosa. `non_disponibili` serve a distinguere una casa senza
    piani da un registro dei piani caduto — producono la stessa lista vuota, e
    senza questo elenco l'anagrafe costruirebbe sul silenzio credendolo un
    dato. Va REGISTRATO, non ingoiato.
    """
    registri, non_disponibili = await client.leggi_registri()
    archivio.sostituisci(registri, non_disponibili)
    conteggi = {chiave: len(valore) for chiave, valore in registri.items()}
    if non_disponibili:
        logger.warning("anagrafe ricostruita, ma questi registri non hanno risposto: %s",
                       non_disponibili)
    logger.info("anagrafe ricostruita: %s", conteggi)
    return {"conteggi": conteggi, "non_disponibili": non_disponibili}


def gerarchia(casa: dict[str, list[dict]]) -> list[dict]:
    """La casa in forma di albero: piani → aree → entita'.

    Due regole di Home Assistant che vanno rispettate o meta' della casa
    sparisce:

    - un'entita' appartiene alla PROPRIA area se ce l'ha, altrimenti a quella
      del proprio dispositivo. Moltissime entita' non hanno area propria: e'
      il dispositivo a portarla;
    - un'area puo' non avere piano, e un'entita' puo' non avere area. Non si
      buttano: finiscono in un piano e in un'area senza nome, cosi' chi guarda
      vede che esistono invece di credere che la casa sia piu' piccola.

    Le entita' disabilitate restano nell'archivio ma non nell'albero: sono in
    Home Assistant e non funzionano, quindi contarle come stanze arredate
    ingannerebbe chi legge.
    """
    area_del_dispositivo = {d["id"]: d.get("area_id") for d in casa.get("dispositivi", [])}

    per_area: dict[str | None, list[dict]] = {}
    for entita in casa.get("entita", []):
        if entita.get("disabilitata"):
            continue
        area_id = entita.get("area_id") or area_del_dispositivo.get(entita.get("dispositivo_id"))
        per_area.setdefault(area_id, []).append(entita)

    aree_per_piano: dict[str | None, list[dict]] = {}
    aree_note = set()
    for area in casa.get("aree", []):
        aree_note.add(area["id"])
        aree_per_piano.setdefault(area.get("piano_id"), []).append({
            "id": area["id"],
            "nome": area["nome"],
            "alias": area.get("alias", []),
            "etichette": area.get("etichette", []),
            "entita": per_area.get(area["id"], []),
        })

    # Le entita' senza area (ne' propria, ne' ereditata dal dispositivo) sono
    # un concetto diverso dalle aree senza piano: non vanno mischiate nello
    # stesso bucket "None", o le prime finiscono per travestirsi da seconde
    # (e un test che verifica il contenuto esatto del piano senza nome
    # smaschera subito la confusione).
    senza_casa = [e for area_id, elenco in per_area.items()
                  if area_id not in aree_note for e in elenco]

    piani = []
    for piano in casa.get("piani", []):
        piani.append({
            "id": piano["id"], "nome": piano["nome"], "livello": piano.get("livello"),
            "aree": aree_per_piano.pop(piano["id"], []),
        })
    piani.sort(key=lambda p: (p["livello"] is None, p["livello"] or 0, p["nome"]))

    resto = [a for elenco in aree_per_piano.values() for a in elenco]
    if resto:
        piani.append({"id": None, "nome": "Senza piano", "livello": None, "aree": resto})

    if senza_casa:
        piani.append({"id": None, "nome": "Senza piano", "livello": None, "aree": [
            {"id": None, "nome": "Senza area", "alias": [], "etichette": [],
             "entita": senza_casa},
        ]})
    return piani
