"""Il catalogo TOOLS della UI (config/templates.js) deve restare sincronizzato
con ALL_TOOL_DEFS, l'elenco autorevole del backend (claude_runner.py) -- l'unica
whitelist da cui un Chatbot puo' scegliere quali strumenti concedere.

Senza questo test i due elenchi divergono in silenzio: un id fantasma nel
catalogo (checkbox che non corrisponde a nessun tool reale) o un tool reale
mai esposto in UI (irraggiungibile per sempre da un bot con whitelist
esplicita, perche' claude_runner.chat() filtra i tool disponibili proprio su
`allowed_tools`, popolato SOLO dalle checkbox di questo catalogo).
"""
import re
from pathlib import Path

TEMPLATES_JS = (
    Path(__file__).resolve().parents[1]
    / "hiris" / "app" / "static" / "config" / "templates.js"
)

# Tool di ALL_TOOL_DEFS deliberatamente assenti dal catalogo TOOLS della UI
# Chatbot. Ogni eccezione DEVE portare un commento che spiega perche' non ha
# senso spuntarla da qui -- altrimenti non e' un'eccezione, e' un tool da
# aggiungere al catalogo. Lista corta apposta: e' l'unico modo per restare
# onesti (vedi il modulo docstring).
KNOWN_BACKEND_ONLY_EXCEPTIONS = {
    # Il checkbox sarebbe un placebo. claude_runner.chat() rimuove SEMPRE
    # http_request dai tool effettivamente passati al modello quando
    # allowed_endpoints e' None (claude_runner.py, poco dopo la costruzione di
    # `tools`), e allowed_endpoints non ha ALCUNA superficie nel Designer: si
    # imposta solo via API diretta (hiris/app/api/handlers_chatbots.py). Finche'
    # quella whitelist di endpoint non ha una sua UI, spuntare questa casella
    # non abiliterebbe mai la chiamata -- coerente col fatto che nessun altro
    # file JS del Designer nomina "http_request" o "allowed_endpoints".
    "http_request",
}


def _extract_tools_block(js_source: str) -> str:
    """Isola il testo del solo array `var TOOLS = [...]`, per non raccogliere
    per sbaglio gli id di ACTIONS o KNOWLEDGE_KINDS (stessa forma {id, label,
    desc}, definiti piu' sotto nello stesso file)."""
    start = js_source.index("var TOOLS = [")
    end = js_source.index("];", start)
    return js_source[start:end]


def _catalog_ids() -> set[str]:
    js_source = TEMPLATES_JS.read_text(encoding="utf-8")
    block = _extract_tools_block(js_source)
    return set(re.findall(r"id:\s*'([a-zA-Z0-9_]+)'", block))


def test_ogni_id_del_catalogo_esiste_nel_backend():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    catalogo = _catalog_ids()
    assert catalogo, "il catalogo TOOLS non deve essere estratto vuoto -- il regex/marcatore e' rotto"
    fantasmi = catalogo - nomi_backend
    assert not fantasmi, (
        f"il catalogo TOOLS della UI elenca id che non esistono in ALL_TOOL_DEFS: {sorted(fantasmi)}"
    )


def test_ogni_tool_del_backend_e_nel_catalogo_o_e_un_eccezione_motivata():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    catalogo = _catalog_ids()
    mancanti = nomi_backend - catalogo - KNOWN_BACKEND_ONLY_EXCEPTIONS
    assert not mancanti, (
        "tool del backend assenti dal catalogo TOOLS della UI e non coperti da "
        f"un'eccezione motivata in KNOWN_BACKEND_ONLY_EXCEPTIONS: {sorted(mancanti)}"
    )


def test_le_eccezioni_note_corrispondono_a_tool_reali_del_backend():
    # Un'eccezione che non e' (piu') un tool del backend e' rumore morto: se il
    # tool sparisce da ALL_TOOL_DEFS va tolta anche da qui, non lasciata a
    # nascondere silenziosamente future voci mancanti con lo stesso nome.
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    orfane = KNOWN_BACKEND_ONLY_EXCEPTIONS - nomi_backend
    assert not orfane, f"eccezioni che non corrispondono piu' a nessun tool del backend: {sorted(orfane)}"
