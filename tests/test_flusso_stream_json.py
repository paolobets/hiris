"""fetta "il ponte riceve gli strumenti" (parita' B, Task 2).

Il ponte non legge piu' un oggetto JSON ma l'NDJSON di
`claude --output-format stream-json --verbose`. Il cambio di formato riscrive
il parsing di OGNI risposta, rami d'errore inclusi: se sbaglia, il ponte
risponde `[vuoto]` o `[errore runner]` a tutto, e nessuno se ne accorge finche'
un utente non se ne lamenta.

Questo file esercita `runner.leggi_flusso` DIRETTAMENTE, su flussi costruiti a
mano (la funzione e' pura: nessun subprocess, nessuna rete), e poi pinna gli
esiti che `_reason_chat` ne ricava -- uno per uno, perche' un ramo d'errore che
sparisce e' un modo di fallire che diventa muto.
"""
import json
import logging
from unittest.mock import patch

from hiris.app.agent import runner
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA


# ── i mattoni dei flussi finti ───────────────────────────────────────────────

def _init(mcp_servers=None, tools=None, **extra):
    # I due campi in coda (`claude_code_version`, `apiKeySource`) NON sono
    # inventati per il test: sono quelli che la CLI vera emette davvero
    # nell'evento `init` -- verificati dal vivo su `claude 2.1.227`
    # (task-7-report.md §2 e la review totale della fetta, voce I-3).
    evento = {
        "type": "system", "subtype": "init",
        "cwd": "/app", "session_id": "S-1", "model": "claude-sonnet-4",
        "tools": tools if tools is not None else ["Task", "Bash"],
        "mcp_servers": mcp_servers if mcp_servers is not None else [],
        "claude_code_version": "2.1.227",
        "apiKeySource": "none",
    }
    evento.update(extra)
    return json.dumps(evento)


def _assistant(testo):
    return json.dumps({"type": "assistant",
                       "message": {"role": "assistant",
                                   "content": [{"type": "text", "text": testo}]}})


# ── fetta "il ponte riceve gli strumenti" (parita' B, Task 5): i mattoni di
# un turno CON strumenti -- il blocco `tool_use` nell'evento assistant, e il
# `tool_result` che torna in un evento "user" (la CLI riecheggia l'esito nel
# flusso, per continuare la conversazione col modello). ────────────────────

def _tool_use(nome, input_, id_="toolu_1"):
    return json.dumps({"type": "assistant",
                       "message": {"role": "assistant",
                                   "content": [{"type": "tool_use", "id": id_,
                                               "name": nome, "input": input_}]}})


def _tool_result(tool_use_id, *, is_error=False, contenuto="ok"):
    return json.dumps({"type": "user",
                       "message": {"role": "user",
                                   "content": [{"type": "tool_result",
                                               "tool_use_id": tool_use_id,
                                               "is_error": is_error,
                                               "content": contenuto}]}})


def _result(testo="2 luci accese", usage=None, **extra):
    evento = {"type": "result", "subtype": "success", "is_error": False,
              "duration_ms": 1234, "num_turns": 1, "result": testo,
              "session_id": "S-1",
              "usage": usage if usage is not None else {
                  "input_tokens": 12,
                  "cache_creation_input_tokens": 4096,
                  "cache_read_input_tokens": 8192,
                  "output_tokens": 57,
              }}
    evento.update(extra)
    return json.dumps(evento)


def _flusso(*righe):
    return "\n".join(righe) + "\n"


def _job(job_id="J-1"):
    return {"job_id": job_id, "kind": "chat",
            "context": {"system_prompt": "Sei HIRIS.",
                        "history": [{"role": "user", "content": "che luci?"}]}}


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _reason(stdout, rc=0, stderr="", job=None):
    with patch.object(runner.subprocess, "run",
                      lambda *a, **k: _Proc(rc, stdout, stderr)):
        return runner._reason_chat(job or _job(), "live")["reply"]


def _reason_full(stdout, rc=0, stderr="", job=None, **kw):
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 5): la variante di
    # `_reason` che NON scarta il resto della `decision` -- serve a leggere
    # `tools_called`, che `_reason` (sopra) getta via prendendo solo `reply`.
    with patch.object(runner.subprocess, "run",
                      lambda *a, **k: _Proc(rc, stdout, stderr)):
        return runner._reason_chat(job or _job(), "live", **kw)


# ── ① il flusso normale ──────────────────────────────────────────────────────

def test_flusso_normale_da_testo_e_usage():
    esito = runner.leggi_flusso(_flusso(
        _init(), _assistant("sto guardando"), _result("2 luci accese")))

    assert esito.testo == "2 luci accese"
    assert esito.risultato_presente is True
    assert esito.righe_saltate == 0
    assert esito.righe_lette == 3
    assert esito.usage == {"input_tokens": 12,
                           "cache_creation_input_tokens": 4096,
                           "cache_read_input_tokens": 8192,
                           "output_tokens": 57}
    # `num_turns` sta in cima all'evento result, non dentro usage: se qualcuno
    # lo cercasse solo in `usage`, la riga di misura del Task 2 (Step 4)
    # loggherebbe `None` a ogni turno e la domanda aperta 2 resterebbe aperta.
    assert esito.num_turni == 1
    # l'evento init e' tenuto INTERO: il Task 4 ci decidera' sopra
    assert esito.init is not None and esito.init["subtype"] == "init"


def test_flusso_normale_la_reply_e_il_testo_del_risultato():
    assert _reason(_flusso(_init(), _assistant("x"),
                           _result("2 luci accese"))) == "2 luci accese"


# ── ② una riga non-JSON in mezzo: si salta e si CONTA ────────────────────────

def test_riga_non_json_non_fa_cadere_il_flusso_e_viene_contata():
    esito = runner.leggi_flusso(_flusso(
        _init(),
        "questa riga non e' JSON",
        _assistant("sto guardando"),
        _result("2 luci accese")))

    assert esito.testo == "2 luci accese"   # il testo arriva LO STESSO
    assert esito.righe_saltate == 1
    assert esito.righe_lette == 4


def test_riga_json_ma_non_oggetto_conta_come_saltata():
    # JSON valido che non e' un evento: stessa sorte di una riga illeggibile.
    esito = runner.leggi_flusso(_flusso(
        _init(), "[1, 2, 3]", "42", _result("ok")))
    assert esito.righe_saltate == 2
    assert esito.testo == "ok"


def test_le_righe_saltate_sono_dichiarate_nel_log(caplog):
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        reply = _reason(_flusso(_init(), "rumore", _result("2 luci accese")))

    # la risposta resta normale...
    assert reply == "2 luci accese"
    # ...ma il fatto non sparisce: se la CLI cambia formato, il conto sale
    # prima che qualcosa si rompa davvero.
    righe = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("non-JSON" in m for m in righe), righe


# ── ③ il flusso SENZA evento finale: il silenzio dichiarato della fetta ──────

def test_flusso_senza_result_non_diventa_una_stringa_vuota():
    esito = runner.leggi_flusso(_flusso(_init(), _assistant("sto guar")))

    assert esito.risultato_presente is False
    assert esito.risultato is None
    assert esito.testo == ""      # vuoto, ma il chiamante SA che manca il finale
    assert esito.usage == {}


def test_flusso_senza_result_e_dichiarato_nel_log_e_nella_reply(caplog):
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        reply = _reason(_flusso(_init(), _assistant("sto guar")))

    # nel log, esplicito
    righe = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("senza evento finale type=result" in m for m in righe), righe
    assert any("J-1" in m for m in righe), righe

    # e nella reply, perche' un log che nessuno legge non e' una dichiarazione
    assert reply.startswith(runner._SENTINELLA_FLUSSO_INCOMPLETO)
    assert "non e' una risposta completa" in reply
    # e non e' il testo parziale spacciato per risposta: il pezzo grezzo c'e',
    # ma etichettato come tale
    assert "ultimo pezzo di flusso letto" in reply


def test_flusso_vuoto_e_flusso_di_solo_rumore_sono_entrambi_dichiarati():
    # Due modi diversi di non avere una risposta, nessuno dei due muto.
    for stdout in ("", "   \n\n", "boom\nboom\n"):
        reply = _reason(stdout)
        assert reply.startswith(runner._SENTINELLA_FLUSSO_INCOMPLETO), stdout

    # e restano distinguibili nell'esito letto: 0 righe contro 2 di rumore
    assert runner.leggi_flusso("").righe_lette == 0
    assert runner.leggi_flusso("boom\nboom\n").righe_saltate == 2


def test_riga_finale_troncata_a_meta_e_dichiarata():
    # Il processo ucciso mentre scriveva l'evento finale: l'ultima riga e' JSON
    # a meta'. Non deve ne' sollevare ne' passare per una risposta.
    troncato = _flusso(_init(), _assistant("x")) + '{"type":"result","resu'
    esito = runner.leggi_flusso(troncato)
    assert esito.righe_saltate == 1 and esito.risultato_presente is False
    assert _reason(troncato).startswith(runner._SENTINELLA_FLUSSO_INCOMPLETO)


# ── ④ l'init con il server MCP fallito: riportato FEDELMENTE ────────────────

def test_init_con_server_mcp_failed_arriva_intero():
    # E' il dato su cui il Task 4 decidera' se ricomporre il prompt senza
    # strumenti. Qui si pinna SOLO che arrivi intero: nessuna decisione.
    esito = runner.leggi_flusso(_flusso(
        _init(mcp_servers=[{"name": "hiris", "status": "failed"}],
              tools=["Task", "mcp__hiris__guarda"]),
        _result("rispondo senza strumenti")))

    assert esito.init["mcp_servers"] == [{"name": "hiris", "status": "failed"}]
    assert esito.init["tools"] == ["Task", "mcp__hiris__guarda"]
    assert esito.testo == "rispondo senza strumenti"


def test_init_e_loggato_ma_non_agito(caplog):
    # Task 2, Step 5: si legge e si logga, NON si agisce. La reply e' quella
    # normale anche con il server dichiarato `failed` -- ad agirci sara' il
    # Task 4, e questo test e' la prova che il dato gli arriva.
    with caplog.at_level(logging.INFO, logger="hiris.agent"):
        reply = _reason(_flusso(
            _init(mcp_servers=[{"name": "hiris", "status": "failed"}]),
            _result("ok")))

    assert reply == "ok"
    righe = [r.getMessage() for r in caplog.records]
    init_log = [m for m in righe if m.startswith("init del ponte")]
    assert len(init_log) == 1, righe
    assert "'name': 'hiris'" in init_log[0] and "'status': 'failed'" in init_log[0]
    assert "strumenti risolti=2" in init_log[0]


def test_l_init_loggato_dice_anche_con_quale_cli_e_con_quale_credenziale(caplog):
    """Review totale della fetta (I-3): due campi che l'`init` porta gia' e che
    nessun altro posto dice.

    - `claude_code_version`: il `Dockerfile` installa
      `@anthropic-ai/claude-code@2`, NON pinnata. Se «strumenti risolti=N»
      cambia fra due build, senza questo campo il log non dice perche'.
    - `apiKeySource`: e' l'UNICA prova a runtime che il ponte parli con
      l'ABBONAMENTO e non con una chiave a consumo. Oggi quella promessa e'
      difesa dal codice da `_SUBPROCESS_ENV_DENYLIST`, cioe' da una denylist
      di due nomi -- e una denylist non puo' provare cio' che NON e' passato.
    """
    with caplog.at_level(logging.INFO, logger="hiris.agent"):
        _reason(_flusso(
            _init(claude_code_version="2.1.227", apiKeySource="none"),
            _result("ok")))
    riga = next(m for m in (r.getMessage() for r in caplog.records)
                if m.startswith("init del ponte"))

    assert "2.1.227" in riga, (
        f"la versione della CLI e' sparita dalla riga di init ({riga!r}): "
        "il Dockerfile installa `@anthropic-ai/claude-code@2`, non una "
        "versione pinnata -- senza questo campo un N diverso fra due build "
        "resta senza spiegazione")
    assert "apiKeySource=none" in riga, (
        f"`apiKeySource` e' sparito dalla riga di init ({riga!r}): e' l'unica "
        "prova a runtime che questo turno sia andato sull'abbonamento e non "
        "su una chiave a consumo")


def test_in_questo_task_i_server_mcp_sono_la_lista_vuota(caplog):
    # La condizione attesa OGGI: nessun `--mcp-config` nell'argv, quindi
    # nessun server. Se un giorno questa riga loggasse un server senza che
    # nessuno abbia attaccato gli strumenti, sarebbe una sorpresa da guardare.
    assert "--mcp-config" not in runner._chat_claude_args("S", "U", "sonnet")
    with caplog.at_level(logging.INFO, logger="hiris.agent"):
        _reason(_flusso(_init(mcp_servers=[]), _result("ok")))
    init_log = [r.getMessage() for r in caplog.records
                if r.getMessage().startswith("init del ponte")]
    assert "mcp_servers=[]" in init_log[0]


def test_flusso_senza_init_e_dichiarato(caplog):
    # La CLI morta prima, `--verbose` non arrivato, o formato cambiato: non e'
    # uno dei cinque esiti della reply (l'init non serve a rispondere, in
    # questo task), ma non passa in silenzio.
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        reply = _reason(_flusso(_result("ok")))
    assert reply == "ok"
    righe = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("senza evento system/init" in m for m in righe), righe


def test_il_warning_dell_init_assente_non_accusa_una_causa_sola(caplog):
    """Review totale della fetta (I-5): il messaggio elencava DUE cause
    (`--verbose` mancante, formato cambiato) e taceva quella che l'implementer
    del Task 7 ha davvero incontrato -- la CLI morta prima di emettere
    l'evento. Chi legge questa riga in UAT viene mandato a controllare l'argv
    mentre il dato che serve e' `rc`. Il messaggio deve nominare **tutte e
    tre** le cause e non sceglierne nessuna: e' una diagnosi, non un verdetto.
    """
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        _reason(_flusso(_result("ok")))
    riga = next(m for m in (r.getMessage() for r in caplog.records)
                if "senza evento system/init" in m)

    assert "rc" in riga, (
        f"il warning non nomina piu' `rc` ({riga!r}): e' il primo campo da "
        "guardare quando la CLI e' morta prima dell'init, ed e' proprio la "
        "causa che questa riga taceva")
    assert "--verbose" in riga and "formato" in riga, (
        f"il warning ha perso una delle altre due cause ({riga!r}): "
        "restringere l'elenco a una sola causa e' il difetto che I-5 ha "
        "chiuso, non importa QUALE causa resti")


# ── la misura del Task 2, Step 4: l'usage loggato a ogni turno ──────────────

def test_usage_loggato_a_ogni_turno_solo_conteggi(caplog):
    with caplog.at_level(logging.INFO, logger="hiris.agent"):
        _reason(_flusso(_init(), _result("2 luci accese")))

    uso = [r.getMessage() for r in caplog.records
           if r.getMessage().startswith("uso del ponte")]
    assert len(uso) == 1, "una riga di misura per turno, ne' zero ne' due"
    riga = uso[0]
    for campo, valore in (("input_tokens", "12"),
                          ("cache_creation_input_tokens", "4096"),
                          ("cache_read_input_tokens", "8192"),
                          ("num_turns", "1")):
        assert f"{campo}={valore}" in riga, riga
    # nessun valore di prompt e nessun testo di risposta nella riga: e' una
    # misura di costo, non una copia della conversazione.
    assert "Sei HIRIS." not in riga and "che luci?" not in riga
    assert "2 luci accese" not in riga


def test_usage_assente_non_fa_saltare_la_riga_di_misura(caplog):
    # Un result senza `usage` (la CLI puo' ometterlo su un errore): la riga
    # esce lo stesso, coi campi a None. Meglio una misura vuota che nessuna:
    # e' il conteggio dei turni che deve tornare a fine settimana.
    with caplog.at_level(logging.INFO, logger="hiris.agent"):
        _reason(_flusso(_init(), _result("ok", usage={})))
    uso = [r.getMessage() for r in caplog.records
           if r.getMessage().startswith("uso del ponte")]
    assert len(uso) == 1 and "input_tokens=None" in uso[0]


# ── i cinque esiti restano cinque, e sono DISTINGUIBILI l'uno dall'altro ────
# Il rischio di questo task e' che un ramo d'errore si perda nel cambio di
# formato e diventi muto, o che due rami diversi producano la stessa risposta
# (allora l'utente e il log non possono piu' dire cosa e' successo).

def test_i_cinque_esiti_del_ponte_sono_distinti():
    import subprocess as _sp

    esiti = {}

    # (1) rc != 0
    esiti["rc"] = _reason(_flusso(_init(), _result("quota superata",
                                                   subtype="error_during_execution")),
                          rc=1)
    # (2) testo
    esiti["testo"] = _reason(_flusso(_init(), _result("2 luci accese")))
    # (3) flusso senza evento finale
    esiti["troncato"] = _reason(_flusso(_init(), _assistant("sto guar")))
    # (4) testo vuoto
    esiti["vuoto"] = _reason(_flusso(_init(), _result("")))
    # (5) CLI non eseguibile

    def _boom(*a, **k):
        raise FileNotFoundError("claude")

    with patch.object(runner.subprocess, "run", _boom):
        esiti["assente"] = runner._reason_chat(_job(), "live")["reply"]

    assert esiti["rc"].startswith("[errore runner rc=1]")
    assert "quota superata" in esiti["rc"]
    assert esiti["testo"] == "2 luci accese"
    assert esiti["troncato"].startswith("[flusso incompleto]")
    assert esiti["vuoto"] == "[vuoto]"
    assert esiti["assente"] == "[runner non disponibile]"
    assert len(set(esiti.values())) == 5, (
        f"due esiti diversi del ponte producono la stessa reply: {esiti!r}")

    # e il timeout resta nel quinto, non in un sesto muto
    def _timeout(*a, **k):
        raise _sp.TimeoutExpired(cmd="claude", timeout=300)

    with patch.object(runner.subprocess, "run", _timeout):
        assert runner._reason_chat(_job(), "live")["reply"] == esiti["assente"]


def test_rc_diverso_da_zero_senza_evento_finale_porta_comunque_il_grezzo():
    # Il processo morto a meta': nessun evento `result` da cui ricavare il
    # dettaglio. La causa non deve sparire dietro il solo numero.
    reply = _reason("Error: not logged in\n", rc=1, stderr="")
    assert reply.startswith("[errore runner rc=1]")
    assert "not logged in" in reply


def test_leggi_flusso_non_solleva_mai():
    # La firma del contratto: qualunque spazzatura entri, esce un EsitoFlusso.
    for spazzatura in ("", "\x00\x01", "null", "{", "[]", '{"type": null}',
                       '"solo una stringa"', "\n\n\n", '{"type":"result"}'):
        esito = runner.leggi_flusso(spazzatura)
        assert isinstance(esito, runner.EsitoFlusso)
        assert isinstance(esito.testo, str) and isinstance(esito.usage, dict)


def test_ultimo_result_e_primo_init_vincono():
    esito = runner.leggi_flusso(_flusso(
        _init(mcp_servers=[{"name": "hiris", "status": "connected"}]),
        _init(mcp_servers=[{"name": "altro", "status": "failed"}]),
        _result("primo"), _result("secondo")))
    assert esito.init["mcp_servers"][0]["name"] == "hiris"
    assert esito.testo == "secondo"


def test_il_sentinella_del_flusso_incompleto_e_filtrato_dalla_cronologia():
    # I sentinella del ponte non sono risposte: se finissero in
    # chat_history.db tornerebbero al modello a ogni turno successivo (difetto
    # gia' trovato dal vivo su questo ramo con `[errore runner rc=...]`). Il
    # quinto sentinella nasce con la sua rete gia' tesa.
    from hiris.app.chat_store import _is_toxic_assistant

    reply = _reason(_flusso(_init(), _assistant("sto guar")))
    assert _is_toxic_assistant(reply) is True, reply


# ── fetta "il ponte riceve gli strumenti" (parita' B, Task 5): la raccolta di
# `tools_called` dallo STESSO flusso che `leggi_flusso` gia' legge -- nessuna
# seconda lettura -- e la forma nella `decision` che il poll (handlers_chat.py)
# restituisce come `debug.tools_called`. La ragione: da questo task `ricorda`
# e' raggiungibile ANCHE dal ponte, e scrive in `memoria.db`; senza questo
# campo l'unico modo di accorgersi di una scrittura indebita e' trovarla nel
# nucleo giorni dopo (vedi il docstring in cima a `agent/runner.py`). ────────

def test_leggi_flusso_estrae_i_tool_use_in_ordine():
    # Step 6, ① del brief: due `tool_use` estratti IN ORDINE da un flusso
    # costruito a mano. Entrambi RISOLTI (un `tool_result` con `is_error:
    # false` per ciascuno): qui si prova l'ORDINE, non lo stato di
    # risoluzione -- quello ha i suoi test dedicati piu' sotto (fix round 1).
    esito = runner.leggi_flusso(_flusso(
        _init(),
        _tool_use("mcp__hiris__guarda", {"cosa": "salotto"}, id_="t1"),
        _tool_result("t1", is_error=False),
        _tool_use("mcp__hiris__ricorda", {"testo": "la caldaia perde"}, id_="t2"),
        _tool_result("t2", is_error=False),
        _result("fatto")))

    assert esito.tools_called == [
        {"tool": "mcp__hiris__guarda", "input": {"cosa": "salotto"}},
        {"tool": "mcp__hiris__ricorda", "input": {"testo": "la caldaia perde"}},
    ]


def test_flusso_senza_tool_use_tools_called_e_lista_vuota_non_none():
    # Step 6, ② del brief: nessuno strumento chiamato -> lista VUOTA, mai
    # `None`. Una lista vuota dice "nessuno strumento chiamato"; `None`
    # direbbe "non lo so" -- e non e' quello il caso qui.
    esito = runner.leggi_flusso(_flusso(
        _init(), _assistant("sto guardando"), _result("ok")))
    assert esito.tools_called == []
    assert esito.tools_called is not None
    assert isinstance(esito.tools_called, list)

    # e vale anche per il flusso completamente vuoto/di rumore.
    assert runner.leggi_flusso("").tools_called == []
    assert runner.leggi_flusso("boom\nboom\n").tools_called == []


def test_il_nome_e_grezzo_e_non_normalizzato():
    # Step 1 del brief: il nome si riporta come il modello lo ha usato. Un
    # nome mai servito (uno strumento locale del CLI, o un nome inventato)
    # arriva cosi' com'e', non filtrato -- e' precisamente il caso ("il
    # modello chiama qualcosa che non gli abbiamo dato") che riscrivere il
    # nome nasconderebbe. Risolta (con esito, per isolare cio' che questo
    # test prova: il nome, non lo stato).
    esito = runner.leggi_flusso(_flusso(
        _init(), _tool_use("Bash", {"command": "rm -rf /"}, id_="t1"),
        _tool_result("t1", is_error=False), _result("ok")))
    assert esito.tools_called == [{"tool": "Bash", "input": {"command": "rm -rf /"}}]


def test_la_forma_e_identica_a_quella_del_ramo_sincrono():
    # Step 2 del brief: `{"tool": ..., "input": ...}`, IDENTICA a
    # `handlers_chat.py` (`tools_called = [{"tool": t.get("tool", ""),
    # "input": t.get("input")} ...]`) -- una forma sola per la UI della E5.
    # Risolta con successo: e' la forma del caso comune, quella che deve
    # combaciare col ramo sincrono bit-per-bit.
    esito = runner.leggi_flusso(_flusso(
        _init(), _tool_use("mcp__hiris__cerca", {"query": "termosifone"}, id_="t1"),
        _tool_result("t1", is_error=False), _result("ok")))
    voce = esito.tools_called[0]
    assert set(voce) == {"tool", "input"}
    assert voce == {"tool": "mcp__hiris__cerca", "input": {"query": "termosifone"}}


def test_una_chiamata_fallita_resta_distinguibile_da_una_riuscita():
    # La preoccupazione esplicita del task: se una `tools/call` fallisce, non
    # deve sparire nella stessa forma di una riuscita -- e' precisamente il
    # caso che rende osservabile un guasto. Il `tool_result` (evento "user")
    # con `is_error: true`, abbinato per `tool_use_id`, e' l'unico segnale che
    # lo dice.
    esito = runner.leggi_flusso(_flusso(
        _init(),
        _tool_use("mcp__hiris__ricorda", {"testo": "ok"}, id_="t-ok"),
        _tool_result("t-ok", is_error=False),
        _tool_use("mcp__hiris__ricorda", {"testo": "fallita"}, id_="t-ko"),
        _tool_result("t-ko", is_error=True, contenuto="errore: memoria non disponibile"),
        _result("fatto")))

    riuscita, fallita = esito.tools_called
    assert riuscita == {"tool": "mcp__hiris__ricorda", "input": {"testo": "ok"}}
    assert "is_error" not in riuscita  # la forma resta identica al ramo sincrono
    assert fallita["tool"] == "mcp__hiris__ricorda"
    assert fallita["is_error"] is True
    assert fallita != riuscita, "una chiamata fallita non deve avere la STESSA forma di una riuscita"


def test_un_tool_result_senza_tool_use_corrispondente_non_solleva():
    # Un `tool_use_id` che non corrisponde a nessuna chiamata vista (flusso
    # troncato proprio li', o formato imprevisto): non deve far cadere la
    # lettura. La chiamata gia' vista (`t1`) pero' NON ha ricevuto nessun
    # `tool_result` -- quello spaiato non conta come suo -- quindi resta
    # SENZA esito confermato: fix round 1, e' esattamente il caso che
    # l'Important ha trovato mancante (vedi il test gemello sotto).
    esito = runner.leggi_flusso(_flusso(
        _init(),
        _tool_use("mcp__hiris__guarda", {}, id_="t1"),
        _tool_result("id-mai-visto", is_error=True),
        _result("ok")))
    assert esito.tools_called == [
        {"tool": "mcp__hiris__guarda", "input": {}, "esito": "sconosciuto"}]


def test_una_chiamata_mai_risolta_non_e_uguale_a_una_riuscita():
    """Fix round 1, Important. Prima di questo fix, un `tool_use` il cui
    `tool_result` non arriva MAI (flusso troncato -- `risultato_presente`
    `False` -- o un `result` di errore/max-turns che chiude il flusso con una
    chiamata ancora aperta pur con `rc == 0`) produceva la STESSA forma di una
    chiamata riuscita: `{"tool", "input"}`, senza nessuna terza chiave. Un
    `ricorda` fallito il cui esito si perde nel troncamento sarebbe apparso,
    nel dato, come un ricordo salvato -- l'esatto opposto di cio' per cui
    questo task esiste.

    Qui il flusso si tronca DAVVERO subito dopo il `tool_use` (nessun evento
    `result` finale): e' il caso (3) gia' dichiarato da
    `risultato_presente`, incontrato ora anche da `tools_called`."""
    esito = runner.leggi_flusso(_flusso(
        _init(), _tool_use("mcp__hiris__ricorda", {"testo": "mai confermato"}, id_="t1")))

    assert esito.risultato_presente is False  # il troncamento vero, non simulato
    mai_risolta = esito.tools_called[0]
    riuscita = {"tool": "mcp__hiris__ricorda", "input": {"testo": "mai confermato"}}

    assert mai_risolta != riuscita, (
        "una chiamata MAI risolta non deve avere la stessa forma di una riuscita")
    assert mai_risolta == {**riuscita, "esito": "sconosciuto"}
    assert "is_error" not in mai_risolta  # non e' nemmeno il caso "fallita": e' IGNOTO


# -- la decision che _reason_chat restituisce --------------------------------

def test_decision_porta_tools_called_in_modalita_live_anche_vuota():
    # `_reason_chat` mette `tools_called` nella `decision` -- SEMPRE in `live`,
    # anche vuota: e' cosi' che il poll (`handlers_chat.py`) sa distinguere
    # "turno vero senza strumenti" da "job mock/legacy senza la chiave".
    decisione = _reason_full(_flusso(_init(), _assistant("ciao"), _result("ciao")))
    assert decisione["tools_called"] == []


def test_decision_mock_non_porta_tools_called():
    # Il ramo mock non ha girato nessun flusso da leggere: la chiave resta
    # ASSENTE (non una lista vuota) -- e' un job che non ha mai avuto
    # l'occasione di chiamare uno strumento, non un turno vero senza.
    decisione = runner._reason_chat(_job(), "mock")
    assert "tools_called" not in decisione


def test_decision_porta_le_chiamate_nella_stessa_forma_della_lista():
    decisione = _reason_full(_flusso(
        _init(), _tool_use("mcp__hiris__ricorda", {"testo": "la caldaia perde"}, id_="t1"),
        _tool_result("t1", is_error=False), _result("preso nota")))
    assert decisione["tools_called"] == [
        {"tool": "mcp__hiris__ricorda", "input": {"testo": "la caldaia perde"}}]


def test_il_token_non_compare_in_tools_called():
    # Il cancello unico in uscita vale anche per questo canale nuovo: se un
    # input di strumento contenesse per caso una delle forme del token, non
    # deve uscire (vedi `_reda_struttura` in agent/runner.py).
    token = "TOK-SEGRETO-123"
    decisione = _reason_full(
        _flusso(_init(),
               _tool_use("mcp__hiris__ricorda", {"testo": f"il token e' {token}"}),
               _result("preso nota")),
        headers={"X-HIRIS-Internal-Token": token})

    assert token not in json.dumps(decisione)
    assert decisione["tools_called"][0]["input"]["testo"] == f"il token e' {runner.REDATTO}"


# -- il conteggio dei giri (Step 4 del brief) --------------------------------

def test_il_conteggio_e_la_lunghezza_della_lista_non_un_secondo_contatore():
    # Il progetto chiede «il conteggio esposto dove l'utente lo vede» (Sec5.2).
    # In questa fetta e' `len(decision["tools_called"])`, e basta: nessun
    # secondo campo da tenere allineato con la lista che lo produce.
    decisione = _reason_full(_flusso(
        _init(),
        _tool_use("mcp__hiris__guarda", {}, id_="t1"),
        _tool_use("mcp__hiris__ricorda", {"testo": "x"}, id_="t2"),
        _result("fatto")))
    assert len(decisione["tools_called"]) == 2


# -- Task 4 incontra Task 5: DUE invocazioni nello stesso turno --------------

class _RispostaSonda:
    def __init__(self, dati):
        self._dati = dati
        self.status_code = 200

    def json(self):
        return self._dati


class _ClientSondaOk:
    """Un client finto che risponde SEMPRE positivamente alla sonda
    `tools/list` (i quattro nomi nudi del catalogo)."""

    def post(self, url, headers=None, json=None, timeout=None):
        nomi = [d["name"] for d in STRUMENTI_CONOSCENZA]
        return _RispostaSonda({"result": {"tools": [{"name": n} for n in nomi]}})


class _CliDueGiri:
    """Un `subprocess.run` finto che restituisce uno stdout diverso a ogni
    chiamata: il primo giro (poi buttato), il secondo (quello che resta)."""

    def __init__(self, *stdouts):
        self._stdouts = list(stdouts)
        self.chiamate = 0

    def __call__(self, argv, *a, **k):
        stdout = self._stdouts[min(self.chiamate, len(self._stdouts) - 1)]
        self.chiamate += 1
        return _Proc(0, stdout, "")


def test_due_invocazioni_nello_stesso_turno_accumulano_le_chiamate_di_entrambe():
    """Task 4 incontra Task 5: quando l'evento `system/init` smentisce la
    sonda, la PRIMA invocazione si butta e se ne ricompone una seconda senza
    strumenti (regole-fetta.md). La risposta OVVIA sarebbe riportare solo
    l'ultima invocazione, quella la cui reply l'utente legge davvero -- ma non
    e' quella giusta: se nella prima invocazione (poi buttata) il modello ha
    chiamato `mcp__hiris__ricorda`, quella chiamata e' gia' passata per
    davvero da `POST /api/mcp` fino a `DispatcherConoscenza` e ha gia' scritto
    in `memoria.db`, PRIMA che il ponte si accorgesse che il prompt prometteva
    strumenti a meta'. Buttare l'invocazione non disfa la scrittura.
    Riportare solo l'ultimo giro nasconderebbe esattamente il turno per cui
    questo task esiste: quello in cui promessa e fatti divergono.
    `tools_called` porta quindi le chiamate di ENTRAMBI i giri, nell'ordine
    (primo, poi secondo)."""
    # `t1` e' RISOLTA (un `tool_result` con `is_error: false`, come una
    # scrittura MCP che verso il NOSTRO stesso add-on e' davvero riuscita):
    # questo test prova l'ACCUMULO fra i due giri, non lo stato di
    # risoluzione -- quello ha i suoi test dedicati (fix round 1, sopra).
    primo_giro = _flusso(
        _init(mcp_servers=[{"name": "hiris", "status": "failed"}]),
        _tool_use("mcp__hiris__ricorda",
                  {"testo": "scritto durante il giro poi buttato"}, id_="t1"),
        _tool_result("t1", is_error=False),
        _result("mi sono segnato la cosa"))
    secondo_giro = _flusso(_init(mcp_servers=[]), _result("ok, senza strumenti"))

    cli = _CliDueGiri(primo_giro, secondo_giro)

    with patch.object(runner.subprocess, "run", cli):
        decisione = runner._reason_chat(
            _job(), "live", client=_ClientSondaOk(),
            base_url="http://127.0.0.1:8099",
            headers={"X-HIRIS-Internal-Token": "TOK"})

    assert cli.chiamate == 2  # la contraddizione ha davvero fatto ricomporre
    # la chiamata del giro BUTTATO resta, da sola: e' l'unica che c'e' stata.
    assert decisione["tools_called"] == [
        {"tool": "mcp__hiris__ricorda",
         "input": {"testo": "scritto durante il giro poi buttato"}}]
    # la reply che l'utente legge resta quella del SECONDO giro (Task 4: mai
    # promettere strumenti che non c'erano) -- questo task non cambia quella
    # disciplina, la affianca.
    assert decisione["reply"].startswith(runner.AVVISO_STRUMENTI_ASSENTI)
    assert "ok, senza strumenti" in decisione["reply"]
