"""fetta «il ponte riceve il nucleo» (parita' A, Task 2): il percorso di chat
in ABBONAMENTO riceve il nucleo, e il prompt di sistema dice esattamente cio'
che quel percorso ha e cio' che non ha.

Prima di questo task i due percorsi di chat erano disuguali: il sincrono
riceveva il nucleo (`handlers_chat.compose_chat_context`, estratta dal Task
1) e i quattro strumenti di `casa/strumenti.py`; il ponte riceveva SOLO
`history` + `system_prompt` e rispondeva senza sapere niente della casa. Qui
si pinna la meta' che questa fetta chiude -- il contesto -- e NON gli
strumenti, che restano fuori (fetta B,
docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md).

Cosa difende ciascun gruppo di test:
- l'ORDINE dei blocchi del system prompt, che deve essere quello del ramo
  sincrono (`claude_runner.py::ClaudeRunner.chat`, dove si compone
  `system_blocks`): BASE -> persona -> guida -> contesto.
  Non e' estetica: la guida esiste per SMENTIRE BASE e la persona (entrambi
  scritti per il percorso sincrono, entrambi nominano strumenti che qui non
  ci sono), e una guida che li precedesse non smentirebbe nulla;
- i DUE rami della guida, cioe' l'interruttore `strumenti_attivi` che la
  fetta B dovra' solo girare;
- il silenzio ①: un job accodato PRIMA di questo deploy arriva senza la
  chiave `contesto`. Deve produrre un log esplicito e un prompt che dichiara
  al modello di non avere nemmeno la fotografia -- mai un pass muto;
- Task 3 ("e i modificatori smettono di essere quattro copie"): le due
  impostazioni della chat `restrict_to_home`/`response_mode`, che ORA
  attraversano anche il ponte -- con le STESSE costanti `RESTRICT_PROMPT`/
  `COMPACT_PROMPT`/`MINIMAL_PROMPT` importate da `claude_runner.py`, mai una
  quarta copia. Il pin decisivo e' l'IDENTITA' con la costante (non una
  sottostringa scritta a mano nel test, che passerebbe anche con un testo
  divergente), l'ordine (fra la persona e la guida, come nel ramo sincrono) e
  che il job accodato porti davvero le due chiavi.
"""
import logging
import os
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.agent import prompts, runner
from hiris.app.api.handlers_chat import handle_chat
from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS
from hiris.app.chat_settings import ChatSettings
from hiris.app.claude_runner import (
    BASE_IDENTITY,
    BASE_SYSTEM_PROMPT,
    BASE_TOOL_RULES,
    COMPACT_PROMPT,
    MINIMAL_PROMPT,
    RESTRICT_PROMPT,
)
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture(autouse=True)
def il_piano_puo_rispondere(monkeypatch):
    """Il token del piano: senza, dal Task 14 il turno NON viene accodato.

    «Ponte acceso senza token» ha smesso di essere uno stato in cui il
    messaggio muore in coda: e' un RIPIEGO, e il turno scende alla catena nella
    stessa richiesta. Un'app di prova col ponte acceso e senza token non
    descrive piu' il ponte, quindi ogni test di questo file che parla del job
    accodato sarebbe diventato un test su un'altra cosa."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")



_CONTESTO = "## La casa\nSalotto: luce accesa.\n\n## Sessioni precedenti\n[2026-08-01] ieri"


# ---------------------------------------------------------------------------
# ① il contesto entra nel prompt, in coda e dopo la guida
# ---------------------------------------------------------------------------

def test_il_contesto_entra_nel_system_prompt_del_ponte():
    system, user = prompts.build_chat_messages(
        "Sei HIRIS.", [{"role": "user", "content": "ciao"}], contesto=_CONTESTO)

    assert _CONTESTO in system, (
        "il ponte non riceve il nucleo: e' la disparita' che questa fetta chiude")
    # e non finisce nel prompt UTENTE, che resta trascrizione + istruzione
    assert _CONTESTO not in user


def test_il_contesto_sta_in_coda_e_dopo_la_guida():
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=_CONTESTO)

    assert system.index(prompts._GUIDE_WITHOUT_TOOLS) < system.index(_CONTESTO)
    assert system.rstrip().endswith(_CONTESTO), (
        "il contesto e' il blocco volatile: nel ramo sincrono sta in fondo, "
        "dopo tutti i blocchi stabili (claude_runner.py::ClaudeRunner.chat, "
        "dove `context_str` e' l'ultimo append a `system_blocks`). Se qui non "
        "e' in coda, i due percorsi compongono cose diverse.")


# ---------------------------------------------------------------------------
# ② l'ordine dei blocchi: BASE -> persona -> guida -> contesto
# ---------------------------------------------------------------------------

def test_ordine_dei_blocchi_uguale_al_ramo_sincrono():
    """Asserito su `system.index(...)` e non su una sottostringa unica: cio'
    che si difende e' l'ORDINE, e un test che si limitasse a cercare i quattro
    pezzi passerebbe anche con la guida davanti a BASE -- cioe' proprio nel
    caso in cui la smentita non smentisce piu' nulla."""
    persona = "Sei HIRIS, la persona della chat."
    system, _user = prompts.build_chat_messages(persona, [], contesto=_CONTESTO)

    i_base = system.index(BASE_IDENTITY.strip())
    i_persona = system.index(persona)
    i_guida = system.index(prompts._GUIDE_WITHOUT_TOOLS)
    i_contesto = system.index(_CONTESTO)

    assert i_base < i_persona < i_guida < i_contesto


def test_base_system_prompt_e_importato_non_ricopiato():
    """BASE ha UNA fonte (`claude_runner.py`). Una seconda copia in
    `prompts.py` sarebbe la "funzione doppia" vietata da CLAUDE.md e
    divergerebbe in silenzio: i due percorsi di chat direbbero al modello due
    cose diverse su chi e'. Vale anche dopo il taglio in due meta' (fix round
    1): si importano, non si riscrivono."""
    assert prompts.BASE_IDENTITY is BASE_IDENTITY
    assert prompts.BASE_TOOL_RULES is BASE_TOOL_RULES
    # fix della review totale della fetta (m-3): l'assert su
    # `prompts.BASE_SYSTEM_PROMPT` e' uscito, e con lui l'import in
    # `prompts.py`. Non pinnava niente di vivo: il codice di `prompts.py` non
    # usa quella costante -- il ternario di `build_chat_messages` compone le
    # due META' -- e un simbolo importato solo perche' un test lo guarda non
    # e' una fonte condivisa, e' un orfano col suo guardiano. I due assert
    # qui sopra sono quelli che contano: sono i simboli che il ponte compone.
    with open(prompts.__file__, encoding="utf-8") as f:
        sorgente = f.read()
    # Task 3 ("i modificatori smettono di essere quattro copie"): l'import
    # e' diventato multilinea per aggiungere RESTRICT_PROMPT/COMPACT_PROMPT/
    # MINIMAL_PROMPT -- si cerca il blocco intero (fino alla parentesi
    # chiusa), non piu' una riga singola letterale, cosi' l'assert resta
    # valido qualunque sia l'a-capo scelto.
    inizio = sorgente.index("from ..claude_runner import")
    blocco_import = sorgente[inizio:sorgente.index(")", inizio) + 1]
    assert "BASE_IDENTITY" in blocco_import
    assert "Sei HIRIS, assistente AI integrata in Home Assistant" not in sorgente, (
        "il testo di BASE e' stato RICOPIATO in prompts.py invece che importato")


# ---------------------------------------------------------------------------
# ②bis fix round 1, Critical 1: di BASE il ponte emette la sola META' VERA.
#
# Prima di questo giro il ponte componeva `BASE_SYSTEM_PROMPT` intero, e la
# guida che segue doveva smentirne quattro affermazioni. Ma «Usa SEMPRE gli
# strumenti per dati sulla casa» e «chiama remember subito, senza chiedere il
# permesso» non sono affermazioni: sono ORDINI di chiamare uno strumento che
# qui non esiste. Il caso peggiore -- l'utente dice "ricordati che la caldaia
# perde", il modello obbedisce a BASE, lo strumento non c'e', e risponde
# "preso nota" -- e' il bug misurato in produzione da cui `remember` e' nato
# (vedi il commento sopra BASE_IDENTITY in claude_runner.py). Un ordine non
# emesso e' un meccanismo; una frase che lo contraddice e' una speranza.
# ---------------------------------------------------------------------------

def test_senza_strumenti_il_ponte_non_emette_le_regole_sugli_strumenti():
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=_CONTESTO)

    assert BASE_IDENTITY.strip() in system, "la meta' VERA di BASE deve esserci"
    assert BASE_TOOL_RULES not in system
    # i quattro pezzi che sul ponte sarebbero falsi o ineseguibili, uno per uno
    assert "Usa SEMPRE gli strumenti" not in system
    assert "chiama remember subito" not in system
    assert "Hai a disposizione strumenti" not in system
    assert "non aggiungere disclaimers" not in system


def test_con_strumenti_il_ponte_riemette_base_intero_e_contiguo():
    """Il complemento, e la ragione per cui non nasce una terza variante di
    BASE da mantenere: con `strumenti_attivi=True` le due meta' tornano
    adiacenti e il blocco e' byte per byte `BASE_SYSTEM_PROMPT`, cioe' quello
    che il ramo sincrono compone gia' oggi."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, active_tools=True)

    assert BASE_SYSTEM_PROMPT.strip() in system
    assert "Usa SEMPRE gli strumenti" in system
    assert "chiama remember subito" in system


# ---------------------------------------------------------------------------
# ②ter fix round 1, Important 1: la fotografia porta anche la MEMORIA, e il
# prompt deve dirlo. `compose_briefing` passa TUTTI i ricordi
# (`fetch(limit=count())`) e `compose_chat_context` aggiunge
# "## Sessioni precedenti": negare al modello di poter "richiamare ricordi"
# mentre il ricordo e' scritto tre blocchi piu' sotto e' la stessa falsita'
# speculare gia' corretta per lo stato della casa.
# ---------------------------------------------------------------------------

def test_la_memoria_nella_fotografia_non_viene_negata():
    ricordo = ("## Cio' che le persone hanno detto" + chr(10)
               + "- la caldaia perde (detto da paolo)")
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=ricordo)

    # quel che si nega e' lo STRUMENTO...
    assert "non puoi salvare nuovi ricordi" in system
    assert "andare a cercarne altri adesso" in system
    # ...non il CONTENUTO, che e' li' dentro
    assert "richiamare ricordi" not in system
    assert "ricordi e sessioni precedenti compresi" in system
    assert ricordo in system


# ---------------------------------------------------------------------------
# ③ l'interruttore: due rami del testo, uno solo raggiungibile dalla fetta A
# ---------------------------------------------------------------------------

def test_il_ramo_senza_strumenti_li_nega():
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=_CONTESTO)

    assert prompts._GUIDE_WITHOUT_TOOLS in system
    assert prompts._GUIDE_WITH_TOOLS not in system
    assert "NON hai alcuno strumento" in system


def test_il_ramo_con_strumenti_afferma_gli_strumenti_del_catalogo():
    """L'UNICO lettore di `_GUIDE_WITH_TOOLS` nella fetta A: e' un orfano
    DICHIARATO, scritto ora perche' la fetta B possa cambiare un argomento
    invece di riscrivere il prompt una terza volta (e' il difetto che il
    docstring di prompts.py documenta di aver gia' commesso due volte).

    Che non possa diventare vero per sbaglio non lo garantisce questo test ma
    `test_argv_del_ponte_non_collega_nessuno_strumento`
    (tests/test_agent_runner_inaddon.py), che resta verde per tutta la fetta A:
    finche' l'argv non porta `--mcp-config` ne' `--allowedTools`, nessuna
    produzione puo' arrivare qui."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, active_tools=True)

    assert prompts._GUIDE_WITH_TOOLS in system
    assert prompts._GUIDE_WITHOUT_TOOLS not in system
    # li afferma tutti, non li nega -- e l'elenco si DERIVA dal catalogo
    # unico (fetta «comandare», Task 7): scritto a mano restava a quattro
    # mentre il catalogo ne aveva cinque, ed e' esattamente la dichiarazione
    # che invecchia in silenzio di cui questo file e' pieno di lapidi.
    for voce in KNOWLEDGE_TOOLS:
        assert f"`{voce['name']}`" in prompts._GUIDE_WITH_TOOLS
    assert "HAI gli strumenti di HIRIS" in system
    assert "NON hai alcuno strumento" not in system
    # riserva 1 del piano della fetta B: attraverso MCP il modello vede i nomi
    # PREFISSATI dal server. Il prefisso esatto e' una decisione della B --
    # qui si pinna solo che il testo prepara il modello a vederli prefissati,
    # invece di nominare dei nomi nudi che non comparirebbero mai.
    assert "mcp__hiris__" in prompts._GUIDE_WITH_TOOLS


def test_il_runner_gira_l_interruttore_da_un_solo_booleano():
    """── IL QUARTO CAMPANELLO, RIBALTATO (fetta "il ponte riceve gli
    strumenti", parita' B, Task 3).

    **Cosa pinnava.** Che nessun chiamante di produzione girasse l'interruttore
    degli strumenti: `"strumenti_attivi" not in inspect.getsource(_reason_chat)`.
    Nella parita' A era vero e doveva restarlo -- il ramo `_GUIDE_WITH_TOOLS`
    era scritto e non raggiungibile.

    **Cosa e' successo.** Il Task 3 lo ha girato, ed e' diventato rosso proprio
    come previsto («il runner del ponte gira l'interruttore degli strumenti:
    e' la fetta B, non questa» -- era la fetta B). Cancellarlo avrebbe
    lasciato senza guardiano la cosa piu' importante di questa fetta.

    **Cosa pinna adesso.** La stessa cosa vista dall'altro verso: che
    l'interruttore ci sia, che sia UNO SOLO, e che il prompt e l'argv lo
    leggano dalla STESSA variabile. Un secondo booleano -- o due chiamate a
    `probe_tools` -- sarebbero due decisioni da tenere allineate, cioe'
    esattamente cio' che questa fetta esiste per rendere impossibile. ──"""
    import inspect

    firma = inspect.signature(prompts.build_chat_messages)
    # il default resta False perche' False e' il ramo di DEGRADO: cio' che si
    # ottiene quando non si sa. Un default True prometterebbe strumenti a chi
    # non li ha chiesti.
    assert firma.parameters["active_tools"].default is False
    assert firma.parameters["contesto"].default == ""
    # i due primi parametri restano POSIZIONALI (i pin esistenti li passano
    # cosi': tests/test_agent_runner_inaddon.py::test_build_chat_messages_available)
    posizionali = [n for n, p in firma.parameters.items()
                   if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
    assert posizionali == ["system_prompt", "history"]

    sorgente = inspect.getsource(runner._reason_chat)
    assert "active_tools" in sorgente, (
        "il runner del ponte non gira piu' l'interruttore degli strumenti: il "
        "ponte e' tornato cieco senza che nessuno lo abbia deciso")
    # UNA sola sonda per turno: due chiamate sarebbero due decisioni, e due
    # decisioni possono divergere (il prompt composto su una, l'argv sull'altra).
    assert sorgente.count("probe_tools(") == 1, (
        "la sonda degli strumenti viene chiamata piu' di una volta in "
        "_reason_chat: e' il modo in cui il prompt e l'argv tornano a essere "
        "due decisioni invece di una")
    # e le due letture del booleano sono la STESSA variabile, non due.
    #
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 4): il soggetto e'
    # vivissimo, cambia la via d'accesso -- quindi il pin **si adegua, non si
    # butta**. Il Task 4 ha spostato la composizione dentro `_invoca`, perche'
    # da quel task il turno puo' comporre DUE volte (l'evento `init` smentisce
    # la sonda: si butta l'invocazione e si ricompone dal booleano a `False`).
    # Le due letture ora nominano il PARAMETRO di `_invoca`, ed e' una garanzia
    # piu' forte di prima: non c'e' piu' un punto del corpo in cui il prompt
    # possa restare avanti all'argv, perche' nascono nella stessa chiamata.
    assert "def _invoca(active_tools: bool)" in sorgente, (
        "la composizione non passa piu' da un solo punto parametrico: se il "
        "prompt e l'argv tornano a comporsi in due posti, il secondo giro del "
        "Task 4 puo' ricomporne uno solo dei due")
    assert sorgente.count("active_tools=active_tools") == 2, (
        "il prompt e l'argv non leggono piu' la stessa variabile: e' il punto "
        "in cui rientra un prompt che promette cio' che l'argv non da'")
    # ...e il chiamante passa UN booleano, quello deciso dalla sonda (primo
    # giro) o messo a False dalla difesa (2) (secondo giro).
    assert sorgente.count("_invoca(tools)") == 2, (
        "le invocazioni di `_invoca` non leggono piu' l'unico booleano del "
        "turno: sono due decisioni da tenere allineate, cioe' esattamente "
        "cio' che questa fetta esiste per rendere impossibile")


def test_il_prompt_che_esce_davvero_dal_ponte_senza_sonda_e_quello_senza_strumenti():
    """La META' DI COMPORTAMENTO del test qui sopra (m-B della review del
    Task 2: quello era per meta' un test di FORMA -- firma, default, nomi dei
    parametri, sorgente letta con `inspect`).

    La forma non basta: la firma potrebbe restare identica e l'interruttore
    essere girato da un chiamante NUOVO, o il default cambiare a valle. Qui
    si guarda il prodotto finito -- il system prompt che finisce davvero
    sulla riga di comando di `claude`, catturato dal percorso reale
    (`_reason_chat` in modalita' live con `subprocess.run` finto) -- e si
    verifica quale delle due guide contiene.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 3): il soggetto e'
    vivo e il test NON si cancella, ma cambia cosa dimostra. `_cattura_system`
    chiama `_reason_chat` SENZA `client` ne' `base_url`: non c'e' niente da
    sondare e nessun `/api/mcp` a cui puntare la mcp-config, quindi gli
    strumenti non sono nemmeno attesi. E' il ramo di DEGRADO, e li' il prompt
    deve continuare a negarli per sempre -- un prompt che li affermasse senza
    che l'argv li porti e' il difetto numero uno di questo prodotto. Il gemello
    (il turno CON la sonda che risponde) e'
    tests/test_strumenti_al_ponte.py."""
    job = {"kind": "chat", "job_id": "job-senza-strumenti",
           "context": {"history": [{"role": "user", "content": "ciao"}],
                       "system_prompt": "Sei HIRIS.", "contesto": _CONTESTO}}

    system = _cattura_system(job)

    assert prompts._GUIDE_WITHOUT_TOOLS in system, (
        "il ponte non emette piu' la guida che nega gli strumenti")
    assert prompts._GUIDE_WITH_TOOLS not in system, (
        "il ponte afferma gli strumenti in un turno in cui non ha nemmeno "
        "potuto sondarli (nessun client, nessuna base_url): il prompt promette "
        "cio' che l'argv non puo' dare -- e l'argv non lo da', perche' senza "
        "base_url non c'e' nessun /api/mcp da mettere nella mcp-config")


# ---------------------------------------------------------------------------
# ④ il silenzio ①: il job legacy, senza la chiave `contesto`
# ---------------------------------------------------------------------------

class _Proc:
    # fetta "il ponte riceve gli strumenti" (parita' B, Task 2, fix round 1):
    # lo stdout finto era rimasto nella forma di `--output-format json`
    # (`{"result": "risposta"}`), che col nuovo parsing NON contiene nessun
    # evento `type=result`: OGNI test di questo file che finti-esegue la CLI
    # cadeva nel silenzio (3) e produceva due avvisi estranei. Due pin ne
    # erano stati svuotati senza diventare rossi -- il modo peggiore di
    # rompere una rete. Forma NDJSON di `stream-json --verbose`: init, un
    # evento assistant, l'evento finale result.
    returncode = 0
    stdout = (
        '{"type":"system","subtype":"init","tools":[],"mcp_servers":[]}\n'
        '{"type":"assistant","message":{"role":"assistant",'
        '"content":[{"type":"text","text":"risposta"}]}}\n'
        '{"type":"result","subtype":"success","is_error":false,"num_turns":1,'
        '"result":"risposta","usage":{"input_tokens":5,'
        '"cache_creation_input_tokens":0,"cache_read_input_tokens":0,'
        '"output_tokens":3}}\n')
    stderr = ""


def _cattura_system(job, caplog=None):
    """Esegue `_reason_chat` in modalita' live con `subprocess.run` finto e
    restituisce il system prompt che sarebbe finito alla CLI."""
    catturato = {}

    def _fake_run(argv, *a, **k):
        catturato["argv"] = argv
        catturato["system"] = argv[argv.index("--system-prompt") + 1]
        return _Proc()

    with patch.object(runner.subprocess, "run", _fake_run):
        runner._reason_chat(job, "live")
    return catturato["system"]


def test_il_job_legacy_senza_contesto_dichiara_il_silenzio_nel_log(caplog):
    """Silenzio ① della fetta: un job accodato PRIMA di questo deploy non ha
    la chiave `contesto` e non c'e' modo di ricomporla nel runner. Deve
    LOGGARE, nominando il job_id -- mai un `.get("contesto") or ""` muto, che
    e' indistinguibile da un'assenza di problemi."""
    job = {"kind": "chat", "job_id": "job-legacy-1",
           "context": {"history": [{"role": "user", "content": "ciao"}],
                       "system_prompt": "Sei HIRIS."}}

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        _cattura_system(job)

    # fix round 1: qui c'era `assert caplog.records`, ed era diventato VACUO
    # -- lo stdout finto nel vecchio formato faceva scattare due avvisi
    # estranei (silenzio (3) + init mancante) che bastavano a riempire
    # `caplog`, quindi il pin passava anche se il log del silenzio (1) fosse
    # sparito del tutto. Si asserisce il CONTEGGIO: un avviso, il suo, e
    # nessun altro -- cosi' non e' riempibile dal rumore di un'altra fetta.
    assert len(caplog.records) == 1, (
        "il job legacy deve produrre ESATTAMENTE un avviso, il suo -- zero "
        "significa che e' passato in silenzio, piu' di uno che questo pin "
        "e' riempibile da rumore altrui: "
        f"{[r.getMessage() for r in caplog.records]!r}")
    testo = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "contesto" in testo and "job-legacy-1" in testo
    assert "PRIMA di questo deploy" in testo
    assert "SENZA la casa" in testo


def test_il_job_legacy_senza_contesto_lo_dichiara_anche_al_modello():
    """Il degrado non si ferma al log: il prompt dice al modello che in questo
    turno non ha nemmeno la fotografia -- altrimenti risponderebbe come se la
    casa non esistesse, che al lettore sembra una risposta normale."""
    job = {"kind": "chat", "job_id": "job-legacy-2",
           "context": {"history": [], "system_prompt": "Sei HIRIS."}}

    system = _cattura_system(job)

    assert prompts._CONTESTO_ASSENTE in system
    assert prompts._CONTESTO_PRESENTE not in system
    assert "non hai nemmeno la fotografia della casa" in system


def test_il_job_con_contesto_non_logga_e_porta_la_casa(caplog):
    """Il complemento: un job accodato DOPO questo deploy non deve produrre
    nessun avviso -- un log che scatta sempre e' rumore, e il silenzio
    dichiarato smette di distinguersi."""
    job = {"kind": "chat", "job_id": "job-nuovo",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": _CONTESTO}}

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        system = _cattura_system(job)

    # fix round 1: l'assert era ristretto ai messaggi contenenti "contesto",
    # e con lo stdout nel vecchio formato questo job produceva due avvisi a
    # ogni esecuzione senza che nulla diventasse rosso: la guardia contro il
    # rumore c'era ancora, ma non vedeva piu' il rumore. Il turno felice del
    # ponte non deve loggare NIENTE a livello WARNING -- ne' sul contesto ne'
    # su altro -- o il silenzio dichiarato smette di distinguersi.
    assert not caplog.records, (
        "il turno felice del ponte ha prodotto degli avvisi: un log che "
        "scatta sempre e' rumore, e il silenzio dichiarato smette di "
        "distinguersi -- "
        f"{[r.getMessage() for r in caplog.records]!r}")
    assert _CONTESTO in system
    assert prompts._CONTESTO_PRESENTE in system
    assert prompts._CONTESTO_ASSENTE not in system


def test_contesto_presente_ma_vuoto_non_e_un_job_legacy(caplog):
    """La chiave c'e' ma il nucleo non si e' composto (stringa vuota): NON e'
    il caso legacy e non deve loggare come tale -- quel degrado lo dichiara
    gia' il testo del nucleo (`compose_chat_context`). Il prompt pero' dice
    comunque al modello che la fotografia non c'e'."""
    job = {"kind": "chat", "job_id": "job-vuoto",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": ""}}

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        system = _cattura_system(job)

    assert not [r for r in caplog.records if "PRIMA di questo deploy" in r.getMessage()]
    # fix round 1, stessa ragione del test qui sopra: nemmeno questo caso
    # deve produrre avvisi estranei che rendano il pin riempibile da rumore.
    assert not caplog.records, (
        "avvisi inattesi sul job col contesto vuoto: "
        f"{[r.getMessage() for r in caplog.records]!r}")
    assert prompts._CONTESTO_ASSENTE in system


def test_senza_sonda_il_ponte_resta_senza_strumenti_anche_col_contesto():
    """La riga che separava questa fetta dalla B, vista dal runner: il contesto
    arriva, gli strumenti no.

    fetta "il ponte riceve gli strumenti" (parita' B, Task 3): non e' piu' la
    riga fra due fette, e' la riga fra i due RAMI. Qui `_reason_chat` non
    riceve ne' `client` ne' `base_url`, quindi non c'e' sonda e non ci sono
    strumenti attesi: l'argv deve restare quello di prima, byte per byte, o
    smentirebbe il prompt che in questo stesso turno li nega."""
    job = {"kind": "chat", "job_id": "job-nuovo",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": _CONTESTO}}

    catturato = {}

    def _fake_run(argv, *a, **k):
        catturato["argv"] = argv
        return _Proc()

    with patch.object(runner.subprocess, "run", _fake_run):
        runner._reason_chat(job, "live")

    opzioni = {a.lower().replace("-", "") for a in catturato["argv"]}
    assert "mcpconfig" not in opzioni
    assert "allowedtools" not in opzioni


# ---------------------------------------------------------------------------
# ⑤ Task 3: `restrict_to_home` e `response_mode` attraversano il ponte --
# con le STESSE costanti del ramo sincrono, mai una quarta copia.
# ---------------------------------------------------------------------------

def test_restrict_to_home_aggiunge_restrict_prompt_importato():
    """L'identita' con la costante (non una sottostringa scritta a mano):
    e' cio' che impedisce a una futura modifica di ricopiare il testo invece
    di importarlo, restando comunque verde."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, restrict_to_home=True)

    assert RESTRICT_PROMPT in system


def test_restrict_to_home_false_non_aggiunge_nulla():
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, restrict_to_home=False)

    assert RESTRICT_PROMPT not in system


def test_response_mode_compact_aggiunge_compact_prompt_importato():
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, response_mode="compact")

    assert COMPACT_PROMPT in system
    assert MINIMAL_PROMPT not in system


def test_response_mode_minimal_aggiunge_minimal_prompt_importato():
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, response_mode="minimal")

    assert MINIMAL_PROMPT in system
    assert COMPACT_PROMPT not in system


def test_response_mode_auto_non_aggiunge_nessun_modificatore():
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, response_mode="auto")

    assert COMPACT_PROMPT not in system
    assert MINIMAL_PROMPT not in system


def test_senza_argomenti_nessun_modificatore_di_default():
    """Il comportamento di prima del Task 3, invariato per chi non li passa
    (i test dei gruppi ①-④ qui sopra, e ogni job legacy senza le due
    chiavi)."""
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=_CONTESTO)

    assert RESTRICT_PROMPT not in system
    assert COMPACT_PROMPT not in system
    assert MINIMAL_PROMPT not in system


def test_i_modificatori_stanno_fra_la_persona_e_la_guida():
    """Stesso posto del ramo sincrono (claude_runner.py::ClaudeRunner.chat,
    dove RESTRICT_PROMPT/COMPACT_PROMPT/MINIMAL_PROMPT si appendono a
    `system_blocks`): dopo i blocchi stabili di identita', prima del
    breakpoint di cache e del contesto volatile. Qui, fra `system_prompt` e
    la guida.

    (I rinvii sono ai NOMI, non ai numeri di riga: i tre che stavano qui
    erano gia' invecchiati -- `claude_runner.py:612-633` cadeva, a fetta
    finita, dentro un commento su `pseudonym_map`, oggi uscito a sua volta.
    Un numero di riga invecchia al primo commit che sposta il blocco; un
    nome no.)"""
    persona = "Sei HIRIS, la persona della chat."
    system, _user = prompts.build_chat_messages(
        persona, [], contesto=_CONTESTO, restrict_to_home=True, response_mode="compact")

    i_persona = system.index(persona)
    i_restrict = system.index(RESTRICT_PROMPT)
    i_compact = system.index(COMPACT_PROMPT)
    i_guida = system.index(prompts._GUIDE_WITHOUT_TOOLS)

    assert i_persona < i_restrict < i_compact < i_guida


def test_i_modificatori_sono_importati_non_ricopiati():
    """Come `test_base_system_prompt_e_importato_non_ricopiato` sopra, ma per
    i due modificatori: una seconda copia del loro testo in `prompts.py`
    sarebbe la "funzione doppia" vietata da CLAUDE.md -- e la quarta copia in
    assoluto (le prime tre, gia' unificate al Task 3 Step 1, erano
    `claude_runner.py` e i due punti di `backends/openai_compat_runner.py`)."""
    with open(prompts.__file__, encoding="utf-8") as f:
        sorgente = f.read()
    assert "from ..claude_runner import" in sorgente
    assert "RESTRICT_PROMPT" in sorgente
    assert "COMPACT_PROMPT" in sorgente
    assert "MINIMAL_PROMPT" in sorgente
    assert "Sei HIRIS, assistente per la smart home" not in sorgente, (
        "RESTRICT_PROMPT e' stato RICOPIATO in prompts.py invece che importato")
    assert "Rispondi in modo conciso" not in sorgente, (
        "COMPACT_PROMPT e' stato RICOPIATO in prompts.py invece che importato")
    assert "Rispondi SOLO in formato chiave" not in sorgente, (
        "MINIMAL_PROMPT e' stato RICOPIATO in prompts.py invece che importato")


def test_il_ponte_non_da_strumenti_anche_coi_modificatori_attivi():
    """La riga che separa la fetta A dalla B, vista con entrambi i
    modificatori accesi insieme: restano innocui rispetto agli strumenti."""
    job = {"kind": "chat", "job_id": "job-modificatori",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": _CONTESTO,
                       "restrict_to_home": True, "response_mode": "minimal"}}

    catturato = {}

    def _fake_run(argv, *a, **k):
        catturato["argv"] = argv
        return _Proc()

    with patch.object(runner.subprocess, "run", _fake_run):
        runner._reason_chat(job, "live")

    opzioni = {a.lower().replace("-", "") for a in catturato["argv"]}
    assert "mcpconfig" not in opzioni
    assert "allowedtools" not in opzioni


def test_reason_chat_legge_i_due_valori_dal_context_e_li_applica():
    """`_reason_chat` legge `restrict_to_home`/`response_mode` dal `context`
    del job e li passa a `build_chat_messages` -- non un default sempre
    disattivo che ignorerebbe l'impostazione dell'utente."""
    job = {"kind": "chat", "job_id": "job-attivi",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": _CONTESTO,
                       "restrict_to_home": True, "response_mode": "compact"}}

    system = _cattura_system(job)

    assert RESTRICT_PROMPT in system
    assert COMPACT_PROMPT in system


def test_reason_chat_col_loro_default_su_un_job_senza_le_due_chiavi():
    """Il complemento: un job che non porta affatto le due chiavi (legacy, o
    impostazioni di default) non deve emettere nessun modificatore --
    `False`/`""`, non un errore."""
    job = {"kind": "chat", "job_id": "job-senza-chiavi",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": _CONTESTO}}

    system = _cattura_system(job)

    assert RESTRICT_PROMPT not in system
    assert COMPACT_PROMPT not in system
    assert MINIMAL_PROMPT not in system


# ---------------------------------------------------------------------------
# ⑥ il trasporto: `_enqueue_chat_job` mette le due chiavi nel `context`, con
# gli stessi valori che il ramo sincrono legge da `impostazioni`
# (`handlers_chat.py::handle_chat`, `agent_restrict`/`agent_response_mode`).
# ---------------------------------------------------------------------------

def _make_app_ponte(tmp_path, *, restrict_to_home=False, response_mode="auto"):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    impostazioni = ChatSettings(
        name="test-ponte", system_prompt="Sei HIRIS.",
        restrict_to_home=restrict_to_home, response_mode=response_mode,
    )
    runner_mock = AsyncMock()
    runner_mock.chat = AsyncMock(return_value="sync reply")
    runner_mock.last_tool_calls = []
    runner_mock.last_thinking_blocks = []

    app = web.Application()
    app["llm_router"] = runner_mock
    app["claude_runner"] = runner_mock
    app["impostazioni_chat"] = impostazioni
    app["data_dir"] = data_dir
    app["ponte_attivo"] = True
    q = ReasoningQueue(str(tmp_path / "reasoning.db"))
    app["reasoning_queue"] = q
    app.router.add_post("/api/chat", handle_chat)
    return app, q, data_dir


@pytest.mark.asyncio
async def test_job_accodato_porta_restrict_to_home_e_response_mode(tmp_path):
    app, q, _data_dir = _make_app_ponte(
        tmp_path, restrict_to_home=True, response_mode="compact")

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        body = await resp.json()

    job = q.get(body["job_id"])
    assert job["context"]["restrict_to_home"] is True
    assert job["context"]["response_mode"] == "compact"


@pytest.mark.asyncio
async def test_job_accodato_porta_i_default_quando_le_impostazioni_sono_di_default(tmp_path):
    app, q, _data_dir = _make_app_ponte(tmp_path)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/chat", json={"message": "ciao"})
        assert resp.status == 202
        body = await resp.json()

    job = q.get(body["job_id"])
    assert job["context"]["restrict_to_home"] is False
    assert job["context"]["response_mode"] == "auto"
