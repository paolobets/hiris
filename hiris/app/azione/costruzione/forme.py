"""I corpi degli oggetti, composti DAI PARAMETRI.

**Un costruttore che riceve lo YAML gia' scritto dal modello e lo gira a Home
Assistant non e' un imbuto: e' un tubo con un bel nome** (spec §2.4). Qui il
modello porta l'intenzione -- inneschi, condizioni, azioni, entita' -- e il
corpo lo compone questo modulo.

**Lo schema e' quello moderno, al plurale** (`triggers`, `conditions`,
`actions`): e' cio' che usa la casa del proprietario su HA 2026.8.3, misurato
sul suo `automations.yaml`. Il singolare e' la forma vecchia, quella che un
modello ha letto di piu', e che questa installazione rifiuta. Non c'e' nessun
catalogo da tenere allineato: chi decide se il corpo va bene e' `validate_config`
(spec §2.2).

Puro: niente rete, niente orologio, niente archivio.
"""
from __future__ import annotations

import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9_]+")


def nuovo_id(esistenti: set[str], seme: int) -> str:
    """Un id di automazione o scena che in questa casa non esiste.

    Home Assistant usa timestamp in millisecondi come id nei file scritti
    dall'editor (`1771346155970`), e questa funzione ne genera uno della
    stessa famiglia. `seme` arriva dal chiamante -- non si legge l'orologio
    qui dentro: un modulo puro si prova senza congelare il tempo.

    **Si verifica assente prima di usarlo** (spec §4.2): un id gia' in uso
    farebbe sostituire una voce esistente invece di crearne una nuova, ed e'
    esattamente la famiglia del danno misurato su `automations.yaml`.
    """
    candidato = str(seme)
    passo = 0
    while candidato in esistenti:
        passo += 1
        candidato = str(seme + passo)
    return candidato


def slug_libero(base: str, esistenti: set[str]) -> str:
    """Una chiave di script che non collide. `cv.slug` la valida lato HA."""
    # Traslittera gli accenti prima di applicare la regex, altrimenti
    # "perché" → "perch" invece di "perche".
    base_clean = unicodedata.normalize("NFKD", base or "")
    base_ascii = base_clean.encode("ascii", "ignore").decode("ascii")
    grezzo = _NON_SLUG.sub("_", base_ascii.strip().lower()).strip("_")
    if not grezzo:
        # Uno slug vuoto finirebbe in `/api/config/script/config/`, che e'
        # un'altra rotta: mai restituire la stringa vuota.
        grezzo = "script_hiris"
    candidato = grezzo
    numero = 1
    while candidato in esistenti:
        numero += 1
        candidato = f"{grezzo}_{numero}"
    return candidato


def componi_automazione(*, id_: str, alias: str, descrizione: str, innesco: list,
                        condizioni: list, azioni: list, modo: str = "single") -> dict:
    """Il corpo di un'automazione, nell'ordine in cui l'editor di HA lo scrive."""
    return {
        "id": id_,
        "alias": alias,
        "description": descrizione,
        "triggers": list(innesco),
        "conditions": list(condizioni),
        "actions": list(azioni),
        "mode": modo,
    }


def componi_script(*, alias: str, descrizione: str, passi: list,
                   campi: dict | None = None, modo: str = "single") -> dict:
    """Il corpo di uno script. La CHIAVE (lo slug) non sta dentro il corpo:
    la porta l'URL, ed e' `slug_libero` a produrla."""
    corpo = {
        "alias": alias,
        "description": descrizione,
        "sequence": list(passi),
        "mode": modo,
    }
    if campi:
        corpo["fields"] = dict(campi)
    return corpo


def componi_scena(*, id_: str, alias: str, stati: list[dict]) -> dict:
    """Il corpo di una scena: gli stati da ristabilire, per entita'.

    `stati` arriva come lista di dizionari con `entity_id` e il resto degli
    attributi; HA vuole una MAPPA `entity_id -> attributi`. La conversione sta
    qui e non nel chiamante: e' la forma dell'oggetto, non una scelta di chi
    lo chiede.

    **Precondizione**: gli stati sono gia' controllati con `problemi_stati`.
    Una scena e' l'unico dominio che a valle non viene validato da Home
    Assistant (`parti_da_validare` restituisce {}): uno stato perso qui non
    lo intercetta piu' nessuno.
    """
    entita: dict[str, dict] = {}
    for voce in stati:
        if not isinstance(voce, dict):
            continue
        eid = voce.get("entity_id")
        if not eid:
            continue
        entita[eid] = {k: v for k, v in voce.items() if k != "entity_id"}
    return {"id": id_, "name": alias, "entities": entita}


def problemi_stati(stati: list) -> list[str]:
    """Cosa non va negli stati di una scena, in italiano leggibile.

    Le tre `componi_*` hanno la stessa forma e restituiscono un corpo, non
    una coppia: la diagnosi vive qui, e la chiede il chiamante PRIMA di
    comporre. E' la stessa forma di `casa/comportamento.py::componi`, che
    gia' separa cio' che ha costruito da cio' che non ha potuto concludere.

    Serve perche' una scena e' l'unico dominio che a valle non viene
    validato da Home Assistant (`parti_da_validare` restituisce {}): uno
    stato perso qui non lo intercetta piu' nessuno.
    """
    problemi: list[str] = []
    viste: set[str] = set()

    for i, voce in enumerate(stati):
        if not isinstance(voce, dict):
            problemi.append(f"Voce {i}: non e' un dizionario")
            continue

        eid = voce.get("entity_id")
        if not eid:
            problemi.append(f"Voce {i}: manca entity_id")
            continue

        if eid in viste:
            problemi.append(f"Duplicato: {eid} gia' visto")
        viste.add(eid)

    return problemi


def parti_da_validare(dominio: str, corpo: dict) -> dict:
    """I kwarg da passare a `HAClient.valida_config` per questo corpo.

    Una **scena non si valida**: non ha inneschi ne' azioni, e chiedere a
    `validate_config` di validare tre liste vuote tornerebbe «valido» su
    nulla -- una frase vera che significa una cosa falsa. Chi legge questo
    dizionario vuoto sa che per le scene la verifica arriva al salvataggio.
    """
    if dominio == "automation":
        return {"triggers": corpo.get("triggers", []),
                "conditions": corpo.get("conditions", []),
                "actions": corpo.get("actions", [])}
    if dominio == "script":
        return {"actions": corpo.get("sequence", [])}
    return {}
