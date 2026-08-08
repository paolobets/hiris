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
# A5 (storico) — cio' che l'opzione "richiedi conferma" dice al modello
# ---------------------------------------------------------------------------
#
# Review finale fetta E2, I-5: `CONFIRMATION_COVERED_TOOLS` e
# `REQUIRE_CONFIRMATION_PROMPT` sono uscite da claude_runner.py, e con loro
# l'iniezione nel system prompt (qui e nei due backend OpenAI-compat). I
# cinque strumenti che nominavano (call_ha_service, trigger_automation,
# toggle_automation, set_input_helper, create_ha_config) non esistono in
# NESSUN catalogo raggiungibile da nessun runner -- la promessa "richiedo
# conferma prima di attuare" non aveva piu' nulla da coprire. I quattro test
# che pinnavano quella copertura (l'elenco dei cinque, il testo del prompt,
# il fatto che l'editor li nominasse) sono usciti con il loro soggetto.
# fetta E2 Task 7 aveva gia' tolto le due guardie sul gate reale di
# `tools/dispatcher.py` (vedi git history) per lo stesso motivo: il soggetto
# a cui il prompt doveva restare fedele e' sparito con lui, non solo la
# lettura che lo scopriva.
#
# Sopravvive un pin sul nuovo stato: l'editor non deve promettere che
# require_confirmation copre strumenti che non esistono piu' in nessun
# catalogo -- deve dire la verita' (oggi non ha alcun effetto osservabile),
# non ripetere una promessa vuota.


def test_editor_non_promette_copertura_di_strumenti_morti():
    """Isola SOLO il blocco "Conferma" (require_confirmation): chatbot-editor.js
    nomina ancora `call_ha_service` altrove (il gruppo di checkbox
    `allowed_tools`, fuori scope qui -- esce con la E5 insieme al resto del
    catalogo a 34 nomi), quindi la guardia non puo' leggere l'intero file."""
    js = _strip_js_comments(
        (BASE / "static" / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    )
    start = js.index('<div class="fg-label">Conferma</div>')
    end = js.index("</p></div>';", start)
    blocco_conferma = js[start:end]
    for tool in ("call_ha_service", "trigger_automation", "toggle_automation",
                 "set_input_helper", "create_ha_config"):
        assert tool not in blocco_conferma, (
            f"il blocco Conferma nomina ancora {tool} come coperto da "
            "require_confirmation, ma nessun catalogo raggiungibile lo offre piu'"
        )
    assert "f-require-confirmation" in blocco_conferma, (
        "il campo require_confirmation e' sparito dall'editor"
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
