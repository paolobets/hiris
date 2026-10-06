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

#: L'impronta e la prova di un'osservazione vivono dove le osservazioni
#: nascono, nell'analista (piano degli attori, Task 3.4, 06/10/2026): una casa
#: sola per l'impronta (fondamenta 2).
from .analyst import evidence_of, observation_key


def to_handle(observations, decided: dict) -> list[dict]:
    """Le osservazioni su cui l'attuatore deve lavorare in questo giro.

    `decided` e' `{impronta: prova}` per cio' che il proprietario ha gia'
    deciso: si salta una domanda **solo** se la sua prova e' rimasta la stessa.
    In produzione `server.py` la chiama con un dizionario vuoto, quindi non
    salta niente: le domande gia' decise le salta `_file_proposals`.
    """
    seen = []
    for observation in observations or []:
        key = observation_key(observation)
        if key in decided and decided[key] == evidence_of(observation):
            continue
        seen.append(observation)
    return seen
