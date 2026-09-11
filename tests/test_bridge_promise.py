"""Il ponte serve anche i risvegli: `kind="promessa"`.

Fetta «le promesse seguono la catena» (22/08/2026). Un turno di promessa e' un
TURNO -- stessa sonda degli strumenti, stesso ritentativo, stessa
`verify_init`, stessa redazione dei segreti. Cio' che cambia e' il contenuto,
e il contenuto arriva tutto dal contesto del job.

Questi test tengono ferme le due cose che rendono quel riuso corretto invece
che comodo: l'intestazione che dice al `/api/mcp` quale promessa si sta
mantenendo, e il fatto che un `kind` di promessa non finisca nel ramo dei kind
sconosciuti -- dove la decisione tornata sarebbe VUOTA e la promessa morirebbe
senza che nessuno sappia perche'.
"""
from __future__ import annotations

import json

from hiris.app.agent.runner import config_mcp


def _intestazioni(conf: str) -> dict:
    return json.loads(conf)["mcpServers"]["hiris"]["headers"]


class _ProcessoFinto:
    """Cio' che `subprocess.run` restituirebbe, senza lanciare niente.

    **Serve perche' una prova unitaria non deve lanciare la CLI `claude`**
    (rilievo della review indipendente, 11/09/2026): su una macchina senza
    `%SystemRoot%` la prova diventa rossa solo dentro la corsa intera, e su
    una macchina con la CLI autenticata spenderebbe un turno vero
    dell'abbonamento da dentro pytest, con 300 secondi di timeout.
    """

    returncode = 1
    stdout = ""
    stderr = "la CLI non e' stata lanciata: e' una prova"


def _cli_finta(monkeypatch):
    from hiris.app.agent import runner as ponte
    monkeypatch.setattr(ponte.subprocess, "run",
                        lambda *a, **kw: _ProcessoFinto())


def test_un_turno_di_promessa_porta_l_intestazione_della_promessa():
    conf = config_mcp("http://127.0.0.1:8099", "tok", "turno-1", "p1")
    assert _intestazioni(conf)["X-HIRIS-Promessa"] == "p1"


def test_un_turno_di_chat_NON_porta_l_intestazione():
    """La chat non mantiene nessuna promessa: un'intestazione sempre presente
    con valore vuoto sarebbe un campo che chi legge deve interpretare, invece
    di un'assenza che parla da se'."""
    conf = config_mcp("http://127.0.0.1:8099", "tok", "turno-1")
    assert "X-HIRIS-Promessa" not in _intestazioni(conf)


def test_il_token_resta_dov_era_anche_con_la_promessa_accanto():
    """L'intestazione nuova non deve spostare ne' indebolire le due che
    tengono viva la rotta (token interno e X-Requested-With)."""
    intestazioni = _intestazioni(config_mcp("http://127.0.0.1:8099", "tok", "t", "p1"))
    assert intestazioni["X-HIRIS-Internal-Token"] == "tok"
    assert intestazioni["X-Requested-With"] == "hiris-mcp"


def test_un_kind_promessa_NON_finisce_fra_i_kind_sconosciuti(caplog):
    """Il ramo dei kind sconosciuti restituisce una decisione VUOTA: una
    promessa che ci finisse morirebbe senza che nessuno sappia perche'. Il log
    di quel ramo resta -- dichiara un silenzio che serve ancora, per i job di
    un'installazione precedente -- ma non deve piu' vedere le promesse."""
    from hiris.app.agent import runner as ponte

    esito = ponte.reason(
        {"kind": "promessa", "job_id": "j1",
         "context": {"promessa_id": "p1", "history": [], "system_prompt": ""}},
        "mock")

    assert "job non-chat in coda" not in caplog.text
    assert esito != {}, "una decisione vuota e' cio' che il ramo sconosciuto da'"


def test_un_kind_davvero_sconosciuto_resta_dichiarato(caplog):
    """L'altra meta': il ramo non si cancella allargandolo."""
    import logging

    from hiris.app.agent import runner as ponte

    with caplog.at_level(logging.WARNING):
        esito = ponte.reason({"kind": "olistico", "job_id": "j2", "context": {}}, "mock")

    assert esito == {}
    assert "job non-chat in coda" in caplog.text


# --- il catalogo del turno vale su TUTTI e tre i punti ------------------------
#
# Difetto trovato dalla VERIFICA LIVE della 3.10.0, non dalla suite: il ponte
# ha servito il risveglio (l'instradamento era giusto) ma il turno ha
# dichiarato «non ho potuto usare gli strumenti» e ha risposto a parole.
#
# La fetta aveva reso il catalogo PER TURNO nella rotta MCP, e lasciato tre
# punti ancorati a quello della chat: `--allowedTools`, la sonda, e la verifica
# dell'init. Un turno di promessa riceve 5 strumenti (4 lettori + `conclude`),
# la verifica ne pretendeva 9, li dichiarava mancanti, e il ritentativo
# ripartiva senza strumenti. Il modello non aveva `conclude`, quindi non aveva
# nessun modo di finire.


def test_i_nomi_attesi_seguono_il_catalogo_del_turno():
    from hiris.app.agent.runner import mcp_names

    chat = set(mcp_names())
    promessa = set(mcp_names(by_promise=True))

    assert any(n.endswith("__conclude") for n in promessa), (
        "senza «conclude» fra i nomi permessi il turno non ha modo di finire")
    assert not any(n.endswith("__execute") for n in promessa), (
        "un turno che gira senza nessuno davanti non tocca la casa")
    assert any(n.endswith("__execute") for n in chat), "la chat non cambia"
    assert any(n.endswith("__view") for n in promessa), "i lettori restano"


def test_la_verifica_dell_init_non_pretende_gli_strumenti_della_chat():
    """Il punto esatto in cui il turno moriva: 9 attesi contro 5 risolti."""
    from hiris.app.agent.runner import StreamOccurrence, mcp_names, verify_init

    esito = StreamOccurrence()
    esito.init = {
        "mcp_servers": [{"name": "hiris", "status": "connected"}],
        "tools": list(mcp_names(by_promise=True)),
    }

    ok, motivo = verify_init(esito, by_promise=True)
    assert ok is True, motivo

    ok_chat, _motivo_chat = verify_init(esito, by_promise=False)
    n_promessa = len(esito.init["tools"])
    assert ok_chat is False, (
        f"col catalogo della chat quegli stessi {n_promessa} strumenti del turno "
        "di promessa risultano incompleti: e' il difetto che la verifica live ha "
        "colto")


def test_l_argv_permette_concludi_su_un_turno_di_promessa():
    from hiris.app.agent.runner import _chat_claude_args

    argv = _chat_claude_args("sys", "user", "sonnet", active_tools=True,
                             mcp_config="{}", by_promise=True)
    permessi = argv[argv.index("--allowedTools") + 1]
    assert "__conclude" in permessi
    assert "__execute" not in permessi


def test_un_kind_scope_NON_finisce_fra_i_kind_sconosciuti(caplog):
    """La terza specie: il turno dell'osservatore (fetta «l'osservatore chiede
    a chi risponde davvero», 11/09/2026).

    Il ramo dei kind sconosciuti torna una decisione VUOTA. Un turno di scope
    che ci finisse lascerebbe la casa **senza nessuna entita' osservata**, e --
    poiche' il cancello di `watcher.watch_reading` e' lo scope -- HIRIS
    smetterebbe di registrare qualunque cosa, in silenzio. E' esattamente il
    guasto misurato in produzione l'11/09/2026 fra le 10:50 e le 11:30, per
    un'altra ragione.

    Mutazione che la uccide: togliere `"scope"` dalle specie che il ponte
    ragiona.
    """
    from hiris.app.agent import runner as ponte

    esito = ponte.reason(
        {"kind": "scope", "job_id": "j3",
         "context": {"history": [{"role": "user", "content": "la casa"}],
                     "system_prompt": "sei l'osservatore"}},
        "mock")

    assert "job non-chat in coda" not in caplog.text
    assert esito != {}, "una decisione vuota e' cio' che il ramo sconosciuto da'"


# ── Il turno dell'osservatore porta il PROPRIO contratto di risposta ─────────
#
# Trovato leggendo il codice prima di rilasciare, l'11/09/2026: l'istruzione
# che il ponte aggiunge in coda a ogni turno di chat dice *«Nella risposta
# finale usa testo semplice: niente blocchi di codice o JSON»*, e l'osservatore
# chiede **esattamente un array JSON**. Un turno di scope instradato senza
# questa distinzione sarebbe tornato in prosa, `observer.read_decisions`
# l'avrebbe dichiarato illeggibile, e l'osservatore avrebbe continuato a
# fallire -- per un'altra causa, con lo stesso identico esito misurato in
# produzione stamattina. Un guasto sostituito con un altro.


def test_un_turno_che_porta_la_sua_istruzione_NON_riceve_quella_della_chat():
    """Mutazione che la uccide: ignorare `istruzione` e mettere sempre
    `_CHAT_INSTRUCTION`."""
    from hiris.app.agent import prompts

    _system, user = prompts.build_chat_messages(
        "Sei l'osservatore.", [{"role": "user", "content": "la casa"}],
        istruzione="Rispondi con un SOLO array JSON.")

    assert "Rispondi con un SOLO array JSON." in user
    assert "niente blocchi di codice o JSON" not in user, (
        "e' l'istruzione della chat, ed e' il contrario di cio' che "
        "l'osservatore deve fare")


def test_un_turno_con_materiale_proprio_non_si_sente_dire_che_gli_manca_la_casa():
    """`_CONTESTO_ASSENTE` dice al modello «non hai nemmeno la fotografia della
    casa... dillo apertamente se per rispondere servirebbe conoscerla». Per
    l'osservatore e' **falso** -- la casa e' dentro la domanda, 381 righe -- e
    per giunta lo invita a rifiutare invece di rispondere.

    Mutazione che la uccide: emettere la coppia guida/contesto anche quando il
    turno porta la sua istruzione.
    """
    from hiris.app.agent import prompts

    system, _user = prompts.build_chat_messages(
        "Sei l'osservatore.", [{"role": "user", "content": "la casa"}],
        istruzione="Rispondi con un SOLO array JSON.")

    assert "non hai nemmeno la fotografia della casa" not in system


def test_la_chat_resta_com_era_quando_nessuno_porta_un_istruzione():
    """Il ramo nuovo e' un'AGGIUNTA: senza `istruzione` il turno di chat e
    quello di promessa compongono esattamente cio' che componevano prima."""
    from hiris.app.agent import prompts

    system, user = prompts.build_chat_messages(
        "Sei HIRIS.", [{"role": "user", "content": "ciao"}])

    assert "niente blocchi di codice o JSON" in user
    assert "non hai nemmeno la fotografia della casa" in system


def test_il_ponte_passa_al_prompt_l_istruzione_che_il_job_porta(monkeypatch):
    """L'anello di mezzo: senza questa riga l'istruzione dell'osservatore
    resterebbe dentro il job e non arriverebbe mai al modello -- il difetto
    sarebbe identico, solo spostato di un file.

    Mutazione che la uccide: non leggere `istruzione` dal contesto.
    """
    from hiris.app.agent import runner as ponte

    # Nessuna CLI lanciata: vedi `_ProcessoFinto`. Prima di questa riga la
    # prova invocava `claude` per davvero -- rossa nella corsa intera su una
    # macchina senza `%SystemRoot%`, e su una macchina autenticata avrebbe
    # speso un turno vero dell'abbonamento da dentro pytest.
    _cli_finta(monkeypatch)
    visto = {}
    vero = ponte.prompts.build_chat_messages

    def spia(system_prompt, history, **kw):
        visto.update(kw)
        return vero(system_prompt, history, **kw)

    monkeypatch.setattr(ponte.prompts, "build_chat_messages", spia)
    try:
        ponte.reason(
            {"kind": "scope", "job_id": "j9",
             "context": {"history": [{"role": "user", "content": "la casa"}],
                         "system_prompt": "sei l'osservatore",
                         "istruzione": "Rispondi con un SOLO array JSON."}},
            "live")
    except Exception as errore:
        # Il turno vero non gira in questa prova (non c'e' nessuna CLI da
        # invocare): quel che si verifica e' cosa e' stato CHIESTO al
        # compositore del prompt, e la composizione avviene PRIMA
        # dell'invocazione. L'errore si nomina invece di essere inghiottito:
        # un `pass` muto renderebbe questa prova cieca al giorno in cui il
        # compositore non venisse chiamato affatto.
        assert "istruzione" not in str(errore), errore

    assert visto.get("istruzione") == "Rispondi con un SOLO array JSON."


def test_un_turno_di_scope_NON_riceve_gli_strumenti_della_chat(monkeypatch):
    """**Il rilievo piu' grave della review indipendente (11/09/2026).** Un job
    di scope non porta `promessa_id`, quindi la sonda degli strumenti girava
    col catalogo della CHAT -- `execute` compreso, cioe' la porta con cui HIRIS
    accende, spegne e chiama un servizio di Home Assistant. L'osservatore, che
    deve solo giudicare 381 righe di anagrafe, sarebbe potuto **agire sulla
    casa** senza che nessun si' lo avesse autorizzato; e il prompt gli avrebbe
    pure ordinato di usarli (`BASE_TOOL_RULES`: «Usa SEMPRE gli strumenti per
    dati sulla casa»).

    Sulla catena lo stesso turno non ha strumenti affatto
    (`observer.reconsider` chiama `runner.chat` senza `tools`): le due porte
    devono dare la stessa cosa, o «la stessa domanda per un'altra porta» e'
    falso.

    Mutazione che la uccide: sondare gli strumenti anche per un turno di scope.
    """
    from hiris.app.agent import runner as ponte

    # **La sonda gira solo se il chiamante passa client e base_url**: senza,
    # `awaited` e' falso e il ramo non si tocca affatto. La prima stesura di
    # questa prova li ometteva ed e' nata VERDE senza provare niente -- il
    # difetto n.1 di questo progetto, di nuovo. Qui si passano entrambi, e la
    # spia non chiama il vero (nessuna rete).
    _cli_finta(monkeypatch)
    sondato = []

    def spia(*a, **kw):
        sondato.append(kw)
        return False, ""

    monkeypatch.setattr(ponte, "probe_tools", spia)
    try:
        ponte.reason(
            {"kind": "scope", "job_id": "js",
             "context": {"history": [{"role": "user", "content": "la casa"}],
                         "system_prompt": "sei l'osservatore",
                         "istruzione": "Rispondi con un SOLO array JSON."}},
            "live", client=object(), base_url="http://127.0.0.1:8099")
    except Exception as errore:
        # Il turno non arriva in fondo (la CLI e' finta): cio' che si verifica
        # e' se la sonda sia stata interrogata PRIMA.
        assert "probe" not in str(errore), errore

    assert sondato == [], "un turno di scope non ha strumenti da sondare"


def test_la_specie_che_l_osservatore_accoda_e_una_di_quelle_che_il_ponte_SERVE():
    """**Le due affermazioni non sono un doppione -- sono due fatti diversi**
    (`mind/observer.SCOPE_TURN_KIND` dice come si chiama il turno che nasce,
    `agent/runner.RAGIONABILI` dice quali specie questo modulo sa servire) --
    ma la loro divergenza e' uno stato significativo, e non aveva nessuna
    sentinella: rinominare la costante lasciava verdi tutte le prove e mandava
    ogni turno dell'osservatore nel ramo «decisione vuota», cioe' la casa senza
    scope e HIRIS che smette di registrare. In silenzio.

    Rilievo della review indipendente, 11/09/2026.

    Mutazione che la uccide: cambiare il valore di `SCOPE_TURN_KIND`.
    """
    from hiris.app.agent.runner import RAGIONABILI
    from hiris.app.mind.observer import SCOPE_TURN_KIND

    assert SCOPE_TURN_KIND in RAGIONABILI
