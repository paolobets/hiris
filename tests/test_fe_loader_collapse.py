"""SP-4 Fase B Task 2: collassa il loader dinamico.

Guardie di WIRING (testo sul sorgente) — la copertura COMPORTAMENTALE reale
(mount -> unmount -> remount -> interazione, nessun `script[data-legacy]`
creato a runtime) vive in tests/js/loader-collapse.test.mjs (node --test +
jsdom), come richiesto dal piano per ogni task che tocca il front-end dal
Task 1b in poi.
"""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

LEGACY = ["templates.js", "permessi.js", "log-row.js", "logs.js", "usage.js",
          "proposals.js", "chatbot-form.js"]


def test_no_runtime_script_injection():
    js = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    for token in ("LEGACY_SCRIPTS", "ensureLegacy", "rewireLegacyAfterMount", "addLegacyShims"):
        assert token not in js, f"{token} deve sparire: gli script sono <script src> in config.html"
    main = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "data-legacy" not in main, "anche il loader ad-hoc di proposals.js deve sparire"


def test_all_editor_scripts_are_declared_in_html():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    for f in LEGACY:
        assert "config/" + f in html, f"{f} deve essere un <script src> (cache-busting per-file)"


def test_usage_js_has_no_iife_time_dom_access():
    """Regressione per il bug che il loader dinamico mascherava: usage.js
    faceva `document.getElementById(...).onclick = ...` a livello IIFE — con
    lo script caricato staticamente (non più iniettato dopo il mount) i
    bottoni non esistono ancora al load, e comunque un binding diretto
    andrebbe perso a ogni remount dell'editor (nodo sostituito)."""
    js = (BASE / "config" / "usage.js").read_text(encoding="utf-8")
    assert "getElementById('u-ag-reset-btn').onclick" not in js
    assert "getElementById('u-ag-toggle-btn').onclick" not in js
    assert "getElementById(\"u-ag-reset-btn\").onclick" not in js
    assert "getElementById(\"u-ag-toggle-btn\").onclick" not in js
    assert "addEventListener('click'" in js or 'addEventListener("click"' in js, \
        "usage.js deve wire i bottoni via event delegation, non binding diretto a IIFE-time"


def test_winners_table_applied():
    """SP-4 Fase B Task 2 — una sola copia per comportamento duplicato."""
    editor = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    usage = (BASE / "config" / "usage.js").read_text(encoding="utf-8")

    # reset consumi: versione editor (HirisState.activeChatbotId), non il
    # global currentId — deve restare da qualche parte nel bundle editor.
    assert "activeChatbotId" in editor

    # toggle abilitato: versione usage.js (confirm + reload lista + riapri
    # agente) — il confirm() e il reload devono sopravvivere.
    assert "confirm(" in usage
    assert "loadChatbots()" in usage
    assert "openAgent(fresh)" in usage


def test_config_html_script_order_respects_dependencies():
    """state -> router -> api -> entity-picker -> templates -> permessi ->
    log-row -> logs -> usage -> proposals -> chatbot-form -> ... ->
    chatbot-editor -> ... -> main, come da grounding A1/A3 e dal piano."""
    html = (BASE / "config.html").read_text(encoding="utf-8")
    order = [
        "config/state.js", "config/router.js", "config/api.js",
        "config/entity-picker.js", "config/templates.js", "config/permessi.js",
        "config/log-row.js", "config/logs.js", "config/usage.js",
        "config/proposals.js", "config/chatbot-form.js", "config/chatbot-editor.js",
        "config/main.js",
    ]
    positions = [html.index(name) for name in order]
    assert positions == sorted(positions), "ordine di dipendenze violato in config.html"
