import asyncio
import logging
import subprocess
import time
from unittest.mock import patch

import pytest

from hiris.app.agent import prompts, runner
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA
from hiris.app.claude_runner import BASE_IDENTITA, BASE_REGOLE_STRUMENTI


def test_build_chat_messages_available():
    system, user = prompts.build_chat_messages("Sei HIRIS.", [{"role": "user", "content": "ciao"}])
    assert "Sei HIRIS." in system and "Utente: ciao" in user


def test_build_headers_only_internal_token_no_cf_access(monkeypatch):
    # Loopback-only reasoning API: only the internal token travels, never a
    # CF-Access service credential or a generic Authorization header.
    monkeypatch.setenv("INTERNAL_TOKEN", "TOK")
    headers = runner.build_headers()
    assert headers["X-HIRIS-Internal-Token"] == "TOK"
    assert "CF-Access-Client-Id" not in headers
    assert "CF-Access-Client-Secret" not in headers
    assert "Authorization" not in headers


def test_safe_subprocess_env_excludes_metered_api_keys(monkeypatch):
    # M-1 (Plan 2B final review, fast-follow): CLAUDE_API_KEY is HIRIS's own
    # METERED Anthropic key (see run.sh); the subscription runner must
    # authenticate `claude` via CLAUDE_CODE_OAUTH_TOKEN only. Forwarding the
    # metered key here would risk silent spend on the wrong credential. Both
    # denylisted names must be dropped even when present in os.environ,
    # while an unrelated CLAUDE_*/ANTHROPIC_* var (e.g. the OAuth token)
    # still passes through.
    monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-metered-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-metered-secret-2")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")

    env = runner._safe_subprocess_env()

    assert "CLAUDE_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "oauth-token"


def test_reason_chat_returns_fallback_reply_on_nonzero_returncode():
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 2): lo stdout
    # finto passa alla forma NDJSON di `--output-format stream-json --verbose`
    # -- il soggetto del test (il ponte non solleva e risponde comunque quando
    # il CLI esce != 0) e' vivo e invariato, cambia solo la forma dello stdout.
    # Gli assert restano identici, ed e' proprio questo il punto: sono la prova
    # che il cambio di formato non ha perso questo ramo.
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}

    class _Proc:
        returncode = 1
        stdout = ('{"type":"result","subtype":"error_during_execution",'
                  '"is_error":true,"result":"quota superata"}\n')
        stderr = "boom"

    with patch.object(runner.subprocess, "run", lambda *a, **k: _Proc()):
        result = runner._reason_chat(job, "live")

    assert isinstance(result, dict)
    assert isinstance(result.get("reply"), str) and result["reply"]
    # ...e il ramo resta RICONOSCIBILE: il sentinella col codice, e la causa
    # estratta dall'evento finale invece che nascosta dietro un numero.
    assert result["reply"].startswith("[errore runner rc=1]")
    assert "quota superata" in result["reply"]


def test_reason_chat_returns_fallback_reply_on_timeout():
    # Il ramo (5) non ha nemmeno uno stdout da leggere: e' l'unico che il
    # cambio di formato non tocca, e va verificato che sia rimasto tale (con
    # `stream-json` la tentazione e' di leggere il flusso parziale del processo
    # ucciso e spacciarlo per risposta).
    job = {"kind": "chat", "context": {"system_prompt": "Sei HIRIS.",
                                        "history": [{"role": "user", "content": "ciao"}]}}

    def _raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=300)

    with patch.object(runner.subprocess, "run", _raise_timeout):
        result = runner._reason_chat(job, "live")

    assert isinstance(result, dict)
    assert isinstance(result.get("reply"), str) and result["reply"]
    assert result["reply"] == "[runner non disponibile]"


class _Resp:
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 3): `status_code`
    # non c'era, perche' nessuno lo guardava. `runner.sonda_strumenti` lo
    # guarda: un 200 e' la condizione minima perche' valga la pena di leggere
    # il corpo.
    def __init__(self, data, status_code=200):
        self._d = data
        self.status_code = status_code
    def json(self): return self._d
    def raise_for_status(self): pass


def _tools_list_come_la_rotta() -> dict:
    """La risposta di `tools/list` nella forma che la rotta vera produce.

    I nomi si DERIVANO da `STRUMENTI_CONOSCENZA`: un elenco scritto a
    mano qui sarebbe il secondo catalogo, e questo finto client smetterebbe
    di somigliare alla rotta il giorno in cui il catalogo cambia."""
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"tools": [{"name": d["name"]} for d in STRUMENTI_CONOSCENZA]}}


class _Client:
    """Il finto client del giro del ponte: claim, submit e -- dal Task 3 della
    parita' B -- la rotta `/api/mcp` che la sonda degli strumenti interroga.

    `mcp=False` spegne la rotta (401): e' il ramo di DEGRADO, quello in cui il
    ponte deve accorgersene prima di comporre il prompt."""
    def __init__(self, claim_body, *, mcp=True):
        self.claim_body = claim_body
        self.submitted = []
        self.mcp = mcp
        self.sondata = []
    def post(self, url, headers=None, json=None, **kwargs):
        if url.endswith("/api/reasoning/claim"): return _Resp(self.claim_body)
        if url.endswith("/api/reasoning/submit"): self.submitted.append(json); return _Resp({"ok": True})
        if url.endswith("/api/mcp"):
            self.sondata.append({"headers": headers, "corpo": json})
            if not self.mcp:
                return _Resp({"error": "unauthorized"}, status_code=401)
            return _Resp(_tools_list_come_la_rotta())
        raise AssertionError(url)


# fetta "il ponte riceve gli strumenti" (parita' B, Task 2): lo stdout finto e'
# il flusso NDJSON vero -- `system/init`, un evento `assistant`, e l'evento
# finale `result` da cui si prende il testo.
def _init_col_server_collegato() -> str:
    """L'evento `system/init` di un turno in cui gli strumenti sono arrivati
    DAVVERO (fetta parita' B, Task 4).

    Prima di quel task questo finto stdout diceva `mcp_servers: []` e `tools:
    ["Task"]` -- cioe' descriveva un turno in cui la CLI NON aveva collegato
    niente -- mentre il test intorno si chiamava «il giro felice CON gli
    strumenti». Nessuno se ne accorgeva perche' nessuno leggeva l'`init`; dal
    Task 4 quell'evento e' cio' su cui il ponte decide, e un finto flusso che
    lo contraddice descrive il guasto, non il giro felice.

    I nomi si derivano da `runner.nomi_mcp()`: un elenco ricopiato qui
    sarebbe il secondo catalogo."""
    nomi = ", ".join(f'"{n}"' for n in runner.nomi_mcp())
    return ('{"type":"system","subtype":"init","tools":["Task", ' + nomi + '],'
            '"mcp_servers":[{"name":"' + runner._nome_server_mcp() +
            '","status":"connected"}]}')


class _ProcFelice:
    returncode = 0
    stdout = (
        _init_col_server_collegato() + '\n'
        '{"type":"assistant","message":{"role":"assistant",'
        '"content":[{"type":"text","text":"2 luci accese"}]}}\n'
        '{"type":"result","subtype":"success","is_error":false,"num_turns":1,'
        '"result":"2 luci accese","usage":{"input_tokens":12,'
        '"cache_creation_input_tokens":4096,"cache_read_input_tokens":8192,'
        '"output_tokens":57}}\n')
    stderr = ""


def test_run_once_chat_reasons_and_submits():
    """Il giro felice del ponte, che dal Task 3 della parita' B e' il giro CON
    gli strumenti: la sonda trova tutti i nomi, l'argv li collega, e la
    `reply` che torna alla reasoning API e' la risposta del modello e basta --
    nessuna riga di degrado, perche' non c'e' nessun degrado da dichiarare."""
    job = {"job_id": "J", "nonce": "N", "kind": "chat",
           "context": {"system_prompt": "Sei HIRIS.", "history": [{"role": "user", "content": "che luci?"}]}}
    c = _Client({"job": job})
    catturato = {}

    def _run(argv, *a, **k):
        catturato["argv"] = argv
        return _ProcFelice()

    with patch.object(runner.subprocess, "run", _run):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")
    assert out == "done"
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 5): la `decision`
    # porta anche `tools_called` -- qui vuota, perche' questo flusso finto
    # (`_ProcFelice`, sotto) non contiene nessun blocco `tool_use`. La lista
    # e' VUOTA, non assente: e' il segnale che il turno e' girato in modalita'
    # `live` senza chiamare nulla, non un job che non ha mai avuto
    # l'occasione di farlo.
    assert c.submitted and c.submitted[0]["decision"] == {
        "reply": "2 luci accese", "tools_called": []}

    # la sonda e' passata dalla rotta, con GLI STESSI header del claim (non un
    # secondo modo di autenticarsi verso se stessi) e col metodo giusto
    assert c.sondata, "il ponte non ha sondato /api/mcp prima di comporre il turno"
    assert c.sondata[0]["headers"] == {"X-HIRIS-Internal-Token": "TOK"}
    assert c.sondata[0]["corpo"]["method"] == "tools/list"
    # ...e il giro di produzione ha davvero collegato gli strumenti
    assert "--mcp-config" in catturato["argv"]


def test_run_once_dichiara_all_utente_il_turno_senza_strumenti():
    """Il gemello, ed e' la difesa (3) del progetto: gli strumenti erano ATTESI
    (il giro di produzione passa client e base_url) e la rotta non li ha dati.
    Il turno non fallisce -- il modello risponde comunque sul nucleo -- ma la
    `reply` lo DICE all'utente, in una riga premessa. Mai una risposta che
    sembra normale.

    E la risposta vera resta sotto, intera: e' il motivo per cui questa riga
    NON e' fra i `chat_store._TOXIC_ASSISTANT_PREFIXES` come gli altri
    sentinella del ponte -- quelli sostituiscono la risposta, questa la
    precede."""
    job = {"job_id": "J", "nonce": "N", "kind": "chat",
           "context": {"system_prompt": "Sei HIRIS.", "history": [{"role": "user", "content": "che luci?"}]}}
    c = _Client({"job": job}, mcp=False)
    catturato = {}

    def _run(argv, *a, **k):
        catturato["argv"] = argv
        return _ProcFelice()

    with patch.object(runner.subprocess, "run", _run):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")

    assert out == "done"
    reply = c.submitted[0]["decision"]["reply"]
    assert reply.startswith(runner.AVVISO_STRUMENTI_ASSENTI)
    assert "2 luci accese" in reply
    # e il prompt e' tornato a negarli, insieme all'argv: un solo booleano
    assert "--mcp-config" not in catturato["argv"]
    system = catturato["argv"][catturato["argv"].index("--system-prompt") + 1]
    assert prompts._GUIDA_SENZA_STRUMENTI in system


@pytest.mark.asyncio
async def test_run_loop_does_not_block_event_loop(monkeypatch):
    # run_once is slow+sync (real impl uses httpx.Client + subprocess.run); it
    # must be offloaded to a thread executor so a concurrent coroutine on the
    # same event loop keeps making progress while it runs. Regression test for
    # the event-loop-blocking defect found in Task 4 review.
    #
    # I-1 fast-follow (Plan 2B final review): the original version of this
    # test (`await ticker()` unconditionally, then assert `ticks >= 4`) is
    # tautological -- it passes even if run_loop blocks the loop, because the
    # ticker's sleeps just fire LATE once run_once finally releases the loop;
    # nothing bounds the wall-clock. Rewritten to bound it: the ticker's 5 x
    # 0.02s iterations are wrapped in `asyncio.wait_for(..., timeout=0.25)`.
    # With the run_in_executor offload, run_once's 0.3s sleep runs on a
    # separate thread, so the ticker finishes in ~0.1s and wait_for does NOT
    # raise. If run_loop were reverted to calling the blocking run_once
    # inline, the ticker would be stalled behind the 0.3s sleep and wait_for
    # WOULD raise TimeoutError -- making this test an actual regression guard.
    def slow_once(client, base_url, headers, mode):
        time.sleep(0.3)
        return "idle"
    monkeypatch.setattr(runner, "run_once", slow_once)

    # run_loop constructs a real httpx.Client(timeout=330) synchronously
    # before its first `await` -- in this environment that constructor alone
    # takes ~2.3s (Windows system cert-store loading), which would blow any
    # tight budget regardless of the run_once-offload fix under test. Stub it
    # out with a near-instant fake context manager so the test isolates
    # exactly the thing it's meant to check.
    class _FakeHttpxClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(runner.httpx, "Client", _FakeHttpxClient)

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.02)
            ticks += 1

    loop_task = asyncio.create_task(
        runner.run_loop("http://127.0.0.1:8099", dict, "live", 0))
    try:
        await asyncio.wait_for(ticker(), timeout=0.25)
    except TimeoutError:
        pytest.fail(
            "ticker did not complete within budget -- run_loop appears to be "
            "blocking the event loop instead of offloading run_once"
        )
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert ticks == 5  # all ticker iterations completed within the tight budget


# ── fetta E4 Task 8 ("un bot solo"): il ramo olistico di `reason()` e' uscito
# (con `prompts.build_holistic_prompt`/`_SYSTEM` e tutto l'apparato che ne
# leggeva la risposta: `Decision`, `VERDICT_*`, `_JSON_RE`,
# `FALLBACK_MESSAGE_MAX`, `_parse_decision`, `parse_decision` -- i cinque test
# che li pinnavano sono caduti per costruzione, `AttributeError: module ... has
# no attribute 'parse_decision'`). Al suo posto un SILENZIO DICHIARATO, e i due
# test qui sotto sono la sua rete: senza di loro, cancellare il `log.warning`
# lascerebbe la suite verde e il ponte tornerebbe a scartare job in silenzio --
# il difetto numero uno di questo prodotto. ──────────────────────────────────

def test_job_non_chat_e_dichiarato_nel_log_e_decide_vuoto(caplog):
    job = {"job_id": "J-legacy", "kind": "holistic",
           "context": {"snapshot": {"luci": 2}}}
    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        decision = runner.reason(job, "live")

    # decisione VUOTA: nessun verdetto, nessuna severita', nessuna azione.
    assert decision == {}
    rec = [r for r in caplog.records if r.name == "hiris.agent"]
    assert len(rec) == 1, "il job scartato deve essere dichiarato una volta sola"
    assert rec[0].levelno == logging.WARNING
    messaggio = rec[0].getMessage()
    assert "J-legacy" in messaggio and "holistic" in messaggio
    assert "non-chat" in messaggio


def test_run_once_job_non_chat_invia_la_decisione_vuota_senza_chiamare_claude():
    # Il guard non e' un `return` muto a meta' strada: il job viene comunque
    # chiuso sulla reasoning API (submit con decisione vuota, che
    # `handle_reasoning_submit` si limita a registrare), e nessun `claude -p`
    # viene speso per ragionarlo.
    job = {"job_id": "J", "nonce": "N", "kind": "holistic", "context": {"snapshot": {}}}
    c = _Client({"job": job})

    def _boom(*a, **k):
        raise AssertionError("nessun subprocess claude per un job non-chat")

    with patch.object(runner.subprocess, "run", _boom):
        out = runner.run_once(c, "http://127.0.0.1:8099", {"X-HIRIS-Internal-Token": "TOK"}, "live")

    assert out == "done"
    assert c.submitted and c.submitted[0]["decision"] == {}


# ── fetta E4 Task 8, Step 1: `_CHAT_TOOL_GUIDANCE` diceva al modello di avere
# strumenti per leggere la casa "e, quando serve, per agire", e che "le azioni
# possono richiedere una conferma" -- tre affermazioni false in tre righe
# (rilievo I-1/I-2 della review finale della fetta E3, dal lato abbonamento).
# Questo runner ragiona in puro testo: nessun catalogo di strumenti gli viene
# passato (`_chat_claude_args` non passa ne' `--mcp-config` ne'
# `--allowedTools` -- non piu' solo qui in commento: lo asserisce
# `test_argv_del_ponte_non_collega_nessuno_strumento` in fondo al file),
# HIRIS non agisce, le conferme sono uscite con l'impianto OTP. Il test
# difende il CONTENUTO del prompt, l'unica riga del prodotto che il modello
# legge come verita': senza, la falsita' potrebbe rientrare a suite verde.
#
# fetta «comandare» (Task 7): di quel blocco una sola cosa e' rimasta indietro,
# ed e' «HIRIS non agisce». Il prodotto agisce dal Task 5 (`esegui`, catalogo
# unico) e il prompt lo dice dal Task 6. Cio' che questo test difende NON
# cambia, e per questo il blocco non si riscrive: il ramo di DEGRADO -- quello
# senza strumenti -- non ha davvero niente da chiamare, e li' l'assenza di
# strumenti E di azione resta vera per sempre. Le asserzioni dentro al test
# sono gia' state riportate dal Task 6 dalla proprieta' del PRODOTTO a quella
# del TURNO; questa riga e' la sola che raccontava ancora il prodotto.
# ─────────────────────────────────────────────────────────────────────────────

def test_il_prompt_di_sistema_del_ponte_non_promette_strumenti_ne_azioni():
    """── PIN RIBALTATO, fetta "il ponte riceve gli strumenti" (parita' B,
    Task 3). Fino a questa fetta questo test guardava il prompt del ponte, e
    basta: gli strumenti non c'erano per NESSUNO. Ora ce ne sono due, di
    prompt, e questo pin difende quello del ramo di DEGRADO --
    `strumenti_attivi=False`, cioe' il turno in cui la sonda non ha trovato la
    rotta o tutti i nomi del catalogo.

    Il valore era il default e ora si passa ESPLICITAMENTE: un pin che si
    appoggia a un default smette di sorvegliare il giorno in cui il default
    cambia, e sarebbe un modo silenzioso di svuotare proprio questo test.

    Tutte le asserzioni qui sotto restano valide PAROLA PER PAROLA, comprese
    le tre falsita' storiche che non devono rientrare: nel ramo di degrado il
    ponte non ha davvero strumenti, e il prompt deve continuare a dirlo per
    sempre. Il gemello sul ramo True e' il test subito sotto. ──"""
    system, _user = prompts.build_chat_messages(
        "Per scoprire cosa c'e' in casa usa `cerca` e `guarda`.",
        [], contesto="## La casa\nSalotto: luce accesa.",
        strumenti_attivi=False)

    # dice il vero su cio' che NON ha
    assert "NON hai alcuno strumento" in system
    # fetta «comandare» (Task 6): questo assert era `"non agisce" in system`.
    # Il soggetto e' vivo -- in QUESTO turno non si tocca la casa -- ma la
    # formula era una proprieta' del PRODOTTO, e dal Task 5 il prodotto agisce
    # (`esegui`). Il testo dice ora la cosa vera e piu' stretta, e il pin la
    # segue: cambia la via d'accesso, non cio' che difende.
    assert "non puoi accendere, spegnere o chiamare un servizio" in system
    assert "non perche' HIRIS non sappia farlo" in system, (
        "la guida del degrado nega la capacita' senza dire che manca solo in "
        "questo turno: e' la vecchia falsita' di prodotto, riscritta")
    assert "nessuna conferma" in system
    # e dice al modello di DICHIARARE cio' che non puo' leggere, non di fingerlo
    assert "DILLO" in system

    # le tre falsita' storiche non devono poter rientrare
    assert "per agire" not in system
    assert "Hai accesso a strumenti" not in system
    assert "in attesa di conferma" not in system

    # ── fix round 1, Important 2 della review indipendente: le tre negative
    # qui sopra erano diventate AGGIRABILI, e l'aggiramento era gia' avvenuto.
    # `"Hai accesso a strumenti" not in system` passava mentre il prompt
    # affermava gli strumenti -- perche' `BASE_SYSTEM_PROMPT`, che il Task 2
    # aveva cominciato a comporre qui, lo scrive con altre parole («Hai A
    # DISPOSIZIONE strumenti»). La rete non era stata tagliata: era stata
    # aggirata. Le negative vanno quindi sui PEZZI CHE CONTANO, presi dal
    # testo reale della meta' che il ponte non deve emettere
    # (`claude_runner.BASE_REGOLE_STRUMENTI`), e applicate al `system`
    # COMPOSTO -- non alla costante.
    for ordine in ("Hai a disposizione strumenti", "Usa SEMPRE gli strumenti",
                   "chiama ricorda subito"):
        assert ordine in BASE_REGOLE_STRUMENTI, (
            f"{ordine!r} non e' piu' nel testo di BASE_REGOLE_STRUMENTI: "
            "questa negativa non sta piu' sorvegliando niente")
        assert ordine not in system, (
            f"il prompt del ponte ORDINA {ordine!r} a un percorso che non ha "
            "strumenti: e' il caso 'preso nota senza aver salvato'")
    # e la meta' vera c'e', cosi' la negativa qui sopra non passa perche' BASE
    # e' sparito del tutto
    assert BASE_IDENTITA.strip() in system

    # ── fix round 1, Important 1: la falsita' speculare era stata corretta
    # per la casa («leggere» -> «guardare adesso») e lasciata in piedi per la
    # META' MEMORIA. Il contesto che arriva al ponte contiene TUTTI i ricordi
    # (`costruisci_nucleo` chiama `richiama(limite=conta())`) e le sessioni
    # precedenti: dire al modello che non puo' «richiamare ricordi» mentre il
    # ricordo e' scritto tre blocchi piu' sotto e' lo stesso difetto.
    assert "richiamare ricordi" not in system
    assert "non puoi salvare nuovi ricordi" in system
    assert "ricordi e sessioni precedenti compresi" in system

    # ── fetta "il ponte riceve il nucleo" (parita' A, Task 2): il pin si
    # ESTENDE, non si riduce. Tutte le asserzioni qui sopra restano -- gli
    # strumenti sul ponte continuano a non esserci, e questa fetta non glieli
    # da'. Cio' che cambia e' che il ponte ora RICEVE il nucleo: continuare a
    # dire al modello «non puoi leggere lo stato della casa» sarebbe la
    # falsita' SPECULARE, dello stesso genere di quelle tre. Il prompt deve
    # dire l'una e l'altra cosa insieme: nessuno strumento, ma una fotografia
    # -- e la fotografia e' ancorata al TURNO, mai a un orario (il nucleo non
    # timbra: `casa/nucleo.py::componi` e' pura e non compone nessuna data,
    # quindi qualunque ora nel prompt sarebbe inventata).
    assert "la fotografia qui sotto" in system
    # fix round 1, Important 1: «non e' aggiornabile in questo turno» e' USCITA
    # da `_CONTESTO_PRESENTE`. Non e' un pin allentato: quel testo esce su
    # ENTRAMBI i rami, ed era l'ultima cosa che il modello leggeva prima di
    # `## La casa` -- col ramo attivo contraddiceva «guarda adesso» due righe
    # sopra ed era falsa al presente. Il SOGGETTO (in questo turno la casa non
    # si puo' guardare) e' vivissimo qui sul ramo di degrado, e vive dove deve:
    # nella guida, che e' l'unico posto che dice cosa il modello ha e non ha.
    # Il test si adegua alla nuova via d'accesso, non si butta.
    assert "non puoi guardare adesso lo stato della casa" in system
    assert "servirebbe un valore aggiornato ADESSO, DILLO" in system
    assert "non presentarla come una lettura fatta adesso" in system
    # la falsita' speculare: il prompt non deve piu' negare al presente che il
    # modello possa leggere la casa, perche' la casa gliela stiamo dando.
    assert "non puoi leggere lo stato della casa" not in system
    # e il contesto ricevuto e' davvero nel prompt, non solo annunciato
    assert "Salotto: luce accesa." in system


# fetta "comandare" (Task 5, lo strumento `esegui`): questo test cade, e cade
# per la ragione GIUSTA -- non perche' contasse quattro dove ora ce ne sono
# cinque. Da questo commit l'argv passa `--allowedTools ... mcp__hiris__esegui`
# (deriva da `STRUMENTI_CONOSCENZA`) mentre `_GUIDA_CON_STRUMENTI` nomina
# ancora solo i quattro e per giunta dichiara «HIRIS non agisce comunque»:
# l'invariante argv <=> prompt e' DAVVERO rotta, e questo test ha fatto
# esattamente il suo mestiere segnalandolo.
#
# Non si allinea e non si indebolisce: il prompt e' materia del Task 6 della
# stessa fetta ("il prompt sa di poter agire"), che riscrive entrambe le guide
# e le due dichiarazioni di `claude_runner.py`. Spezzare quel lavoro in due --
# un pezzo qui e il resto la', su un testo di cui conta l'equilibrio
# complessivo -- e' il motivo per cui il piano lo tiene separato.
#
# `strict=True` non e' un dettaglio: e' cio' che rende questo debito
# AUTO-ESIGIBILE. Appena il Task 6 nominera' `esegui` nella guida, questo test
# passera' -- e con `strict` un XPASS e' un FALLIMENTO: la suite tornera'
# rossa finche' qualcuno non toglie questa riga. Un `xfail` non-strict
# sarebbe stato il modo silenzioso di dimenticarsene.
#
# Task 6, DEBITO SALDATO: il marker e' stato tolto e il test e' un test
# normale, verde. `_GUIDA_CON_STRUMENTI` nomina `mcp__hiris__esegui` e non
# dichiara piu' «HIRIS non agisce comunque»; l'invariante argv <=> prompt e'
# di nuovo intera, e questo test la sorveglia sui CINQUE nomi senza saperlo
# (li prende da `runner.nomi_mcp()`, che deriva dal catalogo unico). Il nome
# del test ha perso «i_quattro_»: contava un numero che non conta.
def test_col_ramo_attivo_il_prompt_afferma_gli_strumenti_prefissati():
    """Il GEMELLO del pin qui sopra, nato con la fetta "il ponte riceve gli
    strumenti" (parita' B, Task 3): sul ramo `strumenti_attivi=True` il prompt
    deve affermare gli strumenti del catalogo -- e affermarli **coi nomi che
    il modello vedra' davvero**.

    E' la meta' che rende il pin dell'argv una coppia invece di un assert
    isolato: l'argv da' `--allowedTools mcp__hiris__*`, e questo test verifica
    che il testo del prompt nomini quegli stessi nomi. Se un giorno il nome
    del server MCP cambiasse senza che il prompt lo segua, il modello
    leggerebbe di poter chiamare `mcp__hiris__cerca` e la CLI gli servirebbe
    tutt'altro: strumenti visibili e non chiamabili, cioe' il difetto numero
    uno di questo prodotto in una forma nuova."""
    system, _user = prompts.build_chat_messages(
        "Per scoprire cosa c'e' in casa usa `cerca` e `guarda`.",
        [], contesto="## La casa\nSalotto: luce accesa.",
        strumenti_attivi=True)

    # dice il vero su cio' che HA
    assert "HAI gli strumenti di HIRIS" in system
    assert "NON hai alcuno strumento" not in system
    # i nomi VERI, derivati dal catalogo e non scritti a mano qui: sono gli
    # stessi che finiscono in --allowedTools (runner.nomi_mcp()).
    for nome in runner.nomi_mcp():
        assert f"`{nome}`" in system, (
            f"il prompt afferma gli strumenti ma non nomina {nome!r}, che e' "
            "il nome con cui la CLI li serve al modello: il modello leggerebbe "
            "un nome e ne dovrebbe chiamare un altro")
    # ...e i nomi NUDI restano nominati, perche' la persona (il system prompt
    # delle impostazioni) continua a usarli: il prompt li ricollega ai nomi
    # prefissati invece di lasciarli orfani.
    # fetta «comandare» (Task 6): «STESSI quattro strumenti» -> «STESSI
    # strumenti». Il numero non partecipava al ricollegamento (che si fa
    # elencando i nomi, non contandoli) ed era l'ennesima dichiarazione da
    # tenere allineata a mano: gli strumenti sono cinque da `33da82b`.
    assert "STESSI strumenti" in system
    # ── fetta «comandare» (Task 6). Qui stavano `"non agisce" in system` e
    # `"per agire" not in system`: il pin di un prodotto che conosceva e non
    # attuava. Il Task 5 ha dato `esegui` al modello, e questa e' la prima
    # riga di test che DEVE cambiare di segno -- non per accomodare il codice
    # ma perche' la proprieta' difesa non esiste piu'. Al suo posto: il prompt
    # del ramo attivo non deve poter tornare a NEGARE l'azione, che sarebbe il
    # sintomo indistinguibile da «gli strumenti sono rotti».
    for negazione in ("non agisce", "non accendi", "non spegni"):
        assert negazione not in system, (
            f"il prompt del ramo ATTIVO dice «{negazione}» mentre la CLI gli "
            "serve `mcp__hiris__esegui`: il modello rifiutera' di agire")
    # cio' che NON diventa vero nemmeno qui: nessuna conferma esiste, e il
    # prompt non deve prometterne una (ne' inventare azioni in sospeso).
    assert "nessuna conferma" in system
    assert "in attesa di conferma" not in system

    # ── fix round 1, Important 1: IL CONTRORDINE.
    # `_CONTESTO_PRESENTE` esce su entrambi i rami ed e' l'ULTIMA cosa che il
    # modello legge prima del blocco `## La casa` -- cioe' quella che pesa di
    # piu'. Due sue clausole erano scritte quando il ramo attivo non esisteva e,
    # accese le quattro chiamate, dicevano al modello l'opposto della riga che
    # le precede di poche parole («quando serve un valore CORRENTE chiama lo
    # strumento ... guarda adesso»). Il sintomo sarebbe stato indistinguibile da
    # «gli strumenti non funzionano»: `status: connected` nel log, NESSUNA
    # `tools/call`, e una risposta costruita sullo snapshot -- e il Task 4 non
    # lo intercetterebbe, perche' la sonda ha detto si' e l'init dira'
    # `connected`. Fino a questo giro NESSUN test guardava cosa c'e' nel prompt
    # attivo oltre alla guida: e' il buco da cui e' passato.
    assert "non e' aggiornabile in questo turno" not in system, (
        "il prompt del ramo ATTIVO dice al modello che la fotografia non e' "
        "aggiornabile in questo turno, mentre due righe sopra gli ordina di "
        "chiamare `mcp__hiris__guarda` per i valori correnti: e' un "
        "contrordine, ed e' falso -- la fotografia E' aggiornabile, con lo "
        "strumento")
    assert "invece di rispondere che non puoi richiamarlo" not in system, (
        "il prompt del ramo ATTIVO manda il modello a frugare nella fotografia "
        "invece di chiamare `mcp__hiris__richiama`, che in questo turno c'e': "
        "quella clausola era la COMPENSAZIONE dell'assenza dello strumento, e "
        "con lo strumento presente diventa un contrordine")
    # ...e l'ordine che DEVE sopravvivere e' ancora li'
    assert "guarda adesso" in system
    # cio' che resta vero su entrambi i rami, e non e' stato buttato col resto
    assert "la fotografia qui sotto" in system
    assert "ricordi e sessioni precedenti compresi" in system
    assert "non presentarla come una lettura fatta adesso" in system


def test_il_prompt_del_ponte_smentisce_gli_strumenti_nominati_dalla_persona():
    # Il `system_prompt` che arriva al ponte e' quello delle impostazioni della
    # chat (`impostazioni_chat.DEFAULT_SYSTEM_PROMPT`), scritto per il percorso
    # SINCRONO -- dove gli strumenti di casa/strumenti.py esistono
    # davvero. Qui non esistono: la guida deve smentirlo esplicitamente, o il
    # modello leggerebbe "usa `cerca`" senza alcun modo di scoprire che non c'e'.
    from hiris.app.impostazioni_chat import DEFAULT_SYSTEM_PROMPT

    # ── PIN RIBALTATO (parita' B, Task 3): il ramo esplicito e' quello di
    # DEGRADO. La smentita resta necessaria esattamente li': quando gli
    # strumenti non ci sono, la persona continua a nominarli.
    system, _user = prompts.build_chat_messages(DEFAULT_SYSTEM_PROMPT, [],
                                                strumenti_attivi=False)

    assert "cerca" in DEFAULT_SYSTEM_PROMPT and "guarda" in DEFAULT_SYSTEM_PROMPT
    assert "quelle istruzioni non si applicano" in system

    # fetta E4, fix della review totale (m9): questi due assert erano su
    # `system` -- e `system` contiene ANCHE DEFAULT_SYSTEM_PROMPT, che quei due
    # nomi li scrive gia' in backtick (impostazioni_chat.py). Non potevano
    # fallire: passavano anche cancellando l'elenco dalla guida del ponte,
    # cioe' proprio la mutazione che questo test dichiara di sorvegliare.
    # L'invariante e' che LA GUIDA li nomini per negarli, quindi si asserisce
    # sul segmento della guida, non sulla concatenazione.
    # fetta "il ponte riceve il nucleo" (parita' A, Task 2): `_CHAT_TOOL_
    # GUIDANCE` si chiama ora `_GUIDA_SENZA_STRUMENTI`, perche' le guide sono
    # diventate DUE -- l'altra (`_GUIDA_CON_STRUMENTI`) e' scritta per la
    # fetta B e non e' raggiungibile dalla produzione. Il soggetto di questo
    # test e' vivo e invariato: cambia solo la via d'accesso, quindi il test
    # si adegua invece di essere cancellato (verificato prima dell'adeguamento
    # che falliva con AttributeError, cioe' per costruzione).
    guida = prompts._GUIDA_SENZA_STRUMENTI
    assert "`cerca`" in guida and "`guarda`" in guida
    assert "`ricorda`" in guida and "`richiama`" in guida
    assert guida in system


def test_col_ramo_attivo_la_persona_non_viene_smentita_ma_ricollegata():
    """Il gemello (parita' B, Task 3). Sul ramo con gli strumenti la persona
    dice il VERO -- `cerca` e `guarda` esistono davvero -- e smentirla sarebbe
    la falsita' speculare, lo stesso difetto girato al contrario.

    Cio' che il prompt deve fare qui e' un'altra cosa: **ricollegare** i nomi
    nudi della persona ai nomi prefissati che la CLI serve davvero.
    Senza quel ponte il modello leggerebbe «usa `cerca`» e chiamerebbe un nome
    che non gli e' stato dato."""
    from hiris.app.impostazioni_chat import DEFAULT_SYSTEM_PROMPT

    system, _user = prompts.build_chat_messages(DEFAULT_SYSTEM_PROMPT, [],
                                                strumenti_attivi=True)
    guida = prompts._GUIDA_CON_STRUMENTI

    assert guida in system
    assert prompts._GUIDA_SENZA_STRUMENTI not in system
    # la smentita del ramo di degrado non deve poter comparire qui: sarebbe
    # falsa, e la falsita' speculare e' lo stesso difetto.
    assert "quelle istruzioni non si applicano" not in guida
    # i nomi nudi del catalogo sono tutti nominati dalla guida -- `esegui`
    # compreso dalla fetta «comandare»: l'elenco si DERIVA da
    # `STRUMENTI_CONOSCENZA`, cosi' uno strumento nuovo entra qui da solo
    # invece di lasciare questo test a sorvegliarne quattro su cinque.
    for voce in STRUMENTI_CONOSCENZA:
        assert f"`{voce['name']}`" in guida
    # ...e i due che la persona nomina davvero (impostazioni_chat.py ne scrive
    # due soli, ed e' una decisione: vedi il commento sopra
    # `DEFAULT_SYSTEM_PROMPT`) sono proprio quelli che la guida ricollega.
    for nudo in ("`cerca`", "`guarda`"):
        assert nudo in DEFAULT_SYSTEM_PROMPT


# ── LA LAPIDE DEL PIN, e perche' e' cambiato ─────────────────────────────
#
# **Cosa pinnava fino alla fetta "il ponte riceve gli strumenti" (parita' B).**
# Il prompt del ponte affermava «NON hai alcuno strumento di HIRIS», ed era vero
# SOLO perche' `_chat_claude_args` non passava `--mcp-config` ne'
# `--allowedTools`. Quella condizione viveva in un commento, e un commento non
# tiene niente: `test_argv_del_ponte_non_collega_nessuno_strumento` la portava
# in un assert, come CAMPANELLO scritto apposta per la fetta che avrebbe
# riattaccato gli strumenti. Il suo messaggio d'errore diceva a chi lo avrebbe
# visto rosso di riscriverlo, non di cancellarlo.
#
# **Cosa e' successo (questa fetta, parita' B, Task 3).** Gli strumenti sono
# tornati. Il campanello ha suonato -- e ha suonato in un modo che vale la pena
# scrivere qui, perche' non era quello previsto: NON e' diventato rosso da solo.
# Chiamava `_chat_claude_args("SYS", "USER", "sonnet")` coi soli argomenti
# posizionali, e quel percorso -- oggi -- e' il ramo di DEGRADO, dove
# `strumenti_attivi=False` e l'argv e' ancora quello di prima. Il pin era
# rimasto verde smettendo di sorvegliare il percorso di produzione: il modo
# peggiore in cui una rete si rompe. Rosso e' diventato il suo gemello a valle,
# `test_run_once_chat_reasons_and_submits` (il giro vero, con client e
# base_url), e il quarto campanello
# `test_nessun_chiamante_di_produzione_gira_l_interruttore`
# (tests/test_ponte_riceve_il_nucleo.py).
#
# **Cosa pinnano adesso i due test qui sotto, insieme.** La nuova condizione di
# verita', nei due rami:
#   - con `strumenti_attivi=True` gli strumenti CI SONO, sono ESATTAMENTE
#     quelli di `casa/strumenti.py` (derivati, mai scritti a mano) e il prompt
#     lo dice (il gemello sul prompt e'
#     `test_col_ramo_attivo_il_prompt_afferma_gli_strumenti_prefissati`);
#   - con `strumenti_attivi=False` l'asserzione vecchia resta viva PAROLA PER
#     PAROLA: e' il ramo di degrado, e deve restare onesto per sempre.
# L'invariante che lega i due rami al prompt -- `--mcp-config` nell'argv <=>
# `_GUIDA_CON_STRUMENTI` nel system, nei DUE VERSI -- e' pinnato in
# tests/test_strumenti_al_ponte.py, ed e' quello da non cancellare mai.
#
# `_normalizza` SI CONSERVA: la variante kebab-case `--allowed-tools` non
# doveva aggirare il vecchio assert e non deve aggirare nemmeno il nuovo.
# ──────────────────────────────────────────────────────────────────────────────

def _normalizza(argv):
    """Le opzioni del CLI, in una forma sola.

    `claude` accetta sia `--allowedTools` sia l'alias kebab-case
    `--allowed-tools`: due grafie della STESSA opzione. Un assert su una sola
    delle due non scatterebbe se la fetta che riattacca gli strumenti al ponte
    scrivesse l'altra -- il campanello resterebbe muto proprio nel caso per cui
    esiste. Confrontare in minuscolo e senza trattini le rende indistinguibili.
    Si confronta elemento per elemento (mai su una concatenazione): normalizzato,
    "--disallowedTools" CONTIENE "allowedtools", e un test per sottostringa
    fallirebbe sull'argv di oggi.
    """
    return {a.lower().replace("-", "") for a in argv}


def test_argv_del_ponte_collega_esattamente_gli_strumenti_del_catalogo():
    """Il pin ribaltato: con `strumenti_attivi=True` gli strumenti ci sono, e
    sono esattamente quelli del catalogo unico -- ne' uno di piu' ne' uno di
    meno. Il nome del test non conta piu' «i quattro»: contava un numero che
    non conta, ed e' cambiato una volta gia' (fetta «comandare»)."""
    argv = runner._chat_claude_args("SYS", "USER", "sonnet",
                                    strumenti_attivi=True,
                                    mcp_config=runner.config_mcp("http://x", "TOK"))
    opzioni = _normalizza(argv)

    _perche = (
        "gli strumenti sono spariti dall'argv del ponte mentre "
        "prompts._GUIDA_CON_STRUMENTI continua ad affermarli al modello: il "
        "prompt e' tornato FALSO a suite verde -- il difetto numero uno di "
        "questo prodotto, un prompt che promette capacita' che l'invocazione "
        "non da'. La risposta giusta e' capire PERCHE' l'argv non le porta "
        "piu' (l'interruttore unico e' `strumenti_attivi` in "
        "runner._reason_chat, deciso da runner.sonda_strumenti), non "
        "cancellare questo assert: cancellarlo lascerebbe il prompt a mentire "
        "in silenzio, che e' la cosa che questo test esiste per impedire."
    )

    assert "mcpconfig" in opzioni, (
        f"--mcp-config e' sparito da argv ({argv!r}): " + _perche)
    assert "allowedtools" in opzioni, (
        f"--allowedTools (o il suo alias --allowed-tools) e' sparito da argv "
        f"({argv!r}): " + _perche)
    assert "strictmcpconfig" in opzioni, (
        f"--strict-mcp-config e' sparito da argv ({argv!r}): senza, la CLI "
        f"carica ANCHE i server MCP dell'ambiente, che non sono nostri -- il "
        f"modello si troverebbe strumenti che HIRIS non gli ha dato e che il "
        f"prompt non nomina.")

    # I NOMI, non solo la presenza dell'opzione: l'insieme passato ad
    # --allowedTools dev'essere IDENTICO a quello derivato dal catalogo. Una
    # lista scritta a mano nel runner sarebbe il secondo catalogo -- l'errore
    # che la fetta E2 e' esistita per chiudere -- e resterebbe verde se qui si
    # controllasse solo che l'opzione c'e'.
    passati = set(argv[argv.index("--allowedTools") + 1].split(","))
    assert passati == set(runner.nomi_mcp()), (
        f"i nomi passati ad --allowedTools ({sorted(passati)!r}) non sono "
        f"quelli derivati da STRUMENTI_CONOSCENZA ({sorted(runner.nomi_mcp())!r})")
    assert passati == {f"mcp__hiris__{d['name']}" for d in STRUMENTI_CONOSCENZA}

    # e i tool LOCALI del CLI restano esplicitamente vietati (shell/fs del
    # container addon): il prompt non e' l'unica difesa.
    assert "disallowedtools" in opzioni, (
        f"il divieto sui tool LOCALI del CLI (shell/fs del container addon) e' "
        f"sparito da argv ({argv!r}): il prompt non e' l'unica difesa, e questa "
        f"e' l'altra.")
    # ToolSearch NON e' nel divieto, e non e' una dimenticanza: la CLI ci passa
    # per risolvere gli schemi MCP, e vietarlo renderebbe gli strumenti
    # visibili e IRRAGGIUNGIBILI.
    assert "ToolSearch" not in runner._LOCAL_TOOLS_DENY, (
        "ToolSearch e' finito in _LOCAL_TOOLS_DENY: la CLI lo usa per "
        "risolvere gli schemi degli strumenti MCP, e vietarlo li rende "
        "irraggiungibili -- il prompt li afferma e la chiamata non arriva mai.")


def test_argv_del_ponte_senza_strumenti_resta_quello_di_prima():
    """Il ramo di DEGRADO: nessuno strumento, e nessuno che ne arrivi da fuori.

    Quando la sonda non trova gli strumenti il ponte compone il prompt che li
    nega: l'argv deve corrispondere, o il prompt torna a mentire nel verso
    opposto. Questo test deve restare onesto PER SEMPRE -- non e' un residuo
    della fetta precedente, e' l'altra meta' dell'interruttore.

    Review totale della fetta (I-1): «nessuno strumento» ha DUE condizioni, non
    una. Non basta che il ponte non ne PASSI (`--mcp-config`/`--allowedTools`
    assenti): serve anche che la CLI non ne PRENDA per conto suo
    (`--strict-mcp-config`). Il pin di questo test e' stato ribaltato per
    questo -- prima chiedeva l'assenza del flag per simmetria con l'altro ramo,
    ed era l'unico assert del file senza un motivo scritto."""
    argv = runner._chat_claude_args("SYS", "USER", "sonnet")
    opzioni = _normalizza(argv)

    _perche = (
        "l'argv del ramo di degrado ha guadagnato gli strumenti, ma quel ramo "
        "e' proprio quello in cui prompts._GUIDA_SENZA_STRUMENTI afferma al "
        "modello «NON hai alcuno strumento di HIRIS»: il prompt e' diventato "
        "FALSO. Il degrado si dichiara, non si rattoppa."
    )

    assert "mcpconfig" not in opzioni, (
        f"--mcp-config e' comparso nell'argv senza strumenti ({argv!r}): " + _perche)
    assert "allowedtools" not in opzioni, (
        f"--allowedTools (o il suo alias --allowed-tools) e' comparso nell'argv "
        f"senza strumenti ({argv!r}): " + _perche)
    assert "strictmcpconfig" in opzioni, (
        f"--strict-mcp-config e' sparito dall'argv del ramo di DEGRADO "
        f"({argv!r}). Qui il flag non e' una simmetria con l'altro ramo: e' "
        f"cio' che RENDE VERO il prompt che nega gli strumenti. Senza, la CLI "
        f"carica ANCHE i server MCP dell'ambiente (verificato dal vivo: SEI "
        f"server offerti al modello mentre prompts._GUIDA_SENZA_STRUMENTI gli "
        f"dice «NON hai alcuno strumento di HIRIS»), e l'ambiente non lo "
        f"controlliamo noi -- `run.sh` esporta CLAUDE_CONFIG_DIR=/data/claude "
        f"e /data e' scrivibile dall'host. Il flag non CONCEDE strumenti, li "
        f"TOGLIE: toglierlo di qui rimette il prompt alla fortuna.")
    assert "disallowedtools" in opzioni, (
        f"il divieto sui tool LOCALI del CLI (shell/fs del container addon) e' "
        f"sparito da argv ({argv!r}): il prompt non e' l'unica difesa, e questa "
        f"e' l'altra.")
    # il default della firma e' False, e il ramo di degrado e' quello che si
    # ottiene quando non si sa: un default True prometterebbe strumenti a chi
    # non li ha chiesti.
    assert argv == runner._chat_claude_args("SYS", "USER", "sonnet",
                                            strumenti_attivi=False)


# ── fetta "il ponte riceve gli strumenti" (parita' B, Task 2) ────────────────

def test_argv_del_ponte_chiede_il_formato_a_flusso_e_verboso():
    """`--output-format stream-json` SENZA `--verbose` e' peggio del vecchio
    `json`: la CLI non emette gli eventi intermedi, l'evento `system/init` non
    arriva mai, e con lui sparisce l'UNICO posto in cui si vede che il server
    MCP non e' partito (reperto dal vivo, progetto 3.4/6). Le due opzioni sono
    una cosa sola e vanno pinnate insieme, o una "pulizia" futura puo'
    togliere `--verbose` lasciando la suite verde e il ponte cieco."""
    argv = runner._chat_claude_args("SYS", "USER", "sonnet")

    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv, (
        f"--verbose e' sparito da argv ({argv!r}): senza, la CLI non emette "
        "l'evento system/init e il fallimento del server MCP torna a essere "
        "invisibile -- il difetto numero uno di questo prodotto.")
    # e il vecchio formato non deve poter rientrare accanto al nuovo: due
    # formati nell'argv sono due strade di lettura, che e' esattamente cio' che
    # il Task 2 esiste per evitare.
    assert "json" not in argv, (
        f"`--output-format json` e' rimasto in argv ({argv!r}) accanto a "
        "stream-json")
