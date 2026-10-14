"""L'avviso per una proposta `alto` (piano degli attori, strato 4, Task 4.3;
D14, approvata dal proprietario il 06/10/2026).

Una proposta del proponente che agisce su una serratura o sull'allarme esce
`alto` qualunque livello scriva il modello (D13, la regola e' in
`action/construction/stakes.py`), e **avvisa gli amministratori**: una push sui
loro telefoni, dal recapito delle promesse e dalla porta dei servizi. Una
`medio` va fra le Proposte e basta.

Le prove del livello dentro l'officina vere stanno in
`tests/test_livello_proposte.py`; il cancello che ammette l'avviso, e solo lui,
in `tests/test_mind_actuator_guards.py`.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from hiris.app.action.actuator import ACTUATOR_KEY
from hiris.app.action.construction.revisions import CONSTRUCTIONS_KEY
from hiris.app.action.construction.workshop import WORKSHOP_KEY
from hiris.app.action.registry import SERVICE_REGISTRY_KEY
from hiris.app.llm_router import LLM_ROUTER_KEY
from hiris.app.mind.store import OBSERVATIONS_KEY
from hiris.app.proxy.ha_client import HA_CLIENT_KEY
from hiris.app.steering import BRIDGE_ACTIVE_KEY
from hiris.app.usage.store import USAGE_KEY

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.stakes import domains_acted_on, impose
from hiris.app.action.registry import ServiceRegistry
from hiris.app.api import soffitto
from hiris.app.chat_thread import new_subject
from hiris.app.keeper import delivery
from hiris.app.keeper.promise import DELIVERY_TITLE
from hiris.app.live_value import LiveValue
from hiris.app.mind import proposer_round as pr
from hiris.app.mind.store import ObservationsStore
from hiris.app.startup import live_values
from hiris.app.usage.store import UsageStore
from tests._casa_sintetica import synthetic_inputs
from tests._oggi_fermo import ferma_oggi
from tests._runner_finto import RunnerFinto

#: Il giorno dell'analisi: lo scrive `_today_frozen` a ogni prova, dallo
#: stesso istante che legge il giro (`tests/_oggi_fermo.py`).
OGGI = ""


@pytest.fixture(autouse=True)
def _today_frozen(monkeypatch):
    ferma_oggi(monkeypatch, __name__)

_SERRATURA = {"gesto": "crea", "dominio": "automation", "alias": "Chiudi la porta di notte",
              "livello": "lieve", "innesco": [],
              "azioni": [{"action": "lock.lock",
                          "target": {"entity_id": "lock.porta_ingresso"}}]}
_LUCE = {"gesto": "crea", "dominio": "automation", "alias": "Luce del portico",
         "livello": "medio", "innesco": [],
         "azioni": [{"action": "light.turn_on",
                     "target": {"entity_id": "light.portico"}}]}


class _Officina:
    """L'officina dal lato del turno, col livello calcolato dalla regola VERA
    (`stakes.impose` su `stakes.domains_acted_on`): il modello sceglie, il
    codice impone `alto` dove la lista lo dice."""

    def __init__(self, archivio):
        self.archivio = archivio

    async def propose(self, intent, *, actor, exchange, now, thread=None,
                      reveal_before=True, refuse_high=False):
        dopo = {"alias": intent["alias"], "actions": intent["azioni"]}
        nata = self.archivio.propose(
            operation=intent["gesto"], domain=intent["dominio"],
            key=intent["alias"].lower().replace(" ", "_"), actor=actor,
            exchange=exchange, phrase=None, prima=None, dopo=dopo, helper=[],
            preview="anteprima", now=now,
            stakes=impose(intent.get("livello"),
                          domains_acted_on(intent["dominio"], dopo)))
        return {"proposta_id": nata["id"], "anteprima": "anteprima"}


def _modello(*intenzioni) -> RunnerFinto:
    """Il modello che propone le `intenzioni` dentro il turno, e le cita
    tutte come costruite."""

    async def _propone(runner, **kwargs):
        nate = []
        for intenzione in intenzioni:
            esito = await kwargs["dispatcher"].dispatch("propose", intenzione)
            nate.append(esito["proposta_id"])
        return json.dumps({"esiti": [
            {"osservazione": n, "esito": "costruita", "proposta_id": ident}
            for n, ident in enumerate(nate)]})

    return RunnerFinto(turno=_propone)


#: Gli utenti di Home Assistant, righe grezze di `config/auth/list`: il
#: proprietario amministra, Marta e' un utente, il Supervisor e' un
#: amministratore DI SISTEMA (`system_generated`, come lo crea Home Assistant).
_UTENTI = [
    {"id": "u-paolo", "name": "Paolo", "is_owner": True, "is_active": True,
     "system_generated": False, "group_ids": ["system-admin"]},
    {"id": "u-marta", "name": "Marta", "is_owner": False, "is_active": True,
     "system_generated": False, "group_ids": ["system-users"]},
    {"id": "u-supervisor", "name": "Supervisor", "is_owner": False,
     "is_active": True, "system_generated": True, "group_ids": ["system-admin"]}]

_TRACKER = {"u-paolo": "iphone_bet", "u-marta": "iphone_di_marta",
            "u-ospite": "ipad_ospite"}


def _casa_ha(utenti=_UTENTI, **guasti) -> CasaFinta:
    """Il client vero sugli ingressi sintetici: una persona col suo telefono
    per ogni utente non di sistema, e i servizi notify dei telefoni di Paolo e
    di Marta (l'ospite non ha le notifiche attive)."""
    inputs = synthetic_inputs()
    inputs["states"] = [
        {"entity_id": f"person.{tracker}", "state": "home",
         "attributes": {"user_id": uid,
                        "device_trackers": [f"device_tracker.{tracker}"]}}
        for uid, tracker in _TRACKER.items()]
    inputs["registries"]["entita"] = [
        {"entity_id": f"device_tracker.{tracker}", "platform": "mobile_app",
         "device_id": f"d-{tracker}"} for tracker in _TRACKER.values()]
    inputs["registries"]["dispositivi"] = []
    inputs["services"] = [{"domain": "notify", "services": {
        "mobile_app_iphone_bet": {}, "mobile_app_iphone_di_marta": {}}}]
    return CasaFinta(inputs, answers={"config/auth/list": lambda extra: utenti},
                     **guasti)


class _Porta:
    """La porta dei servizi: tiene ogni chiamata, e la esegue."""

    def __init__(self):
        self.chiamate = []
        self.arriva = True

    async def execute(self, call, *, actor, subject=None):
        self.chiamate.append({"call": call, "actor": actor, "subject": subject})
        if self.arriva:
            return {"eseguito": True}
        return {"eseguito": False, "errore": "Home Assistant non ha risposto"}


def _osservazioni(quante):
    return [{"soggetto": f"dev{n}", "nome": f"Cosa {n}", "misura": "stato",
             "chiave": None, "innesco": n + 1, "base": 19, "valore": 1.0,
             "cosa": "qualcosa", "spiegato": None, "cosa_cambierebbe": None}
            for n in range(quante)]


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    usage = UsageStore(str(tmp_path / "consumi.db"))
    costruzioni = ConstructionStore(str(tmp_path / "costruzioni.db"))
    app = {**live_values(),
           OBSERVATIONS_KEY: store, USAGE_KEY: usage, CONSTRUCTIONS_KEY: costruzioni,
           WORKSHOP_KEY: _Officina(costruzioni), BRIDGE_ACTIVE_KEY: LiveValue(False),
           HA_CLIENT_KEY: _casa_ha(), SERVICE_REGISTRY_KEY: ServiceRegistry(),
           ACTUATOR_KEY: _Porta()}
    soffitto.prepara_ruoli(app)
    try:
        yield app
    finally:
        store.close()
        usage.close()
        costruzioni.close()


def _analisi(app, quante):
    app[OBSERVATIONS_KEY].replace_analysis(
        OGGI, {"osservazioni": _osservazioni(quante),
               "fondamento": {"giorni": 3, "impronta": "aaa"}})


# -- Passo 1: le prove rosse --------------------------------------------------

@pytest.mark.asyncio
async def test_una_proposta_su_una_SERRATURA_esce_alto_anche_se_il_modello_dice_lieve(casa):
    """D13 dal giro: il modello scrive «lieve», l'archivio dice «alto».

    Mutazione ESEGUITA (06/10/2026): `lock` tolto da `HIGH_STAKES_DOMAINS` --
    rossa, «'lieve' == 'alto'»."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_SERRATURA)

    await pr.proposer_round(casa)

    (riga,) = casa[CONSTRUCTIONS_KEY].list(now=time.time())
    assert riga["livello"] == "alto"


@pytest.mark.asyncio
async def test_una_proposta_ALTO_avvisa_gli_amministratori(casa):
    """D14: la push arriva a chi amministra -- e solo a lui -- con la forma
    unica delle promesse e dalla porta dei servizi, firmata dal proponente.

    Rossa prima del Task 4.3: nessuna push. Mutazione ESEGUITA (06/10/2026):
    `_alert_high` che salta `notify_admins` -- rossa; `_alert_high` che chiede
    le proposte `medio` invece delle `alto` -- rossa."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_SERRATURA)

    await pr.proposer_round(casa)

    (chiamata,) = casa[ACTUATOR_KEY].chiamate
    assert chiamata["call"]["servizio"] == "notify.mobile_app_iphone_bet"
    assert chiamata["call"]["bersaglio"] == {}
    assert chiamata["call"]["dati"]["title"] == DELIVERY_TITLE
    assert "Chiudi la porta di notte" in chiamata["call"]["dati"]["message"]
    assert chiamata["actor"] == "proponente"
    assert chiamata["subject"] == new_subject("persona", ident="u-paolo")


@pytest.mark.asyncio
async def test_una_proposta_MEDIO_non_avvisa_nessuno(casa):
    """D13: nel cervello cambia solo `alto`. Una `medio` va fra le Proposte, e
    nessun telefono suona.

    Mutazione ESEGUITA (06/10/2026): `to_alert` senza il filtro sul livello
    -- rossa."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_LUCE)

    await pr.proposer_round(casa)

    (riga,) = casa[CONSTRUCTIONS_KEY].list(now=time.time())
    assert riga["livello"] == "medio"
    assert casa[ACTUATOR_KEY].chiamate == []


@pytest.mark.asyncio
async def test_un_turno_con_una_ALTO_e_una_MEDIO_avvisa_una_volta(casa):
    _analisi(casa, 2)
    casa[LLM_ROUTER_KEY] = _modello(_LUCE, _SERRATURA)

    await pr.proposer_round(casa)

    assert len(casa[ACTUATOR_KEY].chiamate) == 1


@pytest.mark.asyncio
async def test_un_avviso_ARRIVATO_non_si_ripete_al_battito_dopo(casa):
    """Sul ponte la risposta si rilegge a ogni battito, e il giro guarda gli
    avvisi a ogni battito: uno arrivato e' scritto nell'archivio, e la push
    non parte due volte.

    Mutazione ESEGUITA (06/10/2026): `mark_alerted` che non scrive -- rossa
    (due push)."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_SERRATURA)

    await pr.proposer_round(casa)
    await pr.proposer_round(casa)

    assert len(casa[ACTUATOR_KEY].chiamate) == 1


@pytest.mark.asyncio
async def test_un_avviso_che_NON_PARTE_si_ritenta_finche_arriva(casa):
    """Scelta del proprietario, 06/10/2026 («Ritenta»): un avviso `alto` che
    non arriva si ritenta al giro dopo, e quando arriva smette.

    Mutazione ESEGUITA (06/10/2026): `_alert_high` che segna avvisata la
    proposta anche quando nessuna push e' arrivata -- rossa (una push sola);
    il giro senza il ritentativo in testa -- rossa."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_SERRATURA)
    porta = casa[ACTUATOR_KEY]
    porta.arriva = False

    await pr.proposer_round(casa)
    await pr.proposer_round(casa)
    assert len(porta.chiamate) == 2

    porta.arriva = True
    await pr.proposer_round(casa)
    await pr.proposer_round(casa)
    assert len(porta.chiamate) == 3


@pytest.mark.asyncio
async def test_una_proposta_DECISA_non_si_avvisa_piu(casa):
    """Il limite dei tentativi e' un fatto della proposta, non un numero
    nostro (§10): decisa, non chiede piu' niente a nessuno.

    Mutazione ESEGUITA (06/10/2026): `to_alert` senza `stato='in_attesa'` --
    rossa."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_SERRATURA)
    porta = casa[ACTUATOR_KEY]
    porta.arriva = False
    await pr.proposer_round(casa)
    (riga,) = casa[CONSTRUCTIONS_KEY].list(now=time.time())

    casa[CONSTRUCTIONS_KEY].mark_failed(riga["id"], now=riga["creata_ts"] + 1,
                                        execution_id=None)
    await pr.proposer_round(casa)

    assert len(porta.chiamate) == 1


def test_una_proposta_SCADUTA_non_si_avvisa_piu(tmp_path):
    """Scaduta anche se nessuno ha ancora aperto la pagina che la marca: la
    stessa scadenza di `count_pending`.

    Mutazione ESEGUITA (06/10/2026): `to_alert` senza la scadenza -- rossa."""
    archivio = ConstructionStore(str(tmp_path / "c.db"))
    try:
        archivio.propose(operation="crea", domain="automation", key="k",
                         actor="proponente", exchange="t", phrase=None,
                         prima=None, dopo={"alias": "x"}, helper=[],
                         preview="", stakes="alto", now=1_000_000.0)
        assert len(archivio.to_alert(actor="proponente", stakes="alto",
                                     now=1_000_001.0)) == 1
        dopo = 1_000_000.0 + ConstructionStore.DEADLINE_S + 1
        assert archivio.to_alert(actor="proponente", stakes="alto", now=dopo) == []
    finally:
        archivio.close()


def test_gli_avvisi_nascono_anche_in_un_ARCHIVIO_esistente(tmp_path):
    """Una tabella a parte, `CREATE TABLE IF NOT EXISTS`: un archivio gia' alla
    sua versione la riceve all'apertura, senza gradino di migrazione."""
    import sqlite3

    percorso = str(tmp_path / "c.db")
    ConstructionStore(percorso).close()
    con = sqlite3.connect(percorso)
    con.execute("DROP TABLE avvisi")
    con.commit()
    con.close()

    archivio = ConstructionStore(percorso)
    try:
        archivio.mark_alerted("p1")
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_una_ALTO_che_il_modello_non_cita_si_avvisa_lo_stesso(casa):
    """Le proposte da avvisare le dice l'archivio, non la risposta: una
    costruita che il modello dimentica di citare non resta muta."""
    _analisi(casa, 1)

    async def _propone_dimentica(runner, **kwargs):
        await kwargs["dispatcher"].dispatch("propose", _SERRATURA)

    casa[LLM_ROUTER_KEY] = RunnerFinto(
        json.dumps({"esiti": [{"osservazione": 0, "esito": "niente", "perche": "boh"}]}),
        turno=_propone_dimentica)

    await pr.proposer_round(casa)

    assert len(casa[ACTUATOR_KEY].chiamate) == 1


# -- Chi amministra, e i suoi telefoni ----------------------------------------

@pytest.mark.asyncio
async def test_gli_amministratori_sono_quelli_di_HA_senza_gli_utenti_di_sistema(casa):
    """Chi amministra lo dice Home Assistant, con la regola del cancello al
    confine (`_role_of`). Il Supervisor e' amministratore per HA ma non e' una
    persona: nessun telefono da cercare.

    Mutazione ESEGUITA (06/10/2026): senza il filtro `sistema` -- rossa."""
    assert await soffitto.administrators(casa) == [
        new_subject("persona", ident="u-paolo")]


@pytest.mark.asyncio
async def test_utenti_NON_letti_nessun_avviso_e_lo_si_dice(casa):
    """Il verso del dubbio: se Home Assistant non dice chi amministra, non si
    avvisa a caso -- e il resoconto lo dice."""
    casa[HA_CLIENT_KEY] = _casa_ha(silence={"config/auth/list"})

    esito = await delivery.notify_admins(casa, "x", actor="proponente")

    assert "errore" in esito
    assert casa[ACTUATOR_KEY].chiamate == []


@pytest.mark.asyncio
async def test_un_amministratore_SENZA_telefono_si_conta_non_blocca_gli_altri(casa):
    casa[HA_CLIENT_KEY] = _casa_ha([
        *({**u, "group_ids": ["system-admin"]} if u["id"] == "u-marta" else u
          for u in _UTENTI),
        {"id": "u-ospite", "name": "Ospite", "is_owner": False, "is_active": True,
         "system_generated": False, "group_ids": ["system-admin"]}])

    esito = await delivery.notify_admins(casa, "x", actor="proponente")

    assert esito["push"] == 2
    assert len(esito["senza_telefono"]) == 1
    assert esito["senza_telefono"][0].startswith("u-ospite")
    assert {c["call"]["servizio"] for c in casa[ACTUATOR_KEY].chiamate} == {
        "notify.mobile_app_iphone_bet", "notify.mobile_app_iphone_di_marta"}


@pytest.mark.asyncio
async def test_un_GUASTO_dell_avviso_non_toglie_il_turno(casa):
    """Revisione, giro 58: l'avviso gira in testa a ogni giro, e un suo guasto
    non deve far cadere il turno del proponente.

    Mutazione ESEGUITA (06/10/2026): `_alert_high` chiamato senza la sua
    protezione in testa al giro -- rossa (nessun esito scritto)."""
    _analisi(casa, 1)
    casa[LLM_ROUTER_KEY] = _modello(_LUCE)

    def guasto(**_):
        raise RuntimeError("archivio illeggibile")

    casa[CONSTRUCTIONS_KEY].to_alert = guasto

    esito = await pr.proposer_round(casa)

    assert esito is not None and esito["problemi"] == []
    assert len(casa[CONSTRUCTIONS_KEY].list(now=time.time())) == 1


def test_to_alert_porta_SCADUTA_ORA_che_ROW_legge(tmp_path):
    """Revisione, giro 58 (G58-1): `_row` legge `r["scaduta_ora"]`, che esiste
    solo nei SELECT con `_EXPIRED_SQL AS scaduta_ora`. Un `to_alert` con
    `SELECT *` solleverebbe IndexError, e l'avviso in testa a ogni giro
    fallirebbe sempre.

    Mutazione ESEGUITA (06/10/2026): `to_alert` col `SELECT *` di prima --
    rossa, «IndexError: No item with that key»."""
    archivio = ConstructionStore(str(tmp_path / "c.db"))
    try:
        archivio.propose(operation="crea", domain="automation", key="k",
                         actor="proponente", exchange="t", phrase=None,
                         prima=None, dopo={"alias": "x"}, helper=[],
                         preview="", stakes="alto", now=1_000_000.0)
        (riga,) = archivio.to_alert(actor="proponente", stakes="alto",
                                    now=1_000_001.0)
    finally:
        archivio.close()
    assert riga["stato"] == "in_attesa"
