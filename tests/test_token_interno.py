"""Il token interno c'e' anche con la configurazione predefinita.

**Il guasto che questi test chiudono.** `hiris/config.yaml` ha
`internal_token: ""` come default e le descrizioni dell'opzione promettevano
«Lascia vuoto per generarlo automaticamente» -- ma nessuno generava niente.
Con la configurazione predefinita, quindi: `run.sh` esportava
`INTERNAL_TOKEN=""`, `_on_startup` lo metteva in `app["internal_token"]`, e
`internal_auth_middleware` negava con 401 ogni richiesta non-ingress. L'unico
componente del prodotto che chiama la propria API in modo non-ingress e' il
worker del ponte della chat (`agent/runner.py::build_headers`): il suo `claim`
si prendeva 401 ogni ~3 secondi all'infinito, la CLI `claude` non veniva
invocata mai, e l'utente leggeva solo «La risposta non e' arrivata in tempo».

L'ultimo test di questo file e' **il guasto riprodotto e chiuso**: con
`INTERNAL_TOKEN=""` (il default), con il rifiuto-per-default **attivo**
(`HIRIS_ALLOW_NO_TOKEN` rimossa, che la suite invece imposta globalmente in
`conftest.py`) e col blocco di avvio **vero** estratto da `_on_startup`, il
worker vero completa un giro vero del ponte -- `claim` + `submit` -- contro il
server vero.
"""
import asyncio
import inspect
import logging
import os
import secrets as secrets_stdlib
import textwrap
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from hiris.app import server, token_interno
from hiris.app.agent import runner as agent_runner
from hiris.app.chat_store import close_all_stores
from hiris.app.impostazioni_chat import ImpostazioniChat
from hiris.app.reasoning.queue import ReasoningQueue
from hiris.app.token_interno import (
    prepare_internal_token,
    token_path,
)


@pytest.fixture(autouse=True)
def reset_chat_stores():
    yield
    close_all_stores()


@pytest.fixture(autouse=True)
def ambiente_pulito(monkeypatch):
    """Ogni test parte da un ambiente in cui `INTERNAL_TOKEN` e' quello che il
    test dichiara, e mai quello di un test precedente: `prepare_internal_token`
    scrive in `os.environ` apposta (e' il requisito che fa funzionare il
    worker), quindi senza questo isolamento i test si contaminerebbero."""
    monkeypatch.delenv("INTERNAL_TOKEN", raising=False)
    yield


# ---------------------------------------------------------------------------
# Campo vuoto -> generato, scritto, pubblicato in os.environ
# ---------------------------------------------------------------------------

def test_campo_vuoto_genera_scrive_e_pubblica(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(tmp_path))

    assert token, "con il campo vuoto il token deve essere generato, non restare vuoto"
    assert len(token) >= 40, f"segreto troppo corto per 256 bit: {len(token)} caratteri"
    percorso = token_path(str(tmp_path))
    assert os.path.exists(percorso), "il token deve essere SCRITTO, non solo tenuto in memoria"
    with open(percorso, encoding="utf-8") as f:
        assert f.read().strip() == token
    # Il requisito 4: chi legge dall'ambiente al momento della chiamata (il
    # worker del ponte) deve vederlo.
    assert os.environ["INTERNAL_TOKEN"] == token

    testo = caplog.text
    assert "generato" in testo and str(percorso) in testo
    assert "riavvii" in testo, "il log deve dire che sopravvive ai riavvii"
    assert token not in testo, "il VALORE del token non deve mai finire nel log"


def test_il_token_generato_viene_da_secrets_e_non_e_prevedibile(tmp_path, monkeypatch):
    """Due directory diverse -> due token diversi. Pinna che la generazione usa
    `secrets` (nessuna dipendenza nuova) e non un valore fisso."""
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    primo = prepare_internal_token(str(tmp_path / "a"))
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    secondo = prepare_internal_token(str(tmp_path / "b"))
    assert primo and secondo and primo != secondo


# ---------------------------------------------------------------------------
# Secondo avvio -> RILETTO, non rigenerato (e' la persistenza in /data)
# ---------------------------------------------------------------------------

def test_secondo_avvio_rilegge_lo_stesso_token_e_non_ne_genera_un_altro(
    tmp_path, monkeypatch, caplog
):
    """Il requisito che un test ingenuo non coglie: un token diverso a ogni
    boot invaliderebbe i lavori gia' in coda (vengono claimati dopo il
    riavvio). La prova non e' solo «il valore coincide»: `token_urlsafe` viene
    sostituito da una funzione che ESPLODE, cosi' una rigenerazione silenziosa
    non puo' passare inosservata restituendo per caso lo stesso valore."""
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    primo = prepare_internal_token(str(tmp_path))
    assert primo

    def _mai_piu(*a, **kw):
        raise AssertionError("al secondo avvio il token va RILETTO, non rigenerato")

    monkeypatch.setattr(token_interno.secrets, "token_urlsafe", _mai_piu)
    # run.sh riesporta il campo vuoto a ogni avvio: l'ambiente riparte da li'.
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    secondo = prepare_internal_token(str(tmp_path))

    assert secondo == primo
    assert os.environ["INTERNAL_TOKEN"] == primo
    assert "riletto" in caplog.text
    assert primo not in caplog.text, "il VALORE del token non deve mai finire nel log"


# ---------------------------------------------------------------------------
# Campo valorizzato -> vince l'utente, nessuna generazione, nessuna scrittura
# ---------------------------------------------------------------------------

def test_token_configurato_a_mano_vince_e_non_scrive_niente(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("INTERNAL_TOKEN", "scelto-dall-utente")

    def _mai(*a, **kw):
        raise AssertionError("con il campo valorizzato non si genera niente")

    monkeypatch.setattr(token_interno.secrets, "token_urlsafe", _mai)
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(tmp_path))

    assert token == "scelto-dall-utente"
    assert os.environ["INTERNAL_TOKEN"] == "scelto-dall-utente"
    assert not os.path.exists(token_path(str(tmp_path))), \
        "con il campo valorizzato non si scrive niente su disco"
    assert "configurato" in caplog.text


def test_token_configurato_vince_anche_su_un_file_gia_scritto(tmp_path, monkeypatch):
    """Un'installazione che ha gia' generato un token e poi valorizza il campo:
    vince il campo, e il file NON viene ne' letto ne' riscritto."""
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    generato = prepare_internal_token(str(tmp_path))
    monkeypatch.setenv("INTERNAL_TOKEN", "quello-dell-utente")

    token = prepare_internal_token(str(tmp_path))

    assert token == "quello-dell-utente"
    with open(token_path(str(tmp_path)), encoding="utf-8") as f:
        assert f.read().strip() == generato, \
            "il file su disco non va toccato quando vince il token dell'utente"


def test_token_configurato_con_spazi_viene_normalizzato(tmp_path, monkeypatch):
    """Un header HTTP arriva senza spazi ai bordi: se `app["internal_token"]`
    li conservasse, il worker si prenderebbe 401 pur avendo il token giusto."""
    monkeypatch.setenv("INTERNAL_TOKEN", "  con-spazi  ")
    assert prepare_internal_token(str(tmp_path)) == "con-spazi"
    assert os.environ["INTERNAL_TOKEN"] == "con-spazi"


# ---------------------------------------------------------------------------
# Fallimenti -> si nega e si DICHIARA, non si apre
# ---------------------------------------------------------------------------

def test_scrittura_impossibile_nega_e_dichiara(tmp_path, monkeypatch, caplog):
    """La directory dei dati non e' creabile (c'e' gia' un FILE con quel nome):
    `os.makedirs` solleva `OSError`. Il prodotto non si degrada in «nessun
    token» taciuto: torna "" (il middleware continua a negare) e lo dice."""
    finta_dir = tmp_path / "data"
    finta_dir.write_text("non sono una directory", encoding="utf-8")
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(finta_dir))

    assert token == "", "senza token scritto si nega, non si aprono le porte"
    assert os.environ["INTERNAL_TOKEN"] == ""
    errori = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errori, "il fallimento deve essere DICHIARATO, non ingoiato"
    assert "NEGATA" in caplog.text


def test_file_illeggibile_nega_e_non_lo_sovrascrive(tmp_path, monkeypatch, caplog):
    """Un token gia' scritto ma illeggibile (qui: al suo posto c'e' una
    directory) non viene confuso con «non c'e'»: sovrascriverlo cambierebbe il
    segreto sotto ai lavori gia' in coda. Si nega e si dichiara."""
    os.makedirs(token_path(str(tmp_path)))
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(tmp_path))

    assert token == ""
    assert os.environ["INTERNAL_TOKEN"] == ""
    assert os.path.isdir(token_path(str(tmp_path))), "non deve essere sovrascritto"
    assert [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "NEGATA" in caplog.text


def test_scrittura_fallita_a_meta_non_lascia_un_token_troncato(tmp_path, monkeypatch):
    """Il file definitivo compare solo con `os.replace`: se la scrittura
    esplode a meta', al riavvio successivo non si rilegge mezzo segreto."""
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    vero_replace = os.replace

    def _replace_che_esplode(src, dst):
        raise OSError("disco pieno")

    monkeypatch.setattr(token_interno.os, "replace", _replace_che_esplode)
    token = prepare_internal_token(str(tmp_path))
    monkeypatch.setattr(token_interno.os, "replace", vero_replace)

    assert token == ""
    assert not os.path.exists(token_path(str(tmp_path)))


def test_il_file_del_token_non_e_leggibile_da_tutti(tmp_path, monkeypatch):
    """Su Linux (la piattaforma dell'add-on) il file deve essere 0600. Su
    Windows i bit di gruppo/altri non esistono: li' il test si salta invece di
    fingere una garanzia che il sistema non da'."""
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    prepare_internal_token(str(tmp_path))
    if os.name != "posix":
        pytest.skip("permessi POSIX non applicabili su questa piattaforma")
    modo = os.stat(token_path(str(tmp_path))).st_mode & 0o777
    assert modo == 0o600, f"permessi troppo larghi: {oct(modo)}"


# ---------------------------------------------------------------------------
# Il test che conta: il guasto riprodotto e chiuso, sul giro vero del ponte
# ---------------------------------------------------------------------------

def _carica_blocco_avvio_token():
    """Estrae dal sorgente VERO di `_on_startup` il blocco che risolve la
    directory dei dati e il token interno -- da `data_dir = os.environ.get(...)`
    fino (incluso) ad `app["internal_token"] = prepare_internal_token(data_dir)`.

    Stessa tecnica di `tests/test_avvio_websocket.py`: si esegue il codice di
    produzione, non una sua parafrasi, cosi' che togliere la chiamata da
    `_on_startup` faccia fallire il test invece di lasciarlo verde."""
    src = inspect.getsource(server._on_startup)
    start = src.index('    data_dir = os.environ.get("HIRIS_DATA_DIR", "/data")')
    fine_marcatore = 'app["internal_token"] = prepare_internal_token(data_dir)'
    end = src.index(fine_marcatore, start) + len(fine_marcatore)
    body = textwrap.dedent(src[start:end])
    func_src = "def _avvio(app, os, prepare_internal_token):\n" + textwrap.indent(body, "    ")
    namespace: dict = {}
    exec(compile(func_src, "<_on_startup token interno>", "exec"), namespace)
    return namespace["_avvio"]


def _app_come_in_produzione(tmp_path):
    """`create_app()` vero, con i soli agganci che `_on_startup` avrebbe
    cablato e che qui non servono davvero. `on_startup` viene svuotato perche'
    il boot completo parla col Supervisor: il blocco del token, pero', si
    esegue davvero (vedi `_carica_blocco_avvio_token`)."""
    app = server.create_app()
    mock_ha = AsyncMock()
    mock_ha.start = AsyncMock()
    mock_ha.stop = AsyncMock()
    mock_ha.add_state_listener = MagicMock()
    mock_ha.start_websocket = AsyncMock()
    app["ha_client"] = mock_ha
    app["impostazioni_chat"] = ImpostazioniChat()
    app["claude_runner"] = None
    app["theme"] = "auto"
    # Il default di produzione: la sorgente di questo client di test e' un
    # loopback, che NON e' dentro la CIDR del Supervisor -> nessun bypass
    # ingress, si passa per forza dal token. E' il caso del worker del ponte.
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app.on_startup.clear()
    app.on_cleanup.clear()
    return app


@pytest_asyncio.fixture
async def ponte_con_configurazione_predefinita(aiohttp_client, tmp_path, monkeypatch):
    """Configurazione PREDEFINITA dell'add-on, senza scorciatoie:
    `internal_token: ""` (quindi `INTERNAL_TOKEN=""` da run.sh), e le due
    valvole di sfogo della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`
    di `conftest.py`) RIMOSSE -- altrimenti il test passerebbe anche col
    guasto in piedi."""
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    monkeypatch.setenv("HIRIS_DATA_DIR", str(tmp_path))

    app = _app_come_in_produzione(tmp_path)
    _carica_blocco_avvio_token()(app, os, prepare_internal_token)

    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    app["reasoning_queue"] = coda
    client = await aiohttp_client(app)
    try:
        yield client, coda, app
    finally:
        coda.close()


@pytest.mark.asyncio
async def test_configurazione_predefinita_la_richiesta_del_worker_passa(
    ponte_con_configurazione_predefinita,
):
    """Il guasto, riprodotto e chiuso: con la configurazione predefinita una
    richiesta non-ingress con l'header che il worker manda davvero
    (`agent_runner.build_headers()`, che legge `os.environ["INTERNAL_TOKEN"]`
    al momento della chiamata) ora **passa**. Prima rispondeva 401."""
    client, _coda, app = ponte_con_configurazione_predefinita

    assert app["internal_token"], "con il default vuoto il token va generato all'avvio"
    intestazioni = agent_runner.build_headers()
    assert intestazioni["X-HIRIS-Internal-Token"] == app["internal_token"], \
        "il worker legge os.environ: se l'avvio non lo pubblica li', il guasto resta identico"

    resp = await client.get("/api/health", headers=intestazioni)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_il_rifiuto_per_default_resta_in_piedi(ponte_con_configurazione_predefinita):
    """Controprova: la generazione del token non ha aperto la API. Chi arriva
    da fuori senza l'header giusto continua a prendersi 401."""
    client, _coda, _app = ponte_con_configurazione_predefinita

    assert (await client.get("/api/health")).status == 401
    assert (await client.get(
        "/api/health", headers={"X-HIRIS-Internal-Token": "sbagliato"})).status == 401
    # E nemmeno un X-Ingress-Path forgiato da un IP non fidato basta (CR-1).
    assert (await client.get(
        "/api/health", headers={"X-Ingress-Path": "/api/hassio_ingress/forgiato"})).status == 401


@pytest.mark.asyncio
async def test_il_giro_vero_del_ponte_si_chiude_claim_piu_submit(
    ponte_con_configurazione_predefinita,
):
    """Il giro vero del ponte, senza la CLI `claude` (modalita' `mock`):
    `run_once` del worker vero -- lo stesso codice che in produzione girava a
    vuoto ogni 3 secondi -- fa `POST /api/reasoning/claim` e
    `POST /api/reasoning/submit` contro il server vero e chiude il lavoro.

    `run_once` e' sincero-bloccante (httpx.Client), quindi gira in un thread:
    esattamente come in produzione, dove `run_loop` lo passa a
    `run_in_executor` per non bloccare il loop dell'add-on."""
    client, coda, _app = ponte_con_configurazione_predefinita
    adesso = time.time()
    coda.enqueue(
        "chat", {},
        {"history": [{"role": "user", "content": "ciao"}], "system_prompt": "sei HIRIS"},
        adesso + 300, now=adesso,
    )

    base_url = f"http://127.0.0.1:{client.server.port}"
    with httpx.Client(timeout=30) as http:
        esito = await asyncio.to_thread(
            agent_runner.run_once, http, base_url, agent_runner.build_headers(), "mock"
        )

    assert esito == "done", (
        "con il token generato all'avvio il ponte claima e consegna; "
        "col guasto in piedi qui arrivava un 401 da raise_for_status()"
    )


@pytest.mark.asyncio
async def test_senza_token_pubblicato_il_giro_del_ponte_fallisce_come_prima(
    ponte_con_configurazione_predefinita, monkeypatch,
):
    """La mutazione del test qui sopra: si rimette `os.environ["INTERNAL_TOKEN"]`
    a vuoto (cioe' si annulla il requisito 4 -- token in `app` ma non
    nell'ambiente) e il giro del ponte torna a rompersi con 401. E' la prova
    che il test precedente misura il token pubblicato, non altro."""
    client, coda, app = ponte_con_configurazione_predefinita
    assert app["internal_token"]
    monkeypatch.setenv("INTERNAL_TOKEN", "")

    adesso = time.time()
    coda.enqueue("chat", {}, {"history": [], "system_prompt": ""}, adesso + 300, now=adesso)

    base_url = f"http://127.0.0.1:{client.server.port}"
    with httpx.Client(timeout=30) as http, pytest.raises(httpx.HTTPStatusError) as errore:
        await asyncio.to_thread(
            agent_runner.run_once, http, base_url, agent_runner.build_headers(), "mock"
        )
    assert errore.value.response.status_code == 401


# ---------------------------------------------------------------------------
# fetta «il ponte riceve gli strumenti» (parita' B, Task 3, fix round 2):
# L'ALFABETO DEL TOKEN.
#
# Fino a questo giro nessuno validava l'opzione `internal_token`, che
# `hiris/config.yaml` espone come `password` LIBERA: qualunque cosa l'utente
# scrivesse entrava in circolo dopo un solo `.strip()`. Non era teorico -- con
# un token che contiene CR/LF/NUL il client HTTP solleva **col valore dentro**
# il messaggio, e quel messaggio finisce nel log dell'add-on
# (`agent/runner.py::sonda_strumenti`), cioe' nel file che si incolla in una
# segnalazione. Il docstring di quella funzione prometteva «il motivo non
# contiene mai il token»: era una dichiarazione falsa al presente, ed e' questa
# validazione a renderla vera.
# ---------------------------------------------------------------------------

def test_l_alfabeto_rifiuta_cio_che_rompe_l_header_e_nient_altro():
    """La regola e' la piu' PICCOLA che chiude il difetto, non la piu' severa
    che si possa scrivere: rifiutare anche le virgolette avrebbe respinto
    configurazioni legittime che oggi funzionano, e quel fronte -- la redazione
    del token nei log -- si chiude dove si manifesta
    (`agent/runner.py::forme_del_token`)."""
    # ammessi: tutto cio' che e' consegnabile in un header HTTP
    for buono in ("abc-def_123", 'ab"cd\\ef', "con spazio interno", "a+b/c=",
                  "x" * 200, "!#$%&'()*,;:@"):
        assert token_interno.invalid_token_reason(buono) is None, buono
    # rifiutati: i caratteri di controllo e il non-ASCII
    for cattivo, atteso in (("abc\rdef", "ritorno a capo"),
                            ("abc\ndef", "a-capo"),
                            ("abc\x00def", "NUL"),
                            ("abc\tdef", "tabulazione"),
                            ("abc\x7fdef", "carattere di controllo"),
                            ("ab\u00e8cd", "non-ASCII")):
        motivo = token_interno.invalid_token_reason(cattivo)
        assert motivo is not None, cattivo
        assert atteso in motivo, f"{cattivo!r} -> {motivo!r}"
        # la POSIZIONE si dice (serve a correggere l'opzione), il VALORE no
        assert "posizione" in motivo
    assert token_interno.invalid_token_reason("") is None


def test_un_token_configurato_non_consegnabile_e_rifiutato_e_dichiarato(
    tmp_path, monkeypatch, caplog
):
    """Rifiuto-per-difetto, la disciplina di questo file: si torna `""`, il
    middleware continua a negare, e il guasto si DICHIARA. Mai un pass muto, e
    mai una generazione al posto del token dell'utente -- che gli farebbe
    credere che il valore configurato funziona."""
    cattivo = "abc\r\ndef-SEGRETO"
    monkeypatch.setenv("INTERNAL_TOKEN", cattivo)
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(tmp_path))

    assert token == "", "un token non consegnabile non deve entrare in circolo"
    assert os.environ["INTERNAL_TOKEN"] == "", (
        "il valore rotto e' rimasto in os.environ: il worker del ponte lo "
        "rileggerebbe da li' e continuerebbe a farlo sollevare")
    # e NON si e' generato niente al suo posto: sarebbe un token che l'utente
    # non ha scelto, in silenzio
    assert not os.path.exists(token_path(str(tmp_path)))

    testo = caplog.text
    assert "internal_token" in testo
    assert "ritorno a capo" in testo and "posizione 3" in testo
    assert "NEGATA (401)" in testo, "il log deve dire cosa smette di funzionare"
    assert "Rimedio" in testo, "un guasto senza rimedio e' meta' dichiarazione"
    assert "SEGRETO" not in testo, "il VALORE del token non deve mai finire nel log"
    assert cattivo.strip() not in testo


def test_un_token_configurato_con_virgolette_e_backslash_resta_ACCETTATO(
    tmp_path, monkeypatch
):
    """La mutazione che tiene onesta la regola: se un giorno qualcuno la
    stringesse «per sicurezza» fino a rifiutare le virgolette, respingerebbe
    configurazioni che oggi funzionano -- e questo test lo dice. Quel fronte e'
    coperto altrove, dalla redazione di tutte le forme del token."""
    monkeypatch.setenv("INTERNAL_TOKEN", 'ab"cd\\ef')

    token = prepare_internal_token(str(tmp_path))

    assert token == 'ab"cd\\ef'
    assert os.environ["INTERNAL_TOKEN"] == 'ab"cd\\ef'


def test_il_token_riletto_da_disco_e_validato_come_quello_configurato(
    tmp_path, monkeypatch, caplog
):
    """Il file di `/data` lo scriviamo noi con un valore urlsafe, ma e' un file
    di testo su un volume che l'utente puo' aprire: un file corretto a mano non
    deve poter aggirare la validazione dell'opzione."""
    percorso = token_path(str(tmp_path))
    os.makedirs(str(tmp_path), exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("meta\x00SEGRETO\n")
    monkeypatch.setenv("INTERNAL_TOKEN", "")
    caplog.set_level(logging.INFO, logger="hiris.app.token_interno")

    token = prepare_internal_token(str(tmp_path))

    assert token == ""
    # e NON lo si e' sovrascritto con uno nuovo: invaliderebbe i lavori in coda
    with open(percorso, encoding="utf-8") as f:
        assert f.read().strip() == "meta\x00SEGRETO"
    testo = caplog.text
    assert "NUL" in testo and "modificato a mano" in testo
    assert "SEGRETO" not in testo


def test_i_caratteri_rifiutati_sono_ESATTAMENTE_quelli_che_fanno_sollevare_il_client(
    tmp_path, monkeypatch,
):
    """**Il ponte fra la validazione e la promessa che rende vera.**

    `agent/runner.py::sonda_strumenti` promette nel suo docstring che il motivo
    non nomina mai il token. La promessa regge solo perche' un token che fa
    sollevare il client HTTP non arriva mai fin li'. Qui si prova la premessa
    contro un listener VERO -- non contro un doppio, perche' la validazione
    dell'header avviene dentro il client, al momento dell'invio:

    - col token rotto il client solleva **col valore dentro il messaggio**;
    - la validazione lo rifiuta, quindi in produzione quel valore non esiste
      in `os.environ` e `build_headers()` manda `""`.

    Se un giorno la validazione sparisse, questo test diventa rosso e dice
    che il docstring della sonda e' tornato falso."""
    import http.server
    import socketserver
    import threading

    class _H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}')

        def log_message(self, *a):
            pass

    server = socketserver.TCPServer(("127.0.0.1", 0), _H)
    porta = server.server_address[1]
    filo = threading.Thread(target=server.serve_forever, daemon=True)
    filo.start()
    try:
        cattivo = "abc\r\ndef-SEGRETO"
        # (a) il client solleva, e il motivo porta il valore: e' il guasto
        with httpx.Client(timeout=5) as http_client:
            ok, motivo = agent_runner.probe_tools(
                http_client, f"http://127.0.0.1:{porta}",
                {"X-HIRIS-Internal-Token": cattivo})
        assert ok is False
        assert "SEGRETO" in motivo, (
            "il client HTTP non mette piu' il valore dell'header nel messaggio: "
            "la premessa di questo test e' cambiata, va riletta -- non "
            "cancellata")
        # (b) ...e per questo un token del genere non deve mai arrivare fin qui
        assert token_interno.invalid_token_reason(cattivo) is not None
        monkeypatch.setenv("INTERNAL_TOKEN", cattivo)
        assert prepare_internal_token(str(tmp_path)) == ""
        assert agent_runner.build_headers()["X-HIRIS-Internal-Token"] == ""
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_col_token_rifiutato_il_ponte_resta_negato(
    aiohttp_client, tmp_path, monkeypatch
):
    """Il rifiuto-per-difetto, end-to-end e non solo nel valore di ritorno:
    con un token configurato non consegnabile, il worker del ponte si prende
    401 dal server vero -- che e' il comportamento giusto (rotto e detto), non
    un'apertura silenziosa."""
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN", "abc\ndef-SEGRETO")
    monkeypatch.setenv("HIRIS_DATA_DIR", str(tmp_path))

    app = _app_come_in_produzione(tmp_path)
    _carica_blocco_avvio_token()(app, os, prepare_internal_token)
    client = await aiohttp_client(app)

    assert app["internal_token"] == ""
    risposta = await client.get("/api/health", headers=agent_runner.build_headers())
    assert risposta.status == 401


def test_secrets_e_della_libreria_standard():
    """Nessuna dipendenza nuova: il segreto viene dal `secrets` di sistema."""
    assert token_interno.secrets is secrets_stdlib
