"""Il vocabolario di `forza` esiste in due linguaggi: qui si tengono legati.

Non si possono fondere -- il frontend non importa Python -- ma si possono
legare con una prova che si rompe. E' lo stesso schema gia' applicato a
`FIXED_ORDER` e ai tre preset in `test_models_frontend_wiring.py`; a `forza`
non era mai stato applicato, e quella e' la differenza fra una tendina
incompleta e la perdita di un dato:

`selForza.value = <valore che la pagina non conosce>` ricade in silenzio su
'', il confronto successivo vede una modifica che l'utente non ha fatto, e la
PATCH manda `forza: null`. Chi correggeva «Detto da» si vedeva cancellare la
forza del ricordo. La memoria e' l'unico archivio di HIRIS che non si
ricostruisce da nessuna parte: quel dato non torna.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def _js() -> str:
    return (BASE / "config" / "memoria-route.js").read_text(encoding="utf-8")


def test_ogni_forza_del_vocabolario_ha_un_etichetta_nella_pagina():
    from hiris.app.memoria.interpretazione import VOCABULARY
    js = _js()
    inizio = js.index("var FORZA_LABELS")
    blocco = js[inizio:js.index("};", inizio)]
    mancanti = sorted(f for f in VOCABULARY["forza"] if f + ":" not in blocco)
    assert mancanti == [], f"forze senza etichetta in memoria-route.js: {mancanti}"


def test_ogni_forza_del_vocabolario_e_scegliibile_nella_pagina():
    from hiris.app.memoria.interpretazione import VOCABULARY
    js = _js()
    inizio = js.index("var FORZA_OPZIONI")
    blocco = js[inizio:js.index("];", inizio)]
    mancanti = sorted(f for f in VOCABULARY["forza"] if "'" + f + "'" not in blocco)
    assert mancanti == [], f"forze non scegliibili in memoria-route.js: {mancanti}"


def test_la_pagina_non_offre_forze_che_il_vocabolario_non_ammette():
    """Il contrario, e serve quanto le altre due: un'opzione che il cancello
    di `valida()` rifiuterebbe e' una scelta offerta all'utente che non puo'
    andare a buon fine."""
    import re

    from hiris.app.memoria.interpretazione import VOCABULARY
    js = _js()
    inizio = js.index("var FORZA_OPZIONI")
    blocco = js[inizio:js.index("];", inizio)]
    offerte = {v for v in re.findall(r"\['([a-z_]*)'", blocco) if v}
    assert offerte <= VOCABULARY["forza"], (
        f"la pagina offre forze fuori vocabolario: {sorted(offerte - VOCABULARY['forza'])}")


def test_una_forza_sconosciuta_non_si_perde_in_silenzio():
    """La rete di sicurezza NEL FRATTEMPO: anche se le due liste divergessero,
    la pagina deve mostrare il valore che c'e' invece di azzerarlo."""
    js = _js()
    assert "FORZA_OPZIONI.some(" in js, (
        "manca il ramo che aggiunge alla tendina una forza non prevista")
