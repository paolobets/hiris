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
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from casa_finta import CasaFinta

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.stakes import domains_acted_on, impose
from hiris.app.action.registry import ServiceRegistry
from hiris.app.api import soffitto
from hiris.app.home_space import historian
from hiris.app.keeper import delivery
from hiris.app.keeper.promise import DELIVERY_TITLE
from hiris.app.mind import proposer_round as pr
from hiris.app.mind.store import ObservationsStore
from hiris.app.usage.store import UsageStore
from tests._casa_sintetica import synthetic_inputs

OGGI = historian.today(historian.house_timezone(None)).isoformat()

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
                      reveal_before=True):
        dopo = {"alias": intent["alias"], "actions": intent["azioni"]}
        nata = self.archivio.propose(
            operation=intent["gesto"], domain=intent["dominio"],
            key=intent["alias"].lower().replace(" ", "_"), actor=actor,
            exchange=exchange, phrase=None, prima=None, dopo=dopo, helper=[],
            preview="anteprima", now=now,
            stakes=impose(intent.get("livello"),
                          domains_acted_on(intent["dominio"], dopo)))
        return {"proposta_id": nata["id"], "anteprima": "anteprima"}


class _Modello:
    def __init__(self, *intenzioni):
        self.intenzioni = list(intenzioni)

    async def chat(self, **kwargs):
        nate = []
        for intenzione in self.intenzioni:
            esito = await kwargs["dispatcher"].dispatch("propose", intenzione)
            nate.append(esito["proposta_id"])
        return json.dumps({"esiti": [
            {"osservazione": n, "esito": "costruita", "proposta_id": ident}
            for n, ident in enumerate(nate)]})


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

    async def execute(self, call, *, actor, subject=None):
        self.chiamate.append({"call": call, "actor": actor, "subject": subject})
        return {"eseguito": True}


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
    app = {"observations": store, "usage": usage, "constructions": costruzioni,
           "workshop": _Officina(costruzioni), "bridge_active": False,
           "ha_client": _casa_ha(), "service_registry": ServiceRegistry(),
           "action_actuator": _Porta()}
    soffitto.prepara_ruoli(app)
    try:
        yield app
    finally:
        store.close()
        usage.close()
        costruzioni.close()


def _analisi(app, quante):
    app["observations"].replace_analysis(
        OGGI, {"osservazioni": _osservazioni(quante),
               "fondamento": {"giorni": 3, "impronta": "aaa"}})


# -- Passo 1: le prove rosse --------------------------------------------------

@pytest.mark.asyncio
async def test_una_proposta_su_una_SERRATURA_esce_alto_anche_se_il_modello_dice_lieve(casa):
    """D13 dal giro: il modello scrive «lieve», l'archivio dice «alto».

    Mutazione ESEGUITA (06/10/2026): `lock` tolto da `HIGH_STAKES_DOMAINS` --
    rossa, «'lieve' == 'alto'»."""
    _analisi(casa, 1)
    casa["llm_router"] = _Modello(_SERRATURA)

    await pr.proposer_round(casa)

    (riga,) = casa["constructions"].list()
    assert riga["livello"] == "alto"


@pytest.mark.asyncio
async def test_una_proposta_ALTO_avvisa_gli_amministratori(casa):
    """D14: la push arriva a chi amministra -- e solo a lui -- con la forma
    unica delle promesse e dalla porta dei servizi, firmata dal proponente.

    Rossa prima del Task 4.3: nessuna push. Mutazione ESEGUITA (06/10/2026):
    `_alert_high` che non chiama `notify_admins` -- rossa."""
    _analisi(casa, 1)
    casa["llm_router"] = _Modello(_SERRATURA)

    await pr.proposer_round(casa)

    (chiamata,) = casa["action_actuator"].chiamate
    assert chiamata["call"]["servizio"] == "notify.mobile_app_iphone_bet"
    assert chiamata["call"]["bersaglio"] == {}
    assert chiamata["call"]["dati"]["title"] == DELIVERY_TITLE
    assert "Chiudi la porta di notte" in chiamata["call"]["dati"]["message"]
    assert chiamata["actor"] == "proponente"
    assert chiamata["subject"] == {"specie": "persona", "id": "u-paolo"}


@pytest.mark.asyncio
async def test_una_proposta_MEDIO_non_avvisa_nessuno(casa):
    """D13: nel cervello cambia solo `alto`. Una `medio` va fra le Proposte, e
    nessun telefono suona.

    Mutazione ESEGUITA (06/10/2026): `_alert_high` senza il controllo del
    livello -- rossa."""
    _analisi(casa, 1)
    casa["llm_router"] = _Modello(_LUCE)

    await pr.proposer_round(casa)

    (riga,) = casa["constructions"].list()
    assert riga["livello"] == "medio"
    assert casa["action_actuator"].chiamate == []


@pytest.mark.asyncio
async def test_un_turno_con_una_ALTO_e_una_MEDIO_avvisa_una_volta(casa):
    _analisi(casa, 2)
    casa["llm_router"] = _Modello(_LUCE, _SERRATURA)

    await pr.proposer_round(casa)

    assert len(casa["action_actuator"].chiamate) == 1


def test_una_seconda_lettura_dello_stesso_turno_non_avvisa_di_nuovo():
    """Sul ponte la risposta si rilegge a ogni battito finche' non arriva un
    turno nuovo. `_settle` torna solo le proposte scritte ADESSO: la seconda
    lettura ne torna zero, e la push non parte due volte.

    Mutazione ESEGUITA (06/10/2026): `_settle` che torna ogni «costruita»
    della risposta, anche gia' scritta -- rossa."""
    import tempfile

    with tempfile.TemporaryDirectory() as cartella:
        store = ObservationsStore(f"{cartella}/oss.db")
        try:
            store.replace_analysis(OGGI, {"osservazioni": _osservazioni(1),
                                          "fondamento": {"giorni": 3}})
            (osservazione,) = _osservazioni(1)
            from hiris.app.mind.analyst import observation_key

            esito = {"esiti": [{"impronta": observation_key(osservazione),
                                "esito": "costruita", "proposta_id": "p1"}],
                     "problemi": []}
            assert pr._settle(store, OGGI, esito) == ["p1"]
            assert pr._settle(store, OGGI, esito) == []
        finally:
            store.close()


# -- Chi amministra, e i suoi telefoni ----------------------------------------

@pytest.mark.asyncio
async def test_gli_amministratori_sono_quelli_di_HA_senza_gli_utenti_di_sistema(casa):
    """Chi amministra lo dice Home Assistant, con la regola del cancello al
    confine (`_role_of`). Il Supervisor e' amministratore per HA ma non e' una
    persona: nessun telefono da cercare.

    Mutazione ESEGUITA (06/10/2026): senza il filtro `sistema` -- rossa."""
    assert await soffitto.administrators(casa) == [
        {"specie": "persona", "id": "u-paolo"}]


@pytest.mark.asyncio
async def test_utenti_NON_letti_nessun_avviso_e_lo_si_dice(casa):
    """Il verso del dubbio: se Home Assistant non dice chi amministra, non si
    avvisa a caso -- e il resoconto lo dice."""
    casa["ha_client"] = _casa_ha(silence={"config/auth/list"})

    esito = await delivery.notify_admins(casa, "x", actor="proponente")

    assert "errore" in esito
    assert casa["action_actuator"].chiamate == []


@pytest.mark.asyncio
async def test_un_amministratore_SENZA_telefono_si_conta_non_blocca_gli_altri(casa):
    casa["ha_client"] = _casa_ha([
        *({**u, "group_ids": ["system-admin"]} if u["id"] == "u-marta" else u
          for u in _UTENTI),
        {"id": "u-ospite", "name": "Ospite", "is_owner": False, "is_active": True,
         "system_generated": False, "group_ids": ["system-admin"]}])

    esito = await delivery.notify_admins(casa, "x", actor="proponente")

    assert esito["push"] == 2
    assert len(esito["senza_telefono"]) == 1
    assert esito["senza_telefono"][0].startswith("u-ospite")
    assert {c["call"]["servizio"] for c in casa["action_actuator"].chiamate} == {
        "notify.mobile_app_iphone_bet", "notify.mobile_app_iphone_di_marta"}
