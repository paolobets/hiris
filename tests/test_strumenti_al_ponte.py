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
  `_GUIDA_CON_STRUMENTI in system`. E' il test da non cancellare mai: pinnato
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
  serve davvero la callback -- e la serve per **tutti e quattro** gli
  strumenti, `guarda` compreso, che e' l'unico che legge la `entity_cache` e
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
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.memoria.archivio import ArchivioMemoria
from tests.test_strumenti_conoscenza import _semina_casa

# La fixture della configurazione PREDEFINITA dell'add-on, con le due valvole
# della suite (`HIRIS_ALLOW_NO_TOKEN`, `HIRIS_ALLOW_NO_CSRF`) rimosse: si
# importa invece di essere ricopiata qui: una seconda copia divergerebbe, e
# senza le valvole rimosse questi test passerebbero anche col guasto in piedi.
from tests.test_token_interno import (  # noqa: F401  (fixture usata da pytest)
    ponte_con_configurazione_predefinita,
)

_NOMI_NUDI = {d["name"] for d in STRUMENTI_CONOSCENZA}


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
    """`"--mcp-config" in argv` **<=>** `_GUIDA_CON_STRUMENTI in system`.

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
        strumenti_attivi=strumenti_attivi)
    argv = runner._chat_claude_args(
        "SYS", "USER", "sonnet", strumenti_attivi=strumenti_attivi,
        mcp_config=runner.config_mcp("http://127.0.0.1:8099", "TOK"))

    nell_argv = "mcpconfig" in _normalizza(argv)
    nel_prompt = prompts._GUIDA_CON_STRUMENTI in system

    assert nell_argv == nel_prompt, (
        f"l'argv {'porta' if nell_argv else 'NON porta'} --mcp-config mentre il "
        f"system prompt {'afferma' if nel_prompt else 'NEGA'} gli strumenti: e' "
        "esattamente la divergenza che questa fetta esiste per rendere "
        "impossibile. La risposta giusta e' guardare l'unico booleano di "
        "runner._reason_chat, non allentare questo assert.")
    # e il verso complementare, sull'altra guida: le due non convivono mai
    assert (prompts._GUIDA_SENZA_STRUMENTI in system) == (not nell_argv)


def test_le_due_guide_non_convivono_mai_nello_stesso_prompt():
    """Il corollario: un prompt che contenesse entrambe direbbe al modello una
    cosa e il suo contrario, e vincerebbe l'ultima letta."""
    for attivi in (True, False):
        system, _u = prompts.build_chat_messages("Sei HIRIS.", [], strumenti_attivi=attivi)
        assert (prompts._GUIDA_CON_STRUMENTI in system) != (
            prompts._GUIDA_SENZA_STRUMENTI in system)


def test_i_quattro_nomi_si_derivano_dal_catalogo_e_non_si_riscrivono():
    """Nessun secondo catalogo: i nomi che finiscono in `--allowedTools` e nel
    testo del prompt nascono da `STRUMENTI_CONOSCENZA`. Quattro stringhe
    scritte a mano nel runner sarebbero l'errore che l'intera fetta E2 e'
    esistita per chiudere (tre cataloghi divergenti della stessa cosa)."""
    nomi = runner.nomi_mcp()

    assert len(nomi) == len(STRUMENTI_CONOSCENZA) == 4
    assert set(nomi) == {f"mcp__hiris__{n}" for n in _NOMI_NUDI}
    # il nome del server ha UNA fonte, quella della rotta: se un giorno la
    # rotta si presentasse con un altro nome, il prefisso lo seguirebbe da
    # solo -- e il prompt, che nomina i nomi prefissati, resterebbe vero.
    assert runner._nome_server_mcp() is handlers_mcp.NOME_SERVER_MCP
    for nome in nomi:
        assert nome.startswith(f"mcp__{handlers_mcp.NOME_SERVER_MCP}__")


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

    voce = config["mcpServers"][handlers_mcp.NOME_SERVER_MCP]
    assert voce["type"] == "http"
    assert voce["url"] == "http://127.0.0.1:8099/api/mcp"
    # ENTRAMBE: il token apre la rotta, l'X-Requested-With soddisfa il CSRF.
    # Mandarne uno solo farebbe dipendere la rotta da un solo ramo di un solo
    # middleware -- e i due rami sono pinnati in tests/test_rotta_mcp.py
    # proprio perche' nessuno dei due resti da solo a reggerla.
    assert voce["headers"]["X-HIRIS-Internal-Token"] == "IL-TOKEN"
    assert voce["headers"]["X-Requested-With"] == "hiris-mcp"


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
    return runner.sonda_strumenti(client, "http://127.0.0.1:8099",
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
    """**Tre nomi su quattro non sono «quasi si'».** Il prompt del ramo attivo
    afferma tutti e quattro gli strumenti: con tre, il modello ne chiamerebbe
    uno che non esiste -- e il messaggio che riceverebbe non e' una risposta,
    e' un errore che nessuno gli ha spiegato."""
    tre = sorted(_NOMI_NUDI)[:3]
    ok, motivo = _sonda_con(_ClientFinto(_Risposta(_tools_list(tre), 200)))
    assert ok is False
    mancante = (set(_NOMI_NUDI) - set(tre)).pop()
    assert mancante in motivo


def test_la_sonda_dice_si_solo_con_tutti_e_quattro():
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
        ok, motivo = runner.sonda_strumenti(
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

    with caplog.at_level(logging.DEBUG):
        with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
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

    `guarda` e' l'unico dei quattro che legge la cache delle entita', ed e'
    **l'argomento portante** con cui il disegno giustifica una rotta invece di
    un sottoprocesso stdio separato (`handlers_mcp.py`, «la stessa
    `entity_cache` del turno sincrono»): senza di essa `guarda` risponderebbe
    sempre `stato_non_letto`, e avremmo due intelligenze nella stessa casa che
    ne vedono due diverse. Un'affermazione del genere si prova, non si cita."""
    casa = _semina_casa(tmp_path)
    memoria_db = str(tmp_path / "memoria.db")
    memoria = ArchivioMemoria(memoria_db)
    app["archivio_casa"] = casa
    app["archivio_memoria"] = memoria
    app["entity_cache"] = _CacheViva({"light.cucina_1": "on",
                                      "light.cucina_2": "off"})
    return casa, memoria, memoria_db


class _CacheViva:
    """La forma vera di `entity_cache`: chiave "id", non "entity_id"
    (tests/test_strumenti_conoscenza.py usa lo stesso doppio)."""

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

    `sonda_strumenti` e' sincrona e bloccante (httpx): gira in un thread,
    come in produzione (`run_loop` -> `run_in_executor`). Chiamata
    direttamente qui bloccherebbe il loop che deve servirla, e il test
    andrebbe in stallo invece di fallire."""
    client, _coda, app = ponte_con_configurazione_predefinita
    intestazioni = runner.build_headers()
    assert intestazioni["X-HIRIS-Internal-Token"] == app["internal_token"]

    with httpx.Client(timeout=30) as http:
        ok, motivo = await asyncio.to_thread(
            runner.sonda_strumenti, http, _base_url(client), intestazioni)

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
            runner.sonda_strumenti, http, _base_url(client),
            {"X-HIRIS-Internal-Token": "sbagliato"})

    assert ok is False
    assert "401" in motivo


@pytest.mark.asyncio
async def test_la_sonda_dice_si_anche_senza_archivi_e_va_dichiarato(
    ponte_con_configurazione_predefinita,
):
    """**Il limite di questa difesa, scritto invece che scoperto dopo.**

    `tools/list` risponde 200 coi quattro nomi **anche con gli archivi
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
            runner.sonda_strumenti, http, _base_url(client), runner.build_headers())
        assert ok is True

        risposta = await asyncio.to_thread(
            lambda: http.post(
                f"{_base_url(client)}/api/mcp", headers=runner.build_headers(),
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                      "params": {"name": "cerca", "arguments": {"testo": "cucina"}}}))

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

    Si esercitano **tutti e quattro** gli strumenti attraverso la rotta,
    `guarda` e `richiama` compresi (Minor noto del Task 1: non l'avevano mai
    attraversata), e `guarda` legge la `entity_cache` vera dell'app -- che e'
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

                visto["cerca"] = _chiama("cerca", {"testo": "cucina"})
                visto["guarda"] = _chiama("guarda", {"tipo": "area",
                                                     "riferimento": "cucina"})
                visto["ricorda"] = _chiama(
                    "ricorda", {"testo": "in cucina si cena alle 20",
                                "ancore": [{"tipo": "area", "riferimento": "cucina"}]})
                visto["richiama"] = _chiama("richiama", {"riferimento": "cucina",
                                                         "tipo": "area"})
            return _ProcFelice()

        with patch.object(runner.subprocess, "run", _finta_cli):
            with httpx.Client(timeout=30) as http:
                esito = await asyncio.to_thread(
                    runner.run_once, http, base, runner.build_headers(), "live")

        assert esito == "done"
        # il giro di produzione ha collegato gli strumenti: prompt e argv insieme
        assert "--mcp-config" in visto["argv"]
        system = visto["argv"][visto["argv"].index("--system-prompt") + 1]
        assert prompts._GUIDA_CON_STRUMENTI in system

        # la callback e' stata servita, e ha portato i quattro nomi
        assert visto["nomi"] == _NOMI_NUDI

        # `cerca` legge l'archivio della casa dell'app
        assert visto["cerca"]["trovati"]
        # `guarda` legge la STESSA entity_cache del turno sincrono: e' la
        # ragione per cui questa e' una rotta e non un sottoprocesso separato.
        stati = {e["id"]: e["stato"] for e in visto["guarda"]["entita"]}
        assert stati["light.cucina_1"] == "on"
        assert stati["light.cucina_2"] == "off"
        assert "stato_non_letto" not in visto["guarda"]
        # `ricorda` scrive davvero in memoria.db -- il guasto storico da cui
        # questo strumento e' nato («preso nota» senza salvare niente)
        assert visto["ricorda"]["salvato"] is True
        conn = sqlite3.connect(memoria_db)
        try:
            righe = [r[0] for r in conn.execute("SELECT testo FROM ricordi")]
        finally:
            conn.close()
        assert righe == ["in cucina si cena alle 20"]
        # `richiama` rilegge cio' che `ricorda` ha appena scritto, dalla stessa
        # rotta e nello stesso turno
        assert [r["testo"] for r in visto["richiama"]["ricordi"]] == [
            "in cucina si cena alle 20"]
    finally:
        memoria.chiudi()
        casa.chiudi()


class _ProcFelice:
    returncode = 0
    stdout = (
        '{"type":"system","subtype":"init","tools":["mcp__hiris__cerca"],'
        '"mcp_servers":[{"name":"hiris","status":"connected"}]}\n'
        '{"type":"result","subtype":"success","is_error":false,"num_turns":2,'
        '"result":"in cucina una luce e\' accesa","usage":{"input_tokens":10,'
        '"output_tokens":5}}\n')
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

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        with patch.object(runner.subprocess, "run", lambda *a, **k: _ProcFelice()):
            esito = runner._reason_chat(
                job, "live",
                client=_ClientFinto(_Risposta({"error": "unauthorized"}, 401)),
                base_url="http://127.0.0.1:8099",
                headers={"X-HIRIS-Internal-Token": "TOK"})

    reply = esito["reply"]
    assert reply.startswith(runner.AVVISO_STRUMENTI_ASSENTI)
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

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        with patch.object(runner.subprocess, "run", _run):
            esito = runner._reason_chat(
                job, "live",
                client=_ClientFinto(_Risposta(_tools_list(sorted(_NOMI_NUDI)), 200)),
                base_url="http://127.0.0.1:8099",
                headers={"X-HIRIS-Internal-Token": "TOK"})

    assert esito["reply"] == "in cucina una luce e' accesa"
    assert runner.AVVISO_STRUMENTI_ASSENTI not in esito["reply"]
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

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        with patch.object(runner.subprocess, "run", lambda *a, **k: _ProcFelice()):
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
    assert runner.AVVISO_STRUMENTI_ASSENTI not in esito["reply"]
