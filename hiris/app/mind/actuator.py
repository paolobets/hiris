"""L'attuatore: la parte che decide, **senza modello** (spec 2026-09-21).

Il terzo attore del cervello (25/08/2026). Qui non si parla col modello e non
si scrive niente: si decide **quali domande dell'analista sono ancora aperte**
e **cosa e' cambiato** rispetto a cio' che il proprietario ha gia' deciso. Il
modello sceglie, il codice fa i conti -- la stessa divisione dell'analista, e
la ragione per cui un numero inventato dentro un rapporto che sembra
autorevole qui e' impossibile.

**Cosa ha deciso la forma di questo modulo**: le osservazioni vere che
l'analista ha scritto sulla casa il 15 e il 16/09/2026. La maggior parte
chiedeva di indagare («il sensore era fermo?», «a che ore e' avvenuto il
prelievo?»), alcune di riparare una ricetta di HIRIS che non si esegue piu',
una di cambiare un comportamento, **nessuna di costruire un'automazione**. Il
mestiere dell'attuatore e' stato disegnato su quelle, non sulla parola
«attuatore».
"""
from __future__ import annotations

#: Le chiavi che fanno l'IDENTITA' di una domanda: chi, cosa si misura, quale
#: chiave dentro la misura, e con quale innesco. **I numeri non ci stanno**: se
#: ci stessero, ogni giorno sarebbe una domanda nuova e una proposta rifiutata
#: ieri tornerebbe oggi con la stessa faccia.
_IDENTITY = ("soggetto", "misura", "chiave", "innesco")

#: Cio' che rende una prova **diversa** da quella contro cui il proprietario ha
#: deciso: su quanti giorni si regge (`base`), quanto si stacca
#: (`quanti_scarti`), e se nel frattempo qualcuno l'ha spiegata. Cambiano
#: questi, la domanda si riapre (spec §4); non cambia niente, tace.
#:
#: **Non a tempo**: il tempo non e' una prova, e riproporre la stessa cosa con
#: gli stessi dati e' insistere, non informare. E' la stessa regola che il
#: sapere usa per i rifiuti delle ricette -- «un rifiuto vale finche' vale il
#: registro contro cui e' stato deciso».
_EVIDENCE = ("base", "quanti_scarti", "spiegato")

def observation_key(observation: dict) -> str:
    """L'impronta identitaria di una domanda dell'analista."""
    return "|".join(str(observation.get(name)) for name in _IDENTITY)


def evidence_of(observation: dict) -> dict:
    """La forza della prova su cui quella domanda si regge, adesso."""
    return {name: observation.get(name) for name in _EVIDENCE}


def latest_decided(*sources: dict) -> dict[str, dict]:
    """Le proposte gia' fatte, da piu' archivi, in un dizionario solo: per
    ogni impronta vince la piu' recente (`creata_ts`).

    Le proposte da fare a mano e quelle costruibili vivono in due archivi
    (`mind/store.proposte`, `revisions.costruzioni`), con la stessa forma.
    Fino al 06/10/2026 si leggeva solo il primo, e una costruibile non
    fermava niente: la stessa domanda con la stessa prova chiamava
    l'officina a ogni giro (revisione indipendente, giro 24, D24-2).
    """
    merged: dict[str, dict] = {}
    for source in sources:
        for key, entry in (source or {}).items():
            if key not in merged or entry["creata_ts"] >= merged[key]["creata_ts"]:
                merged[key] = entry
    return merged


def already_answered(observation: dict, decided: dict) -> str | None:
    """Perche' questa domanda non va proposta di nuovo, o `None` se va.

    `decided` e' `store.decided_proposals()`: per impronta, la prova
    dell'ultima proposta e se aspetta ancora una risposta. **Una aperta non
    si duplica**; una decisa vale finche' vale la prova contro cui e' stata
    decisa, e a prova cambiata la domanda torna (S-26, scelta del
    proprietario del 06/10/2026). Il motivo e' una frase: chi salta lo scrive
    nel registro, perche' una proposta potata in silenzio il 01/10/2026 e'
    costata una diagnosi (misura del Task 4.0 degli attori).
    """
    entry = decided.get(observation_key(observation))
    if entry is None:
        return None
    if entry["aperta"]:
        return "ha gia' una proposta in attesa"
    if entry["prova"] == evidence_of(observation):
        return "e' gia' stata decisa con la stessa prova"
    return None


def to_handle(observations, decided: dict) -> list[dict]:
    """Le osservazioni su cui l'attuatore deve lavorare in questo giro: tutte
    tranne quelle che `already_answered` salta.

    In produzione `server.py` la chiama con un dizionario vuoto, quindi non
    salta niente: l'elenco che si chiede al modello deve restare lo stesso
    fra la domanda e la raccolta, perche' la risposta lo cita per indice. Le
    domande gia' decise le salta `_file_proposals`, con la stessa regola.
    """
    return [observation for observation in observations or []
            if already_answered(observation, decided) is None]
