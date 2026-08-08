# tests/test_coerenza_conferma.py — sprint coerenza, A5 + A6.
#
# Due difetti di SICUREZZA PERCEPITA: HIRIS dichiarava una rete di protezione
# piu' larga di quella che ha. Chi si fida agisce con meno cautela di quanta
# ne servirebbe, quindi una promessa non mantenuta e' peggio di nessuna
# promessa.
#
# A5 — l'opzione "richiedi conferma" di un Chatbot nominava il solo
# call_ha_service, mentre altri quattro strumenti attuano davvero. Il
# meccanismo e' una ISTRUZIONE nel system prompt (claude_runner.py e
# backends/openai_compat_runner.py la accodano ai system blocks): non c'e'
# alcun controllo nel codice che la faccia rispettare. Il controllo nel
# codice esiste, ma e' un altro meccanismo -- il semaforo
# (tools/dispatcher.py::_gate) -- e non copre create_ha_config, che scrive
# subito su Home Assistant. Le guardie qui sotto tengono allineati i due
# elenchi: cio' che il modello legge e cio' che il codice attua.
#
# A6 — mcp/tiers.py descriveva create_task e cancel_task come "richiede
# conferma", ma api/handlers_execute.py li dispaccia senza alcun gate. Il
# limite reale su create_task esiste ed e' un altro: le sue azioni
# call_ha_service devono essere verdi per-entita' (handlers_execute:224-246,
# gia' coperto da tests/test_execute_api.py). Le guardie qui sotto vietano
# che una descrizione MCP prometta una conferma a un tool che non la
# attraversa.
#
# Fix wave 1 -- la correzione stessa sovra-affermava in due punti, la stessa
# classe di difetto in scala minore: la descrizione di create_task prometteva
# un filtro piu' stretto del reale (vale sulle azioni di PRIMO LIVELLO) e i
# documenti descrivevano il semaforo come rete completa, mentre
# create_ha_config e' proprio cio' che non copre. Le guardie qui sotto ora
# coprono anche i documenti, che nessun test leggeva.
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app"
DOCS = Path(__file__).resolve().parents[1] / "docs"


def _strip_js_comments(js: str) -> str:
    """Toglie i commenti /* */ e // prima di ogni assert: le guardie devono
    leggere il CODICE, non la prosa che lo descrive."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"//[^\n]*", "", js)
    return js


# ---------------------------------------------------------------------------
# A5 — cio' che l'opzione "richiedi conferma" dice al modello
# ---------------------------------------------------------------------------

def test_prompt_conferma_nomina_ogni_strumento_coperto():
    from hiris.app.claude_runner import (
        CONFIRMATION_COVERED_TOOLS,
        REQUIRE_CONFIRMATION_PROMPT,
    )

    for tool in CONFIRMATION_COVERED_TOOLS:
        assert tool in REQUIRE_CONFIRMATION_PROMPT, (
            f"{tool} e' dichiarato coperto ma non compare nel testo che il "
            "modello riceve"
        )


def test_copertura_conferma_include_i_cinque_strumenti_che_attuano():
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    assert set(CONFIRMATION_COVERED_TOOLS) == {
        "call_ha_service",
        "trigger_automation",
        "toggle_automation",
        "set_input_helper",
        "create_ha_config",
    }


def _tool_con_gate_semaforo() -> set[str]:
    """Nomi dei tool che nel dispatcher attraversano il semaforo (_gate).

    Legge il sorgente invece di importarlo perche' i rami sono dentro una
    catena di `if name == "..."` in un'unica funzione: non esiste una tabella
    da interrogare a runtime.

    LIMITE DICHIARATO del parsing: riconosce il semaforo solo dalla chiamata
    letterale `self._gate(` dentro il ramo. Un gate futuro raggiunto per via
    indiretta -- un helper che chiama _gate al posto del ramo, un decoratore,
    un dispatch a tabella -- sfuggirebbe IN SILENZIO: l'insieme resterebbe non
    vuoto grazie ai rami attuali, quindi nemmeno l'assert `gated` sotto se ne
    accorgerebbe, e lo strumento nuovo risulterebbe "non gated" senza che
    nessuno lo dica. Chi introduce un percorso del genere deve aggiornare
    anche questa lettura.
    """
    src = (BASE / "tools" / "dispatcher.py").read_text(encoding="utf-8")
    corrente = None
    trovati: set[str] = set()
    for line in src.splitlines():
        m = re.search(r'if name == "([a-z_]+)"', line)
        if m:
            corrente = m.group(1)
        elif "self._gate(" in line and corrente:
            trovati.add(corrente)
    return trovati


def test_ogni_tool_gated_dal_semaforo_e_anche_coperto_dalla_conferma():
    """Anti-deriva: se domani un nuovo strumento passa dal semaforo, deve
    entrare anche nell'elenco che l'opzione dichiara di coprire."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    gated = _tool_con_gate_semaforo()
    assert gated, "nessun ramo con self._gate trovato: guardia da rivedere"
    mancanti = gated - set(CONFIRMATION_COVERED_TOOLS)
    assert not mancanti, f"strumenti che attuano ma fuori dalla conferma: {mancanti}"


def test_create_ha_config_e_coperto_pur_non_avendo_semaforo():
    """create_ha_config scrive script e scene su HA immediatamente
    (dispatcher: apply_ha_config, nessun _gate): e' proprio lo strumento per
    cui la conferma dell'utente e' l'unico passaggio prima dell'effetto."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    assert "create_ha_config" in CONFIRMATION_COVERED_TOOLS
    assert "create_ha_config" not in _tool_con_gate_semaforo()


def test_backend_openai_usa_lo_stesso_testo_di_conferma():
    """Un secondo runner con un testo proprio farebbe divergere la copertura
    a seconda del provider scelto."""
    src = (BASE / "backends" / "openai_compat_runner.py").read_text(encoding="utf-8")
    assert "REQUIRE_CONFIRMATION_PROMPT" in src
    assert "Proposta:" not in src, "testo di conferma duplicato nel backend OpenAI"


def test_editor_chatbot_dichiara_cosa_copre_la_conferma():
    """La descrizione che l'utente legge deve nominare gli stessi strumenti
    del prompt e dire che e' un'istruzione al modello, non un blocco."""
    from hiris.app.claude_runner import CONFIRMATION_COVERED_TOOLS

    js = _strip_js_comments(
        (BASE / "static" / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    )
    for tool in CONFIRMATION_COVERED_TOOLS:
        assert tool in js, f"l'editor non dice all'utente che {tool} e' coperto"
    assert "istruzione al modello" in js, (
        "l'editor non dichiara che la conferma e' un'istruzione, non un blocco tecnico"
    )


# ---------------------------------------------------------------------------
# A6 (storico) — le descrizioni MCP promettevano una conferma al modello
# ---------------------------------------------------------------------------
#
# Il catalogo MCP (mcp/tiers.py) e il server che lo esponeva sono usciti con
# la Fetta E2 Task 3 -- MCP non e' piu' servito a Claude. Le guardie che
# leggevano le sue descrizioni (promesse di conferma, perimetro del filtro di
# create_task) sono uscite con lui: quel testo non esiste piu' in nessun file.
#
# I due pin che restavano qui (cancel_task senza gate, create_task filtrato
# solo al primo livello) esercitavano `handle_execute` direttamente: erano
# fatti reali di /api/execute, non della descrizione MCP. Con la Fetta E2
# Task 4 api/handlers_execute.py esce a sua volta -- quella superficie (e il
# suo pre-screening delle azioni di create_task per tier, unico nel suo
# genere: ne' dispatcher.py ne' task_engine.py lo rifanno) non esiste piu' in
# nessun file. Il soggetto dei due pin e' sparito con lei, non solo la via
# d'accesso: nessun posto dove spostarli.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix wave 1 -- cio' che i documenti dichiarano
# ---------------------------------------------------------------------------

# I quattro documenti che descrivono require_confirmation all'utente. Nessun
# test li leggeva, quindi il testo poteva derivare senza che nulla cadesse:
# e' successo proprio qui, con il semaforo presentato come rete completa.
_DOC_CONFERMA = ("come-funziona.md", "how-it-works.md", "casi-duso.md", "use-cases.md")

# Marcatori con cui un testo dichiara che la copertura ha un buco. Ne basta
# uno: la guardia verifica che l'eccezione sia DETTA, non come sia scritta.
_MARCATORI_ECCEZIONE = (
    "eccezione", "tranne", "salvo", "non copre", "non tocca",
    "except", "does not cover", "outside",
)


def _blocchi_su_require_confirmation(testo: str) -> list[str]:
    """Paragrafi (o righe di tabella) che parlano di require_confirmation."""
    return [b for b in re.split(r"\n\s*\n", testo) if "require_confirmation" in b]


def test_i_documenti_non_dichiarano_un_semaforo_piu_largo_del_vero():
    """create_ha_config e' esattamente cio' che il semaforo NON copre: dalla
    chat crea script e scene su Home Assistant subito. Un documento che
    presenta il semaforo come l'argine che regge da solo promette una rete
    piu' larga di quella che c'e'. Dove si nomina il semaforo, l'eccezione va
    nominata insieme."""
    for nome in _DOC_CONFERMA:
        testo = (DOCS / nome).read_text(encoding="utf-8")
        blocchi = _blocchi_su_require_confirmation(testo)
        assert blocchi, f"docs/{nome}: nessun blocco su require_confirmation, guardia da rivedere"
        for blocco in blocchi:
            basso = blocco.lower()
            if "semaforo" not in basso and "semaphore" not in basso:
                continue
            assert "create_ha_config" in basso and any(
                m in basso for m in _MARCATORI_ECCEZIONE
            ), (
                f"docs/{nome}: il semaforo e' presentato come rete completa senza "
                "dichiarare che create_ha_config ne resta fuori"
            )
