"""Gli indirizzi del frontend e del suo finto contro le rotte vere (T-12, 14/10/2026).

Due confronti che nessuna prova faceva:

1. **Il finto `fetch` delle prove JS contro il server.** Dal 14/10/2026 il finto
   (`tests/js/helpers/fetch.mjs`) fa fallire la prova che chiede un indirizzo
   che non conosce (T-03). Ma le rotte che conosce le scrive la prova: una
   rotta del finto che il server non registra fa passare la prova su una
   pagina che in produzione riceverebbe un 404. Le rotte del finto devono
   essere rotte vere.
2. **Le pagine contro il server.** Gli indirizzi `api/...` che i sorgenti di
   `static/` scrivono devono essere rotte registrate. `scripts/censimento.py`
   guarda l'altra direzione (una rotta che nessuno chiama).

**Le rotte si chiedono al router** di `create_app()` (I-0), non si
ricopiano. Un indirizzo combacia con una rotta se e' il suo percorso, se ne
riempie i segmenti `{parametro}`, o se ne e' l'inizio fino a una `/` (la
pagina compone `'api/executions/' + id`, il finto serve `'api/proposals'` per
`api/proposals/<id>/<verbo>`). Una chiave del finto col metodo
(`'POST api/chat'`) deve combaciare con una rotta di quel metodo.

**Cosa non vede, dichiarato.** Solo i letterali fra apici che cominciano con
`api/`: un indirizzo montato da pezzi che non cominciano cosi' resta fuori.
Nei sorgenti delle pagine i commenti non contano (raccontano rotte uscite).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from hiris.app.server import create_app

RADICE = Path(__file__).resolve().parents[1]
PROVE_JS = RADICE / "tests" / "js"
STATIC = RADICE / "hiris" / "app" / "static"

_CHIAVE_FINTO = re.compile(r"['\"](?:(GET|POST|PUT|PATCH|DELETE) )?(api/[^'\"?\s]*)['\"]\s*:")
_INDIRIZZO = re.compile(r"['\"`](api/[A-Za-z0-9_\-/]*)")
_COMMENTO_JS = re.compile(r"/\*.*?\*/|(?<![:\\'\"])//[^\n]*", re.DOTALL)

#: Ammissioni: i file di prova che provano un MECCANISMO di rete, non una
#: pagina, e per questo servono indirizzi inventati. Chiude per difetto.
_SINTETICI = {
    "fetch-finto.test.mjs": "le prove del finto stesso: le sue regole sugli "
                            "indirizzi si provano su indirizzi inventati",
    "common.test.mjs": "`api()` di common.js si prova su `api/x` e `api/y`: "
                       "la funzione non sa niente delle rotte",
}


@pytest.fixture(scope="module")
def rotte() -> list[tuple[str, str]]:
    app = create_app()
    return [(r.method, r.resource.canonical) for r in app.router.routes()
            if r.resource is not None]


def _combacia(indirizzo: str, canonico: str) -> bool:
    percorso = "/" + indirizzo.rstrip("/")
    if canonico == percorso or canonico.startswith(percorso + "/"):
        return True
    schema = "^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(canonico)) + "$"
    return re.match(schema, percorso) is not None


def _conosciuto(rotte, metodo: str | None, indirizzo: str) -> bool:
    return any(_combacia(indirizzo, canonico)
               and (metodo is None or m == metodo or (metodo == "GET" and m == "HEAD"))
               for m, canonico in rotte)


def chiavi_finto() -> list[tuple[str, str | None, str]]:
    """`(file:riga, metodo, indirizzo)` di ogni rotta scritta per il finto."""
    trovate = []
    for file in sorted(PROVE_JS.glob("*.test.mjs")):
        if file.name in _SINTETICI:
            continue
        for n, riga in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            for metodo, indirizzo in _CHIAVE_FINTO.findall(riga):
                trovate.append((f"{file.name}:{n}", metodo or None, indirizzo))
    return trovate


def indirizzi_pagine() -> list[tuple[str, str]]:
    trovati = []
    for file in sorted(STATIC.rglob("*.js")):
        sorgente = _COMMENTO_JS.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                                    file.read_text(encoding="utf-8"))
        for n, riga in enumerate(sorgente.splitlines(), 1):
            for indirizzo in _INDIRIZZO.findall(riga):
                trovati.append((f"{file.relative_to(STATIC)}:{n}", indirizzo))
    return trovati


def test_le_derivazioni_trovano_davvero_qualcosa(rotte):
    """Un insieme improvvisamente piccolo e' un cancello che non guarda piu'
    niente. Mutazione ESEGUITA (14/10/2026): `_CHIAVE_FINTO` che cerca
    `apix/` -- rossa qui."""
    assert len(rotte) >= 30, len(rotte)
    assert len(chiavi_finto()) >= 30, len(chiavi_finto())
    assert len(indirizzi_pagine()) >= 15, len(indirizzi_pagine())


def test_il_finto_fetch_serve_solo_rotte_vere(rotte):
    """Mutazione ESEGUITA (14/10/2026): una rotta `'api/memorie'` in
    `memory-route-struttura.test.mjs` -- rossa, col file e la riga; una
    `'PATCH api/chat-settings'` (la rotta c'e', il metodo no) -- rossa."""
    false = [f"{dove}: {metodo + ' ' if metodo else ''}{indirizzo}"
             for dove, metodo, indirizzo in chiavi_finto()
             if not _conosciuto(rotte, metodo, indirizzo)]
    assert false == [], ("rotte del finto fetch che il server non registra:\n"
                         + "\n".join(false))


def test_le_pagine_chiedono_solo_rotte_vere(rotte):
    """Mutazione ESEGUITA (14/10/2026): `'api/memorie'` scritto in
    `config/memory-route.js` -- rossa."""
    false = [f"{dove}: {indirizzo}" for dove, indirizzo in indirizzi_pagine()
             if not _conosciuto(rotte, None, indirizzo)]
    assert false == [], ("indirizzi del frontend che il server non registra:\n"
                         + "\n".join(false))


def test_la_regola_del_combaciare():
    assert _combacia("api/chat", "/api/chat")
    assert _combacia("api/executions/", "/api/executions/{run_id}")
    assert _combacia("api/proposals", "/api/proposals/{pid}/done")
    assert _combacia("api/chat/reply/job-1", "/api/chat/reply/{job_id}")
    assert not _combacia("api/chat", "/api/chat-settings")
    assert not _combacia("api/chat/reply/job-1/altro", "/api/chat")


def test_le_ammissioni_nominano_file_che_esistono():
    for nome in _SINTETICI:
        assert (PROVE_JS / nome).exists(), f"{nome} non c'e' piu': l'ammissione esce"
