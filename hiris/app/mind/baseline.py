"""Cosa l'osservatore guarda comunque, qualunque cosa dica l'obiettivo.

**Il pavimento non e' una lista scritta a mano.** Si deriva da cio' che Home
Assistant dichiara gia' su ogni entita' -- dominio, classe del dispositivo
(`device_class`), `source_type` -- perche' una lista a mano invecchia col
primo dispositivo nuovo e nessuno se ne accorge. **Non `state_class`**
(correzione di parole della review, mandato «il bilancio dell'energia»,
punto 7, 27/08/2026): dopo la correzione del 27/08, questa funzione non la
legge piu' per decidere nessuna gamba -- resta grezzo conservato
nell'archivio (`mind/store.py`), non un criterio del pavimento.

**Perche' esiste un pavimento.** Il prompt dell'obiettivo decide cosa entra
nelle osservazioni, quindi e' un punto singolo che puo' ACCECARE l'osservatore
-- e cio' che non e' stato osservato non esiste piu': riscrivere il prompt fra
tre mesi non fa ricomparire i tre mesi mancanti. Il pavimento e' cio' che il
prompt non puo' togliere. Sopra di esso allarga; sotto, mai.

**Dove vive il giudizio, dal 07/09/2026.** Non piu' qui. Le otto costanti che
raggruppavano le classi di Home Assistant per gamba -- `_PRESENZA`,
`_APERTURA`, `_COMFORT`, `_QUALITA_ARIA`, `_ENERGIA`, `_DOMINI_SICUREZZA`,
`_SICUREZZA_BINARIA`, `_SICUREZZA_SENSORE` -- e i sette rami di dominio che le
leggevano sono diventati righe del **vocabolario dei tipi**
(`home_space/type_vocabulary.py`), interrogate con la metrica «gamba». Questo
modulo resta il LETTORE: la domanda («questa entita' serve all'obiettivo?») e'
sua, la risposta viene dall'unica casa che tiene cio' che sappiamo di un tipo.
Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md`.
"""
from __future__ import annotations

from ..home_space.type_vocabulary import ASPECTS, aspect_of

# Ri-esportata, non ricopiata: le sei gambe sono il vocabolario dei VALORI che
# `aspect` restituisce, e vivono con le righe che li assegnano. Chi importava
# `baseline.ASPECTS` continua a trovarla qui -- e' un collegamento per
# identificatore, esattamente cio' che la seconda fondamenta chiede.
__all__ = ["ASPECTS", "aspect", "in_baseline"]


def aspect(entity_id: str, attributes: dict | None) -> str | None:
    """A quale gamba dell'obiettivo serve questa entita', o `None`.

    L'obiettivo e' «ottimizzare la casa e renderla confortevole», e ha tre
    gambe -- efficiente, confortevole, in buono stato -- che qui diventano
    sei domande: chi c'e', che aria si respira, cosa disperde, quanta
    energia si muove, cosa si sta rompendo, cosa minaccia la sicurezza.

    **La funzione resta, il giudizio no.** Ogni ramo che questa funzione
    conteneva -- `person`, i tre domini della sicurezza, il `device_tracker`
    coi suoi `gps`, `climate`, `cover`, e le coppie di `binary_sensor` e
    `sensor` -- e' ora una riga del vocabolario dei tipi, con la propria
    provenienza dichiarata (`nostro`: nessuna API di Home Assistant sa dire a
    quale gamba di quale obiettivo un tipo serve). Qui resta la domanda, e la
    firma che i suoi chiamanti gia' conoscono.
    """
    return aspect_of(entity_id, attributes)


def in_baseline(entity_id: str, attributes: dict | None) -> bool:
    """Se questa entita' si osserva comunque. Derivata da `aspect`, mai
    riscritta: due risposte alla stessa domanda divergono, e la prima a
    divergere e' quella che nessuno guarda."""
    return aspect(entity_id, attributes) is not None
