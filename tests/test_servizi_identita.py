"""I servizi firmati: chi sono, e dove arrivano (Tappa 7, Task 8; D7).

- **S-16**: l'`id` di un servizio firmato e' l'impronta della sua chiave, il
  nome un'etichetta. Due servizi omonimi hanno due fili; i fili di prima
  migrano all'avvio (`servizi.migrate_service_threads`).
- **S-21**: un servizio firmato non arriva a `/api/mcp`, che e' del ponte.
- **S-15 / F-10**: il valore di fabbrica delle reti fidate ha una casa sola.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest
import pytest_asyncio

from conftest import firma, servizio_approvato
from hiris.app import chat_store
from hiris.app.api import canali, ingresso
from hiris.app.api.servizi import (
    ServiziStore,
    migrate_service_threads,
    open_services,
    service_thread_renames,
)
from hiris.app.chat_store import close_all_stores
from hiris.app.chat_thread import ChatThread, subject_key_for, thread_for
from hiris.app.keeper.store import AgendaStore
from tests.test_admission import _compose

_HIRIS = Path(__file__).resolve().parents[1] / "hiris"


@pytest.fixture(autouse=True)
def _confine_vero(monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    yield
    close_all_stores()


def _riconosci(app, privata, pubblica) -> dict:
    """Il soggetto che `canali.riconosci` attacca a una richiesta firmata da
    questa chiave -- la stessa funzione del confine, col contratto vero."""
    testata = firma(privata, pubblica, "GET", "/api/health")
    soggetto, rifiuto = canali.riconosci(
        chiave=pubblica, momento=testata["X-HIRIS-Momento"],
        unico=testata["X-HIRIS-Unico"], firma=testata["X-HIRIS-Firma"],
        metodo="GET", percorso="/api/health", corpo=b"", servizi=app["servizi"],
        visti={}, adesso=time.time())
    assert rifiuto is None, rifiuto
    return soggetto


def test_due_servizi_OMONIMI_hanno_due_fili(tmp_path):
    """S-16. Fino al 07/10/2026 l'id del soggetto era il nome: due servizi
    approvati con lo stesso nome scrivevano nella stessa chat.

    Rossa sul codice di prima (verificato il 07/10/2026: l'`ident=nome` in
    `canali.riconosci` -- `luogo:retropanel` per entrambi). Mutazione ESEGUITA
    (07/10/2026): `ident=autorizzato["nome"]` -- rossa sull'uguaglianza delle
    due chiavi."""
    app = {"servizi": ServiziStore(str(tmp_path / "servizi.db"))}
    primo = servizio_approvato(app, "utente", nome="retropanel")
    secondo = servizio_approvato(app, "utente", nome="retropanel")

    uno, due = _riconosci(app, *primo), _riconosci(app, *secondo)

    assert uno["nome"] == due["nome"] == "retropanel"
    assert uno["id"] == ServiziStore.fingerprint(primo[1])
    assert subject_key_for(uno) != subject_key_for(due)
    assert thread_for(uno, "canale") != thread_for(due, "canale")
    app["servizi"].close()


def _sessione(data_dir: str, chiave: str, testo: str) -> None:
    chat_store.append_messages([{"role": "user", "content": testo}], data_dir,
                               thread=ChatThread(chiave, "canale"))


def _testi(data_dir: str, chiave: str) -> list[str]:
    return [m["content"] for m in chat_store.load_history(
        data_dir, thread=ChatThread(chiave, "canale"))]


def test_la_migrazione_porta_i_fili_dal_nome_all_IMPRONTA(tmp_path, caplog):
    """Un archivio di prova coi fili com'erano: chiave `specie:nome`. Dopo la
    migrazione la conversazione sta sotto `specie:impronta`, che e' la chiave
    che il confine calcola adesso per lo stesso servizio; il registro dice
    quante sessioni sono passate. Un nome portato da due servizi non si
    separa: resta dov'era, e il registro lo nomina. La seconda volta non
    trova niente.

    Mutazione ESEGUITA (07/10/2026): `rekey_subjects` che non scrive (il
    corpo dell'`UPDATE` con `WHERE 0`) -- rossa (`0 == 1`)."""
    data_dir = str(tmp_path)
    app = {"servizi": ServiziStore(str(tmp_path / "servizi.db")), "data_dir": data_dir}
    privata, pubblica = servizio_approvato(app, "utente", nome="cucina", specie="luogo")
    servizio_approvato(app, "utente", nome="gemello", specie="integrazione")
    servizio_approvato(app, "utente", nome="gemello", specie="integrazione")
    _sessione(data_dir, "luogo:cucina", "accendi la luce")
    _sessione(data_dir, "integrazione:gemello", "di chi sono")
    _sessione(data_dir, "persona:u-paolo", "ciao")

    with caplog.at_level(logging.INFO, logger="hiris.app.api.servizi"):
        moved = migrate_service_threads(app)

    nuova = subject_key_for(_riconosci(app, privata, pubblica))
    assert nuova == f"luogo:{ServiziStore.fingerprint(pubblica)}"
    assert moved == {"sessioni di chat": 1}
    assert _testi(data_dir, nuova) == ["accendi la luce"]
    assert _testi(data_dir, "luogo:cucina") == []
    assert _testi(data_dir, "integrazione:gemello") == ["di chi sono"]
    assert _testi(data_dir, "persona:u-paolo") == ["ciao"]
    righe = [r.getMessage() for r in caplog.records]
    assert any("1 sessioni di chat" in r for r in righe), righe
    assert any("integrazione:gemello" in r for r in righe), righe

    assert migrate_service_threads(app) == {"sessioni di chat": 0}
    app["servizi"].close()


T_NASCITA = 1_790_000_000.0  # un istante fisso, scelto a mano: non e' una misura


def _servizio_parlante(tmp_path) -> tuple[dict, str]:
    """Una casa con un servizio `luogo:cucina` approvato e gli archivi che la
    migrazione tocca; torna l'app e la chiave nuova del servizio."""
    app = {"servizi": ServiziStore(str(tmp_path / "servizi.db")),
           "data_dir": str(tmp_path),
           "agenda": AgendaStore(str(tmp_path / "promesse.db"))}
    privata, pubblica = servizio_approvato(app, "utente", nome="cucina", specie="luogo")
    return app, subject_key_for(_riconosci(app, privata, pubblica))


def _chiudi(app) -> None:
    for chiave in ("servizi", "agenda"):
        app[chiave].close()


def test_le_promesse_del_servizio_passano_all_IMPRONTA(tmp_path, caplog):
    """G83-3 (giro 83; Paolo, 07/10/2026: «Migra tutto»). Con la chiave
    vecchia il servizio non vedeva piu' le sue promesse in agenda, non le
    poteva disdire, e l'esito di un `fai` andava nel filo vecchio. Le
    promesse di un altro soggetto non si toccano; la seconda volta non c'e'
    niente.

    Mutazione ESEGUITA (07/10/2026): l'agenda tolta dagli archivi di
    `_service_thread_archives` -- rossa, la promessa resta sotto il nome."""
    app, nuova = _servizio_parlante(tmp_path)
    sua = app["agenda"].create(
        {"specie": "chiedi", "frase": "x", "quando_ts": T_NASCITA + 3600,
         "domanda": "?"}, thread=ChatThread("luogo:cucina", "canale"),
        now=T_NASCITA)["promessa"]["id"]
    altrui = app["agenda"].create(
        {"specie": "chiedi", "frase": "y", "quando_ts": T_NASCITA + 3600,
         "domanda": "?"}, thread=ChatThread("persona:u-paolo", "interno"),
        now=T_NASCITA)["promessa"]["id"]

    with caplog.at_level(logging.INFO, logger="hiris.app.api.servizi"):
        moved = migrate_service_threads(app)

    assert app["agenda"].read_in_thread(sua, ChatThread(nuova, "canale")) is not None
    assert moved["promesse"] == 1
    assert app["agenda"].read_in_thread(altrui, ChatThread("persona:u-paolo",
                                                           "interno")) is not None
    assert "1 promesse" in caplog.text
    assert migrate_service_threads(app)["promesse"] == 0
    _chiudi(app)


def test_l_avvio_apre_l_archivio_e_migra_nello_stesso_gesto(tmp_path):
    """L'avvio chiama `open_services` (la chiamata sta fuori da `server.py`,
    regola del 06/10/2026): apre l'archivio, lo mette in `app["servizi"]` e
    migra i fili. Mutazione ESEGUITA (07/10/2026): togliere
    `migrate_service_threads(app)` da `open_services` -- rossa, il filo resta
    sotto il nome."""
    data_dir = str(tmp_path)
    path = str(tmp_path / "servizi.db")
    prima = {"servizi": ServiziStore(path), "data_dir": data_dir}
    _privata, pubblica = servizio_approvato(prima, "utente", nome="cucina", specie="luogo")
    prima["servizi"].close()
    _sessione(data_dir, "luogo:cucina", "accendi la luce")

    app = {"data_dir": data_dir}
    store = open_services(app, path)

    assert app["servizi"] is store
    assert _testi(data_dir, f"luogo:{ServiziStore.fingerprint(pubblica)}") == [
        "accendi la luce"]
    store.close()


def test_la_tabella_dei_nomi_conta_autorizzati_e_revocati_e_basta():
    """Chi non e' mai stato approvato non ha mai parlato: niente da migrare."""
    righe = [
        {"stato": "autorizzato", "specie": "luogo", "nome": "a", "impronta": "f1"},
        {"stato": "revocato", "specie": None, "nome": "b", "impronta": "f2"},
        {"stato": "in_attesa", "specie": None, "nome": "c", "impronta": "f3"},
    ]
    renames, ambiguous = service_thread_renames(righe)
    assert renames == {"luogo:a": "luogo:f1", f"{canali.SPECIE_IGNOTA}:b":
                       f"{canali.SPECIE_IGNOTA}:f2"}
    assert ambiguous == []


@pytest_asyncio.fixture
async def casa(aiohttp_client, tmp_path):
    app = _compose(tmp_path)
    client = await aiohttp_client(app)
    yield client
    app["memory_store"].close()
    app["servizi"].close()


@pytest.mark.asyncio
async def test_un_servizio_firmato_NON_arriva_a_mcp(casa):
    """S-21. `/api/mcp` serve i turni del ponte (credenziale `turno`); un
    servizio firmato, anche amministratore e con la firma giusta, riceve 401
    e la rotta non apre il corpo. Il codice lo impediva gia': questa prova lo
    sorveglia.

    Mutazione ESEGUITA (07/10/2026): in `handle_mcp` il controllo
    `auth_via != "turno"` allargato a `not in ("turno", "canale")` -- rossa
    (200 invece di 401)."""
    privata, pubblica = servizio_approvato(casa.app, "amministratore")
    body = (b'{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": '
            b'{"name": "search", "arguments": {"nome": "cucina"}}}')
    headers = {**firma(privata, pubblica, "POST", "/api/mcp", body),
               "Content-Type": "application/json", "X-Requested-With": "hiris-mcp"}

    risposta = await casa.post("/api/mcp", data=body, headers=headers)

    assert risposta.status == 401, await risposta.text()


def test_il_valore_di_fabbrica_delle_reti_fidate_ha_UNA_casa():
    """S-15 / F-10. Fino al 07/10/2026 la rete di fabbrica era scritta in
    quattro posti: `api/ingresso.py`, il ripiego del middleware, il default di
    `run.sh` e le opzioni di `config.yaml`. I file si chiedono alla cartella
    dell'add-on, il valore a `ingresso`.

    Mutazione ESEGUITA (07/10/2026): rimesso `'172.30.32.0/23'` come default
    di `bashio::config` in `run.sh` -- rossa, e nomina il file."""
    testi = [f for f in _HIRIS.rglob("*")
             if f.is_file() and f.suffix in (".py", ".sh", ".yaml", ".yml", ".js",
                                             ".json", ".html")
             and "__pycache__" not in f.parts]
    assert len(testi) > 50, "la cartella dell'add-on non si e' letta"
    assert (_HIRIS / "run.sh") in testi and (_HIRIS / "config.yaml") in testi
    copie = sorted(str(f.relative_to(_HIRIS)) for f in testi
             if ingresso.RETE_PREDEFINITA in f.read_text(encoding="utf-8"))
    assert copie == ["app/api/ingresso.py"], copie
