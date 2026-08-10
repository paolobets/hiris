"""fetta «il ponte riceve il nucleo» (parita' A, Task 2): il percorso di chat
in ABBONAMENTO riceve il nucleo, e il prompt di sistema dice esattamente cio'
che quel percorso ha e cio' che non ha.

Prima di questo task i due percorsi di chat erano disuguali: il sincrono
riceveva il nucleo (`handlers_chat.componi_contesto_chat`, estratta dal Task
1) e i quattro strumenti di `casa/strumenti.py`; il ponte riceveva SOLO
`history` + `system_prompt` e rispondeva senza sapere niente della casa. Qui
si pinna la meta' che questa fetta chiude -- il contesto -- e NON gli
strumenti, che restano fuori (fetta B,
docs/superpowers/plans/2026-08-10-il-ponte-riceve-gli-strumenti.md).

Cosa difende ciascun gruppo di test:
- l'ORDINE dei blocchi del system prompt, che deve essere quello del ramo
  sincrono (`claude_runner.py:612-633`): BASE -> persona -> guida -> contesto.
  Non e' estetica: la guida esiste per SMENTIRE BASE e la persona (entrambi
  scritti per il percorso sincrono, entrambi nominano strumenti che qui non
  ci sono), e una guida che li precedesse non smentirebbe nulla;
- i DUE rami della guida, cioe' l'interruttore `strumenti_attivi` che la
  fetta B dovra' solo girare;
- il silenzio ①: un job accodato PRIMA di questo deploy arriva senza la
  chiave `contesto`. Deve produrre un log esplicito e un prompt che dichiara
  al modello di non avere nemmeno la fotografia -- mai un pass muto.
"""
import logging

from unittest.mock import patch

from hiris.app.agent import prompts, runner
from hiris.app.claude_runner import BASE_SYSTEM_PROMPT


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

    assert system.index(prompts._GUIDA_SENZA_STRUMENTI) < system.index(_CONTESTO)
    assert system.rstrip().endswith(_CONTESTO), (
        "il contesto e' il blocco volatile: nel ramo sincrono sta in fondo, "
        "dopo tutti i blocchi stabili (claude_runner.py:612-633). Se qui non "
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

    i_base = system.index(BASE_SYSTEM_PROMPT.strip())
    i_persona = system.index(persona)
    i_guida = system.index(prompts._GUIDA_SENZA_STRUMENTI)
    i_contesto = system.index(_CONTESTO)

    assert i_base < i_persona < i_guida < i_contesto


def test_base_system_prompt_e_importato_non_ricopiato():
    """`BASE_SYSTEM_PROMPT` ha UNA fonte (`claude_runner.py:101`). Una seconda
    copia in `prompts.py` sarebbe la "funzione doppia" vietata da CLAUDE.md e
    divergerebbe in silenzio: i due percorsi di chat direbbero al modello due
    cose diverse su chi e'."""
    assert prompts.BASE_SYSTEM_PROMPT is BASE_SYSTEM_PROMPT
    sorgente = open(prompts.__file__, encoding="utf-8").read()
    assert "from ..claude_runner import BASE_SYSTEM_PROMPT" in sorgente
    assert "Sei HIRIS, assistente AI integrata in Home Assistant" not in sorgente, (
        "il testo di BASE_SYSTEM_PROMPT e' stato RICOPIATO in prompts.py "
        "invece che importato")


# ---------------------------------------------------------------------------
# ③ l'interruttore: due rami del testo, uno solo raggiungibile dalla fetta A
# ---------------------------------------------------------------------------

def test_il_ramo_senza_strumenti_li_nega():
    system, _user = prompts.build_chat_messages("Sei HIRIS.", [], contesto=_CONTESTO)

    assert prompts._GUIDA_SENZA_STRUMENTI in system
    assert prompts._GUIDA_CON_STRUMENTI not in system
    assert "NON hai alcuno strumento" in system


def test_il_ramo_con_strumenti_afferma_i_quattro_strumenti():
    """L'UNICO lettore di `_GUIDA_CON_STRUMENTI` nella fetta A: e' un orfano
    DICHIARATO, scritto ora perche' la fetta B possa cambiare un argomento
    invece di riscrivere il prompt una terza volta (e' il difetto che il
    docstring di prompts.py documenta di aver gia' commesso due volte).

    Che non possa diventare vero per sbaglio non lo garantisce questo test ma
    `test_argv_del_ponte_non_collega_nessuno_strumento`
    (tests/test_agent_runner_inaddon.py), che resta verde per tutta la fetta A:
    finche' l'argv non porta `--mcp-config` ne' `--allowedTools`, nessuna
    produzione puo' arrivare qui."""
    system, _user = prompts.build_chat_messages(
        "Sei HIRIS.", [], contesto=_CONTESTO, strumenti_attivi=True)

    assert prompts._GUIDA_CON_STRUMENTI in system
    assert prompts._GUIDA_SENZA_STRUMENTI not in system
    # afferma i quattro, non li nega
    for nome in ("`cerca`", "`guarda`", "`ricorda`", "`richiama`"):
        assert nome in prompts._GUIDA_CON_STRUMENTI
    assert "HAI gli strumenti di HIRIS" in system
    assert "NON hai alcuno strumento" not in system
    # riserva 1 del piano della fetta B: attraverso MCP il modello vede i nomi
    # PREFISSATI dal server. Il prefisso esatto e' una decisione della B --
    # qui si pinna solo che il testo prepara il modello a vederli prefissati,
    # invece di nominare quattro nomi nudi che non comparirebbero mai.
    assert "mcp__hiris__" in prompts._GUIDA_CON_STRUMENTI


def test_nessun_chiamante_di_produzione_gira_l_interruttore():
    """La fetta A non da' strumenti al ponte: il default resta False e il
    runner non lo passa. Se un giorno questo test diventa rosso senza che i
    pin dell'argv siano stati ribaltati, il prompt sta mentendo."""
    import inspect

    firma = inspect.signature(prompts.build_chat_messages)
    assert firma.parameters["strumenti_attivi"].default is False
    assert firma.parameters["contesto"].default == ""
    # i due primi parametri restano POSIZIONALI (i pin esistenti li passano
    # cosi': tests/test_agent_runner_inaddon.py:11)
    posizionali = [n for n, p in firma.parameters.items()
                   if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
    assert posizionali == ["system_prompt", "history"]

    sorgente = inspect.getsource(runner._reason_chat)
    assert "strumenti_attivi" not in sorgente, (
        "il runner del ponte gira l'interruttore degli strumenti: e' la fetta "
        "B, non questa")


# ---------------------------------------------------------------------------
# ④ il silenzio ①: il job legacy, senza la chiave `contesto`
# ---------------------------------------------------------------------------

class _Proc:
    returncode = 0
    stdout = '{"result": "risposta"}'
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

    assert caplog.records, "il job legacy e' passato in silenzio"
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

    assert not [r for r in caplog.records if "contesto" in r.getMessage()]
    assert _CONTESTO in system
    assert prompts._CONTESTO_PRESENTE in system
    assert prompts._CONTESTO_ASSENTE not in system


def test_contesto_presente_ma_vuoto_non_e_un_job_legacy(caplog):
    """La chiave c'e' ma il nucleo non si e' composto (stringa vuota): NON e'
    il caso legacy e non deve loggare come tale -- quel degrado lo dichiara
    gia' il testo del nucleo (`componi_contesto_chat`). Il prompt pero' dice
    comunque al modello che la fotografia non c'e'."""
    job = {"kind": "chat", "job_id": "job-vuoto",
           "context": {"history": [], "system_prompt": "Sei HIRIS.",
                       "contesto": ""}}

    with caplog.at_level(logging.WARNING, logger="hiris.agent"):
        system = _cattura_system(job)

    assert not [r for r in caplog.records if "PRIMA di questo deploy" in r.getMessage()]
    assert prompts._CONTESTO_ASSENTE in system


def test_il_ponte_resta_senza_strumenti_anche_col_contesto():
    """La riga che separa questa fetta dalla B, vista dal runner: il contesto
    arriva, gli strumenti no."""
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
