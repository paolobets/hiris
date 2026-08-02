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


# ── I TESTI dei modelli (TEMPLATES[].strategic), non solo il catalogo ──────
#
# Il catalogo TOOLS sopra e' sincronizzato con ALL_TOOL_DEFS dai tre test
# precedenti, ma i cinque modelli preconfigurati in `var TEMPLATES` hanno una
# stringa `strategic` a parte -- prosa in italiano data in pasto al modello
# come istruzione -- che puo' citare uno strumento per nome senza che nessuno
# dei test sopra se ne accorga. E' successo davvero: undici citazioni di
# `search_entities(...)`, uno strumento rimosso da tempo, sono rimaste nei
# testi per mesi (vedi docs/design/2026-08-02-design-consolidamento.md,
# sezione 1.3) mentre il catalogo era gia' pulito.

_TOOL_CITATION_RE = re.compile(r"\b([a-z][a-z0-9]*_[a-z0-9_]*)\(")
# Criterio per riconoscere "una citazione di strumento" dentro prosa italiana:
# un identificativo minuscolo snake_case (quindi con ALMENO un underscore)
# incollato SENZA spazio a una parentesi aperta -- esattamente come vengono
# scritte le chiamate a tool in questi testi: get_entities_by_domain("sensor"),
# get_weather_forecast(hours=24), get_home_status(). Le due condizioni servono
# insieme a escludere la prosa normale:
#   - richiedere l'underscore esclude qualunque parola italiana (l'italiano
#     non usa underscore: "risultati", "device_class" e' gia' un caso limite
#     ma non un problema, vedi sotto);
#   - richiedere l'assenza di spazio prima della parentesi esclude le
#     parentesi esplicative del prosa, es. "disponibile (HA 2023.9+)" o
#     "irrigazione completa (20-30 min per zona)": qui c'e' sempre uno spazio
#     prima di "(" perche' e' punteggiatura, non sintassi di chiamata.
# Un identificatore con underscore seguito DIRETTAMENTE da "(" nella prosa che
# non sia una chiamata reale (es. "device_class(" senza spazio) sarebbe un
# falso positivo genuino con questo criterio -- ma va scritto con lo spazio
# ("dal device_class (door, window, motion)") proprio per non assomigliare a
# una chiamata: e' la stessa disciplina che il criterio impone al testo.


def _extract_templates_block(js_source: str) -> str:
    """Isola il testo del solo array `var TEMPLATES = [...]`, cosi' non si
    raccolgono per sbaglio identificatori con underscore+parentesi che
    comparissero altrove nel file (es. in codice JS come
    `document.getElementById(...)`, che pero' non ha underscore quindi non
    servirebbe comunque -- isolamento per lo stesso principio di
    _extract_tools_block sopra)."""
    start = js_source.index("var TEMPLATES = [")
    end = js_source.index("\n];", start)
    return js_source[start:end]


def _strategic_texts() -> list[str]:
    js_source = TEMPLATES_JS.read_text(encoding="utf-8")
    block = _extract_templates_block(js_source)
    return re.findall(r"strategic:\s*'((?:[^'\\]|\\.)*)'", block)


def _cited_tool_identifiers() -> set[str]:
    identificatori: set[str] = set()
    for testo in _strategic_texts():
        identificatori.update(_TOOL_CITATION_RE.findall(testo))
    return identificatori


def test_i_testi_strategici_dei_modelli_non_citano_tool_inesistenti():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    testi = _strategic_texts()
    assert len(testi) == 5, (
        f"attesi 5 modelli preconfigurati (Energia, Sicurezza, Presenza, Clima, "
        f"Irrigazione) in TEMPLATES, trovati {len(testi)} -- il regex/marcatore "
        "di estrazione e' rotto"
    )
    citati = _cited_tool_identifiers()
    assert citati, "nessuna citazione di tool trovata nei testi -- il regex e' probabilmente rotto"
    fantasmi = citati - nomi_backend
    assert not fantasmi, (
        "i testi strategici dei modelli preconfigurati citano strumenti che non "
        f"esistono in ALL_TOOL_DEFS: {sorted(fantasmi)}"
    )
