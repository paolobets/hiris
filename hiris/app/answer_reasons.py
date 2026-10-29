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

# -- le parole del ripiego dal ponte alla catena -------------------------------
#
# Sono le chiavi di `model_resolution._DOWNGRADE_REASONS`, e vivono QUI perche'
# chi le scrive (`steering`, `api/handlers_chat`) e chi le legge
# (`model_resolution`) non possono importarsi a vicenda: `steering` passa da
# `claude_runner`, che importa `model_resolution`. Fino al giro 222 del
# revisore erano ricopiate nei due posti, e una parola cambiata da una parte
# avrebbe spento la nota del ripiego senza errori. La terza, «manca il token»,
# nasce con il provider: `providers.SUBSCRIPTION.missing_reason`.

#: Il ponte c'era e non ha risposto entro il tempo concesso.
DEADLINE_REASON = "scadenza"

#: Il ponte ha gia' risposto oggi tutti i turni che il suo tetto gli concede.
DAILY_CAP_REASON = "tetto giornaliero"
