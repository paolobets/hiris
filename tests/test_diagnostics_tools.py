"""Test dei due tool di diagnosi: cronologia eventi e valutazione template.

Non sono fotografie periodiche come lo snapshot di salute: rispondono a domande
puntuali ("cosa e' successo ieri sera in salotto?", "questa condizione e' vera
adesso?") e sono gli unici tool nuovi che colpiscono Home Assistant a ogni
chiamata. Per questo la validazione degli input deve fermare la richiesta PRIMA
della chiamata, non dopo.
"""
import pytest

from hiris.app.tools.diagnostics_tools import (
    DEFAULT_LOGBOOK_HOURS,
    GET_LOGBOOK_TOOL_DEF,
    MAX_LOGBOOK_ENTRIES,
    MAX_LOGBOOK_HOURS,
    MAX_TEMPLATE_LEN,
    RENDER_TEMPLATE_TOOL_DEF,
    get_logbook,
    render_template,
    validate_logbook_inputs,
    validate_template,
)


class _FakeHA:
    """Client HA finto: registra le chiamate e restituisce risposte preconfezionate."""

    def __init__(self, voci=None, template_result=None):
        self.voci = voci if voci is not None else []
        self.template_result = template_result or {"result": "on"}
        self.chiamate_logbook = []
        self.chiamate_template = []

    async def get_logbook(self, entity_id, hours):
        self.chiamate_logbook.append((entity_id, hours))
        return list(self.voci)

    async def render_template(self, template):
        self.chiamate_template.append(template)
        return dict(self.template_result)


def _voce(entity_id="light.salotto", when="2026-07-31T22:10:00+00:00"):
    return {"when": when, "name": "Salotto", "message": "acceso",
            "entity_id": entity_id}


# --- definizioni dei tool ---------------------------------------------------

def test_le_definizioni_sono_valide_e_dichiarano_i_limiti():
    assert GET_LOGBOOK_TOOL_DEF["name"] == "get_logbook"
    props = GET_LOGBOOK_TOOL_DEF["input_schema"]["properties"]
    assert props["hours"]["maximum"] == MAX_LOGBOOK_HOURS
    assert props["hours"]["minimum"] == 1
    # entity_id e' FACOLTATIVO: la domanda "cosa e' successo ieri sera?" non ha
    # un'entita'.
    assert GET_LOGBOOK_TOOL_DEF["input_schema"].get("required", []) == []

    assert RENDER_TEMPLATE_TOOL_DEF["name"] == "render_template"
    assert RENDER_TEMPLATE_TOOL_DEF["input_schema"]["required"] == ["template"]


def test_la_descrizione_del_logbook_istruisce_sul_troncamento():
    # Il taglio esiste solo se il modello lo riferisce: senza questa istruzione
    # l'LLM conclude "non e' successo altro".
    assert "truncated" in GET_LOGBOOK_TOOL_DEF["description"]


# --- validazione: nessuna chiamata a HA se l'input e' sbagliato -------------

@pytest.mark.asyncio
@pytest.mark.parametrize("ore", [0, -1, MAX_LOGBOOK_HOURS + 1, 10_000])
async def test_ore_fuori_intervallo_non_raggiungono_ha(ore):
    ha = _FakeHA()
    out = await get_logbook(ha, hours=ore)
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ore", ["24", 2.5, True])
async def test_ore_non_intere_non_raggiungono_ha(ore):
    # `True` e' un int per Python ma non e' una finestra temporale: una
    # tool-call dell'LLM puo' portare qualunque tipo.
    ha = _FakeHA()
    out = await get_logbook(ha, hours=ore)
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{}, {"hours": None}])
async def test_ore_assenti_o_nulle_valgono_il_default(kwargs):
    # La normalizzazione vive QUI, non nel dispatcher: il contratto del tool
    # deve valere anche per un chiamante diverso, che altrimenti dovrebbe
    # ricordarsi di replicarla. "Non l'ho specificato" (assente o `null`) e'
    # un'intenzione, non una finestra non valida.
    ha = _FakeHA()
    out = await get_logbook(ha, **kwargs)
    assert "error" not in out
    assert ha.chiamate_logbook == [(None, DEFAULT_LOGBOOK_HOURS)]
    assert out["hours"] == DEFAULT_LOGBOOK_HOURS


@pytest.mark.asyncio
async def test_ore_zero_resta_un_errore_anche_nel_tool():
    # `0` non e' un'omissione: e' un input sbagliato, e tradurlo nel default
    # nasconderebbe l'errore al modello invece di respingerlo.
    ha = _FakeHA()
    out = await get_logbook(ha, hours=0)
    assert "error" in out
    assert ha.chiamate_logbook == []


@pytest.mark.asyncio
@pytest.mark.parametrize("eid", ["salotto", "Light.Salotto", "light.", "../x",
                                 "light.a; drop", 12])
async def test_entity_id_malformato_non_raggiunge_ha(eid):
    ha = _FakeHA()
    out = await get_logbook(ha, entity_id=eid, hours=24)
    assert "error" in out
    assert ha.chiamate_logbook == []


def test_validate_logbook_inputs_accetta_il_caso_buono():
    assert validate_logbook_inputs(None, DEFAULT_LOGBOOK_HOURS) is None
    assert validate_logbook_inputs("light.salotto", MAX_LOGBOOK_HOURS) is None


# --- percorso buono ---------------------------------------------------------

@pytest.mark.asyncio
async def test_passa_gli_argomenti_a_ha_e_restituisce_le_voci():
    ha = _FakeHA(voci=[_voce(), _voce("lock.ingresso")])
    out = await get_logbook(ha, entity_id="light.salotto", hours=12)
    assert ha.chiamate_logbook == [("light.salotto", 12)]
    assert out["count"] == 2
    assert out["hours"] == 12
    assert out["entity_id"] == "light.salotto"
    assert out["entries"][0]["message"] == "acceso"
    assert "truncated" not in out


@pytest.mark.asyncio
async def test_entita_omessa_significa_tutta_la_casa():
    ha = _FakeHA(voci=[_voce()])
    out = await get_logbook(ha)
    assert ha.chiamate_logbook == [(None, DEFAULT_LOGBOOK_HOURS)]
    assert out["entity_id"] is None


# --- cap e dichiarazione del troncamento ------------------------------------

@pytest.mark.asyncio
async def test_lista_al_massimo_significa_voci_scartate_e_va_dichiarato():
    # ha_client tronca a MAX_LOGBOOK_ENTRIES tenendo le PIU' RECENTI: una lista
    # lunga esattamente il massimo dice che le piu' vecchie sono sparite. Il
    # tipo di ritorno di ha_client non puo' dichiararlo, questo tool si'.
    ha = _FakeHA(voci=[_voce() for _ in range(MAX_LOGBOOK_ENTRIES)])
    out = await get_logbook(ha, hours=48)
    assert out["truncated"]["shown"] == MAX_LOGBOOK_ENTRIES
    assert out["truncated"]["oldest_dropped"] is True
    # La finestra effettivamente coperta va detta insieme al taglio, altrimenti
    # "200 voci" non significa nulla.
    assert out["truncated"]["window_hours"] == 48


@pytest.mark.asyncio
async def test_sotto_il_massimo_non_si_dichiara_alcun_taglio():
    ha = _FakeHA(voci=[_voce() for _ in range(MAX_LOGBOOK_ENTRIES - 1)])
    out = await get_logbook(ha, hours=48)
    assert "truncated" not in out


@pytest.mark.asyncio
async def test_troncamento_e_perimetro_sono_dichiarazioni_indipendenti():
    # I due tagli misurano cose diverse e vanno letti separatamente:
    # `truncated.shown` e' quante voci sono state LETTE dalla finestra (il cap
    # di ha_client), `filtered.shown` quante ne sono sopravvissute al perimetro.
    # Calcolare `truncated.shown` dopo il filtro lo farebbe coincidere con
    # l'altro numero: smetterebbe di dire "N delle voci massime lette" e il
    # modello concluderebbe che il taglio della finestra e' meno severo di
    # quanto sia.
    voci = ([_voce("light.salotto") for _ in range(10)]
            + [_voce("lock.ingresso") for _ in range(MAX_LOGBOOK_ENTRIES - 10)])
    ha = _FakeHA(voci=voci)
    out = await get_logbook(ha, hours=48, allowed_entities=["light.*"])
    assert out["truncated"] == {"shown": MAX_LOGBOOK_ENTRIES,
                                "window_hours": 48, "oldest_dropped": True}
    assert out["filtered"] == {"shown": 10, "total": MAX_LOGBOOK_ENTRIES}
    assert out["count"] == 10


# --- perimetro delle entita' ------------------------------------------------

@pytest.mark.asyncio
async def test_il_perimetro_filtra_le_voci_e_lo_dichiara():
    # Senza filtro sulle voci, un agente ristretto a light.* che chiede il
    # logbook dell'intera casa leggerebbe serrature, allarme e presenze: il
    # perimetro sarebbe aggirabile omettendo entity_id.
    ha = _FakeHA(voci=[_voce("light.salotto"), _voce("lock.ingresso"),
                       _voce("light.cucina")])
    out = await get_logbook(ha, allowed_entities=["light.*"])
    ids = [v["entity_id"] for v in out["entries"]]
    assert ids == ["light.salotto", "light.cucina"]
    assert out["count"] == 2
    assert out["filtered"] == {"shown": 2, "total": 3}


@pytest.mark.asyncio
async def test_voce_senza_entita_scartata_sotto_perimetro_attivo():
    # Avvio di HA, script, eventi di sistema: non attribuibili a un'entita',
    # quindi non verificabili contro il perimetro -> fail-closed.
    ha = _FakeHA(voci=[_voce("light.salotto"), _voce(None)])
    out = await get_logbook(ha, allowed_entities=["light.*"])
    assert [v["entity_id"] for v in out["entries"]] == ["light.salotto"]


@pytest.mark.asyncio
async def test_perimetro_vuoto_nega_tutto():
    # `[]` e' una decisione ("niente concesso"), non un'omissione: stessa
    # semantica di tutto il dispatcher.
    ha = _FakeHA(voci=[_voce("light.salotto")])
    out = await get_logbook(ha, allowed_entities=[])
    assert out["entries"] == []


@pytest.mark.asyncio
async def test_senza_perimetro_nessun_filtro_e_nessuna_dichiarazione():
    ha = _FakeHA(voci=[_voce("light.salotto"), _voce("lock.ingresso")])
    out = await get_logbook(ha, allowed_entities=None)
    assert out["count"] == 2
    assert "filtered" not in out


# --- dipendenza assente -----------------------------------------------------

@pytest.mark.asyncio
async def test_logbook_senza_client_ha_degrada_con_errore():
    out = await get_logbook(None, hours=24)
    assert "error" in out


@pytest.mark.asyncio
async def test_template_senza_client_ha_degrada_con_errore():
    out = await render_template(None, "{{ 1 }}")
    assert "error" in out


# --- render_template --------------------------------------------------------

@pytest.mark.asyncio
async def test_template_troppo_lungo_non_raggiunge_ha():
    ha = _FakeHA()
    out = await render_template(ha, "x" * (MAX_TEMPLATE_LEN + 1))
    assert "error" in out
    assert str(MAX_TEMPLATE_LEN) in out["error"]
    assert ha.chiamate_template == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tpl", ["", "   ", None, 42])
async def test_template_vuoto_o_non_stringa_non_raggiunge_ha(tpl):
    ha = _FakeHA()
    out = await render_template(ha, tpl)
    assert "error" in out
    assert ha.chiamate_template == []


def test_validate_template_accetta_il_caso_buono():
    assert validate_template("{{ states('light.salotto') }}") is None


@pytest.mark.asyncio
async def test_template_valido_passa_e_restituisce_il_risultato():
    ha = _FakeHA(template_result={"result": "on"})
    out = await render_template(ha, "{{ states('light.salotto') }}")
    assert ha.chiamate_template == ["{{ states('light.salotto') }}"]
    assert out == {"result": "on"}


@pytest.mark.asyncio
async def test_errore_di_ha_inoltrato_al_modello():
    # Il messaggio d'errore di HA serve al modello per correggere il template:
    # ha_client lo tronca gia', qui si inoltra senza reinterpretarlo.
    ha = _FakeHA(template_result={"error": "UndefinedError: 'states' is undefined"})
    out = await render_template(ha, "{{ nope }}")
    assert out["error"].startswith("UndefinedError")


# --- registrazione: dove i due tool sono raggiungibili, e dove no ------------
# Entrambi vivono in chat (ALL_TOOL_DEFS + catalogo della UI); il solo logbook
# e' concesso anche agli agenti locali (EVALUATION_ONLY_TOOLS) e al gateway MCP,
# dove la denylist di lettura pota la sua risposta; render_template resta fuori
# dal gateway. Il catalogo della UI (static/config/templates.js) e' JS e vive in
# tests/js/tool-catalog.test.mjs.

def test_registrati_nel_runner_con_il_gating_giusto():
    from hiris.app.claude_runner import ALL_TOOL_DEFS, EVALUATION_ONLY_TOOLS
    nomi = {t["name"] for t in ALL_TOOL_DEFS}
    assert "get_logbook" in nomi
    assert "render_template" in nomi
    # Decisione di sicurezza: il logbook e' una lettura utile a un sorvegliante;
    # un template puo' leggere QUALUNQUE stato ed e' il vettore di prompt
    # injection perfetto per un agente reattivo che gira sullo stato di HA.
    assert "get_logbook" in EVALUATION_ONLY_TOOLS
    assert "render_template" not in EVALUATION_ONLY_TOOLS


def test_solo_il_logbook_fra_i_read_tools_del_gateway():
    # Stessa ragione: derive_execute_policy concede SEMPRE i READ_TOOLS, senza
    # opt-in per singolo tool, e le letture partono con allowed_entities=None.
    from hiris.app.api.handlers_gateway_policy import READ_TOOLS
    assert "get_logbook" in READ_TOOLS
    assert "render_template" not in READ_TOOLS


# La potatura della risposta del logbook (api/read_denylist.py) e' uscita con
# la Fetta E2 Task 4 insieme a tutta la superficie /api/execute che la
# consumava: il suo soggetto (prune_read_result) non esiste piu' in nessun
# file, quindi il test che lo pinnava qui e' stato rimosso, non spostato.
