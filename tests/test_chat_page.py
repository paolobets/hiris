"""Wiring guards for the rebuilt standalone chat page (SP-4 Fase B Task 8).

Real behaviour (send -> POST api/chat, 202 -> polling, turn-limit)
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

# fetta E5 Task 6: tasks.js e proposals.js sono usciti insieme alle rotte
# /api/tasks* e /api/proposals*, che il backend non serve piu' dalla E3.
# fetta E5 Task 9: knowledge-core.js e knowledge.js sono usciti a loro volta,
# insieme al pannello Memoria della chat che interrogava la coda di
# approvazione (vuota per costruzione da mesi) -- vedi
# static/config/memoria-route.js, che la sostituisce sulla pagina di
# configurazione.
EXPECTED_CHAT_FILES = (
    "state.js", "messages.js", "agents.js", "send.js", "theme.js",
    "sidebar.js", "keyboard.js", "main.js",
)


def test_index_html_has_no_inline_script_block():
    html = INDEX.read_text(encoding="utf-8")
    # Two small inline <script> blocks are expected and out of scope: the
    # theme-bootstrap snippet in <head> (paints the theme before first
    # render, shared shape with config.html) has no logic worth extracting.
    # Everything else must be <script src="static/chat/...">.
    scripts = html.count("<script")
    literal_src_scripts = (
        html.count('<script src="static/chat/')
        + html.count('<script src="static/config/')
        # Task B8: build-check.js e' condiviso dalle DUE pagine (chat e
        # configurazione), quindi vive alla radice di static/ e non sotto
        # chat/ o config/ -- ma e' comunque un src= letterale, fingerprintato
        # dalla stessa _ASSET_REF_RE di ogni altro asset qui sopra.
        + html.count('<script src="static/build-check.js')
    )
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


def test_chat_wire_non_manda_piu_chatbot_id():
    """Rovescio di test_chat_wire_uses_chatbot_id (fetta E5 Task 3, "via
    l'elenco dei bot"): un solo assistente non ha piu' bisogno di dirsi
    quale. La chiave resta accettata e ignorata lato server fino al Task 10
    (che smonta anche quella lettura, §3 del brief); qui si pinna solo che
    il wire non la mandi piu'. Verificato a mutazione: reintrodurre
    `chatbot_id: state.activeAgentId` nel body fa fallire questo test."""
    send_js = (CHAT / "send.js").read_text(encoding="utf-8")
    assert "chatbot_id:" not in send_js, "il wire non deve piu' inviare chatbot_id nel body"
    assert "agent_id:" not in send_js, "il wire non deve inviare la chiave legacy agent_id"


def test_no_inline_onclick_attributes_left():
    html = INDEX.read_text(encoding="utf-8")
    assert "onclick=" not in html, "gli onclick= inline devono essere sostituiti da addEventListener"


def test_only_one_poll_chat_reply_implementation_on_this_surface():
    """Il Task 8 di SP-4 aveva tolto il doppione inline della pagina, ma ne
    restava un secondo nella card Lovelace (codice Shadow-DOM copiato dentro
    Home Assistant, che non poteva condividere un file di static/chat/). Col
    Task 5 della E5 la card e' uscita: adesso di cicli di polling della
    risposta ne esiste **uno solo** in tutto il prodotto, ed e' questo."""
    send_js = (CHAT / "send.js").read_text(encoding="utf-8")
    assert send_js.count("function pollChatReply") == 1
    assert "function pollChatReply" not in INDEX.read_text(encoding="utf-8")
