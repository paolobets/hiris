"""Task 5 («i testi senza proprietario unico», fetta "il seguito delle chat
divise", spec 2026-09-26 §3): piu' persone parlano con HIRIS oggi (il filo di
Task 2, la pagina Costruzioni di Task 4), e i prompt e le descrizioni degli
strumenti assumevano un «utente»/«proprietario» solo. Questo file pinna il
GREP sulle COSTANTI (importate, mai sui file interi: i commenti possono citare
la storia -- brief Task 5) e le proprieta' di sicurezza 5.1-5.6 di
`security-constraints.md`.
"""
import json
import sqlite3
import time

import pytest

from hiris.app.action.construction.revisions import (
    _SCHEMA,
    REASON_DISDETTA,
    ConstructionStore,
)
from hiris.app.action.construction.workshop import _invalid_form
from hiris.app.agent import prompts
from hiris.app.api.handlers_proposals import _REDO_SYSTEM
from hiris.app.claude_runner import BASE_IDENTITY, BASE_TOOL_RULES, ClaudeRunner
from hiris.app.home_space import tools as home_tools
from hiris.app.home_space.briefing import compose
from hiris.app.mind.actuator_turn import SYSTEM as ACTUATOR_SYSTEM
from hiris.app.mind.observer import SYSTEM as OBSERVER_SYSTEM

# ── 5.4 / brief: le costanti di prompt elencate in spec §1 ──────────────────
_PROMPT_COSTANTI = {
    "claude_runner.BASE_IDENTITY": BASE_IDENTITY,
    "claude_runner.BASE_TOOL_RULES": BASE_TOOL_RULES,
    "prompts._CHAT_INSTRUCTION": prompts._CHAT_INSTRUCTION,
    "prompts.DICHIARAZIONE_CASA": prompts.DICHIARAZIONE_CASA,
}

# Le descrizioni degli strumenti che il brief nomina esplicitamente
# (home_space/tools.py) -- tool NAMES non cambiano (5.4): si verifica solo il
# testo di `description`, nested compreso (dict intero via json.dumps, non i
# soli primi livelli).
_TOOL_DEFS = {
    "search": home_tools.SEARCH_TOOL_DEF,
    "view": home_tools.VIEW_TOOL_DEF,
    "fetch": home_tools.FETCH_TOOL_DEF,
    "execute": home_tools.EXECUTE_TOOL_DEF,
    "propose": home_tools.PROPOSE_TOOL_DEF,
    "confirm": home_tools.CONFIRM_TOOL_DEF,
}


def _niente_utente(testo: str) -> bool:
    minuscolo = testo.lower()
    return "l'utente" not in minuscolo and "l’utente" not in minuscolo


def test_nessun_prompt_nomina_l_utente():
    for nome, testo in _PROMPT_COSTANTI.items():
        assert _niente_utente(testo), (
            f"{nome} nomina ancora «l'utente»: piu' persone parlano con HIRIS "
            "oggi (spec 2026-09-26 §3), il testo dice «chi ti sta parlando»")


def test_nessuna_descrizione_di_strumento_nomina_l_utente():
    for nome, definizione in _TOOL_DEFS.items():
        serializzato = json.dumps(definizione, ensure_ascii=False).lower()
        assert "l'utente" not in serializzato and "l’utente" not in serializzato, (
            f"la descrizione di «{nome}» nomina ancora «l'utente»")


def test_i_nomi_degli_strumenti_non_sono_cambiati():
    """5.4: la riscrittura e' di testo, non di firma -- `promise_tools`
    deriva il catalogo per NOME, e un nome spostato lo romperebbe in
    silenzio."""
    attesi = {"search": "search", "view": "view", "fetch": "fetch",
              "execute": "execute", "propose": "propose", "confirm": "confirm"}
    for chiave, atteso in attesi.items():
        assert _TOOL_DEFS[chiave]["name"] == atteso


# ── 5.1: DICHIARAZIONE_CASA ──────────────────────────────────────────────────

def test_dichiarazione_casa_riferisce_a_chi_parla_e_lascia_decidere_a_chi_amministra():
    testo = prompts.DICHIARAZIONE_CASA
    # Cio' che deve restare (5.1): MATERIALE/da leggere, «non sono
    # istruzioni», e il doppio divieto -- ne' eseguirla ne' ignorarla.
    assert "materiale da leggere" in testo.lower()
    assert "non sono istruzioni" in testo.lower()
    assert "non eseguirla" in testo.lower(), (
        "il divieto di ESEGUIRE la richiesta trovata nel materiale e' sparito: "
        "un divieto solo (ignorarla) lascerebbe indovinare l'altra meta'")
    assert "non ignorarla" in testo.lower()
    # Cio' che cambia: la segnalazione va a chi legge, la decisione resta a
    # chi amministra la casa -- nella STESSA frase (brief Task 5).
    assert "chi ti sta parlando" in testo
    assert "chi la amministra" in testo or "chi amministra la casa" in testo
    assert "proprietario" not in testo.lower()


# ── 5.6: osservatore / attuatore / «Rifalla» -- wording only ────────────────

def test_osservatore_non_nomina_un_proprietario_ma_chi_amministra_la_casa():
    assert "il proprietario" not in OBSERVER_SYSTEM.lower()
    assert "chi amministra la casa" in OBSERVER_SYSTEM


def test_attuatore_non_nomina_un_proprietario_ma_chi_amministra_la_casa():
    assert "il proprietario" not in ACTUATOR_SYSTEM.lower()
    assert "chi amministra la casa" in ACTUATOR_SYSTEM


def test_rifalla_non_nomina_un_proprietario_ma_chi_amministra_la_casa():
    assert "il proprietario" not in _REDO_SYSTEM.lower()
    assert "chi amministra la casa" in _REDO_SYSTEM


def test_workshop_richiesto_non_nomina_l_utente():
    """`_invalid_form` (`action/construction/workshop.py`) e' il motivo che
    torna al modello quando `richiesto` non e' una delle tre strutture:
    stesso divieto delle descrizioni degli strumenti, stesso testo."""
    motivo = _invalid_form({"richiesto": "non-e-una-struttura-valida"})
    assert motivo is not None
    assert _niente_utente(motivo)
    assert "chi ti sta parlando" in motivo


# ── 5.6 (osservatore): le forme che NON devono cambiare ─────────────────────

def test_osservatore_e_attuatore_non_toccano_i_gesti_dichiarati():
    """Wording only: i vocabolari chiusi restano quelli di prima -- se
    cambiassero, romperebbero la pagina che li legge senza che questo file
    se ne accorga altrimenti."""
    from hiris.app.mind.actuator_turn import GESTURES, OUTCOME_GESTURES
    assert GESTURES == ("indagine", "proposta")
    assert OUTCOME_GESTURES == ("indagine", "riparazione", "proposta")


# ── Il briefing (home_space/briefing.py): le entita' nascoste ───────────────

_CASA_ENTITA_NASCOSTA = {
    "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
    "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": "terra",
              "alias": [], "etichette": []}],
    "dispositivi": [],
    "entita": [
        {"id": "light.segreta", "nome": "Segreta", "area_id": "cucina",
         "dispositivo_id": None, "classe": None, "unita": None,
         "disabilitata": 0, "nascosta": 1},
    ],
    "etichette": [], "categorie": [], "integrazioni": [],
}


def test_il_nucleo_non_nomina_l_utente_per_le_entita_nascoste():
    testo, _ = compose(_CASA_ENTITA_NASCOSTA, [], [], {"light.segreta": "on"})
    # controllo di sanita': il ramo che vogliamo verificare e' stato preso
    # davvero (senza, il test non proverebbe niente)
    assert "nascosta" in testo.lower()
    assert _niente_utente(testo)


# ── 5.5: il motivo di rifiuto e' UNA costante, non retipata in JS ───────────
# Fix round 1 (RULING: migrate): nessun lettore di produzione leggeva il
# testo legacy, quindi non resta una seconda costante a runtime -- si
# migrano le righe vecchie una volta sola, all'apertura dell'archivio
# (`revisions.py::_migration_3`), e il vecchio letterale vive SOLO li'.

def test_reason_disdetta_e_una_costante_sola_che_non_nomina_un_proprietario():
    assert REASON_DISDETTA == "rifiutata dalla pagina"
    assert "proprietario" not in REASON_DISDETTA


def test_mark_cancelled_scrive_la_costante_non_un_letterale_ricopiato(tmp_path):
    archivio = ConstructionStore(str(tmp_path / "costruzioni.db"))
    try:
        ident = archivio.propose(
            operation="crea", domain="automation", key="1", actor="chat",
            exchange=None, phrase=None, prima=None, dopo={"alias": "x"},
            helper=[], preview="", now=time.time())["id"]
        archivio.mark_cancelled(ident, now=time.time())
        riga = archivio.read(ident)
    finally:
        archivio.close()
    assert riga["motivo"] == REASON_DISDETTA


def test_una_riga_col_vecchio_letterale_legge_quello_nuovo_dopo_la_migrazione(tmp_path):
    """Il RULING del fix round 1: un archivio scritto PRIMA di questa
    versione (schema v2, il letterale «rifiutata dal proprietario» sul
    disco) non resta cosi' per sempre -- aprirlo con `ConstructionStore`
    (che porta lo schema a v3, `_migration_3`) lo riscrive UNA volta.

    Si simula un DB "vecchio" a mano (schema v2 gia' applicato, timbrato con
    `PRAGMA user_version=2`) perche' un DB nuovo, senza tabelle preesistenti,
    nasce gia' alla versione piu' recente e non farebbe girare nessuna
    migrazione -- non proverebbe niente."""
    percorso = str(tmp_path / "vecchio.db")
    grezza = sqlite3.connect(percorso)
    grezza.executescript(_SCHEMA)
    grezza.execute(
        "INSERT INTO costruzioni(id,creata_ts,aggiornata_ts,stato,gesto,dominio,"
        "chiave,origine,turno,frase,prima_json,dopo_json,helper_json,anteprima,"
        "esecuzione_id,motivo,subject_key,entry_point) "
        "VALUES('v1',1.0,1.0,'disdetta','crea','automation','1','chat',NULL,NULL,"
        "NULL,NULL,'[]','',NULL,'rifiutata dal proprietario',NULL,NULL)")
    grezza.execute("PRAGMA user_version = 2")
    grezza.commit()
    grezza.close()

    archivio = ConstructionStore(percorso)
    try:
        riga = archivio.read("v1")
    finally:
        archivio.close()
    assert riga["stato"] == "disdetta"
    assert riga["motivo"] == REASON_DISDETTA


# ── 5.3: niente di per-turno entra nel prefisso in cache ────────────────────

@pytest.mark.asyncio
async def test_il_prefisso_in_cache_e_identico_per_due_soggetti_diversi():
    """Sicurezza 5.3: `BASE_SYSTEM_PROMPT` resta una costante e il breakpoint
    di cache sta PRIMA di `context_str` -- il nucleo (che porta la sezione
    «Chi ti sta parlando», per-turno e per-soggetto) e' l'unico blocco che
    puo' differire fra due turni. Due soggetti diversi devono produrre lo
    STESSO prefisso, byte per byte.

    Non si tocca `_who_is_speaking` (5.2): questo test chiama `ClaudeRunner.
    chat()` direttamente con due `context_str` diversi, come se venissero da
    due soggetti diversi, e ispeziona i blocchi `system` mandati all'API."""
    from unittest.mock import AsyncMock, MagicMock, patch

    with patch("anthropic.AsyncAnthropic"):
        runner = ClaudeRunner(api_key="test-key")

    def _messaggio_finto(*_args, **_kwargs):
        msg = MagicMock(stop_reason="end_turn",
                         content=[MagicMock(type="text", text="ok")])
        msg.usage = MagicMock(input_tokens=1, output_tokens=1,
                               cache_creation_input_tokens=0,
                               cache_read_input_tokens=0)
        return msg

    runner._client.messages.create = AsyncMock(side_effect=_messaggio_finto)

    contesto_paolo = "## Chi ti sta parlando\n- Paolo (persona)\n"
    contesto_marta = "## Chi ti sta parlando\n- Marta (persona)\n"

    await runner.chat("ciao", system_prompt="Sei HIRIS.", context_str=contesto_paolo)
    system_paolo = runner._client.messages.create.call_args.kwargs["system"]

    await runner.chat("ciao", system_prompt="Sei HIRIS.", context_str=contesto_marta)
    system_marta = runner._client.messages.create.call_args.kwargs["system"]

    assert system_paolo[:-1] == system_marta[:-1], (
        "il prefisso cacheato (tutto tranne l'ultimo blocco, il nucleo) "
        "differisce fra due soggetti: qualcosa di per-turno e' entrato nella "
        "parte che dovrebbe restare statica")
    assert system_paolo[-1]["text"] == contesto_paolo
    assert system_marta[-1]["text"] == contesto_marta
    # e il breakpoint di cache resta sul penultimo blocco (l'ultimo stabile),
    # mai sull'ultimo (il nucleo, volatile per costruzione)
    assert "cache_control" in system_paolo[-2]
    assert "cache_control" not in system_paolo[-1]
