"""Le notifiche persistenti di HIRIS in Home Assistant (richiesta del
proprietario del 21/10/2026: la push toccata apre Home Assistant e sparisce, e
il testo dell'avviso non si ritrova piu'). Proposta:
`/mnt/project-files/analisi/2026-10-21-avvisi-persistenti-proposta.md`.

Qui la lettura (`HAClient.persistent_notifications`) e la forma delle due
chiamate (`delivery.notice_call`, `delivery.withdrawal_call`) davanti alla
verifica VERA. Chi le usa ha le sue prove: `tests/test_integrazioni_ferme.py`
e `tests/test_proponente_avviso.py`.
"""
from __future__ import annotations

import pytest

from hiris.app.action.verification import verification
from hiris.app.keeper.delivery import notice_call, withdrawal_call
from hiris.app.proxy.ha_client import HAClient, notification_fingerprint
from tests.test_action_registry import _house
from tests.test_action_verification import STATI, _registro_pronto

#: Il dominio come Home Assistant lo dichiara in `/api/services`: i campi di
#: `persistent_notification/services.yaml`, letti al tag 2026.9.4 il
#: 21/10/2026 -- nessun `target`, come i `notify.*`.
_PERSISTENTI = {"domain": "persistent_notification", "services": {
    "create": {"fields": {"message": {}, "title": {}, "notification_id": {}}},
    "dismiss": {"fields": {"notification_id": {}}},
    "dismiss_all": {"fields": {}}}}


def _casa(notifiche=None, **guasti):
    return _house([], answers={"persistent_notification/get": lambda extra: notifiche},
                  **guasti) if notifiche is not None else _house([], **guasti)


@pytest.mark.asyncio
async def test_la_lettura_porta_l_impronta_non_il_testo():
    """Il testo libero non esce dal client: esce l'impronta, la stessa che
    calcola chi scrive.

    Mutazione ESEGUITA (21/10/2026): l'impronta del solo testo, senza il
    titolo -- rossa."""
    casa = _casa([{"notification_id": "hiris_x", "title": "HIRIS",
                   "message": "ciao", "created_at": "2026-10-21T08:00:00+00:00"},
                  {"notification_id": "altro", "title": None, "message": "m"}])

    letto = await casa.persistent_notifications()

    assert letto == {"notifiche": {
        "hiris_x": notification_fingerprint("HIRIS", "ciao"),
        "altro": notification_fingerprint(None, "m")}}
    assert letto["notifiche"]["hiris_x"] != notification_fingerprint("altro", "ciao")


@pytest.mark.asyncio
async def test_una_lettura_mancata_non_e_un_elenco_vuoto():
    """Un elenco vuoto direbbe «nessuna notifica», e chi scrive le
    riscriverebbe tutte."""
    casa = _casa(silence={"persistent_notification/get"})
    assert "errore" in await casa.persistent_notifications()
    strana = _casa({"non": "una lista"})
    assert "errore" in await strana.persistent_notifications()


def test_la_lettura_dichiara_il_suo_costo():
    assert HAClient.persistent_notifications.cost == {"ws": 1, "rest": 0}


@pytest.mark.asyncio
async def test_le_due_chiamate_passano_la_verifica_vera():
    """Bersaglio vuoto e campi dichiarati: la porta dei servizi le accetta
    perche' `persistent_notification` e' un recapito
    (`_DOMINI_DI_RECAPITO`), non per un'eccezione nuova."""
    registro = await _registro_pronto([_PERSISTENTI])
    for chiamata in (notice_call("hiris_x", "HIRIS", "testo"), withdrawal_call("hiris_x")):
        verdetto = verification(chiamata, registro, STATI)
        assert verdetto.ok is True, verdetto.reason
