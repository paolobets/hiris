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


# ── I TESTI dei modelli (TEMPLATES[].strategic e [].prompt), non il catalogo ─
#
# Il catalogo TOOLS sopra e' sincronizzato con ALL_TOOL_DEFS dai tre test
# precedenti, ma i cinque modelli preconfigurati in `var TEMPLATES` hanno DUE
# stringhe a parte -- `strategic` e `prompt`, entrambe prosa in italiano data
# in pasto al modello come istruzione, entrambe finiscono nel system prompt del
# bot allo stesso modo -- che possono citare uno strumento per nome senza che
# nessuno dei test sopra se ne accorga. E' successo davvero: undici citazioni
# di `search_entities(...)`, uno strumento rimosso da tempo, sono rimaste nei
# testi per mesi (vedi docs/design/2026-08-02-design-consolidamento.md,
# sezione 1.3) mentre il catalogo era gia' pulito.
#
# ── IL CRITERIO ──────────────────────────────────────────────────────────────
#
# Cosa si cerca: il NOME DI UNO STRUMENTO citato in un testo destinato al
# modello. Il nome dello strumento non lo si puo' cercare per elenco (l'elenco
# dei nomi leciti e' proprio ALL_TOOL_DEFS: cercare solo quelli non troverebbe
# MAI un nome inesistente, che e' l'unica cosa che questo test deve scoprire).
# Quindi il criterio riconosce la FORMA "identificatore di strumento" senza
# sapere in anticipo quali esistano, e poi confronta il raccolto con
# ALL_TOOL_DEFS.
#
# Un riferimento a strumento e' un identificatore snake_case tutto minuscolo
# (almeno un underscore: l'italiano non ne usa, quindi la prosa non entra),
# preso in QUALUNQUE posizione -- con la parentesi di chiamata
# `get_home_status()` o nudo in prosa `controlla con get_entity_states sui
# sensori`. Entrambe le forme sono presenti oggi nel file: la prima in
# `strategic`, la seconda in `prompt`. Il criterio precedente vedeva solo la
# prima ed era per questo cieco proprio dove il buco si era aperto.
#
# Non sono riferimenti a strumento -- ed e' qui che si separa il vocabolario di
# Home Assistant, che ha la stessa forma e nel testo compare a pieno diritto:
#
#   1. cio' che sta fra virgolette: e' un VALORE (dominio, stato, nome di zona)
#      passato come argomento, mai il nome dello strumento che lo riceve.
#      `get_entities_by_domain("binary_sensor")` cita UN solo strumento.
#   2. cio' che e' qualificato da un punto, da un lato o dall'altro: e' un
#      servizio o un'entita' di HA. `switch.turn_on(entity_id=...)` non e' una
#      citazione di `turn_on`, e `binary_sensor.porta_ingresso` non e' una
#      citazione di `binary_sensor`. Questo e' il difetto strutturale che il
#      criterio precedente aveva: il confine di parola matcha anche dopo il
#      punto, quindi decapitava i servizi HA del loro dominio e li denunciava.
#   3. cio' che tocca un `=`, da un lato o dall'altro: e' un parametro, nome
#      (`entity_id=light.cucina`) o valore (`service=open_valve`). Il nome di
#      uno strumento non e' mai un operando di assegnamento: e' seguito da `(`
#      o da prosa.
#
# Cosa il criterio NON puo' distinguere, e come si chiude: un nome di servizio
# HA scritto NUDO, senza dominio (`poi close_valve`, `poi turn_off`), e' per
# forma indistinguibile da una citazione di strumento. Non esiste regola
# sintattica che li separi: la differenza sta nel significato. Per questi c'e'
# l'elenco esplicito qui sotto. La scelta e' deliberata ed e' "fail-closed":
# qualunque identificatore snake_case nuovo che compaia nei testi e non sia ne'
# uno strumento reale ne' una voce dichiarata fa FALLIRE il test, e chi lo ha
# scritto deve classificarlo. Il criterio precedente sbagliava dal lato
# opposto: taceva su tutto cio' che non riconosceva.

# Parole del vocabolario di Home Assistant che nei testi dei modelli compaiono
# NUDE (senza dominio davanti) e che non sono e non saranno mai strumenti
# HIRIS. Ogni voce DEVE portare un commento: se non si sa dire perche' non e'
# uno strumento, allora e' un refuso da correggere nel testo, non una voce da
# aggiungere qui.
HA_VOCABULARY_NOT_TOOLS = {
    # Servizi di Home Assistant citati dal modello Irrigazione per spiegare la
    # coppia apri/chiudi da passare a call_ha_service: "valve: service=
    # open_valve poi close_valve; switch: service=turn_on poi turn_off". Sono
    # nomi di servizi HA (dominio valve.* e switch.*, vedi ACTIONS in
    # templates.js), non strumenti del catalogo TOOLS.
    "open_valve",
    "close_valve",
    "turn_on",
    "turn_off",
    # Attributo delle entita' di Home Assistant, non uno strumento: il modello
    # Sicurezza dice di riconoscere i sensori "dal nome o dal device_class
    # (door, window, motion)".
    "device_class",
}

# Le virgolette delimitano argomenti/valori, mai nomi di strumento (punto 1 del
# criterio): il contenuto viene tolto prima di cercare gli identificatori.
_STRING_VALUE_RE = re.compile(r'"[^"]*"')

_TOOL_REFERENCE_RE = re.compile(
    r"(?<![\w.=])"                       # 2/3: non preceduto da punto (servizio o
                                         #      entita' HA qualificata) ne' da '='
                                         #      (valore di parametro), ne' spezzato
                                         #      a meta' di una parola piu' lunga
    r"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)"   # identificatore snake_case minuscolo
    r"(?!\w)"                            # non prosegue in una parola piu' lunga
    r"(?!\.[a-z0-9_])"                   # 2: non e' il dominio di `dominio.entita`
                                         #    (ma il punto di fine frase va bene:
                                         #    "controlla con get_home_status.")
    r"(?!=)"                             # 3: non e' il nome di un parametro,
                                         #    `entity_id=...`
)


def _extract_templates_block(js_source: str) -> str:
    """Isola il testo del solo array `var TEMPLATES = [...]`, cosi' non si
    raccolgono per sbaglio identificatori snake_case che comparissero altrove
    nel file (es. gli `id:` del catalogo TOOLS, che sono per costruzione tutti
    leciti e renderebbero il test cieco proprio sui testi -- isolamento per lo
    stesso principio di _extract_tools_block sopra)."""
    start = js_source.index("var TEMPLATES = [")
    end = js_source.index("\n];", start)
    return js_source[start:end]


def _model_texts(js_source: str) -> list[tuple[str, str]]:
    """Tutti i testi dei modelli destinati al modello, come (campo, testo).

    Entrambi i campi, non solo `strategic`: `prompt` alimenta il system prompt
    del bot esattamente allo stesso modo e oggi cita tre strumenti."""
    block = _extract_templates_block(js_source)
    testi: list[tuple[str, str]] = []
    for campo in ("strategic", "prompt"):
        for testo in re.findall(rf"{campo}:\s*'((?:[^'\\]|\\.)*)'", block):
            testi.append((campo, testo))
    return testi


def _tool_references(testo: str) -> set[str]:
    """Gli identificatori che nel testo sono riferimenti a uno strumento,
    secondo il criterio documentato sopra."""
    senza_valori = _STRING_VALUE_RE.sub(" ", testo)
    return {
        nome
        for nome in _TOOL_REFERENCE_RE.findall(senza_valori)
        if nome not in HA_VOCABULARY_NOT_TOOLS
    }


def test_i_testi_dei_modelli_non_citano_tool_inesistenti():
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    testi = _model_texts(TEMPLATES_JS.read_text(encoding="utf-8"))
    assert len(testi) == 10, (
        "attesi 5 modelli preconfigurati (Energia, Sicurezza, Presenza, Clima, "
        f"Irrigazione) x 2 campi (strategic, prompt) in TEMPLATES, trovati "
        f"{len(testi)} testi -- il regex/marcatore di estrazione e' rotto"
    )
    fantasmi: dict[str, set[str]] = {}
    citati: set[str] = set()
    for campo, testo in testi:
        riferimenti = _tool_references(testo)
        citati |= riferimenti
        if riferimenti - nomi_backend:
            fantasmi.setdefault(campo, set()).update(riferimenti - nomi_backend)
    assert citati, (
        "nessun riferimento a strumento trovato nei testi dei modelli -- il "
        "criterio di riconoscimento e' probabilmente rotto"
    )
    assert not fantasmi, (
        "i testi dei modelli preconfigurati citano strumenti che non esistono "
        f"in ALL_TOOL_DEFS: { {k: sorted(v) for k, v in fantasmi.items()} }"
    )


# ── Un solo percorso, oggi ────────────────────────────────────────────────
#
# Fino alla Fetta E2 Task 3 esistevano DUE cataloghi di strumenti per lo
# stesso bot: la chat locale (claude_runner.ALL_TOOL_DEFS) e la chat via
# abbonamento, che parlava con l'MCP interno (agent/runner._DEFAULT_CHAT_TOOLS,
# nomi del catalogo mcp/tiers.py). L'MCP interno e' uscito -- e' il terzo
# catalogo della mappa del prodotto, e ora MCP non e' piu' servito a Claude --
# quindi la chat via abbonamento ragiona in puro testo, senza alcun catalogo di
# strumenti da tenere sincronizzato. Le guardie che confrontavano i due
# percorsi sono uscite con lui.


def test_il_vocabolario_ha_non_maschera_strumenti_reali():
    # Una voce di HA_VOCABULARY_NOT_TOOLS che sia ANCHE un nome di strumento
    # reale renderebbe invisibile al test proprio quello strumento: e' rumore
    # contraddittorio, va tolta di qui.
    from hiris.app.claude_runner import ALL_TOOL_DEFS
    nomi_backend = {t["name"] for t in ALL_TOOL_DEFS}
    collisioni = HA_VOCABULARY_NOT_TOOLS & nomi_backend
    assert not collisioni, (
        "voci di HA_VOCABULARY_NOT_TOOLS che sono strumenti reali del backend, "
        f"quindi mascherate al controllo: {sorted(collisioni)}"
    )


# ── Il criterio contro i casi che la review ha elencato ──────────────────────

def test_il_criterio_riconosce_le_citazioni_senza_parentesi():
    # Il buco vero: forma nuda in prosa. Il criterio precedente restava verde.
    assert _tool_references("Usa search_entities per trovare il sensore") == {"search_entities"}
    assert _tool_references(
        "controlla le precipitazioni con get_entity_states sui sensori pioggia"
    ) == {"get_entity_states"}
    # anche a fine frase, dove il punto e' punteggiatura e non qualificazione
    assert _tool_references("chiedi a get_home_status.") == {"get_home_status"}
    # e fra backtick o virgolette basse, come si citano gli identificatori
    assert _tool_references("Usa `search_entities` per trovare il sensore") == {"search_entities"}


def test_il_criterio_riconosce_le_citazioni_con_la_parentesi():
    assert _tool_references('get_entities_by_domain("binary_sensor")') == {"get_entities_by_domain"}
    assert _tool_references("get_weather_forecast(hours=48)") == {"get_weather_forecast"}
    assert _tool_references("get_home_status()") == {"get_home_status"}


def test_il_criterio_non_accusa_i_servizi_di_home_assistant():
    # Il falso positivo strutturale del criterio precedente: il confine di
    # parola matcha anche dopo il punto, quindi `turn_on` veniva denunciato.
    assert _tool_references("chiama light.turn_on(entity_id=light.cucina)") == set()
    assert _tool_references("scrivi switch.turn_on(...) sulla presa") == set()
    assert _tool_references("valve: service=open_valve poi close_valve") == set()
    assert _tool_references("switch: service=turn_on poi turn_off") == set()


def test_il_criterio_non_accusa_le_entita_di_home_assistant():
    assert _tool_references('"Prato nord" valve.irrigazione_prato_nord') == set()
    assert _tool_references("il sensore binary_sensor.porta_ingresso") == set()
    assert _tool_references('usa valve.* se disponibile, altrimenti switch.*') == set()
    assert _tool_references('person.* (state="home" = presente)') == set()


def test_il_criterio_non_accusa_la_prosa_ne_i_valori_fra_virgolette():
    # Parentesi esplicative della prosa: nessun identificatore, nessun allarme.
    assert _tool_references("disponibile (HA 2023.9+)") == set()
    assert _tool_references("irrigazione completa (20-30 min per zona)") == set()
    assert _tool_references("Batteria < 15%: livello critico -- avvisa") == set()
    # Vocabolario HA nudo, dichiarato in HA_VOCABULARY_NOT_TOOLS.
    assert _tool_references("individua dal nome o dal device_class (door, window, motion)") == set()
    # Un valore fra virgolette non e' mai il nome di uno strumento.
    assert _tool_references('il dominio "binary_sensor" e il dominio "input_boolean"') == set()


def test_il_criterio_e_fail_closed_su_un_campo_prompt_nuovo(tmp_path):
    # Un modello che cita uno strumento inesistente nel campo `prompt` -- lo
    # scope che il criterio precedente non guardava affatto -- viene visto.
    finto = tmp_path / "templates.js"
    finto.write_text(
        "var TEMPLATES = [\n"
        "  {\n"
        "    id: 'x',\n"
        "    strategic: 'Usa get_home_status() per la panoramica.',\n"
        "    prompt: 'poi affina con search_entities sui sensori',\n"
        "  },\n"
        "];\n",
        encoding="utf-8",
    )
    testi = _model_texts(finto.read_text(encoding="utf-8"))
    assert dict(testi).keys() == {"strategic", "prompt"}
    riferimenti: set[str] = set()
    for _campo, testo in testi:
        riferimenti |= _tool_references(testo)
    assert riferimenti == {"get_home_status", "search_entities"}
