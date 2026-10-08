"""Lo scope e le ricette DAVANTI ALLA FONTE (piano degli attori, strato 1,
Task 1.5; G-01, G-02, G-03 per la parte che legge; D1 «si ripartiscono»).

Fino al 05/10/2026 gli attori non chiedevano a nessuno se le cose che
guardano e misurano parlano ancora:

- la pagina dell'osservatore rendeva un soggetto spento dal proprietario o
  sparito da Home Assistant come uno vivo (G-01: sulla casa, 26 soggetti
  guardati su 95 senza stato, nessuno marcato -- registro, voce G-01);
- la domanda di riconsiderazione non lo diceva al modello, e un soggetto deciso
  «dentro» che la casa non mostra piu' (spento) non tornava mai davanti a lui:
  restava dentro per sempre;
- una ricetta di un dispositivo con tutte le entita' spente girava ogni giorno
  e scriveva un rifiuto PER PASSO, sempre lo stesso (G-02, G-03).

Lo stato della fonte si chiede a `House.source(id)` (Tappa 3, Task 8): qui non
si legge `disabled_by` ne' lo specchio. Qui nessuna riga si cancella dagli
archivi: dalla Tappa 8 (D1) le righe di chi non ha piu' un referente le toglie
la riconciliazione (`tests/test_riconciliazione.py`).

La casa e' quella di `tests/test_fonte_della_casa.py` (righe nella forma di
Home Assistant, passate dal lettore vero): ogni stato della fonte c'e' una
volta.

Mutazioni ESEGUITE (05/10/2026), ognuna ripristinata (file confrontati con
la copia di prima, `git status` invariato), tutte rosse per la ragione giusta:
- `watching` non chiede piu' la fonte (il passo 3 del piano) -- rosse le tre
  prove della marca, rotta compresa;
- la riga della domanda non porta piu' «fonte: ...» -- rossa la riga che tace;
- `apply_answer` non accetta i soggetti che tacciono -- rossa «il modello puo'
  togliere» (`decise` 0);
- i taciuti in ogni lotto, non solo in quello che apre -- rossa la prova
  dell'apertura;
- `muted_recipes` sempre vuota -- rosse le tre prove del dispositivo muto;
- `non_disponibile` (e a parte `integrazione_ferma`) ammessi fra gli stati muti
  -- rosse le prove delle fonti che tacciono per un giorno [la prima stesura,
  con le tre entita' in una ricetta sola, era INERTE: una sola ammessa per
  sbaglio restava nascosta dalle altre; ora una ricetta per entita'];
- una parola che la fonte non dice aggiunta agli stati muti -- rossa la
  derivazione dal sorgente di `House.source`;
- lo specchio non letto trattato come «sparita» -- rossa la prova cieca;
- gli ingredienti che non tolgono i muti -- rossa (serie chieste anche per
  loro);
- la rotta che apre la casa su un'anagrafe mai letta -- rossa
  («anagrafe mai letta»);
- il resoconto che fa girare il muto passo per passo -- rossa la riga unica.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from hiris.app import server
from hiris.app.api.handlers_mind import handle_watching
from hiris.app.home_space.house import SOURCE_STATES, House
from hiris.app.mind import observer
from hiris.app.mind.recipes import MUTED_SOURCE_STATES, muted_recipes
from hiris.app.mind.report import build_report
from hiris.app.mind.store import ObservationsStore
from hiris.app.mind.watcher import Watcher
from tests._casa_sintetica import synthetic_inputs
from tests.test_fonte_della_casa import DEVICES, ENTITIES, ENTRIES, _house, _Store

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

OBSERVER = "observer"


@pytest.fixture
def store(tmp_path):
    archive = ObservationsStore(str(tmp_path / "osservazioni.db"))
    for subject in ("light.viva", "light.sparita", "light.del_proprietario",
                    "light.inventata"):
        assert archive.decide_scope(subject, inside=True, reason="pesa",
                                    author=OBSERVER, when_ts=1_790_000_000.0)
    assert archive.decide_scope("sensor.mai_attivata", inside=False,
                                reason="non pesa", author=OBSERVER,
                                when_ts=1_790_000_000.0)
    return archive


# -- 1. la pagina: `watching()` chiede la fonte per id ------------------------


def test_watching_rende_ogni_soggetto_con_la_sua_fonte(store):
    """Un soggetto sparito e uno spento dal proprietario escono con lo stato
    della fonte e la causa, nella forma di `House.source` (la stessa della
    scheda di un'entita', `queries._view_entity`: fondamenta 3)."""
    house = _house()
    rows = {row["soggetto"]: row for row in Watcher(store).watching(house=house)}
    assert rows["light.sparita"]["fonte"] == house.source("light.sparita")
    assert rows["light.sparita"]["fonte"]["stato"] == "sparita"
    assert rows["light.del_proprietario"]["fonte"]["stato"] == "spenta_dal_proprietario"
    assert rows["light.del_proprietario"]["fonte"]["causa"] == "user"
    assert rows["light.viva"]["fonte"]["stato"] == "viva"


def test_un_soggetto_che_ne_il_registro_ne_gli_stati_conoscono_e_marcato_lo_stesso(store):
    """`fonte: None` e' il contratto di `House.source` per un id che nessuno
    conosce: la chiave c'e' (il soggetto e' marcato), il valore dice «non
    c'e'». Non e' «non l'ho chiesto»: quello e' la chiave assente."""
    rows = {row["soggetto"]: row for row in Watcher(store).watching(house=_house())}
    assert "fonte" in rows["light.inventata"]
    assert rows["light.inventata"]["fonte"] is None


def test_senza_la_casa_watching_non_afferma_niente_sulla_fonte(store):
    rows = Watcher(store).watching()
    assert rows and all("fonte" not in row for row in rows)


def test_le_condizioni_di_sistema_non_hanno_una_fonte_da_chiedere(store):
    watcher = Watcher(store)
    watcher._conditions = {"problema:qualcosa"}
    rows = {row["soggetto"]: row for row in watcher.watching(house=_house())}
    assert "fonte" not in rows["problema:qualcosa"]


class _HomeSpaceStore(_Store):
    """L'anagrafe dal lato della pagina: anche il fuso (il volume del grezzo
    lo chiede, `historian.house_timezone`)."""

    def reference_frame(self):
        return {}


def _registries(extra_devices=()):
    from hiris.app.home_space.reader import build_home_space
    return build_home_space({"entita": ENTITIES, "integrazioni": ENTRIES,
                             "dispositivi": DEVICES + list(extra_devices)})


def _mirror_cache():
    from hiris.app.proxy.entity_cache import _to_minimal
    from tests.test_fonte_della_casa import STATES
    return _Cache([_to_minimal(row) for row in STATES])


class _Cache:
    """Lo specchio dal lato della rotta: `topology.read_mirror` chiede
    `all_states` (una cache senza `loaded` vale pronta,
    `entity_cache.inventory_is_readable`)."""

    def __init__(self, rows):
        self._rows = rows

    def all_states(self):
        return list(self._rows)


@pytest.mark.asyncio
async def test_la_rotta_della_pagina_porta_la_fonte(store):
    """`GET /api/mind/watching` apre la casa del momento (`House.read`) e la
    passa a `watching`: la pagina e la batteria leggono la marca da li'."""
    app = {"watcher": Watcher(store), "observations": store,
           "home_space_store": _HomeSpaceStore(_registries()),
           "entity_cache": _mirror_cache()}

    class _Request:
        def __init__(self):
            self.app = app
            self.query = {}

    import json
    body = json.loads((await handle_watching(_Request())).body)
    rows = {row["soggetto"]: row for row in body["watching"]}
    assert rows["light.sparita"]["fonte"]["stato"] == "sparita"
    assert rows["light.viva"]["fonte"]["stato"] == "viva"


@pytest.mark.asyncio
async def test_anche_cio_che_e_fuori_porta_la_fonte_nella_stessa_forma(store):
    """La stessa riga dello scope, dall'altra meta' (trovato della Tappa 8,
    Task 1): fino all'08/10/2026 `fuori` (`MindView._left_out`) non portava la
    `fonte` che `watching` porta. Una forma sola, `watcher.scope_row`.

    Mutazione ESEGUITA: `_left_out` che torna a comporre la riga senza la
    casa -- rossa (`fonte` assente)."""
    app = {"watcher": Watcher(store), "observations": store,
           "home_space_store": _HomeSpaceStore(_registries()),
           "entity_cache": _mirror_cache()}

    class _Request:
        def __init__(self):
            self.app = app
            self.query = {}

    import json
    body = json.loads((await handle_watching(_Request())).body)
    (left,) = [row for row in body["fuori"] if row["soggetto"] == "sensor.mai_attivata"]
    assert left["fonte"]["stato"] == "spenta_da_home_assistant"
    assert set(left) == set(body["watching"][0]) | {"fonte"}


@pytest.mark.parametrize("home_space_store", [None, _HomeSpaceStore({})],
                         ids=["senza archivio", "anagrafe mai letta"])
@pytest.mark.asyncio
async def test_senza_anagrafe_la_rotta_non_inventa_fonti(store, home_space_store):
    app = {"watcher": Watcher(store), "observations": store,
           "home_space_store": home_space_store, "entity_cache": _mirror_cache()}

    class _Request:
        def __init__(self):
            self.app = app
            self.query = {}

    import json
    body = json.loads((await handle_watching(_Request())).body)
    assert body["watching"] and all("fonte" not in row for row in body["watching"])


# -- 2. la domanda di riconsiderazione porta lo stato --------------------------


def test_la_riga_di_un_entita_che_tace_dice_perche():
    """Una sparita e' ancora nell'anagrafe -- e quindi fra quelle che
    l'osservatore giudica -- ma tace: il modello lo legge sulla sua riga."""
    lines = {line.split(" · ", 1)[0]: line for line in observer.house_lines(_house())}
    assert "fonte: sparita" in lines["light.sparita"]
    assert "fonte: non_disponibile" in lines["light.irraggiungibile"]
    assert "fonte" not in lines["light.viva"], "una fonte viva non costa una parola"


def test_i_soggetti_dentro_che_la_casa_non_mostra_piu_tornano_davanti_al_modello(store):
    """Uno spento dal proprietario non e' fra le entita' che l'osservatore
    giudica (la regola del fuori lo toglie), quindi fino a ieri restava dentro
    per sempre. Ora la domanda che apre la campagna lo porta, con la fonte."""
    gone = observer.gone_lines(store, _house())
    assert {line.split(" · ", 1)[0] for line in gone} == {
        "light.del_proprietario", "light.inventata"}
    assert any("spenta_dal_proprietario" in line for line in gone)
    question = observer.build_question("obiettivo", ["light.viva"], gone)
    assert "light.del_proprietario" in question


def test_una_fonte_viva_fuori_dalla_regola_del_fuori_non_torna(store):
    """Il proprietario puo' mettere dentro una nascosta o una di servizio
    (decisione del 10/09/2026): non tace, e non si ridomanda."""
    store.decide_scope("light.viva", inside=True, reason="io", author="proprietario",
                       when_ts=1_790_000_001.0)
    house = _house()
    with mock.patch.object(House, "visible_entities", lambda self: []):
        gone = observer.gone_lines(store, house)
    assert "light.viva" not in {line.split(" · ", 1)[0] for line in gone}


def test_il_modello_puo_togliere_un_soggetto_che_tace(store):
    """La risposta su un soggetto della lista dei taciuti si accetta (si puo'
    togliere alla prossima cadenza); chi non risponde su di lui lo lascia
    com'e': il codice non decide niente al posto del modello (D1)."""
    house = _house()
    answer = ('[{"id": "light.del_proprietario", "dentro": false, '
              '"motivo": "spenta dal proprietario, non parla piu\'"}]')
    outcome = observer.apply_answer(store, house, answer, asked={"light.viva"},
                                    record=False)
    assert outcome["decise"] == 1
    scope = store.scope()
    assert scope["light.del_proprietario"]["dentro"] is False
    assert scope["light.inventata"]["dentro"] is True, "omesso non vuol dire tolto"


def test_solo_la_domanda_che_apre_la_campagna_porta_i_taciuti(store):
    house = _house()
    opening = observer.bridge_turn(store, house, None)["history"][0]["content"]
    later = observer.bridge_turn(store, house, None, opening=False)["history"][0]["content"]
    assert "light.del_proprietario" in opening
    assert "light.del_proprietario" not in later


# -- 3. il resoconto: una riga per il dispositivo che tace ---------------------


#: Un dispositivo con la ricetta e TUTTE le entita' spente o sparite.
SPENTA = {"why": "prova", "steps": [
    {"name": f"m{i}", "operation": "somma_periodo", "inputs": [f"@{eid}"],
     "params": {"unit": "h"}}
    for i, eid in enumerate(("light.del_proprietario", "sensor.mai_attivata",
                             "light.sparita"))]}
#: Uno con un'entita' viva in mezzo: gira, e ogni passo dice il suo.
MISTA = {"why": "prova", "steps": [
    {"name": f"m{i}", "operation": "somma_periodo", "inputs": [f"@{eid}"],
     "params": {"unit": "h"}}
    for i, eid in enumerate(("light.del_proprietario", "light.viva"))]}


def test_una_ricetta_che_non_puo_produrre_si_riconosce_dalla_fonte():
    muted = muted_recipes(_house(), {"d_spenta": SPENTA, "d_mista": MISTA})
    assert set(muted) == {"d_spenta"}
    # La causa e' quella della prima entita' nominata (in ordine), come il
    # rifiuto di un passo: dal vocabolario del Task 8, non una parola nuova.
    assert muted["d_spenta"]["causa"] == "spenta_dal_proprietario"
    assert "spenta dal proprietario" in muted["d_spenta"]["non_calcolabile"]
    assert "light.sparita" in muted["d_spenta"]["non_calcolabile"]


@pytest.mark.parametrize("entity_id", ["light.irraggiungibile", "light.ricreata",
                                       "sensor.senza_valore",
                                       "light.di_istanza_che_ritenta"])
def test_le_fonti_che_tacciono_per_un_giorno_non_spengono_la_ricetta(entity_id):
    """`non_disponibile`, `senza_valore`, `integrazione_ferma` possono tornare
    domani: la ricetta gira e i passi dicono il loro rifiuto. Una per ricetta,
    o una sola ammessa per sbaglio passerebbe nascosta dalle altre."""
    temporanea = {"why": "prova", "steps": [
        {"name": "m", "operation": "somma_periodo", "inputs": [f"@{entity_id}"],
         "params": {"unit": "h"}}]}
    assert muted_recipes(_house(), {"d": temporanea}) == {}


def test_con_lo_specchio_non_letto_una_ricetta_non_si_dichiara_muta_per_sparizione():
    assert muted_recipes(_house(readable=False), {"d": {"why": "p", "steps": [
        {"name": "m", "operation": "somma_periodo", "inputs": ["@light.sparita"],
         "params": {"unit": "h"}}]}}) == {}


def test_gli_stati_muti_sono_parole_della_fonte():
    """La lista di ammissione si confronta con il vocabolario della fonte,
    `house.SOURCE_STATES` (I-0: si chiede l'elenco a chi lo tiene, non al
    testo di `House.source`, che dal Task 1.4 degli attori nomina gli stati
    per costante e non piu' per letterale): una parola che la fonte non dice
    piu' sarebbe una regola morta."""
    assert len(SOURCE_STATES) == 7, f"derivazione svuotata: {SOURCE_STATES}"
    assert set(MUTED_SOURCE_STATES) <= set(SOURCE_STATES)


def test_gli_stati_muti_sono_cause_della_misura():
    """La riga di una ricetta muta porta `causa`: dev'essere una parola che
    `NotComputable` accetta (`operations.CAUSES`, Task 1.2), la stessa del
    rifiuto di un passo. Le due fette si sono unite il 05/10/2026."""
    from hiris.app.mind.operations import CAUSES
    assert set(MUTED_SOURCE_STATES) <= CAUSES


def test_il_resoconto_porta_una_riga_per_il_dispositivo_muto():
    muted = muted_recipes(_house(), {"d_spenta": SPENTA})
    report = build_report(day="2026-10-04", episodes=[], series={}, recipes={},
                          names={"d_spenta": "Lampade spente"}, muted=muted)
    assert report["misure"] == [{
        "soggetto": "d_spenta", "nome": "Lampade spente", "misura": "(la ricetta)",
        "non_calcolabile": muted["d_spenta"]["non_calcolabile"],
        "causa": "spenta_dal_proprietario"}]


async def _ingredients(recipes):
    app = {"knowledge": object(),
           "home_space_store": _Store(_registries({"id": d, "name": d} for d in recipes)),
           "entity_cache": _mirror_cache()}
    asked: list[list[str]] = []

    async def _stat_ids(_app, _ha, **_kw):
        return set()

    house = CasaFinta(synthetic_inputs(), answers={
        "recorder/statistics_during_period":
            lambda extra: asked.append(sorted(extra["statistic_ids"])) or {}})
    with mock.patch.object(server.recipe_turn, "recipes", lambda _k: recipes), \
            mock.patch.object(server, "statistic_ids_for_round", _stat_ids):
        result = await server._report_ingredients(app, house, giorno="2026-10-03",
                                                  timezone="Europe/Rome")
    return result, asked


@pytest.mark.asyncio
async def test_gli_ingredienti_non_chiedono_le_serie_di_un_dispositivo_muto():
    (ricette, _serie, _nomi, _silent, muted), asked = await _ingredients(
        {"d_spenta": SPENTA, "d_mista": MISTA})
    assert set(ricette) == {"d_mista"}
    assert set(muted) == {"d_spenta"}
    assert asked == [["light.del_proprietario", "light.viva"]]
