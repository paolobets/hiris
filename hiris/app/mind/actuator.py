"""L'attuatore: la parte che decide, **senza modello** (spec 2026-09-21).

Il terzo attore del cervello (25/08/2026). Qui non si parla col modello e non
si scrive niente: si decide **quali domande dell'analista sono ancora aperte**
e **cosa e' cambiato** rispetto a cio' che il proprietario ha gia' deciso. Il
modello sceglie, il codice fa i conti -- la stessa divisione dell'analista, e
la ragione per cui un numero inventato dentro un rapporto che sembra
autorevole qui e' impossibile.

**Cosa ha deciso la forma di questo modulo**: le otto osservazioni vere che
l'analista ha scritto sulla casa il 15 e il 16/09/2026. Cinque chiedono di
indagare («il sensore era fermo?», «a che ore e' avvenuto il prelievo?»), tre
di riparare una ricetta di HIRIS che non si esegue piu', una di cambiare un
comportamento, **zero di costruire un'automazione**. Il mestiere
dell'attuatore e' stato disegnato su quei numeri, non sulla parola «attuatore».
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

#: Il terzo innesco dell'analista e' «qualcosa non c'e' piu'» (`analyst.py`), e
#: una misura che non si calcola piu' e' il suo caso piu' frequente sulla casa
#: vera: **3 osservazioni su 8**, misurate il 20/09/2026.
_MISSING_TRIGGER = 3


def observation_key(observation: dict) -> str:
    """L'impronta identitaria di una domanda dell'analista."""
    return "|".join(str(observation.get(name)) for name in _IDENTITY)


def evidence_of(observation: dict) -> dict:
    """La forza della prova su cui quella domanda si regge, adesso."""
    return {name: observation.get(name) for name in _EVIDENCE}


def to_handle(observations, decided: dict) -> list[dict]:
    """Le osservazioni su cui l'attuatore deve lavorare in questo giro.

    `decided` e' `{impronta: prova}` per cio' che il proprietario ha gia'
    deciso: si salta una domanda **solo** se la sua prova e' rimasta la stessa.
    """
    seen = []
    for observation in observations or []:
        key = observation_key(observation)
        if key in decided and decided[key] == evidence_of(observation):
            continue
        seen.append(observation)
    return seen


def broken_recipes(observations) -> list[dict]:
    """Le osservazioni che dicono «questa misura non si calcola piu'».

    **E' il gesto che nessun altro fara' mai**: `devices_to_ask` salta i
    dispositivi che una ricetta ce l'hanno gia', quindi una ricetta che esiste
    ma non si esegue piu' non viene riscritta da nessuno -- ed e' esattamente
    cio' di cui l'analista si lamenta da due giorni. La stessa forma che questo
    prodotto ha gia' pagato tre volte: *la porta salta chi ha gia' una
    risposta, anche quando la risposta e' rotta*.

    Si riconoscono dall'**innesco** e dalla base vuota, non dalla prosa: il
    modello scrive la stessa cosa in dieci modi diversi, e un elenco di frasi
    da cercare sarebbe rotto al primo undicesimo.
    """
    return [o for o in observations or []
            if o.get("innesco") == _MISSING_TRIGGER and not o.get("base")]
