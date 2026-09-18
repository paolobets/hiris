"""La rotta dei giudizi e la lettura per la pagina (spec 2026-09-16 §4, §7).

Stile delle prove della rotta dell'obiettivo (`tests/test_mind_api.py`): il
gestore si chiama direttamente con una richiesta finta; la registrazione sul
router si prova a parte, leggendo il sorgente."""
import json
import pathlib

import pytest
import pytest_asyncio

from hiris.app import server
from hiris.app.api.handlers_mind import handle_knowledge, handle_set_judgment
from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.type_census import OPEN_QUESTIONS
from hiris.app.mind.judgments import JUDGMENT_AUTHOR, build_judgments
from hiris.app.mind.knowledge import Fact, KnowledgeStore
from hiris.app.mind.seed import REPO_PRIORITY, SEED_AUTHOR, judgment_seed

_ILLEGGIBILE = object()


def _richiesta(app, corpo=None):
    class _R:
        def __init__(self):
            self.app = app
            self.query = {}

        async def json(self):
            if corpo is _ILLEGGIBILE:
                raise ValueError("corpo non leggibile")
            return corpo
    return _R()


def _app_seminata(tmp_path):
    s = KnowledgeStore(str(tmp_path / "sapere.db"))
    s.seed(judgment_seed(when_ts=1.0), priority=REPO_PRIORITY)
    j, stato = build_judgments(s)
    return s, {"knowledge": s, "type_judgments": j, "type_judgments_status": stato}


@pytest.mark.asyncio
async def test_scrivere_giudizio_200_impronta_nuova(tmp_path):
    """Mutazione: il gestore torna 200 con l'impronta di prima senza chiamare
    `write_judgment` -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        prima = app["type_judgments_status"]["impronta"]
        r = await handle_set_judgment(_richiesta(app, {
            "soggetto_genere": "tipo", "soggetto": "binary_sensor.occupancy",
            "campo": "genere", "valore": "presenza"}))
        assert r.status == 200
        corpo = json.loads(r.text)
        assert corpo["impronta"] != prima
        assert corpo["impronta"] == app["type_judgments_status"]["impronta"]
        assert corpo["provenienza_istantanea"] == "sapere"
        assert corpo["riga"]["valore"] == "presenza"
        assert corpo["riga"]["chi"] == JUDGMENT_AUTHOR
    finally:
        s.close()


@pytest.mark.asyncio
async def test_valore_null_torna_seme(tmp_path):
    """Mutazioni: leggere `valore` con `str(...)` (None diventa «None») -- rossa;
    il gestore risponde 200 senza scrivere -- rossa (la prima scrittura deve
    cambiare l'istantanea, altrimenti il ritorno al seme non prova niente)."""
    s, app = _app_seminata(tmp_path)
    try:
        attese = {"sicurezza": False, None: True}
        for valore, seminata in attese.items():
            r = await handle_set_judgment(_richiesta(app, {
                "soggetto_genere": "tipo", "soggetto": "light",
                "campo": "genere", "valore": valore}))
            assert r.status == 200, r.text
            assert (app["type_judgments"].rows() == tv.REPO_JUDGMENTS.rows()) is seminata
    finally:
        s.close()


@pytest.mark.asyncio
async def test_fatto_ha_400_errore(tmp_path):
    """Mutazione: lasciar propagare `JudgmentRefused` -- eccezione, non 400."""
    s, app = _app_seminata(tmp_path)
    try:
        r = await handle_set_judgment(_richiesta(app, {
            "soggetto_genere": "tipo", "soggetto": "climate",
            "campo": "capability_names", "valore": "{}"}))
        assert r.status == 400
        assert "capability_names" in json.loads(r.text)["errore"]
    finally:
        s.close()


@pytest.mark.asyncio
async def test_corpo_storto_400_non_500(tmp_path):
    """Un `valore` MANCANTE non e' `null`: tornare al seme per un campo
    dimenticato cancellerebbe una correzione. Mutazione: `body.get("valore")`
    -- rossa sull'ultimo corpo."""
    s, app = _app_seminata(tmp_path)
    try:
        conto = s.count()
        for corpo in (_ILLEGGIBILE, [], {},
                      {"soggetto_genere": "tipo", "soggetto": 3, "campo": "genere",
                       "valore": "presenza"},
                      {"soggetto_genere": "tipo", "soggetto": "light", "campo": "genere",
                       "valore": 7},
                      {"soggetto_genere": "tipo", "soggetto": "light", "campo": "genere"}):
            r = await handle_set_judgment(_richiesta(app, corpo))
            assert r.status == 400, corpo
            assert json.loads(r.text)["errore"]
        assert s.count() == conto
    finally:
        s.close()


@pytest.mark.asyncio
async def test_senza_sapere_503():
    """Mutazione: togliere la guardia -- 400 dal rifiuto della porta, non 503."""
    r = await handle_set_judgment(_richiesta({}, {
        "soggetto_genere": "tipo", "soggetto": "light", "campo": "genere",
        "valore": "sicurezza"}))
    assert r.status == 503


@pytest.mark.asyncio
async def test_scrittura_non_in_vigore_409(tmp_path):
    """La riga e' scritta ma l'istantanea e' tornata al solo seme per un'altra
    riga storta: non e' un 200. Mutazione: rispondere 200 -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="light", field="genere",
                     value="acceso", provenance="nostro", who="a mano", when_ts=2.0))
        r = await handle_set_judgment(_richiesta(app, {
            "soggetto_genere": "tipo", "soggetto": "binary_sensor.occupancy",
            "campo": "genere", "valore": "presenza"}))
        assert r.status == 409
        corpo = json.loads(r.text)
        assert "solo seme" in corpo["errore"]
        assert corpo["provenienza_istantanea"] == "solo seme"
        assert corpo["riga"]["valore"] == "presenza"
    finally:
        s.close()


def test_rotta_REGISTRATA():
    """Mutazione: togliere la registrazione da `server.py` -- rossa."""
    sorgente = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    assert 'add_post("/api/mind/judgment", handle_set_judgment)' in sorgente


# -- la lettura per la pagina (spec §7, §11) ------------------------------------

@pytest.mark.asyncio
async def test_sapere_porta_giudizi_ORIGINE_quando(tmp_path):
    """Mutazioni: `da` sempre «seme» -- rossa; togliere `quando_ts` -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="binary_sensor.occupancy",
                     field="genere", value="presenza", provenance="nostro",
                     who=JUDGMENT_AUTHOR, when_ts=5.0))
        r = await handle_knowledge(_richiesta(app))
        assert r.status == 200
        giudizi = json.loads(r.text)["giudizi"]
        assert len(giudizi) == len(tv.judgment_seed_rows()) + 1
        per_chiave = {(g["soggetto_genere"], g["soggetto"], g["campo"]): g for g in giudizi}
        assert per_chiave[("tipo", "binary_sensor.occupancy", "genere")] == {
            "soggetto_genere": "tipo", "soggetto": "binary_sensor.occupancy",
            "campo": "genere", "valore": "presenza", "da": "proprietario",
            "chi": JUDGMENT_AUTHOR, "quando_ts": 5.0}
        persona = per_chiave[("tipo", "person", "genere")]
        assert (persona["da"], persona["valore"], persona["quando_ts"]) == ("seme", "presenza", 1.0)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_riga_seme_TOCCATA_mano_NON_dice_seme(tmp_path):
    """L'archivio si corregge a mano con un `UPDATE` che non cambia `who`
    (`knowledge.py`, schema): una riga con l'autore del seme e un valore che
    il seme non ha scritto non e' «del seme». Mutazione: `da` letto dal solo
    `who` -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="light", field="genere",
                     value="nessuno", provenance="nostro", who=SEED_AUTHOR, when_ts=6.0))
        r = await handle_knowledge(_richiesta(app))
        giudizi = json.loads(r.text)["giudizi"]
        luce = next(g for g in giudizi if (g["soggetto"], g["campo"]) == ("light", "genere"))
        assert luce["da"] == "altro"
    finally:
        s.close()


@pytest.mark.asyncio
async def test_sapere_porta_domande_aperte(tmp_path):
    """Mutazione: togliere `domande_aperte` -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        corpo = json.loads((await handle_knowledge(_richiesta(app))).text)
        domande = corpo["domande_aperte"]
        assert len(domande) == len(OPEN_QUESTIONS) == 6
        assert sum(len(d["chiavi"]) for d in domande) == 115
        assert domande[0]["chiavi"] == ["lock=jammed"]
        assert domande[0]["domanda"] == OPEN_QUESTIONS[0].question
        assert {"conteggi", "non_capito"} <= set(corpo)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_archivio_che_SOLLEVA_scrivendo_e_503_non_500(tmp_path):
    """Giro di correzioni 1, punto 8 (MEDIO): l'archivio che c'e' ma non
    scrive.

    Il 503 di `test_senza_sapere_503` copre il sapere **assente**. Un archivio
    aperto che solleva mentre scrive -- disco pieno, `database is locked` oltre
    il `busy_timeout` -- usciva grezzo dalla porta fino ad aiohttp, che ne
    faceva un 500 con un corpo HTML: la pagina cadeva nel ramo generico («Non
    e' stato possibile scrivere») senza distinguere «riprova» da «e' rotto
    qualcosa nel programma».

    Le due cose sono la stessa per chi guarda -- il sapere adesso non si puo'
    usare -- e hanno lo stesso rimedio: riprovare. Stesso 503.

    Rossa prima della correzione: `sqlite3.OperationalError: disco pieno`
    propagata dal gestore invece di una risposta.
    """
    import sqlite3

    s, app = _app_seminata(tmp_path)
    try:
        def _rotto(_fact):
            raise sqlite3.OperationalError("disco pieno")

        s.write = _rotto
        r = await handle_set_judgment(_richiesta(app, {
            "soggetto_genere": "tipo", "soggetto": "binary_sensor.occupancy",
            "campo": "genere", "valore": "presenza"}))
        assert r.status == 503
        assert "disco pieno" in json.loads(r.text)["errore"]
    finally:
        s.close()


# -- la rotta sta dietro ai middleware come le sorelle (spec §4) ---------------
#
# Giro di correzioni 1, punto 8 (BASSO): finora c'era solo `test_rotta_REGISTRATA`,
# che e' lessicale -- cerca una stringa nel sorgente. Non dice niente su QUALE
# app la porti, e una rotta registrata su un'app senza i due middleware
# resterebbe verde. Stesso trattamento delle sorelle: `test_settings_api.py` e
# `test_agenda_api.py`, da cui si riusa la fixture `csrf_stretto` invece di
# scriverne una seconda identica.

from tests.test_settings_api import csrf_stretto  # noqa: F401


@pytest_asyncio.fixture
async def client_vero(aiohttp_client):
    """L'app VERA (`create_app`), non due rotte montate a mano: una prova che
    scavalcasse i middleware non direbbe niente su cio' che accade in
    produzione."""
    app = server.create_app()
    app.on_startup.clear()
    app.on_cleanup.clear()
    return await aiohttp_client(app)


@pytest.mark.asyncio
async def test_POST_giudizio_senza_x_requested_with_e_403(client_vero, csrf_stretto):
    """**E' una scrittura**: passa dallo stesso `csrf_middleware` di ogni altra
    `/api/`. Un sito ostile non deve poter correggere il giudizio della casa
    con una POST cross-site.

    Mutazione ESEGUITA: registrare la rotta su un'app senza middleware --
    rossa. Qui la si esegue nella forma economica: `HIRIS_ALLOW_NO_CSRF=1`
    (quello che `conftest.py` mette per tutta la suite) rimesso al posto della
    fixture -- la risposta torna 200/400 invece di 403.
    """
    resp = await client_vero.post("/api/mind/judgment", json={
        "soggetto_genere": "tipo", "soggetto": "light", "campo": "genere",
        "valore": "sicurezza"})
    assert resp.status == 403
    assert (await resp.json())["error"] == "csrf_required"


@pytest.mark.asyncio
async def test_POST_giudizio_senza_token_e_401(client_vero, monkeypatch):
    """E dallo stesso `internal_auth_middleware`: senza `internal_token` e
    senza la valvola di sviluppo la richiesta e' un 401, come per ogni altra
    rotta dell'API. `internal_auth_middleware` gira PRIMA del csrf, quindi qui
    non serve `csrf_stretto`."""
    monkeypatch.setenv("HIRIS_ALLOW_NO_TOKEN", "")
    resp = await client_vero.post("/api/mind/judgment", json={
        "soggetto_genere": "tipo", "soggetto": "light", "campo": "genere",
        "valore": "sicurezza"}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resp.status == 401
    assert (await resp.json())["error"] == "unauthorized"
