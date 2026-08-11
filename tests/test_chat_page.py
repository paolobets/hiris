"""Wiring guards for the rebuilt standalone chat page (SP-4 Fase B Task 8).

Real behaviour (send -> chatbot_id, 202 -> polling, turn-limit, tasks panel)
is covered by tests/js/chat-page.test.mjs (node --test + jsdom, per the
plan's "test comportamentali richiesti" table, row 8). These are text-source
guards only: that the inline <script> block is gone, that each functional
block was actually extracted to static/chat/*.js so the server's per-file
cache-busting (_ASSET_REF_RE) covers it, and that the removed private
duplicates (esc/applyTheme/loadUsage/pollChatReply) don't come back.
"""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"
INDEX = STATIC / "index.html"
CHAT = STATIC / "chat"

EXPECTED_CHAT_FILES = (
    "state.js", "messages.js", "agents.js", "send.js", "theme.js",
    "tasks.js", "proposals.js", "sidebar.js", "keyboard.js", "main.js",
)


def test_index_html_has_no_inline_script_block():
    html = INDEX.read_text(encoding="utf-8")
    # Two small inline <script> blocks are expected and out of scope: the
    # theme-bootstrap snippet in <head> (paints the theme before first
    # render, shared shape with config.html) has no logic worth extracting.
    # Everything else must be <script src="static/chat/...">.
    scripts = html.count("<script")
    literal_src_scripts = html.count('<script src="static/chat/') + html.count('<script src="static/config/')
    theme_bootstrap = html.count("localStorage.getItem('hiris-theme')")
    assert theme_bootstrap == 1, "il bootstrap tema inline deve restare (evita il flash pre-render)"
    # Every <script> tag besides the theme-bootstrap one must be a literal
    # src= reference so _ASSET_REF_RE (per-file cache-busting) can see it.
    assert scripts == literal_src_scripts + 1, (
        "ogni <script> oltre al bootstrap tema deve essere un src= letterale "
        "(fingerprint per-file) -- niente blocco inline residuo"
    )


def test_all_chat_js_files_exist_and_are_declared_in_html():
    html = INDEX.read_text(encoding="utf-8")
    for fname in EXPECTED_CHAT_FILES:
        assert (CHAT / fname).is_file(), f"static/chat/{fname} deve esistere"
        assert f'src="static/chat/{fname}"' in html, f"static/chat/{fname} deve essere un <script src> in index.html"


def test_shared_api_js_is_reused_not_forked():
    html = INDEX.read_text(encoding="utf-8")
    assert 'src="static/config/api.js"' in html, "la pagina chat deve caricare config/api.js (esc/applyTheme/loadUsage condivisi)"

    chat_src = "\n".join((CHAT / f).read_text(encoding="utf-8") for f in EXPECTED_CHAT_FILES)
    # The page's private forks must be gone: no local `function esc(`,
    # `function applyTheme(` or `function loadUsage(` redeclared anywhere
    # under static/chat/.
    assert "function esc(" not in chat_src, "esc() deve venire da config/api.js, non da una copia privata"
    assert "function applyTheme(" not in chat_src, "applyTheme() deve venire da config/api.js"
    assert "function loadUsage(" not in chat_src, "loadUsage() deve venire da config/api.js"


def test_chat_wire_uses_chatbot_id():
    send_js = (CHAT / "send.js").read_text(encoding="utf-8")
    assert "chatbot_id: state.activeAgentId" in send_js or "chatbot_id:" in send_js
    assert "agent_id:" not in send_js, "il wire non deve inviare la chiave legacy agent_id"


def test_no_inline_onclick_attributes_left():
    html = INDEX.read_text(encoding="utf-8")
    assert "onclick=" not in html, "gli onclick= inline devono essere sostituiti da addEventListener"


def test_only_one_poll_chat_reply_implementation_on_this_surface():
    """Task 8 removes the page's inline pollChatReply duplicate. The card
    (hiris-chat-card.js) keeps its own -- it is Shadow-DOM code copied into
    HA's www/ folder via a different deploy path (server.py) and cannot
    <script src> a static/chat/*.js file, so cross-surface sharing is out
    of scope here (see task-8-report.md)."""
    send_js = (CHAT / "send.js").read_text(encoding="utf-8")
    assert send_js.count("function pollChatReply") == 1
    assert "function pollChatReply" not in INDEX.read_text(encoding="utf-8")
