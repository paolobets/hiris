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

    Se TUTTI i registri sono in `non_disponibili` (Home Assistant
    irraggiungibile: riavvio, blip di rete, il ritardo dell'antirimbalzo
    scaduto a HA spento), non si sostituisce niente. `archivio.sostituisci`
    e' incondizionato: chiamato lo stesso, rimpiazzerebbe la casa buona di
    ieri con dieci liste vuote, e la casa resterebbe vuota finche' qualcuno
    non ritocca un registro — anche per settimane, se il ② (rilettura ad ogni
    riconnessione) non basta a farla ritentare subito. Una replica vecchia e
    dichiarata stantia e' meglio di una vuota spacciata per fresca.
    """
    registri, non_disponibili = await client.leggi_registri()
    conteggi = {chiave: len(valore) for chiave, valore in registri.items()}
    # "categorie:script" fallisce per un solo ambito, non per l'intero
    # registro "categorie": si confronta il nome del registro (prima dei
    # due punti), non la stringa intera.
    registri_falliti = {nome.split(":", 1)[0] for nome in non_disponibili}
    if non_disponibili and registri_falliti >= set(registri):
        logger.warning(
            "lettura dei registri fallita per intero (%s): la casa precedente resta "
            "quella di prima, non sostituita da un vuoto", non_disponibili)
    else:
        archivio.sostituisci(registri, non_disponibili)
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
_ID_DISPOSITIVI_NON_LETTI = "__dispositivi_non_letti__"
_ID_SENZA_PIANO = "__senza_piano__"
_ID_PIANI_NON_LETTI = "__piani_non_letti__"
_ID_FUORI_DALLE_AREE = "__fuori_dalle_aree__"

# Le pseudo-aree che una vista di dettaglio (`domande.guarda("area", ...)`)
# sa raggiungere per ID -- MAI per nome: "Senza area" e' un nome che due case
# diverse possono condividere (e' generico, non dichiarato dall'utente), e
# `cerca()`/l'indice (riconoscitore.py) non lo indicizzano perche' non
# esistono nell'anagrafe grezza di Home Assistant, solo nell'albero che
# `gerarchia()` costruisce. Chi mostra il nome da solo (IMPORTANT ⑦) mostra
# un vicolo cieco: il nome non porta a nessun `guarda()` che funzioni.
_ID_PSEUDO_AREA = frozenset(
    {_ID_SENZA_AREA, _ID_AREE_NON_LETTE, _ID_AREA_SCONOSCIUTA, _ID_DISPOSITIVI_NON_LETTI})


def e_pseudo_area(area_id: str) -> bool:
    """Vero se `area_id` e' una pseudo-area generata da `gerarchia()` (non
    un'area vera di Home Assistant): chi la mostra per nome deve mostrare
    anche l'id, l'unica chiave con cui `guarda('area', ...)` la ritrova
    davvero (IMPORTANT ⑦)."""
    return area_id in _ID_PSEUDO_AREA


def gerarchia(casa: dict[str, list[dict]], non_disponibili: tuple[str, ...] = ()) -> list[dict]:
    """La casa in forma di albero: piani → aree → entita'.

    Due regole di Home Assistant che vanno rispettate o meta' della casa
    sparisce:

    - un'entita' appartiene alla PROPRIA area se ce l'ha, altrimenti a quella
      del proprio dispositivo. Moltissime entita' non hanno area propria: e'
      il dispositivo a portarla — e' il caso normale, non l'eccezione;
    - un'area puo' non avere piano: le aree vere di Home Assistant senza piano
      finiscono nel contenitore "Senza piano" (`__senza_piano__`), separato da
      tutto il resto.

    Cinque cause distinte producono un silenzio che va dichiarato invece che
    ingoiato — e vanno tenute separate perche' sono cause contrapposte, non
    varianti di un unico "non si sa":

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
      casa non ha organizzazione";
    - se un'entita' non ha area propria e la eredita dal dispositivo (il caso
      normale), ma il registro dei DISPOSITIVI non e' stato letto, non
      possiamo sapere quale area avrebbe ereditato: trattarla come "senza
      area" affermerebbe un dato che non abbiamo. Va in "Dispositivi non
      letti" (`__dispositivi_non_letti__`), cosi' una casa vera non appare ne'
      vuota ne' senza organizzazione solo perche' e' caduto il registro che
      porta l'ereditarieta';
    - se ci sono aree vere senza piano ma il registro dei PIANI non e' stato
      letto, quelle aree NON vanno in "Senza piano": quel nome afferma "questa
      casa non organizza per piani", e potrebbe non essere vero — sappiamo
      solo di non aver potuto leggere i piani. Vanno in "Piani non letti"
      (`__piani_non_letti__`), distinto da "Senza piano".

    I quattro gruppi di entita' fuori dalle aree note (quelli non vuoti) stanno
    dentro un secondo piano-contenitore, "Fuori dalle aree"
    (`__fuori_dalle_aree__`), distinto dal "Senza piano"/"Piani non letti"
    delle aree vere — sono concetti diversi che in una versione precedente
    condividevano per errore lo stesso id `None`, facendo sparire in silenzio
    l'uno o l'altro a chiunque indicizzasse i piani per id.

    Le entita' disabilitate restano nell'archivio ma non nei CONTEGGI: sono in
    Home Assistant e non funzionano, quindi contarle come stanze arredate
    ingannerebbe chi legge. Restano pero' raggiungibili per area, nella chiave
    parallela `entita_disabilitate` di ogni area (mai in `entita`, che conta):
    una vista di DETTAGLIO su un'area (`domande.guarda`) deve poter mostrare
    "questa luce c'e' ma e' disabilitata", marcata, non farla sparire in
    silenzio come se non esistesse (IMPORTANT ⑦-adiacente, Minor).
    """
    dispositivi_letti = "dispositivi" not in non_disponibili
    area_del_dispositivo = {d["id"]: d.get("area_id") for d in casa.get("dispositivi", [])}

    per_area: dict[str | None, list[dict]] = {}
    per_area_disabilitate: dict[str | None, list[dict]] = {}
    dispositivi_non_letti = []
    for entita in casa.get("entita", []):
        area_propria = entita.get("area_id")
        dispositivo_id = entita.get("dispositivo_id")
        if not area_propria and dispositivo_id and not dispositivi_letti:
            # Erediterebbe l'area dal dispositivo, ma il registro dei
            # dispositivi non ha risposto: non possiamo sapere quale sarebbe,
            # quindi non finge di essere "senza area". Vale anche per le
            # disabilitate: non risolvibili, non tracciate nemmeno a parte.
            if not entita.get("disabilitata"):
                dispositivi_non_letti.append(entita)
            continue
        area_id = area_propria or area_del_dispositivo.get(dispositivo_id)
        if entita.get("disabilitata"):
            per_area_disabilitate.setdefault(area_id, []).append(entita)
        else:
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
            # Non nei conteggi (vedi il docstring), ma raggiungibili nel
            # dettaglio di un'area -- vedi `domande._guarda_area`.
            "entita_disabilitate": per_area_disabilitate.get(area["id"], []),
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

    # Le aree senza piano si dividono per la stessa causa delle entita' senza
    # area sopra: se i piani non sono stati letti, "Senza piano" affermerebbe
    # un dato che non abbiamo.
    piani_letti = "piani" not in non_disponibili
    resto = [a for elenco in aree_per_piano.values() for a in elenco]
    if resto:
        if piani_letti:
            piani.append({"id": _ID_SENZA_PIANO, "nome": "Senza piano", "livello": None,
                          "aree": resto})
        else:
            piani.append({"id": _ID_PIANI_NON_LETTI, "nome": "Piani non letti", "livello": None,
                          "aree": resto})

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
    if dispositivi_non_letti:
        fuori_dalle_aree.append({"id": _ID_DISPOSITIVI_NON_LETTI, "nome": "Dispositivi non letti",
                                 "alias": [], "etichette": [], "entita": dispositivi_non_letti})
    if fuori_dalle_aree:
        piani.append({"id": _ID_FUORI_DALLE_AREE, "nome": "Fuori dalle aree", "livello": None,
                      "aree": fuori_dalle_aree})

    return piani
