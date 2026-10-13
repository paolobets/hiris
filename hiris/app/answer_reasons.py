"""Le frasi con cui HIRIS dice perche' un turno non ha una risposta da leggere.

**Foglia** (N152-2, giro 152 del revisore, Chiusura): non importa niente del
prodotto. `NO_ANSWER_REASON` nasceva in `steering.py`, e `keeper/promise.py`
la importava da li' per comporre il motivo di una promessa: l'archivio delle
promesse si portava dietro `steering`, e con lui `claude_runner` e la coda del
ponte -- uno strato che puntava in su, per una stringa sola.
"""
from __future__ import annotations

#: Una risposta vuota non e' un silenzio: e' un modello che non ha risposto.
NO_ANSWER_REASON = "il modello non ha risposto"
