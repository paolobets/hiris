"""I nomi delle persone non arrivano a un attore nemmeno dagli strumenti
(decisione 12 estesa, «Segnaposto», scelta dal proprietario il 06/10/2026;
attori, Task 3.6, Passo 4).

**La misura che l'ha chiesta** (Task 3.0, Passo 4, dallo sprint, solo conti):
`search` portava un nome di persona in 4 risposte su 35, quasi sempre DENTRO
il nome di un'entita' -- la batteria del telefono, accanto al tracker dello
stesso dispositivo. La decisione 12 copriva le sole righe dell'osservatore.

**La regola**: per un attore, le entita' di una persona -- le presenze
(`privacy.MOVING_DOMAINS`) e tutte le entita' del dispositivo che porta una
presenza, chiesto al registro di Home Assistant col `device_id` -- arrivano
col segnaposto, e il loro nome e quello del dispositivo con lui. Il filtro
vive in `home_space/privacy.py` (`PresenceMask`), e lo usa il guardiano
dell'attore: la chat resta com'e'.
"""
from __future__ import annotations

import json

import pytest

from hiris.app.home_space.house import House
from hiris.app.home_space.privacy import PresenceMask, person_bound
from hiris.app.home_space.topology import Mirror
from hiris.app.mind import analyst_turn as at

_NAMES = ("paolo", "giulia")


def _row(entity_id, name, **extra):
    row = {"id": entity_id, "nome": name, "classe": None, "unita": None,
           "translation_key": None, "categoria": None, "disabilitata": 0,
           "nascosta": 0, "area_id": None, "piattaforma": "x"}
    row.update(extra)
    return row


def _house():
    rows = [
        _row("climate.camera_t", "Termostato Camera"),
        _row("person.paolo", "Paolo"),
        _row("person.giulia", "Giulia"),
        _row("device_tracker.iphone_di_paolo", "iPhone di Paolo",
             dispositivo_id="d1", piattaforma="mobile_app"),
        _row("sensor.iphone_di_paolo_batteria", "iPhone di Paolo Batteria",
             dispositivo_id="d1", piattaforma="mobile_app"),
        _row("sensor.inverter_potenza", "Inverter Potenza", dispositivo_id="d2"),
        _row("device_tracker.pixel", "Posizione", dispositivo_id="d3"),
    ]
    devices = [{"id": "d1", "nome": "iPhone di Paolo"},
               {"id": "d2", "nome": "Inverter"},
               {"id": "d3", "nome": "Pixel di Giulia"}]
    return House({"entita": rows, "dispositivi": devices, "aree": []},
                 Mirror(state={row["id"]: "on" for row in rows}))


def _without_names(value) -> None:
    text = json.dumps(value, ensure_ascii=False).lower()
    for name in _NAMES:
        assert name not in text, f"il nome «{name}» arriva al modello: {text}"


def test_le_entita_di_una_persona_sono_le_presenze_e_il_loro_DISPOSITIVO():
    """Il legame e' il `device_id` del registro, non il nome: l'inverter, che
    non porta presenze, resta fuori.

    Mutazione ESEGUITA (06/10/2026): `person_bound` senza le sorelle del
    dispositivo -- rossa (qui, e il nome della batteria arriva al modello
    nella prova dopo)."""
    ids, devices = person_bound(_house())
    assert ids == ["device_tracker.iphone_di_paolo", "device_tracker.pixel",
                   "person.giulia", "person.paolo", "sensor.iphone_di_paolo_batteria"]
    assert devices == ["d1", "d3"]


def test_una_risposta_di_SEARCH_esce_senza_nomi():
    """La forma che la misura ha trovato: il nome dentro il nome di
    un'entita' e del suo dispositivo. Il resto della casa resta com'e'."""
    risposta = {"trovate": [
        {"id": "sensor.iphone_di_paolo_batteria", "nome": "iPhone di Paolo Batteria",
         "dispositivo": "iPhone di Paolo", "stato": "80"},
        {"id": "climate.camera_t", "nome": "Termostato Camera"},
        {"id": "sensor.inverter_potenza", "nome": "Inverter Potenza",
         "dispositivo": "Inverter"},
        {"id": "device_tracker.pixel", "nome": "Posizione",
         "dispositivo": "Pixel di Giulia"}],
        "nota": "Paolo e Giulia sono a casa"}
    coperta = PresenceMask(_house()).mask(risposta)
    _without_names(coperta)
    righe = coperta["trovate"]
    # Il dispositivo si chiama come il suo tracker («iPhone di Paolo»): lo
    # stesso testo prende il segnaposto che ha gia', quello dell'entita'.
    assert righe[0] == {"id": "sensor.#1", "nome": "sensor.#1",
                        "dispositivo": "device_tracker.#1", "stato": "80"}
    assert righe[1:3] == risposta["trovate"][1:3]
    assert righe[3] == {"id": "device_tracker.#2", "nome": "device_tracker.#2",
                        "dispositivo": "dispositivo.#2"}


def test_le_CHIAVI_si_coprono_come_i_valori():
    """Una serie per entita' arriva come dizionario per id (`history`)."""
    coperta = PresenceMask(_house()).mask(
        {"serie": {"device_tracker.iphone_di_paolo": [], "climate.camera_t": []}})
    assert set(coperta["serie"]) == {"device_tracker.#1", "climate.camera_t"}


def test_un_nome_si_copre_solo_INTERO():
    """«Paolo» dentro un'altra parola non e' il nome di nessuno."""
    coperta = PresenceMask(_house()).mask("Paolone e Paolo")
    assert coperta == "Paolone e person.#2"


def test_un_nome_si_copre_in_QUALUNQUE_maiuscolo():
    """G26-1 (giro 26 della revisione, 06/10/2026): il nome dichiarato da Home
    Assistant e' «Paolo», una risposta lo puo' portare «paolo» o «PAOLO».

    Mutazione ESEGUITA (06/10/2026): `_alternation` senza `re.IGNORECASE` --
    rossa («PAOLO» passa intatto)."""
    mask = PresenceMask(_house())
    assert mask.mask("quando paolo esce") == "quando person.#2 esce"
    assert mask.mask("PAOLO") == "person.#2"
    assert mask.mask("IPHONE DI PAOLO BATTERIA") == "sensor.#1"


def _people(*names):
    rows = [_row(f"person.p{i}", name) for i, name in enumerate(names, start=1)]
    return House({"entita": rows, "dispositivi": [], "aree": []},
                 Mirror(state={row["id"]: "home" for row in rows}))


def test_un_nome_che_CASEFOLD_cambia_di_forma_si_copre_anche_scritto_esatto():
    """G27-1 (giro 27 della revisione, 06/10/2026): `"Strauß".casefold()` e'
    «strauss», che `re.IGNORECASE` non fa corrispondere a «Strauß». Su
    3aee25b5 il nome scritto proprio come lo dichiara Home Assistant passava
    -- rossa (eseguita): «Strauß è a casa» intatto."""
    mask = PresenceMask(_people("Strauß", "İlker"))
    assert mask.mask("Strauß è a casa") == "person.#1 è a casa"
    assert mask.mask("STRAUSS") == "person.#1"
    assert mask.mask("strauss") == "person.#1"
    assert mask.mask("İlker esce") == "person.#2 esce"


def test_una_I_turca_non_fa_SOLLEVARE_il_filtro():
    """G27-2: `re.IGNORECASE` fa corrispondere «I» a «ı», `casefold` no. Su
    3aee25b5 la ricerca nel dizionario sollevava -- rossa (eseguita):
    `KeyError: 'işil'`."""
    mask = PresenceMask(_people("Işıl"))
    assert mask.mask("IŞIL") == "person.#1"
    assert mask.mask("Işıl") == "person.#1"
    assert mask.mask("ışıl") == "person.#1"


def test_il_segnaposto_torna_id_negli_argomenti():
    mask = PresenceMask(_house())
    assert mask.unmask({"riferimento": "sensor.#1", "altro": "sensor.#10"}) == {
        "riferimento": "sensor.iphone_di_paolo_batteria", "altro": "sensor.#10"}


class _Sotto:
    def __init__(self):
        self.argomenti: list = []

    async def dispatch(self, name, arguments):
        self.argomenti.append(arguments)
        return {"trovate": [{"id": "device_tracker.iphone_di_paolo",
                             "nome": "iPhone di Paolo"}]}


@pytest.mark.asyncio
async def test_il_GUARDIANO_dell_attore_copre_le_risposte_e_scopre_le_domande():
    """Mutazione ESEGUITA (06/10/2026): il guardiano che non passa da
    `PresenceMask` -- rossa (il nome arriva, e il lettore riceve il
    segnaposto invece dell'id)."""
    sotto = _Sotto()
    house = _house()
    guardiano = at.AnalystDispatcher(sotto, ha=None, house=house, timezone=None,
                                     presence=PresenceMask(house))
    esito = await guardiano.dispatch("history", {"riferimento": "device_tracker.#1"})
    _without_names(esito)
    assert sotto.argomenti == [{"riferimento": "device_tracker.iphone_di_paolo"}]


@pytest.mark.asyncio
async def test_il_guardiano_costruito_per_il_turno_ha_il_filtro(monkeypatch):
    """`analyst_turn.guard`, quello che catena e ponte chiedono alla
    dichiarazione del mestiere: il filtro c'e' sulla casa del turno."""
    house = _house()
    monkeypatch.setattr(House, "read", classmethod(lambda cls, *a, **k: house))

    class _Anagrafe:
        def reference_frame(self):
            return {}

    guardiano = await at.guard({"home_space_store": _Anagrafe()})
    assert guardiano.presence is not None
    assert guardiano.presence.handles["person.paolo"] == "person.#2"


def test_un_RIMETTI_col_segnaposto_si_archivia_con_l_id_vero():
    """Il modello ha letto `sensor.#1` negli strumenti, e lo chiede indietro
    con quel nome."""
    serie = {"giorni": ["2026-09-12"], "obiettivi": [], "serie": []}
    risposta = json.dumps({"osservazioni": [], "rimetti": [
        {"id": "sensor.#1", "perche": "la batteria spiega il calo"}]})
    esito = at.apply_analysis(serie, risposta, presence=PresenceMask(_house()))
    assert esito["analisi"]["rimetti"] == [
        {"id": "sensor.iphone_di_paolo_batteria", "perche": "la batteria spiega il calo"}]


def test_sul_PONTE_il_rimetti_col_segnaposto_torna_id(tmp_path, monkeypatch):
    """Il raccoglitore rifa' il filtro sulla casa di adesso, come l'osservatore
    (decisione 12): la stessa numerazione, senza archiviare una tabella.

    Mutazione ESEGUITA (06/10/2026): il raccoglitore senza filtro -- rossa
    (il segnaposto non e' un entity_id, e l'analisi si rifiuta)."""
    from hiris.app import server
    from hiris.app.home_space import historian
    from hiris.app.mind.store import ObservationsStore

    house = _house()
    monkeypatch.setattr(House, "read", classmethod(lambda cls, *a, **k: house))

    class _Anagrafe:
        def reference_frame(self):
            return {}

    oggi = historian.today(None).isoformat()

    class _Coda:
        def latest(self, kind):
            return {"status": "decided", "wake": {"giorno": oggi},
                    "decision": {"reply": json.dumps({"osservazioni": [], "rimetti": [
                        {"id": "sensor.#1", "perche": "la batteria spiega il calo"}]})}}

    store = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        app = {"observations": store, "reasoning_queue": _Coda(),
               "home_space_store": _Anagrafe()}
        raccolto = server._collect_analyst_turn(app, store, oggi)
        assert raccolto["analisi"]["rimetti"] == [
            {"id": "sensor.iphone_di_paolo_batteria",
             "perche": "la batteria spiega il calo"}]
    finally:
        store.close()
