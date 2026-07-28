# tests/test_chatbot_editor.py — SP-4 Fase B Task 4 (editor Chatbot sul kit +
# knowledge_access, mai avuto UI). Guardie di WIRING (testo sul sorgente); la
# copertura COMPORTAMENTALE (payload di save, dirty via picker, cancel guard)
# vive in tests/js/chatbot-editor.test.mjs (node --test + jsdom).
#
# Nota anti-falso-segnale: le guardie sotto controllano il CODICE, non la
# prosa che lo descrive. chatbot-editor.js apre con un lungo commento a
# blocco che, per necessità documentale, ripete quasi ogni identificatore
# rilevante (incluso `currentId`, il nome proprio della cosa rimossa). Un
# assert grezzo `"X" not in js` su tutto il sorgente puo' quindi fallire (o
# passare a vuoto) sul commento invece che sul codice. Le funzioni sotto
# spogliano i commenti prima di ogni assert -- positivo o negativo -- cosi'
# il segnale viene sempre dal codice reale.
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def _strip_js_comments(js: str) -> str:
    """Remove /* block */ and // line comments. Verified against this file:
    nessuna occorrenza di `//` dentro stringhe/URL (niente `://`), quindi lo
    strip a riga e' sicuro qui senza un parser JS completo."""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"//[^\n]*", "", js)
    return js


def _strip_html_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _editor_code():
    js = (BASE / "config" / "chatbot-editor.js").read_text(encoding="utf-8")
    return _strip_js_comments(js)


def _config_html_code():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    return _strip_html_comments(html)


def test_editor_uses_kit_and_picker_and_owns_payload():
    code = _editor_code()
    assert "HirisEditorKit" in code and "HirisEntityPicker" in code
    assert "HirisChatbotEditor" in code and "function mount(" in code
    assert not (BASE / "config" / "chatbot-form.js").exists(), "il form deve essere assorbito"


def test_knowledge_access_is_finally_editable():
    code = _editor_code()
    assert "knowledge_access" in code, "il dial knowledge non deve piu' essere solo-API"
    assert "allow_sensitive" in code


def test_no_double_source_of_truth_for_the_active_chatbot_id():
    """window.currentId (ex chatbot-form.js) must be gone entirely --
    HirisState.get('activeChatbotId') is the sole owner (grounding A4).
    The header comment legitimately *names* `currentId` while documenting
    its removal -- checked on comment-stripped code so that documentation
    can't trip (or silently satisfy) this guard."""
    code = _editor_code()
    assert "currentId" not in code
    assert "HirisState.get('activeChatbotId')" in code


def test_section_list_has_a_single_source_of_truth():
    """The 8-section duplication (template + anchor rail + sc-body-* literals,
    grounding A3) must not survive as 3 independently-maintained lists: the
    template in config.html carries no per-section markup anymore, and
    chatbot-editor.js builds both the section-cards and the anchor rail from
    one array."""
    code = _editor_code()
    assert "var SECTIONS" in code
    assert "function buildSections(" in code

    html = _config_html_code()
    tpl_start = html.index('id="tpl-agent-editor"')
    tpl_end = html.index("</template>", tpl_start)
    tpl_body = html[tpl_start:tpl_end]
    # The template must not hardcode any section-card anymore.
    assert "sc-body-" not in tpl_body
    assert "anchor-link" not in tpl_body


def test_new_sections_present_scope_knowledge_autonomia():
    code = _editor_code()
    for sid in ("scope", "knowledge", "autonomia"):
        assert "sc-body-" + sid in code or "id: '" + sid + "'" in code, f"missing section: {sid}"


def test_autonomia_is_read_only_and_does_not_touch_the_semaphore():
    """Autonomia summarizes the gateway tier + require_confirmation; it must
    never write policy -- the only api/gateway call is a plain GET (no
    method: 'POST'/'PUT' anywhere near it)."""
    code = _editor_code()
    assert "fetch('api/gateway', { headers: { 'X-Requested-With': 'fetch' } })" in code
    assert "require_confirmation" in code


def test_config_html_no_longer_includes_chatbot_form():
    code = _config_html_code()
    assert "config/chatbot-form.js" not in code
