"""La forma dell'esito di una scrittura su Home Assistant: UNA, per le due
porte (E-04, decisione D2a della Tappa 7, 07/10/2026).

Fino a quel giorno la porta dei servizi (`actuator.py`) rispondeva
`{"eseguito", "errore"}` e l'officina (`construction/workshop.py`)
`{"applicata": True}` oppure `{"errore", "esecuzione_id", "guasto_rete"}`: chi
leggeva le due porte -- la chat, la pagina, le promesse -- doveva sapere da
quale delle due arrivava un esito per sapere come leggerlo, e il motivo di
Home Assistant, sull'officina, poteva essere SOSTITUITO da una frase di
HIRIS (`workshop._translate_rejection`) e non c'era piu'.

La forma:

- `eseguito`: vero o falso, **sempre presente**. Falso vuol dire «la
  scrittura non risulta fatta»: con `causa` di tipo silenzio vuol dire «non
  so se e' arrivata» (la frase in `errore` lo dice);
- sul rifiuto, `errore`: la frase di HIRIS, per chi legge;
- sul rifiuto, `causa`: **la busta del client** (`proxy/ha_client._failure`)
  cosi' com'e' arrivata -- `{"errore": il motivo di Home Assistant INTATTO,
  "causa": silenzio | rifiuto | forma | richiesta, "codice": il codice di
  Home Assistant o lo stato HTTP}`. Non si inventa una seconda busta: si
  estende quella che il client ha gia'. Un rifiuto deciso da HIRIS prima
  della rete (la verifica, il freno di ritmo, il cancello del turno) ha la
  causa `richiesta`, che e' esattamente cio' che la busta dice di una
  domanda fermata prima di partire;
- sul successo, ogni porta aggiunge i suoi campi (lo stato prima e dopo per
  i servizi, le entita' nate per la configurazione).

**Cosa resta diverso fra le due porte, e perche'** (E-05, decisione D14a
della Tappa 7, 07/10/2026). Solo i servizi controllano il registro fresco
dei servizi, lo specchio leggibile, `verification`, la risoluzione del
bersaglio e il freno di ritmo; solo la configurazione controlla la forma
dell'intento, il consiglio, `validate_config`, la chiave libera, il cancello
del turno, la rivendicazione (`claim`), la rilettura prima di scrivere
(S-17) e il livello. Non e' un doppione mancato: sono canali diversi. Un
servizio non sovrascrive il lavoro di nessuno e si ripete in un attimo --
il ritmo lo frena; una configurazione sovrascrive il lavoro di una persona
e resta -- si rilegge, si rivendica, si chiede il si'. Si unisce solo cio'
che CLAUDE.md («Un canale, una porta») dice comune: la cronaca, l'origine e
la forma di questo esito.
"""
from __future__ import annotations

from ..proxy.ha_client import REQUEST, SILENCE, _failure


def refused(text: str, cause: dict | None = None) -> dict:
    """L'esito di una scrittura che non risulta fatta: L'UNICO costruttore.

    `cause` e' la busta del client da cui il rifiuto nasce, intatta. Senza,
    il rifiuto e' di HIRIS, deciso prima della rete: la causa e' una
    `richiesta` col motivo stesso."""
    return {"eseguito": False, "errore": text,
            "causa": cause if cause is not None else _failure(REQUEST, text)}


def silent(occurrence: dict) -> bool:
    """Vero se l'esito -- o la busta del client da cui nasce -- e' un
    silenzio del trasporto: la domanda puo' essere arrivata. Si legge la
    causa, non il testo."""
    cause = occurrence.get("causa")
    if isinstance(cause, dict):
        cause = cause.get("causa")
    return cause == SILENCE
