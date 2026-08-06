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


# Id espliciti per le pseudo-aree e i piani-contenitore: mai None, cosi' un
# consumatore che indicizzi per id (naturale, su un albero con id) non fa
# sparire in silenzio due contenitori diversi che per caso condividevano la
# stessa chiave.
_ID_SENZA_AREA = "__senza_area__"
_ID_AREE_NON_LETTE = "__aree_non_lette__"
_ID_AREA_SCONOSCIUTA = "__area_sconosciuta__"
_ID_SENZA_PIANO = "__senza_piano__"
_ID_FUORI_DALLE_AREE = "__fuori_dalle_aree__"


def gerarchia(casa: dict[str, list[dict]], non_disponibili: tuple[str, ...] = ()) -> list[dict]:
    """La casa in forma di albero: piani → aree → entita'.

    Due regole di Home Assistant che vanno rispettate o meta' della casa
    sparisce:

    - un'entita' appartiene alla PROPRIA area se ce l'ha, altrimenti a quella
      del proprio dispositivo. Moltissime entita' non hanno area propria: e'
      il dispositivo a portarla;
    - un'area puo' non avere piano: le aree vere di Home Assistant senza piano
      finiscono nel contenitore "Senza piano" (`__senza_piano__`), separato da
      tutto il resto.

    Le entita' che non finiscono in nessuna area nota si dividono per CAUSA,
    non si mischiano in un unico "non si sa", perche' le cause sono
    contrapposte:

    - se il registro delle aree e' stato letto con successo (`"aree"` non e'
      in `non_disponibili`), un'entita' senza `area_id` (ne' proprio ne'
      ereditato dal dispositivo) davvero non sta in nessuna stanza: va in
      "Senza area" (`__senza_area__`). Se invece ha un `area_id` che non
      corrisponde a nessuna area nota, e' un riferimento penzolante —
      un'incoerenza vera dell'anagrafe, non un'assenza: va in "Area
      sconosciuta" (`__area_sconosciuta__`), cosi' resta visibile invece di
      confondersi con chi davvero non ha casa;
    - se il registro delle aree NON e' stato letto, non possiamo piu' fidarci
      di nessuna delle due letture sopra: un'entita' con `area_id` a None
      potrebbe davvero non avere area, ma un'entita' con un `area_id` che
      "non risulta noto" potrebbe semplicemente stare in un'area che non
      abbiamo potuto leggere. Non potendo distinguerle, non si distinguono:
      finiscono tutte insieme in "Aree non lette" (`__aree_non_lette__`),
      cosi' chi guarda vede "non ho potuto leggere le aree" e non "questa
      casa non ha organizzazione".

    Questi tre gruppi (quelli non vuoti) stanno dentro un secondo
    piano-contenitore, "Fuori dalle aree" (`__fuori_dalle_aree__`), distinto
    dal "Senza piano" delle aree vere — sono concetti diversi che in una
    versione precedente condividevano per errore lo stesso id `None`,
    facendo sparire in silenzio l'uno o l'altro a chiunque indicizzasse i
    piani per id.

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

    # Le entita' fuori dalle aree note si dividono per causa. Se le aree non
    # sono state lette, non possiamo fidarci nemmeno della distinzione fra
    # "area_id assente" e "area_id sconosciuto": vanno tutte in un unico
    # bucket "Aree non lette".
    aree_lette = "aree" not in non_disponibili
    senza_area, aree_non_lette, area_sconosciuta = [], [], []
    for area_id, elenco in per_area.items():
        if area_id in aree_note:
            continue
        if not aree_lette:
            aree_non_lette.extend(elenco)
        elif area_id is None:
            senza_area.extend(elenco)
        else:
            area_sconosciuta.extend(elenco)

    piani = []
    for piano in casa.get("piani", []):
        piani.append({
            "id": piano["id"], "nome": piano["nome"], "livello": piano.get("livello"),
            "aree": aree_per_piano.pop(piano["id"], []),
        })
    piani.sort(key=lambda p: (p["livello"] is None, p["livello"] or 0, p["nome"]))

    resto = [a for elenco in aree_per_piano.values() for a in elenco]
    if resto:
        piani.append({"id": _ID_SENZA_PIANO, "nome": "Senza piano", "livello": None, "aree": resto})

    fuori_dalle_aree = []
    if aree_non_lette:
        fuori_dalle_aree.append({"id": _ID_AREE_NON_LETTE, "nome": "Aree non lette",
                                 "alias": [], "etichette": [], "entita": aree_non_lette})
    if area_sconosciuta:
        fuori_dalle_aree.append({"id": _ID_AREA_SCONOSCIUTA, "nome": "Area sconosciuta",
                                 "alias": [], "etichette": [], "entita": area_sconosciuta})
    if senza_area:
        fuori_dalle_aree.append({"id": _ID_SENZA_AREA, "nome": "Senza area",
                                 "alias": [], "etichette": [], "entita": senza_area})
    if fuori_dalle_aree:
        piani.append({"id": _ID_FUORI_DALLE_AREE, "nome": "Fuori dalle aree", "livello": None,
                      "aree": fuori_dalle_aree})

    return piani
