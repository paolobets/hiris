"""fetta «il ponte riceve gli strumenti» (parita' B, Task 3): l'interruttore.

Qui si difende **una cosa sola**, ed e' la ragione per cui l'intera fetta e'
stata tagliata cosi': **il prompt e l'`argv` sono la stessa decisione scritta
due volte, e non devono mai divergere**. Un `argv` con `--mcp-config` e un
prompt che nega gli strumenti darebbe al modello capacita' che il testo gli
vieta; un prompt che le afferma senza l'`argv` gliele prometterebbe senza
darle -- e quello e' il difetto numero uno di questo prodotto, quello che ha
prodotto il rilievo peggiore della fetta E3 (due prompt di sistema che
promettevano capacita' inesistenti).

Cosa difende ciascun gruppo:

- ① **l'invariante nei due versi**: `"--mcp-config" in argv` **<=>**
  `_GUIDE_WITH_TOOLS in system`. E' il test da non cancellare mai: pinnato
  in un verso solo, il giorno in cui i due divergono nessuno se ne accorge;
- ② **la mcp-config**: JSON valido, la URL giusta, **entrambe** le
  intestazioni, e **nessun file** su disco (dentro c'e' un segreto);
- ③ **la sonda che non solleva**: 401, 500, connessione caduta, lista
  incompleta -- tutti `False` + un motivo leggibile, e un `log.warning` che lo
  nomina (silenzio dichiarato ① della fetta). E il **token non compare mai**
  ne' nel motivo ne' nel log;
- ④ **la sonda vera contro il server vero**: l'autenticazione della rotta e
  quella del ponte sono **lo stesso token**, non due;
- ⑤ **la rientranza**: mentre la CLI "gira" nel thread dell'executor, l'add-on
  serve davvero la callback -- e la serve per **tutti** gli
  strumenti di conoscenza, `view` compreso, che e' l'unico che legge la `entity_cache` e
  quindi l'argomento portante con cui il disegno giustifica una rotta invece
  di un sottoprocesso separato;
- ⑥ **il degrado dichiarato**: gli strumenti erano attesi e non ci sono -- la
  `reply` lo dice **all'utente**, non solo al log.
"""
from __future__ import annotations

import asyncio
import builtins
import json
import logging
import os
import sqlite3
import time
from unittest.mock import patch

import httpx
import pytest

from hiris.app.agent import prompts, runner
from hiris.app.api import handlers_mcp
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS
from hiris.app.memory.store import MemoryStore

# La fixture della configurazione PREDEFINITA dell'add-on, con le due valvole
# della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`) rimosse: si
# importa invece di essere ricopiata qui: una seconda copia divergerebbe, e
# senza le valvole rimosse questi test passerebbero anche col guasto in piedi.
from tests.test_internal_token import (  # noqa: F401  (fixture usata da pytest)
    ponte_con_configurazione_predefinita,
)
from tests.test_knowledge_tools import _semina_casa

_NOMI_NUDI = {d["name"] for d in KNOWLEDGE_TOOLS}


def _normalizza(argv):
    """La stessa normalizzazione del pin dell'argv
    (tests/test_agent_runner_inaddon.py): `--allowed-tools` non deve aggirare
    nessuna delle due reti."""
    return {a.lower().replace("-", "") for a in argv}


def _tools_list(nomi) -> dict:
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"tools": [{"name": n} for n in nomi]}}


class _Risposta:
    def __init__(self, dati, status_code=200, solleva_json=False):
        self._dati = dati
        self.status_code = status_code
        self._solleva_json = solleva_json

    def json(self):
        if self._solleva_json:
            raise ValueError("non e' JSON")
        return self._dati


class _ClientFinto:
    """Un client che risponde cio' che il test gli dice, e registra come e'
    stato chiamato."""

    def __init__(self, risposta=None, solleva=None):
        self._risposta = risposta
        self._solleva = solleva
        self.chiamate = []

    def post(self, url, headers=None, json=None, **kwargs):
        self.chiamate.append({"url": url, "headers": headers, "corpo": json,
                              "extra": kwargs})
        if self._solleva is not None:
            raise self._solleva
        return self._risposta


# ---------------------------------------------------------------------------
# ① L'INVARIANTE, NEI DUE VERSI -- il test da non cancellare mai
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("strumenti_attivi", [True, False])
def test_invariante_argv_e_prompt_nei_due_versi(strumenti_attivi):
    """`"--mcp-config" in argv` **<=>** `_GUIDE_WITH_TOOLS in system`.

    E' il test che rende impossibile un prompt che promette cio' che l'`argv`
    non da' -- e, nell'altro verso, un `argv` che serve strumenti a un modello
    a cui il testo li nega. Si compongono **insieme**, dallo stesso booleano,
    come fa `runner._reason_chat`: se un giorno le due composizioni si
    separassero, e' qui che si vede.

    Pinnato in un verso solo non varrebbe niente: il caso pericoloso non e'
    «manca l'uno» ma «i due si sono scambiati», e per vederlo servono
    entrambe le direzioni."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto="## La casa\nSalotto: luce accesa.",
        active_tools=strumenti_attivi)
    argv = runner._chat_claude_args(
        "SYS", "USER", "sonnet", active_tools=strumenti_attivi,
        mcp_config=runner.config_mcp("http://127.0.0.1:8099", "TOK"))

    nell_argv = "mcpconfig" in _normalizza(argv)
    nel_prompt = prompts._GUIDE_WITH_TOOLS in system

    assert nell_argv == nel_prompt, (
        f"l'argv {'porta' if nell_argv else 'NON porta'} --mcp-config mentre il "
        f"system prompt {'afferma' if nel_prompt else 'NEGA'} gli strumenti: e' "
        "esattamente la divergenza che questa fetta esiste per rendere "
        "impossibile. La risposta giusta e' guardare l'unico booleano di "
        "runner._reason_chat, non allentare questo assert.")
    # e il verso complementare, sull'altra guida: le due non convivono mai
    assert (prompts._GUIDE_WITHOUT_TOOLS in system) == (not nell_argv)


def test_le_due_guide_non_convivono_mai_nello_stesso_prompt():
    """Il corollario: un prompt che contenesse entrambe direbbe al modello una
    cosa e il suo contrario, e vincerebbe l'ultima letta."""
    for attivi in (True, False):
        system, _u = prompts.build_chat_messages("Sei HIRIS.", [], active_tools=attivi)
        assert (prompts._GUIDE_WITH_TOOLS in system) != (
            prompts._GUIDE_WITHOUT_TOOLS in system)


def test_i_nomi_si_derivano_dal_catalogo_e_non_si_riscrivono():
    """Nessun secondo catalogo: i nomi che finiscono in `--allowedTools` e nel
    testo del prompt nascono da `KNOWLEDGE_TOOLS`. Stringhe scritte a
    mano nel runner sarebbero l'errore che l'intera fetta E2 e' esistita per
    chiudere (tre cataloghi divergenti della stessa cosa).

    Il numero letterale e' un filo teso di proposito: non aggiunge nulla alla
    verifica dei nomi qui sotto, ma fa in modo che uno strumento che entra o
    esce dal catalogo passi da una decisione esplicita invece che di
    soppiatto. fetta "comandare" Task 5: da 4 a 5, entra `execute`; fetta
    «i legami» : da 5 a 6, entra `related` -- che al ponte serve quanto alla
    chat, perche' «se cancello questa entita' cosa smette di funzionare?» e'
    una domanda da farsi PRIMA di proporre una modifica, ed e' il ponte a
    proporne. Fetta «lo schedulatore» Task 6: da 6 a 9, entrano `promise`,
    `agenda` e `cancel` -- le promesse che il modello puo' far nascere
    parlando, non solo leggere (`keeper/exchange.py` le tiene FUORI dal
    proprio catalogo derivato, con un elenco di ammissione a parte: un turno
    non si da' appuntamenti da solo). Fetta «costruire» Task 9: da 9 a 11,
    entrano `propose` e `confirm` -- che scrivono CONFIGURAZIONE passando
    per l'officina, non un servizio (`keeper/exchange.py` li tiene FUORI
    dallo stesso elenco di ammissione, per la stessa ragione: un turno di
    promessa non costruisce da solo). Fetta «HIRIS e il tempo» Task 6: da 11
    a 13, entrano `trend` e `logbook` -- che guardano indietro nel tempo
    passando per `home_space/historian.py`, LEGGONO e basta, ed entrano invece nello
    stesso elenco di ammissione del turno delle promesse, per la ragione
    opposta a `propose`/`confirm`."""
    nomi = runner.mcp_names()

    assert len(nomi) == len(KNOWLEDGE_TOOLS) == 13
    assert set(nomi) == {f"mcp__hiris__{n}" for n in _NOMI_NUDI}
    # il nome del server ha UNA fonte, quella della rotta: se un giorno la
    # rotta si presentasse con un altro nome, il prefisso lo seguirebbe da
    # solo -- e il prompt, che nomina i nomi prefissati, resterebbe vero.
    assert runner._mcp_server_name() is handlers_mcp.MCP_SERVER_NAME
    for nome in nomi:
        assert nome.startswith(f"mcp__{handlers_mcp.MCP_SERVER_NAME}__")


def test_toolsearch_non_e_vietato_o_gli_strumenti_sono_irraggiungibili():
    """La CLI passa da `ToolSearch` per risolvere gli schemi degli strumenti
    MCP: vietarlo li renderebbe visibili nell'elenco e non chiamabili -- il
    prompt li afferma e la chiamata non arriva mai. E' il genere di stringa
    che qualcuno «completa» leggendo l'elenco dei tool locali vietati."""
    assert "ToolSearch" not in runner._LOCAL_TOOLS_DENY


# ---------------------------------------------------------------------------
# ② LA MCP-CONFIG: una stringa, non un file (dentro c'e' un segreto)
# ---------------------------------------------------------------------------

def test_config_mcp_e_json_valido_con_la_url_e_le_due_intestazioni():
    testo = runner.config_mcp("http://127.0.0.1:8099", "IL-TOKEN")
    config = json.loads(testo)

    voce = config["mcpServers"][handlers_mcp.MCP_SERVER_NAME]
    assert voce["type"] == "http"
    assert voce["url"] == "http://127.0.0.1:8099/api/mcp"
    # ENTRAMBE: il token apre la rotta, l'X-Requested-With soddisfa il CSRF.
    # Mandarne uno solo farebbe dipendere la rotta da un solo ramo di un solo
    # middleware -- e i due rami sono pinnati in tests/test_mcp_route.py
    # proprio perche' nessuno dei due resti da solo a reggerla.
    assert voce["headers"]["X-HIRIS-Internal-Token"] == "IL-TOKEN"
    assert voce["headers"]["X-Requested-With"] == "hiris-mcp"


def test_config_mcp_aggiunge_x_hiris_turno_quando_l_identita_e_valorizzata():
    """Task 6 (fix round 1, Important): specchio del test sulle DUE
    intestazioni qui sopra, per la TERZA -- facoltativa -- che quel test non
    copriva. Quando il chiamante passa un'identita' di turno, l'header
    `X-HIRIS-Turno` compare nella stessa voce, accanto alle altre due, e non
    al loro posto."""
    testo = runner.config_mcp("http://127.0.0.1:8099", "IL-TOKEN", "IDENTITA-DEL-TURNO")
    config = json.loads(testo)

    voce = config["mcpServers"][handlers_mcp.MCP_SERVER_NAME]
    assert voce["headers"]["X-HIRIS-Turno"] == "IDENTITA-DEL-TURNO"
    assert voce["headers"]["X-HIRIS-Internal-Token"] == "IL-TOKEN"
    assert voce["headers"]["X-Requested-With"] == "hiris-mcp"


def test_config_mcp_senza_id_turno_non_aggiunge_l_intestazione():
    """Il default vuoto (nessun terzo argomento) non aggiunge NESSUN header al
    suo posto: e' cio' che permette a chi chiama `config_mcp` con i soli due
    argomenti di sempre -- ogni altro test di questo file, e
    `tests/test_agent_runner_inaddon.py:648` -- di continuare a funzionare
    invariato. Un tetto per-turno non e' niente che quei test debbano
    conoscere."""
    testo = runner.config_mcp("http://127.0.0.1:8099", "IL-TOKEN")
    config = json.loads(testo)

    voce = config["mcpServers"][handlers_mcp.MCP_SERVER_NAME]
    assert "X-HIRIS-Turno" not in voce["headers"]


def test_config_mcp_normalizza_la_barra_finale_della_base_url():
    """`http://host:8099/` + `/api/mcp` farebbe `//api/mcp`, che non e' la
    stessa rotta."""
    config = json.loads(runner.config_mcp("http://127.0.0.1:8099/", "T"))
    assert config["mcpServers"]["hiris"]["url"] == "http://127.0.0.1:8099/api/mcp"


def test_config_mcp_non_scrive_nessun_file(tmp_path, monkeypatch):
    """Il vecchio disegno (Piano 2A) scriveva un file 0600 perche' la sua
    config NON conteneva segreti. Questa si': il token interno e' dentro. Una
    stringa non resta su disco, e il residuo dichiarato -- il token visibile
    nell'`argv` del processo dentro il container -- e' una decisione presa e
    consegnata alla fase sicurezze (C.3.5), non una svista.

    Non si CONTANO i file di una cartella: su questa macchina esiste ancora un
    `C:/tmp/hiris-mcp.json` lasciato dal vecchio disegno, e un test che
    contasse li' dentro accuserebbe questo codice di un residuo altrui. Si
    guarda che nessuna scrittura AVVENGA: `builtins.open` in scrittura viene
    reso esplosivo per la durata della chiamata, cosi' il giorno in cui
    qualcuno "sistemasse" la mcp-config rimettendola su disco il test lo dice
    subito e col motivo giusto."""
    monkeypatch.chdir(tmp_path)
    prima = set(os.listdir(tmp_path))
    apri_vero = builtins.open

    def _apri(file, mode="r", *a, **k):
        if any(c in mode for c in "wxa+"):
            raise AssertionError(
                f"config_mcp ha aperto {file!r} in scrittura ({mode!r}): la "
                "mcp-config del ponte contiene il token interno e non deve "
                "restare su disco")
        return apri_vero(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", _apri)
    testo = runner.config_mcp("http://127.0.0.1:8099", "SEGRETO")
    monkeypatch.undo()

    assert set(os.listdir(tmp_path)) == prima
    assert "SEGRETO" in testo  # sta nella stringa, e solo li'


# ---------------------------------------------------------------------------
# ③ LA SONDA: mai un'eccezione che risale, sempre un motivo leggibile
# ---------------------------------------------------------------------------

def _sonda_con(client, caplog=None):
    return runner.probe_tools(client, "http://127.0.0.1:8099",
                                  {"X-HIRIS-Internal-Token": "TOK"},
                                  job_id="J-1")


def test_la_sonda_dice_no_se_la_rotta_nega():
    ok, motivo = _sonda_con(_ClientFinto(_Risposta({"error": "unauthorized"}, 401)))
    assert ok is False
    assert "401" in motivo


def test_la_sonda_dice_no_se_la_rotta_esplode():
    ok, motivo = _sonda_con(_ClientFinto(_Risposta({"error": "boom"}, 500)))
    assert ok is False
    assert "500" in motivo


def test_la_sonda_dice_no_se_la_connessione_fallisce():
    """Il ponte non deve cadere perche' una difesa non ha risposto: qui
    degraderebbe da «risposta senza strumenti» a «nessuna risposta»."""
    ok, motivo = _sonda_con(_ClientFinto(solleva=httpx.ConnectError("rifiutata")))
    assert ok is False
    assert "ConnectError" in motivo


def test_la_sonda_dice_no_se_il_corpo_non_e_json():
    ok, motivo = _sonda_con(_ClientFinto(_Risposta(None, 200, solleva_json=True)))
    assert ok is False
    assert "JSON" in motivo


def test_la_sonda_dice_no_se_la_lista_e_incompleta():
    """**Una lista incompleta non e' «quasi si'».** Il prompt del ramo attivo
    afferma TUTTI gli strumenti del catalogo: se ne mancasse uno, il modello ne chiamerebbe
    uno che non esiste -- e il messaggio che riceverebbe non e' una risposta,
    e' un errore che nessuno gli ha spiegato."""
    tre = sorted(_NOMI_NUDI)[:3]
    ok, motivo = _sonda_con(_ClientFinto(_Risposta(_tools_list(tre), 200)))
    assert ok is False
    mancante = (set(_NOMI_NUDI) - set(tre)).pop()
    assert mancante in motivo


def test_la_sonda_dice_si_solo_col_catalogo_intero():
    client = _ClientFinto(_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200))
    ok, motivo = _sonda_con(client)

    assert ok is True and motivo == ""
    # ...e ha chiesto proprio `tools/list` alla rotta giusta, con gli header
    # ricevuti (mai ricostruiti: l'add-on non deve avere due modi di
    # autenticarsi verso se stesso).
    chiamata = client.chiamate[0]
    assert chiamata["url"] == "http://127.0.0.1:8099/api/mcp"
    assert chiamata["corpo"] == {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert chiamata["headers"] == {"X-HIRIS-Internal-Token": "TOK"}


def test_ogni_no_della_sonda_e_un_silenzio_dichiarato(caplog):
    """Silenzio dichiarato ① della fetta: ogni `False` produce un
    `log.warning` che nomina **il motivo e il job_id**. Un `False` muto
    sarebbe indistinguibile da un'assenza di problemi -- il difetto numero uno
    di questo prodotto."""
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        _sonda_con(_ClientFinto(_Risposta({"error": "unauthorized"}, 401)))

    righe = [r for r in caplog.records if r.name == "hiris.agent"]
    assert len(righe) == 1
    messaggio = righe[0].getMessage()
    assert "J-1" in messaggio
    assert "401" in messaggio
    assert "SENZA strumenti" in messaggio


def test_il_si_della_sonda_non_logga_niente(caplog):
    """Un log che scatta sempre e' rumore, e il silenzio dichiarato smette di
    distinguersi."""
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        _sonda_con(_ClientFinto(_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200)))
    assert not [r for r in caplog.records if r.name == "hiris.agent"]


def test_il_token_non_compare_mai_nel_motivo_ne_nel_log(caplog):
    """Il segreto vive nella mcp-config e negli header, e li' deve restare.
    Un motivo generoso (o un `%r` sugli header) e' il modo classico di far
    finire un token in un file di log -- ed e' gia' successo su questo ramo,
    in un'altra forma."""
    segreto = "token-interno-segretissimo-42"
    client = _ClientFinto(solleva=httpx.ConnectError("rifiutata"))

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        ok, motivo = runner.probe_tools(
            client, "http://127.0.0.1:8099",
            {"X-HIRIS-Internal-Token": segreto, "X-Requested-With": "hiris-agent"},
            job_id="J-2")

    assert ok is False
    assert segreto not in motivo
    for record in caplog.records:
        assert segreto not in record.getMessage()


def test_il_token_non_compare_nel_log_del_turno_degradato(caplog):
    """Lo stesso, ma sul giro intero: nessuna riga di `_reason_chat` deve
    portare fuori il token, nemmeno quando tutto va storto."""
    segreto = "token-interno-segretissimo-99"

    class _Proc:
        returncode = 3
        stdout = '{"type":"result","subtype":"error","result":"boom"}\n'
        stderr = "errore"

    job = {"kind": "chat", "job_id": "J-3",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}

    with (
        caplog.at_level(logging.DEBUG),
        patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()),
    ):
        esito = runner._reason_chat(
            job, "live", client=_ClientFinto(_Risposta({}, 401)),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": segreto})

    assert segreto not in json.dumps(esito)
    for record in caplog.records:
        assert segreto not in record.getMessage()


# ---------------------------------------------------------------------------
# ④ e ⑤ LA SONDA VERA E LA RIENTRANZA, contro il server vero
# ---------------------------------------------------------------------------

def _base_url(client) -> str:
    return f"http://127.0.0.1:{client.server.port}"


def _semina_gli_archivi(app, tmp_path):
    """Gli archivi veri e la `entity_cache` vera nell'app gia' avviata.

    `view` e' l'unico strumento di lettura che legge la cache delle entita', ed e'
    **l'argomento portante** con cui il disegno giustifica una rotta invece di
    un sottoprocesso stdio separato (`handlers_mcp.py`, «la stessa
    `entity_cache` del turno sincrono»): senza di essa `view` risponderebbe
    sempre `stato_non_letto`, e avremmo due intelligenze nella stessa casa che
    ne vedono due diverse. Un'affermazione del genere si prova, non si cita."""
    casa = _semina_casa(tmp_path)
    memoria_db = str(tmp_path / "memoria.db")
    memoria = MemoryStore(memoria_db)
    app["archivio_casa"] = casa
    app["archivio_memoria"] = memoria
    app["entity_cache"] = _CacheViva({"light.cucina_1": "on",
                                      "light.cucina_2": "off"})
    return casa, memoria, memoria_db


class _CacheViva:
    """La forma vera di `entity_cache`: chiave "id", non "entity_id"
    (tests/test_knowledge_tools.py usa lo stesso doppio)."""

    loaded = True

    def __init__(self, stati):
        self._stati = stati

    def all_states(self):
        return [{"id": k, "state": v} for k, v in self._stati.items()]


@pytest.mark.asyncio
async def test_la_sonda_vera_contro_il_server_vero(ponte_con_configurazione_predefinita):
    """④ La prova che l'autenticazione della rotta e quella del ponte sono
    **lo stesso token**, e non due.

    Configurazione PREDEFINITA dell'add-on (`internal_token: ""`, quindi
    generato all'avvio) e valvole della suite rimosse: se il token che
    `build_headers()` legge da `os.environ` non fosse quello che l'app
    conosce, la rotta risponderebbe 401 e la sonda direbbe di no -- che e'
    esattamente il guasto gia' visto su questo ramo, quando il worker si
    prendeva 401 ogni tre secondi all'infinito.

    `probe_tools` e' sincrona e bloccante (httpx): gira in un thread,
    come in produzione (`run_loop` -> `run_in_executor`). Chiamata
    direttamente qui bloccherebbe il loop che deve servirla, e il test
    andrebbe in stallo invece di fallire."""
    client, _coda, app = ponte_con_configurazione_predefinita
    intestazioni = runner.build_headers()
    assert intestazioni["X-HIRIS-Internal-Token"] == app["internal_token"]

    with httpx.Client(timeout=30) as http:
        ok, motivo = await asyncio.to_thread(
            runner.probe_tools, http, _base_url(client), intestazioni)

    assert ok is True, f"la sonda ha detto no contro il server vero: {motivo}"
    assert motivo == ""


@pytest.mark.asyncio
async def test_la_sonda_vera_dice_no_col_token_sbagliato(ponte_con_configurazione_predefinita):
    """La mutazione del test qui sopra: senza il token giusto la rotta nega, e
    la sonda lo vede. E' cio' che prova che il test precedente misura
    l'autenticazione e non il fatto che la rotta esista."""
    client, _coda, _app = ponte_con_configurazione_predefinita

    with httpx.Client(timeout=30) as http:
        ok, motivo = await asyncio.to_thread(
            runner.probe_tools, http, _base_url(client),
            {"X-HIRIS-Internal-Token": "sbagliato"})

    assert ok is False
    assert "401" in motivo


@pytest.mark.asyncio
async def test_la_sonda_dice_si_anche_senza_archivi_e_va_dichiarato(
    ponte_con_configurazione_predefinita,
):
    """**Il limite di questa difesa, scritto invece che scoperto dopo.**

    `tools/list` risponde 200 con tutti i nomi **anche con gli archivi
    assenti** (l'anagrafe mai letta): il catalogo e' una costante, e l'errore
    «la conoscenza della casa non e' ancora stata caricata» sta DENTRO il
    risultato della singola `tools/call`, non nello stato HTTP. La sonda dice
    quindi di si', e fa bene: il modello **ha** gli strumenti, e ciascuno
    dichiarera' da se' se non puo' rispondere.

    Cio' che questa sonda NON prova e' che gli strumenti abbiano qualcosa da
    dire. Provarlo qui vorrebbe dire chiamarli sul serio a ogni turno -- una
    scrittura in memoria per una diagnosi -- e la difesa costerebbe piu' di
    cio' che difende."""
    client, _coda, app = ponte_con_configurazione_predefinita
    assert app.get("archivio_casa") is None

    with httpx.Client(timeout=30) as http:
        ok, _motivo = await asyncio.to_thread(
            runner.probe_tools, http, _base_url(client), runner.build_headers())
        assert ok is True

        risposta = await asyncio.to_thread(
            lambda: http.post(
                f"{_base_url(client)}/api/mcp", headers=runner.build_headers(),
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "search", "arguments": {"testo": "cucina"}}}))

    assert risposta.status_code == 200
    contenuto = risposta.json()["result"]
    assert contenuto["isError"] is True
    assert "non e' disponibile" in json.loads(contenuto["content"][0]["text"])["errore"]


@pytest.mark.asyncio
async def test_durante_l_invocazione_della_cli_l_addon_serve_davvero_la_callback(
    ponte_con_configurazione_predefinita, tmp_path,
):
    """⑤ **La cosa piu' forte e piu' specifica di questa fetta.**

    `test_run_loop_does_not_block_event_loop` prova gia' che il loop non si
    blocca. Questo prova l'altra meta', e non e' la stessa: che **mentre la
    CLI gira**, dal thread dell'executor, l'add-on **risponde davvero** alle
    chiamate degli strumenti. E' cio' che rende il disegno «una rotta e non un
    sottoprocesso» qualcosa di piu' di un'affermazione.

    Se un giorno qualcuno «semplificasse» chiamando `run_once` direttamente
    nella coroutine, la chat andrebbe in **stallo circolare**: il modello
    chiama lo strumento, l'HTTP non viene servito perche' il loop e' fermo
    dentro `subprocess.run`, e dopo cinque minuti scatta il timeout. Questo
    test e' cio' che glielo impedisce -- e fallirebbe **in stallo**, che e'
    l'unico modo onesto di fallire per questa proprieta'.

    Si esercitano **tutti e quattro** gli strumenti DI CONOSCENZA attraverso la
    rotta, `view` e `fetch` compresi (Minor noto del Task 1: non l'avevano mai
    attraversata), e `view` legge la `entity_cache` vera dell'app -- che e'
    l'argomento con cui il disegno ha scartato un sottoprocesso stdio."""
    client, coda, app = ponte_con_configurazione_predefinita
    casa, memoria, memoria_db = _semina_gli_archivi(app, tmp_path)
    try:
        base = _base_url(client)
        adesso = time.time()
        coda.enqueue("chat", {},
                     {"history": [{"role": "user", "content": "che luci?"}],
                      "system_prompt": "Sei HIRIS.", "contesto": "## La casa\nCucina",
                      "model": "sonnet"},
                     adesso + 300, now=adesso)

        visto: dict = {}

        def _finta_cli(argv, *a, **k):
            # QUI siamo nel thread dell'executor, e il "processo claude" sta
            # girando: e' il momento esatto in cui, in produzione, la CLI
            # chiama gli strumenti. Se l'add-on non servisse la callback
            # adesso, questo blocco resterebbe appeso.
            visto["argv"] = argv
            with httpx.Client(timeout=30) as dentro:
                def _rpc(corpo):
                    return dentro.post(f"{base}/api/mcp",
                                       headers=runner.build_headers(),
                                       json=corpo).json()

                elenco = _rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                visto["nomi"] = {v["name"] for v in elenco["result"]["tools"]}

                def _chiama(nome, argomenti):
                    risposta = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                     "params": {"name": nome, "arguments": argomenti}})
                    return json.loads(risposta["result"]["content"][0]["text"])

                visto["search"] = _chiama("search", {"testo": "cucina"})
                visto["view"] = _chiama("view", {"tipo": "area",
                                                     "riferimento": "cucina"})
                visto["remember"] = _chiama(
                    "remember", {"testo": "in cucina si cena alle 20",
                                "ancore": [{"tipo": "area", "riferimento": "cucina"}]})
                visto["fetch"] = _chiama("fetch", {"riferimento": "cucina",
                                                         "tipo": "area"})
            return _ProcFelice()

        with (
            patch.object(runner.subprocess, "run", _finta_cli),
            httpx.Client(timeout=30) as http,
        ):
            esito = await asyncio.to_thread(
                runner.run_once, http, base, runner.build_headers(), "live")

        assert esito == "done"
        # il giro di produzione ha collegato gli strumenti: prompt e argv insieme
        assert "--mcp-config" in visto["argv"]
        system = visto["argv"][visto["argv"].index("--system-prompt") + 1]
        assert prompts._GUIDE_WITH_TOOLS in system

        # la callback e' stata servita, e ha portato i nomi del catalogo
        assert visto["nomi"] == _NOMI_NUDI

        # `search` legge l'archivio della casa dell'app
        assert visto["search"]["trovati"]
        # `view` legge la STESSA entity_cache del turno sincrono: e' la
        # ragione per cui questa e' una rotta e non un sottoprocesso separato.
        stati = {e["id"]: e["stato"] for e in visto["view"]["entita"]}
        assert stati["light.cucina_1"] == "on"
        assert stati["light.cucina_2"] == "off"
        assert "stato_non_letto" not in visto["view"]
        # `remember` scrive davvero in memoria.db -- il guasto storico da cui
        # questo strumento e' nato («preso nota» senza salvare niente)
        assert visto["remember"]["salvato"] is True
        conn = sqlite3.connect(memoria_db)
        try:
            righe = [r[0] for r in conn.execute("SELECT testo FROM ricordi")]
        finally:
            conn.close()
        assert righe == ["in cucina si cena alle 20"]
        # `fetch` rilegge cio' che `remember` ha appena scritto, dalla stessa
        # rotta e nello stesso turno
        assert [r["testo"] for r in visto["fetch"]["ricordi"]] == [
            "in cucina si cena alle 20"]
    finally:
        memoria.close()
        casa.close()


def _riga_init(*, stato: str = "connected", nomi=None) -> str:
    """L'evento `system/init` come lo emette la CLI quando gli strumenti sono
    arrivati DAVVERO: il server col nostro nome in stato `connected`, e tutti e
    i `mcp__<server>__*` del catalogo nella lista `tools` risolta.

    Si costruisce da `runner.mcp_names()` e `runner._mcp_server_name()`, non a
    mano: un elenco ricopiato qui sarebbe il secondo catalogo, e uno
    strumento che entrasse in `home_space/tools.py` lascerebbe questo finto init
    disallineato dal vero senza che nessuno se ne accorga. `ToolSearch` c'e'
    perche' c'e' anche nel flusso vero (la CLI lo usa per risolvere gli schemi
    MCP) e perche' un `tools` con SOLO i nostri nomi renderebbe il test piu'
    facile del reale."""
    if nomi is None:
        nomi = list(runner.mcp_names())
    return json.dumps({
        "type": "system", "subtype": "init",
        "tools": ["ToolSearch", *nomi],
        "mcp_servers": [{"name": runner._mcp_server_name(), "status": stato}]})


_RIGA_RESULT = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
    "result": "in cucina una luce e' accesa",
    "usage": {"input_tokens": 10, "output_tokens": 5}})


class _ProcFelice:
    """Il turno che riesce, per intero.

    Task 4: fino a ieri questo finto stdout dichiarava UN solo strumento
    risolto (`mcp__hiris__search`) mentre il prompt li prometteva tutti --
    cioe' precisamente il guasto che il Task 4 esiste per scoprire. Passava
    perche' nessuno leggeva l'`init`. Ora si legge, e la forma dello stdout
    finto deve essere quella del flusso vero: e' la stessa passata che il
    Task 2 ha gia' dovuto fare una volta su questo file."""

    returncode = 0
    stdout = _riga_init() + "\n" + _RIGA_RESULT + "\n"
    stderr = ""


# ---------------------------------------------------------------------------
# ⑥ IL DEGRADO DICHIARATO: all'utente, non solo nel log
# ---------------------------------------------------------------------------

def test_il_turno_senza_strumenti_lo_dichiara_all_utente_e_nel_log(caplog):
    """Difesa ③ del progetto: «mai un `[errore runner]` criptico, mai una
    risposta che sembra normale».

    Gli strumenti erano ATTESI (il chiamante ha passato client e base_url) e
    la sonda non li ha trovati: la `reply` porta in testa la riga rivolta
    all'utente, e sotto resta la risposta vera che il modello ha comunque
    dato sul nucleo. Il log porta il motivo."""
    job = {"kind": "chat", "job_id": "J-degrado",
           "context": {"history": [{"role": "user", "content": "ciao"}],
                       "system_prompt": "Sei HIRIS.", "contesto": "## La casa\nx"}}

    with (
        caplog.at_level(logging.WARNING, logger="hiris.agent"),
        patch.object(runner.subprocess, "run", lambda *a, **k: _ProcFelice()),
    ):
        esito = runner._reason_chat(
            job, "live",
            client=_ClientFinto(_Risposta({"error": "unauthorized"}, 401)),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": "TOK"})

    reply = esito["reply"]
    assert reply.startswith(runner.MISSING_TOOLS_NOTICE)
    assert "non ho potuto usare gli strumenti" in reply
    # la risposta vera non si perde: la riga la PRECEDE, non la sostituisce --
    # ed e' il motivo per cui non e' fra i `_TOXIC_ASSISTANT_PREFIXES`.
    assert "in cucina una luce e' accesa" in reply

    messaggi = "\n".join(r.getMessage() for r in caplog.records
                         if r.name == "hiris.agent")
    assert "J-degrado" in messaggi and "401" in messaggi


def test_il_turno_con_gli_strumenti_non_dichiara_nessun_degrado(caplog):
    """Il complemento: quando gli strumenti ci sono, la reply e' la risposta e
    basta. Una riga di degrado che comparisse sempre sarebbe rumore, e
    smetterebbe di significare qualcosa."""
    job = {"kind": "chat", "job_id": "J-ok",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}
    catturato = {}

    def _run(argv, *a, **k):
        catturato["argv"] = argv
        return _ProcFelice()

    with (
        caplog.at_level(logging.WARNING, logger="hiris.agent"),
        patch.object(runner.subprocess, "run", _run),
    ):
        esito = runner._reason_chat(
            job, "live",
            client=_ClientFinto(_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200)),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": "TOK"})

    assert esito["reply"] == "in cucina una luce e' accesa"
    assert runner.MISSING_TOOLS_NOTICE not in esito["reply"]
    assert not [r for r in caplog.records if r.name == "hiris.agent"]
    # e la mcp-config nell'argv porta la URL vera e il token ricevuto
    config = json.loads(catturato["argv"][catturato["argv"].index("--mcp-config") + 1])
    assert config["mcpServers"]["hiris"]["url"] == "http://127.0.0.1:8099/api/mcp"
    assert config["mcpServers"]["hiris"]["headers"]["X-HIRIS-Internal-Token"] == "TOK"


def test_senza_client_non_c_e_degrado_da_dichiarare(caplog):
    """Il terzo stato non esiste per chi non ha mai atteso gli strumenti: un
    chiamante che non passa `client`/`base_url` non ha nessun `/api/mcp` a cui
    puntare la mcp-config, quindi non c'e' nessun guasto -- e' il vecchio
    comportamento, non un degrado nuovo. Un avviso qui sarebbe rumore, e il
    silenzio dichiarato smetterebbe di distinguersi."""
    job = {"kind": "chat", "job_id": "J-locale",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}

    with (
        caplog.at_level(logging.WARNING, logger="hiris.agent"),
        patch.object(runner.subprocess, "run", lambda *a, **k: _ProcFelice()),
    ):
        esito = runner._reason_chat(job, "live")

    assert esito["reply"] == "in cucina una luce e' accesa"
    assert not [r for r in caplog.records if r.name == "hiris.agent"]


def test_la_riga_di_degrado_non_precede_i_sentinella_di_guasto():
    """Gli altri sentinella del ponte (`[errore runner rc=...]`,
    `[runner non disponibile]`, `[flusso incompleto]`, `[vuoto]`) sono
    riconosciuti **per prefisso** da `chat_store._TOXIC_ASSISTANT_PREFIXES`:
    anteporre qualcosa li renderebbe invisibili a quel filtro e tornerebbero
    al modello a ogni turno successivo -- un guasto gia' trovato dal vivo su
    questo ramo e riparato una volta.

    Quindi la riga di degrado precede SOLO una risposta vera."""
    class _ProcRotto:
        returncode = 7
        stdout = '{"type":"result","subtype":"error","result":"quota"}\n'
        stderr = ""

    job = {"kind": "chat", "job_id": "J-rotto",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}

    with patch.object(runner.subprocess, "run", lambda *a, **k: _ProcRotto()):
        esito = runner._reason_chat(
            job, "live", client=_ClientFinto(_Risposta({}, 401)),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": "TOK"})

    assert esito["reply"].startswith("[errore runner rc=7]")
    assert runner.MISSING_TOOLS_NOTICE not in esito["reply"]


# ---------------------------------------------------------------------------
# FIX ROUND 1, Important 1 -- il ramo attivo non deve leggere frasi scritte per
# il ramo spento. `_CONTESTO_PRESENTE` esce su ENTRAMBI i rami ed e' l'ULTIMA
# cosa che il modello legge prima del blocco `## La casa`: una sua clausola
# falsa al presente pesa piu' della guida, che sta sopra.
# ---------------------------------------------------------------------------

# Le due clausole uscite da `_CONTESTO_PRESENTE`. Scritte qui come costanti e
# non ricopiate in ogni assert: se un giorno rientrassero con parole leggermente
# diverse, il posto da aggiornare e' uno solo.
_CONTRORDINI = (
    "non e' aggiornabile in questo turno",
    "invece di rispondere che non puoi richiamarlo",
)


@pytest.mark.parametrize("strumenti_attivi", [True, False])
def test_il_blocco_del_contesto_non_contraddice_nessuno_dei_due_rami(strumenti_attivi):
    """Le due clausole non devono rientrare su NESSUNO dei due rami.

    Sul ramo attivo sono un contrordine e sono false. Sul ramo di degrado sono
    ridondanti -- e la ridondanza e' stata verificata prima di togliere, non
    assunta: e' il test qui sotto."""
    system, _u = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto="## La casa\nSalotto: luce accesa.",
        active_tools=strumenti_attivi)

    for clausola in _CONTRORDINI:
        assert clausola not in system, (
            f"{clausola!r} e' rientrata nel prompt: sul ramo attivo contraddice "
            "l'ordine di chiamare lo strumento due righe sopra, ed e' falsa -- "
            "il tester vedrebbe `status: connected` nel log, nessuna "
            "tools/call, e una risposta costruita sullo snapshot")


def test_la_ridondanza_che_ha_permesso_di_togliere_le_due_clausole():
    """**La verifica, non l'assunzione.** Togliere una clausola dal prompt del
    ramo di degrado si puo' solo se cio' che diceva resta detto altrove: se
    domani qualcuno alleggerisse `_GUIDE_WITHOUT_TOOLS`, questo test diventa
    rosso e dice che la rimozione di allora non e' piu' coperta.

    - «non e' aggiornabile in questo turno» -> la guida dice gia' che non si
      puo' guardare adesso, e ordina di DIRLO quando servirebbe un valore
      corrente;
    - «cercalo li' dentro invece di rispondere che non puoi richiamarlo» ->
      la compensazione dell'assenza di `fetch` resta detta due volte nello
      stesso blocco del contesto («ricordi e sessioni precedenti compresi»,
      «Usala per rispondere»), e il divieto di negare la memoria e' intatto."""
    system, _u = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto="## Cio' che le persone hanno detto\n- la caldaia perde",
        active_tools=False)

    # cio' che copre la prima clausola tolta
    assert "non puoi guardare adesso lo stato della casa" in prompts._GUIDE_WITHOUT_TOOLS
    assert "servirebbe un valore aggiornato ADESSO, DILLO" in system
    # cio' che copre la seconda
    assert "ricordi e sessioni precedenti compresi" in system
    assert "Usala per rispondere" in system
    assert "richiamare ricordi" not in system, (
        "il prompt e' tornato a NEGARE la memoria mentre il ricordo e' scritto "
        "tre blocchi piu' sotto: e' la falsita' speculare gia' chiusa una volta")
    assert "la caldaia perde" in system


def test_il_blocco_del_contesto_resta_uno_solo_su_entrambi_i_rami():
    """Nessun terzo testo, e nessuna biforcazione nella composizione: e' lo
    STESSO `_CONTESTO_PRESENTE` che esce sui due rami. Se un giorno diventasse
    condizionale, sarebbero due testi da tenere veri invece di uno."""
    with_, _u = prompts.build_chat_messages("Sei HIRIS.", [], contesto="X",
                                            active_tools=True)
    without, _u2 = prompts.build_chat_messages("Sei HIRIS.", [], contesto="X",
                                               active_tools=False)
    assert prompts._CONTESTO_PRESENTE in with_
    assert prompts._CONTESTO_PRESENTE in without


# ---------------------------------------------------------------------------
# FIX ROUND 1, Important 2 -- il token non esce da NESSUNO dei canali che
# portano fuori lo stdout/stderr del sottoprocesso.
#
# Prima di questo task era innocuo: l'argv non conteneva segreti. Da oggi il
# token viaggia in `--mcp-config`, ed e' il genere di stringa che una CLI
# riecheggia quando rifiuta o non riesce a connettere il server MCP. I canali
# sono CINQUE, e si chiudono tutti in un punto solo (`reda_segreti`, applicata
# appena il sottoprocesso risponde): ① il log del ramo rc!=0; ② la reply del
# ramo rc!=0 quando non c'e' un dettaglio strutturato; ③ la reply del ramo
# rc!=0 quando il dettaglio strutturato c'e' ma porta l'eco; ④ la coda di 200
# caratteri del flusso incompleto (canale introdotto dal Task 2); ⑤ il testo
# del risultato sul ramo felice.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FIX ROUND 2 -- la redazione redigeva la RAPPRESENTAZIONE SBAGLIATA.
#
# I test del giro precedente provavano la difesa con un solo token urlsafe:
# per quei token la forma grezza e quella JSON-encoded COINCIDONO, quindi la
# difesa sembrava funzionare. `hiris/config.yaml` espone pero' `internal_token`
# come `password` libera, e con un token che contiene `"` o `\` nell'argv
# finisce la forma **escaped** -- che la redazione, cercando la grezza, mancava
# su tutti e cinque i canali. Provare una difesa solo con l'input facile e' la
# stessa classe di problema dei quattro test del giro ancora precedente: da qui
# in giu' OGNI canale si prova con ENTRAMBI i token.
# ---------------------------------------------------------------------------

_TOKEN_URLSAFE = "TOKEN-SEGRETISSIMO-42"
# Il token che ROMPE: virgolette e backslash. E' ammesso dalla validazione di
# `token_interno` (sono caratteri header-safe: cio' che quella validazione
# rifiuta sono i caratteri di CONTROLLO) -- quindi puo' arrivare fin qui, ed e'
# esattamente il motivo per cui questa seconda difesa esiste.
_TOKEN_ROTTO = 'ab"cd\\ef'

# I due token si passano a ogni canale. Gli id rendono leggibile quale dei due
# ha fallito quando il rosso arriva.
_TOKEN_IDS = ["urlsafe", "con-virgolette-e-backslash"]
_TOKEN_SPIE = [_TOKEN_URLSAFE, _TOKEN_ROTTO]


def _eco_della_cli(token: str) -> str:
    """L'eco realistica: la CLI ripete la mcp-config che le abbiamo passato.

    Si costruisce dalla `config_mcp` VERA e non a mano: e' l'unico modo perche'
    il token compaia qui nella stessa forma in cui compare nell'argv -- ed e'
    proprio la differenza fra le due forme il difetto che questo giro chiude."""
    return ("Error: failed to connect to MCP server from --mcp-config "
            + runner.config_mcp("http://127.0.0.1:8099", token))


def _ricostruibile(token: str, testo: str) -> bool:
    """**L'oracolo forte.** Non «la forma X compare», che dipende da quanti
    involucri JSON (o da un `%r`) ci sono in mezzo, ma «il segreto e'
    ricostruibile»: si tolgono TUTTI i backslash da entrambi i lati e si
    guarda se il token resta dentro. Un oracolo per forme esatte e' proprio
    quello che ha fatto sembrare chiuso il fix del giro precedente."""
    def nudo(t):
        return t.replace("\\", "")
    return nudo(token) in nudo(testo)


def _con_strumenti_e_processo(proc, caplog, token=_TOKEN_URLSAFE):
    """Il turno pericoloso: strumenti ATTIVI (quindi il token E' nell'argv) e
    un sottoprocesso che riecheggia la configurazione."""
    job = {"kind": "chat", "job_id": "J-eco",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}
    argv_visti = []

    def _run(argv, *a, **k):
        # Task 4: si registrano TUTTE le invocazioni, non solo l'ultima. Da
        # questo task un turno puo' invocare due volte (quando l'init smentisce
        # la sonda), e la premessa qui sotto riguarda la PRIMA -- l'unica in
        # cui il token entra nell'argv.
        argv_visti.append(argv)
        return proc

    with caplog.at_level(logging.DEBUG), patch.object(runner.subprocess, "run", _run):
        esito = runner._reason_chat(
            job, "live",
            client=_ClientFinto(_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200)),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": token})
    # La premessa del test, asserita e non assunta: senza il token nell'argv non
    # si starebbe provando niente. Si usa l'oracolo forte perche' per il token
    # che rompe la forma nell'argv NON e' quella grezza -- ed e' precisamente
    # l'errore che la premessa del giro precedente commetteva.
    assert _ricostruibile(token, " ".join(argv_visti[0])), (
        "il token non e' nell'argv: questo test non sta provando la difesa")
    return esito, "\n".join(r.getMessage() for r in caplog.records)


def test_reda_segreti_non_esplode_su_un_segreto_vuoto():
    """`"".replace("", "***")` sostituirebbe ogni posizione della stringa: e'
    il modo in cui una redazione distrugge cio' che doveva proteggere."""
    assert runner.reda_segreti("abc", "") == "abc"
    assert runner.reda_segreti("abc", None or "") == "abc"
    assert runner.reda_segreti("a-TOK-b", "TOK") == f"a-{runner.REDATTO}-b"


def test_reda_segreti_sostituisce_la_forma_piu_lunga_per_prima():
    """Due forme dello stesso segreto in cui una contiene l'altra: se si
    sostituisse la corta per prima, resterebbe in giro un pezzo della lunga."""
    testo = "prima ABCDEF poi ABC"
    assert runner.reda_segreti(testo, "ABC", "ABCDEF") == (
        f"prima {runner.REDATTO} poi {runner.REDATTO}")


def test_forme_del_token_copre_i_due_livelli_di_annidamento():
    """La misura che ha chiuso il giro: il token compare a tre profondita' --
    grezza, dentro la stringa JSON di `--mcp-config`, e dentro l'evento
    `stream-json` che a sua volta cita quella config."""
    forme = runner.token_forms(_TOKEN_ROTTO)

    assert forme[0] == _TOKEN_ROTTO
    assert forme[1] == json.dumps(_TOKEN_ROTTO)[1:-1]
    assert forme[2] == json.dumps(json.dumps(_TOKEN_ROTTO)[1:-1])[1:-1]
    assert len(forme) == 3
    # per un token urlsafe le tre forme COINCIDONO: una sola, senza doppioni --
    # ed e' il motivo per cui il difetto era invisibile ai test di prima.
    assert runner.token_forms(_TOKEN_URLSAFE) == (_TOKEN_URLSAFE,)
    assert runner.token_forms("") == ()


def test_la_forma_nell_argv_non_e_quella_grezza_per_un_token_con_virgolette():
    """Il difetto, isolato: e' la premessa di tutto questo giro."""
    config = runner.config_mcp("http://127.0.0.1:8099", _TOKEN_ROTTO)

    assert _TOKEN_ROTTO not in config, (
        "se la forma grezza fosse nella config, non ci sarebbe nessun difetto "
        "da chiudere e questo test non starebbe difendendo niente")
    assert json.dumps(_TOKEN_ROTTO)[1:-1] in config


@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_canali_1_e_2_il_token_non_esce_dal_log_ne_dalla_reply_su_rc_diverso_da_zero(
    caplog, token,
):
    """(1) e (2). Il caso riprodotto dalla review: `rc != 0`, l'eco della
    mcp-config su stderr e nessun evento `result` da cui ricavare un dettaglio
    strutturato -- quindi il grezzo finisce **nella reply che l'utente legge in
    chat** e nel log che si incolla in una segnalazione."""
    class _Proc:
        returncode = 1
        stdout = ""
        stderr = _eco_della_cli(token)

    esito, log_testo = _con_strumenti_e_processo(_Proc(), caplog, token)

    assert esito["reply"].startswith("[errore runner rc=1]")
    assert not _ricostruibile(token, esito["reply"]), (
        "l'utente legge il proprio token in chat")
    assert not _ricostruibile(token, log_testo), (
        "il token e' nel log dell'add-on, cioe' nel file che si incolla in una "
        "segnalazione")
    # ...e la diagnosi non si perde: la causa resta leggibile, redatta
    assert "failed to connect to MCP server" in esito["reply"]
    assert runner.REDATTO in esito["reply"]


@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_canale_3_il_token_non_esce_dal_dettaglio_strutturato(caplog, token):
    """(3). Stesso ramo, ma con l'evento `result` presente: il dettaglio viene
    da `esito.testo`, cioe' dallo stdout **PARSATO** -- e li' lo stdout grezzo
    e' un JSON che ne contiene un altro, quindi il token sta a profondita' 2.
    E' uno dei due canali che il fix round 1 lasciava aperti."""
    class _Proc:
        returncode = 1
        stdout = json.dumps({"type": "result", "subtype": "error_during_execution",
                             "is_error": True, "result": _eco_della_cli(token)}) + "\n"
        stderr = ""

    esito, log_testo = _con_strumenti_e_processo(_Proc(), caplog, token)

    assert not _ricostruibile(token, esito["reply"])
    assert not _ricostruibile(token, log_testo)
    assert runner.REDATTO in esito["reply"]


@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_canale_4_il_token_non_esce_dalla_coda_del_flusso_incompleto(caplog, token):
    """(4). Il canale che il **Task 2** ha introdotto: `rc == 0` ma nessun
    evento finale, e gli ultimi 200 caratteri dello stdout grezzo finiscono
    nella reply. Era il canale piu' facile da dimenticare, perche' non e' un
    ramo d'errore."""
    class _Proc:
        returncode = 0
        stdout = ('{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
                  + _eco_della_cli(token))
        stderr = ""

    esito, log_testo = _con_strumenti_e_processo(_Proc(), caplog, token)

    assert esito["reply"].startswith("[flusso incompleto]")
    assert "ultimo pezzo di flusso letto" in esito["reply"]
    assert not _ricostruibile(token, esito["reply"])
    assert not _ricostruibile(token, log_testo)


@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_canale_5_il_token_non_esce_dal_testo_del_risultato(caplog, token):
    """(5). Il ramo FELICE: `rc == 0`, evento `result` presente, ma la CLI ha
    messo l'eco dentro il testo. E' il canale meno probabile e il piu'
    pericoloso, perche' quella reply non porta nessun sentinella: sembra una
    risposta normale. Anche qui il testo viene dallo stdout PARSATO, ed era il
    secondo canale che il fix round 1 lasciava aperto."""
    class _Proc:
        returncode = 0
        stdout = json.dumps({"type": "result", "subtype": "success",
                             "is_error": False, "num_turns": 1,
                             "result": f"ecco cosa e' successo: {_eco_della_cli(token)}"}) + "\n"
        stderr = ""

    esito, log_testo = _con_strumenti_e_processo(_Proc(), caplog, token)

    assert not _ricostruibile(token, esito["reply"])
    assert not _ricostruibile(token, log_testo)
    assert runner.REDATTO in esito["reply"]


def test_la_redazione_non_tocca_il_turno_senza_strumenti(caplog):
    """Il complemento: senza strumenti il token non e' mai stato nell'argv, e
    la redazione non deve alterare cio' che la CLI dice -- una reply
    inspiegabilmente piena di `***` sarebbe un guasto nuovo."""
    class _Proc:
        returncode = 0
        stdout = json.dumps({"type": "result", "subtype": "success",
                             "is_error": False,
                             "result": "in cucina una luce e' accesa"}) + "\n"
        stderr = ""

    job = {"kind": "chat", "job_id": "J-pulito",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}
    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        esito = runner._reason_chat(job, "live")

    assert esito["reply"] == "in cucina una luce e' accesa"
    assert runner.REDATTO not in esito["reply"]


# ---------------------------------------------------------------------------
# TASK 4, nit 1 della review del Task 3 -- IL SETTIMO CANALE.
#
# I cinque canali qui sopra nascono dallo stdout della CLI. Il sesto e' la
# reply. Il settimo e' un'ECCEZIONE: `run_once` fa HTTP verso la reasoning API
# con gli header del claim, che portano `X-HIRIS-Internal-Token`, e con un
# valore che il protocollo non accetta il client solleva **col valore dentro**.
# Il catch del giro lo logga. Era irraggiungibile solo grazie a una difesa che
# sta in un altro file (la validazione del token all'avvio) e che nessun test
# legava a queste due righe.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_il_settimo_canale_l_eccezione_del_giro_non_porta_il_token(monkeypatch, token):
    """Il messaggio dell'eccezione non si butta -- `run_once errore:
    HTTPStatusError` non direbbe ne' quale rotta ne' quale codice, e un log che
    non serve a diagnosticare e' il primo che smette di essere letto -- ma
    passa dalla redazione che c'e' gia'."""
    monkeypatch.setenv("INTERNAL_TOKEN", token)
    exc = httpx.LocalProtocolError(f"Illegal header value b'{token}'")

    motivo = runner._exception_reason(exc)

    assert not _ricostruibile(token, motivo), (
        "il token e' nel log del giro, cioe' nel file che si incolla in una "
        "segnalazione")
    # ...e la diagnosi resta: tipo dell'eccezione e causa, redatta
    assert "LocalProtocolError" in motivo
    assert "Illegal header value" in motivo and runner.REDATTO in motivo


def test_i_due_giri_del_runner_loggano_l_eccezione_redatta():
    """I punti di perdita sono **due** -- `run_loop` (in-addon) e `main()` (il
    runner come processo a se') -- e una difesa applicata a uno solo dei due
    lascia aperto l'altro: e' la classe di difetto che questo prodotto ha gia'
    pagato con la redazione dello stdout, chiusa in un punto e dimenticata in
    quelli del catalogo."""
    import inspect

    atteso = 'log.warning("run_once errore: %s", _exception_reason(exc))'
    for funzione in (runner.run_loop, runner.main):
        assert atteso in inspect.getsource(funzione), (
            f"{funzione.__name__} logga l'eccezione GREZZA: con un token non "
            "consegnabile ne porterebbe il valore")


# ---------------------------------------------------------------------------
# TASK 4 -- L'`init` SMENTISCE LA SONDA: si butta l'invocazione, non si
# corregge il prompt.
#
# La sonda (difesa 1) prova che la rotta risponde con tutti i nomi DAL NOSTRO
# LATO. L'evento `system/init` dice se la CLI ci e' ARRIVATA: fra i due ci sono
# Node, il parsing della stringa `--mcp-config`, `--strict-mcp-config` e il
# loopback visto da un altro processo -- tutta la superficie a cui nessuna
# suite verde puo' rispondere. Quando i due si contraddicono, il prompt e' gia'
# partito affermando strumenti che il modello non ha.
#
# Cosa si difende qui:
#   (a) il guasto viene VISTO in tutte le sue forme (server `failed`, server
#       connesso ma strumenti a meta', `init` assente del tutto);
#   (b) l'invocazione si BUTTA: prompt e argv si ricompongono INSIEME dal
#       booleano a `False`, e l'invariante dei due versi vale anche al secondo
#       giro;
#   (c) **una sola volta**: due invocazioni per turno, mai tre, nemmeno quando
#       anche la seconda fallisce. E' un tetto di costo oltre che di logica;
#   (d) l'utente lo legge, con la STESSA riga della difesa (1) -- due testi per
#       lo stesso fatto sarebbero due cose da tenere vere;
#   (e) il token non compare in nessuno dei percorsi nuovi.
# ---------------------------------------------------------------------------


def _proc(rc=0, stdout="", stderr=""):
    return type("_ProcFinto", (), {"returncode": rc, "stdout": stdout,
                                   "stderr": stderr})()


class _CliFinta:
    """Una CLI finta che RICORDA ogni invocazione.

    Contare le invocazioni e' l'unico modo di provare un tetto di costo: un
    finto `subprocess.run` che restituisce e basta direbbe che il ponte
    risponde, non quante volte ha pagato per farlo. L'ultimo processo si
    ripete se le invocazioni superano i processi dati, cosi' un test che
    volesse provare "non c'e' un terzo giro" non finisce per misurare la
    lunghezza della propria lista."""

    def __init__(self, *procs):
        self.procs = list(procs)
        self.argv = []

    def __call__(self, argv, *a, **k):
        self.argv.append(list(argv))
        return self.procs[min(len(self.argv) - 1, len(self.procs) - 1)]

    @property
    def invocations(self) -> int:
        return len(self.argv)

    def system(self, n: int) -> str:
        argv = self.argv[n]
        return argv[argv.index("--system-prompt") + 1]


def _turno(cli, *, token="TOK", job_id="J-init", sonda=True):
    """Un turno del ponte con gli strumenti ATTESI (client + base_url), la
    sonda che dice di si', e la CLI finta al posto del sottoprocesso."""
    job = {"kind": "chat", "job_id": job_id,
           "context": {"history": [{"role": "user", "content": "che luci?"}],
                       "system_prompt": "Sei HIRIS.", "contesto": "## La casa\nx"}}
    risposta = (_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200) if sonda
                else _Risposta({"error": "unauthorized"}, 401))
    client = _ClientFinto(risposta)
    with patch.object(runner.subprocess, "run", cli):
        esito = runner._reason_chat(
            job, "live", client=client, base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": token})
    return esito, client


def _messaggi(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records
                     if r.name == "hiris.agent")


# -- (a) il guasto viene visto, nelle sue tre forme -------------------------

@pytest.mark.parametrize("init_rotto, come", [
    (_riga_init(stato="failed"), "server-failed"),
    (_riga_init(nomi=list(runner.mcp_names())[:3]), "lista-strumenti-incompleta"),
    ("", "init-assente"),
], ids=["server-failed", "lista-strumenti-incompleta", "init-assente"])
def test_l_init_che_smentisce_la_sonda_butta_l_invocazione(init_rotto, come, caplog):
    """① ② ④ del brief, in un test solo perche' e' UN fatto solo: qualunque
    modo l'`init` abbia di smentire la sonda porta allo stesso esito.

    - **server `failed`**: il guasto conclamato -- Node non ha collegato la
      rotta, o la mcp-config non e' stata digerita;
    - **lista incompleta**: un server connesso che non espone tutto e'
      lo stesso guasto visto da un'altra parte, e per il modello e' peggio,
      perche' il prompt li nomina uno per uno;
    - **`init` assente**: CLI piu' vecchia, `--verbose` che non arriva, formato
      cambiato. Vale **guasto, non conferma**: un'assenza non e' una conferma,
      o la promessa del prompt finirebbe per dipendere da cio' che non e'
      stato detto."""
    stdout = (init_rotto + "\n" if init_rotto else "") + _RIGA_RESULT + "\n"
    cli = _CliFinta(_proc(0, stdout), _ProcFelice())

    # Task 6 (fix round 1, Important): l'identita' del turno
    # (`secrets.token_urlsafe`, minted in `_reason_chat` PRIMA di `_invoca`)
    # deve restare la STESSA anche quando il turno si sdoppia in due
    # invocazioni -- e' esattamente questo test, l'unico che sdoppia un
    # turno, il posto in cui quell'invariante puo' rompersi. Prima di questo
    # fix nessun test in tutta la suite chiamava mai `config_mcp` col terzo
    # argomento ne' verificava quante volte l'identita' viene coniata: una
    # decisione protetta da un commento invece che da una rete. La spia conta
    # le chiamate VERE a `secrets.token_urlsafe` (non solo quelle che finiscono
    # nell'argv: oggi la seconda invocazione riparte senza strumenti e non
    # chiama mai `config_mcp`, ma la conta deve restare giusta anche se quel
    # dettaglio cambiasse) -- e' lo stesso controllo fatto a mano nello
    # scratchpad in fase di sviluppo, portato dentro la suite.
    identita_coniate = []
    vera_token_urlsafe = runner.secrets.token_urlsafe

    def _spia_token_urlsafe(*a, **k):
        valore = vera_token_urlsafe(*a, **k)
        identita_coniate.append(valore)
        return valore

    with caplog.at_level(logging.WARNING, logger="hiris.agent"), \
         patch.object(runner.secrets, "token_urlsafe", _spia_token_urlsafe):
        esito, client = _turno(cli, job_id=f"J-{come}")

    # (b) l'invocazione si e' BUTTATA e se n'e' composta un'altra
    assert cli.invocations == 2

    # L'INVARIANTE del fix: UNA identita' sola per l'intero turno, non una
    # per invocazione della CLI. Se `exchange_id = secrets.token_urlsafe(9)`
    # migrasse DENTRO `_invoca` -- errore facilissimo, dato che il codice gia'
    # chiama `config_mcp` dentro quella chiusura -- verrebbe coniata due
    # volte (una per ciascuna delle due chiamate a `_invoca` sopra) e questo
    # assert diventa rosso. Verificato per mutazione durante lo sviluppo di
    # questo fix (spostata l'assegnazione dentro `_invoca`, il test e' andato
    # rosso, ripristinato): vedi il report, sezione "Fix round 1".
    assert len(identita_coniate) == 1, (
        f"l'identita' di turno e' stata coniata {len(identita_coniate)} volte "
        "in un turno sdoppiato (attese: 1): il tetto per-turno della rotta "
        "MCP raddoppierebbe in silenzio")
    # ...e la seconda e' composta dall'ALTRO valore dello stesso booleano:
    # niente mcp-config, e la guida che nega gli strumenti. L'invariante dei
    # due versi vale anche qui, ed e' la ragione per cui il prompt si RICOMPONE
    # invece di essere rattoppato.
    assert "mcpconfig" in _normalizza(cli.argv[0])
    assert "mcpconfig" not in _normalizza(cli.argv[1])
    assert "allowedtools" not in _normalizza(cli.argv[1])
    assert prompts._GUIDE_WITH_TOOLS in cli.system(0)
    assert prompts._GUIDE_WITHOUT_TOOLS in cli.system(1)
    assert prompts._GUIDE_WITH_TOOLS not in cli.system(1)

    # (d) l'utente lo legge, e sotto resta la risposta vera
    assert esito["reply"].startswith(runner.MISSING_TOOLS_NOTICE)
    assert "in cucina una luce e' accesa" in esito["reply"]

    # il silenzio (2), dichiarato: job_id + il motivo, e il motivo dice cosa
    # la CLI ha davvero collegato
    testo = _messaggi(caplog)
    assert f"J-{come}" in testo
    assert "system/init smentisce la sonda" in testo

    # la sonda NON si ripete: la decisione e' una sola, presa una volta sola.
    # Una seconda sonda sarebbe un secondo punto di decisione da tenere
    # allineato -- esattamente cio' che l'interruttore unico esiste per negare.
    assert len(client.chiamate) == 1


def test_il_motivo_del_silenzio_2_nomina_lo_stato_e_i_nomi_mancanti(caplog):
    """«Non ha funzionato» senza il PERCHE' e' un silenzio con una riga di log
    intorno. Il motivo deve portare lo stato dei server e i nomi che la CLI non
    ha risolto: sono le due sole informazioni da cui, davanti al log di un
    utente UAT, si capisce da che parte guardare."""
    mancante = min(runner.mcp_names())
    nomi = [n for n in runner.mcp_names() if n != mancante]
    cli = _CliFinta(_proc(0, _riga_init(nomi=nomi) + "\n" + _RIGA_RESULT + "\n"),
                    _ProcFelice())

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        _turno(cli, job_id="J-motivo")

    testo = _messaggi(caplog)
    assert "'connected'" in testo          # lo stato atteso, dichiarato
    assert mancante in testo               # il nome che manca, per esteso
    assert "J-motivo" in testo


# -- (b) il complemento: l'init regolare non costa niente -------------------

def test_l_init_regolare_non_fa_ricomporre_niente(caplog):
    """③ del brief. Il costo della difesa (2) si paga **solo quando il guasto
    c'e' davvero**: col flusso buono l'invocazione resta una, la reply e' la
    risposta e basta, e non c'e' nessun avviso da leggere. Una difesa che
    costasse un'invocazione a ogni turno sarebbe stata scartata dal progetto."""
    cli = _CliFinta(_ProcFelice())

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        esito, _client = _turno(cli, job_id="J-buono")

    assert cli.invocations == 1
    assert esito["reply"] == "in cucina una luce e' accesa"
    assert runner.MISSING_TOOLS_NOTICE not in esito["reply"]
    assert not [r for r in caplog.records if r.name == "hiris.agent"]


def test_senza_strumenti_attesi_l_init_rotto_non_scatena_niente(caplog):
    """Il secondo tentativo non ha nessun `init` da verificare, e chi non ha
    mai atteso gli strumenti nemmeno: la verifica gira **solo** quando il
    booleano diceva `True`. Senza questo, il turno degradato controllerebbe la
    presenza di strumenti che ha appena deciso di non chiedere -- e ogni turno
    del ramo di degrado costerebbe due invocazioni."""
    cli = _CliFinta(_proc(0, _riga_init(stato="failed") + "\n" + _RIGA_RESULT + "\n"))
    job = {"kind": "chat", "job_id": "J-nessun-cliente",
           "context": {"history": [], "system_prompt": "Sei HIRIS.", "contesto": "x"}}

    with (
        caplog.at_level(logging.WARNING, logger="hiris.agent"),
        patch.object(runner.subprocess, "run", cli),
    ):
        esito = runner._reason_chat(job, "live")

    assert cli.invocations == 1
    assert esito["reply"] == "in cucina una luce e' accesa"
    assert "smentisce la sonda" not in _messaggi(caplog)


# -- (c) il tetto: due invocazioni, mai tre --------------------------------

def test_mai_piu_di_due_invocazioni_nemmeno_quando_anche_la_seconda_fallisce(caplog):
    """⑥ del brief, e non e' una ridondanza dei test qui sopra: quelli provano
    che il secondo giro AVVIENE, questo che non ne esiste un terzo **proprio
    nel caso in cui la tentazione di riprovare e' massima** -- il secondo
    tentativo fallisce a sua volta.

    Un ciclo qui sarebbe peggio del guasto: moltiplicherebbe per N il costo di
    un turno che sta gia' fallendo, e sull'abbonamento quel costo e' il tetto
    giornaliero dell'utente."""
    rotto = _proc(1, "", "Error: MCP server 'hiris' failed to start")
    cli = _CliFinta(_proc(0, _riga_init(stato="failed") + "\n" + _RIGA_RESULT + "\n"),
                    rotto)

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        esito, _client = _turno(cli, job_id="J-due-volte")

    assert cli.invocations == 2 == runner.MAX_INVOCATIONS_PER_EXCHANGE
    # Step 4: si restituisce l'esito d'errore del Task 2, senza un terzo giro
    assert esito["reply"].startswith("[errore runner rc=1]")
    # ...e il sentinella resta il PRIMO carattere della reply: anteporre
    # l'avviso lo renderebbe invisibile a `chat_store._TOXIC_ASSISTANT_PREFIXES`
    assert runner.MISSING_TOOLS_NOTICE not in esito["reply"]
    # il log dice che si e' arrivati qui DOPO un ri-tentativo: senza, «claude
    # rc=1» sembrerebbe il primo guasto del turno invece dell'ultimo di due
    assert "secondo e ULTIMO tentativo" in _messaggi(caplog)


def test_il_tetto_e_un_contatore_non_una_forma():
    """Il tetto non e' affidato al fatto che le due chiamate stiano in fila
    invece che in un ciclo: e' una costante letta da un contatore. Questo test
    la pinna, perche' il giorno in cui qualcuno trasformasse quella sequenza in
    un ciclo il costo per turno resti due invocazioni invece di diventare
    illimitato."""
    assert runner.MAX_INVOCATIONS_PER_EXCHANGE == 2


# -- (d) una sola formulazione per un solo fatto ---------------------------

def test_le_due_difese_dicono_all_utente_la_stessa_identica_riga():
    """⑤ del brief. La sonda che dice di no e l'`init` che smentisce sono due
    scoperte diverse dello **stesso fatto**: in questo turno gli strumenti non
    ci sono. Due testi diversi sarebbero due cose da tenere vere, e la seconda
    invecchierebbe."""
    dalla_sonda, _c = _turno(_CliFinta(_ProcFelice()), sonda=False)
    dall_init, _c2 = _turno(
        _CliFinta(_proc(0, _riga_init(stato="failed") + "\n" + _RIGA_RESULT + "\n"),
                  _ProcFelice()))

    prima = dalla_sonda["reply"].split("\n\n")[0]
    assert prima == dall_init["reply"].split("\n\n")[0]
    assert prima == runner.MISSING_TOOLS_NOTICE


# -- (e) il token non entra nei percorsi nuovi -----------------------------

@pytest.mark.parametrize("token", _TOKEN_SPIE, ids=_TOKEN_IDS)
def test_il_token_non_esce_dal_percorso_di_ri_invocazione(caplog, token):
    """I percorsi nuovi di questo task sono due -- il motivo del silenzio (2) e
    la reply del secondo tentativo -- e il primo turno del giro e' proprio
    quello in cui il token E' nell'argv. Si prova con **entrambi** i token,
    perche' per un urlsafe la forma grezza e quella JSON-escaped coincidono e
    una difesa rotta sembrerebbe funzionare (e' il difetto del fix round 1)."""
    # la CLI fallisce a collegare il server e RIECHEGGIA la mcp-config: e' il
    # caso realistico, non uno costruito -- la config e' cio' che la CLI cita
    # quando non riesce ad avviare un server MCP.
    primo = _proc(0, _riga_init(stato="failed") + "\n" + json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": _eco_della_cli(token)}) + "\n")
    cli = _CliFinta(primo, _ProcFelice())

    with caplog.at_level(logging.DEBUG):
        esito, _client = _turno(cli, token=token, job_id="J-eco-init")

    assert cli.invocations == 2
    assert _ricostruibile(token, " ".join(cli.argv[0])), (
        "il token non e' nell'argv del primo tentativo: questo test non sta "
        "provando niente")
    assert not _ricostruibile(token, esito["reply"])
    assert not _ricostruibile(
        token, "\n".join(r.getMessage() for r in caplog.records))


# -- la verifica in se', provata da sola ------------------------------------

def test_verifica_init_pretende_entrambe_le_condizioni():
    """La funzione pura, senza il turno intorno. Le due condizioni si chiedono
    **insieme**: un server connesso senza gli strumenti e uno strumento risolto
    da un server `failed` sono lo stesso guasto visto da due lati."""
    def esito(riga):
        return runner.read_stream(riga + "\n")

    ok, motivo = runner.verify_init(esito(_riga_init()))
    assert ok is True and motivo == ""

    ok, motivo = runner.verify_init(esito(_riga_init(stato="failed")))
    assert ok is False and "failed" in motivo

    tolto = list(runner.mcp_names())[-1]
    ok, motivo = runner.verify_init(
        esito(_riga_init(nomi=list(runner.mcp_names())[:3])))
    assert ok is False and tolto in motivo

    ok, motivo = runner.verify_init(runner.StreamOccurrence())
    assert ok is False and "non e' una conferma" in motivo


def test_verifica_init_non_confonde_un_altro_server_col_nostro():
    """Un `mcp_servers` che porta un server connesso **con un altro nome** non
    e' il nostro: senza `--strict-mcp-config` la CLI userebbe anche i server
    MCP dell'ambiente, e un controllo che guardasse solo "c'e' qualcosa di
    connesso" direbbe di si' mentre HIRIS non c'e'."""
    evento = json.loads(_riga_init())
    evento["mcp_servers"] = [{"name": "qualcun-altro", "status": "connected"}]
    esito = runner.read_stream(json.dumps(evento) + "\n")

    ok, motivo = runner.verify_init(esito)
    assert ok is False
    assert runner._mcp_server_name() in motivo
