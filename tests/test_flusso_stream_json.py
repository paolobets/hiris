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


# ── i mattoni dei flussi finti ───────────────────────────────────────────────

def _init(mcp_servers=None, tools=None):
    return json.dumps({
        "type": "system", "subtype": "init",
        "cwd": "/app", "session_id": "S-1", "model": "claude-sonnet-4",
        "tools": tools if tools is not None else ["Task", "Bash"],
        "mcp_servers": mcp_servers if mcp_servers is not None else [],
    })


def _assistant(testo):
    return json.dumps({"type": "assistant",
                       "message": {"role": "assistant",
                                   "content": [{"type": "text", "text": testo}]}})


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
    # `--verbose` non arrivato alla CLI, o formato cambiato: non e' uno dei
    # cinque esiti della reply (l'init non serve a rispondere, in questo task),
    # ma non passa in silenzio.
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        reply = _reason(_flusso(_result("ok")))
    assert reply == "ok"
    righe = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("senza evento system/init" in m for m in righe), righe


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
