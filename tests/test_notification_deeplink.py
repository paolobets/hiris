"""Fase 2.5 live-verify issue #1: le notifiche Companion aprivano la Dashboard
home (nessun clickAction) ed erano poco leggibili. Ora ogni push HIRIS porta un
deep-link alla UI ingress dell'add-on (`/hassio/ingress/<slug>`) sul tap del
corpo, un canale dedicato e, per il testo lungo, un `subject` leggibile."""
import pytest

from hiris.app.tools.notify_tools import build_push_data, send_notification
from hiris.app.api import handlers_gateway_pending as gp


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return True


# --- build_push_data (pura) -------------------------------------------------

def test_build_push_data_deeplinks_when_click_path_present():
    d = build_push_data({"ingress_click_path": "/hassio/ingress/abc_hiris"}, "ciao")
    assert d["clickAction"] == "/hassio/ingress/abc_hiris"   # Android
    assert d["url"] == "/hassio/ingress/abc_hiris"           # iOS
    assert d["channel"] == "HIRIS"
    assert "subject" not in d  # messaggio corto


def test_build_push_data_long_message_gets_subject():
    long = "x" * 200
    d = build_push_data({"ingress_click_path": "/hassio/ingress/x"}, long)
    assert d["subject"] == long


def test_build_push_data_without_click_path_still_has_channel():
    d = build_push_data({}, "ciao")
    assert d == {"channel": "HIRIS"}
    assert "clickAction" not in d and "url" not in d


# --- send_notification ha_push wiring ---------------------------------------

@pytest.mark.asyncio
async def test_ha_push_attaches_deeplink_data():
    ha = _FakeHA()
    ok = await send_notification(
        ha, "messaggio", "ha_push",
        {"ha_notify_service": "notify.mobile_app_bet",
         "ingress_click_path": "/hassio/ingress/abc_hiris"},
        title="HIRIS")
    assert ok
    domain, service, data = ha.calls[0]
    assert (domain, service) == ("notify", "mobile_app_bet")
    assert data["message"] == "messaggio"
    assert data["title"] == "HIRIS"
    assert data["data"]["clickAction"] == "/hassio/ingress/abc_hiris"
    assert data["data"]["url"] == "/hassio/ingress/abc_hiris"
    assert data["data"]["channel"] == "HIRIS"


@pytest.mark.asyncio
async def test_ha_push_without_click_path_still_sends_channel():
    ha = _FakeHA()
    ok = await send_notification(
        ha, "messaggio", "ha_push",
        {"ha_notify_service": "notify.notify"})  # no ingress_click_path
    assert ok
    _, _, data = ha.calls[0]
    assert data["data"]["channel"] == "HIRIS"
    assert "clickAction" not in data["data"]


# --- pending step-up notify -------------------------------------------------

@pytest.mark.asyncio
async def test_pending_notify_deeplinks_body_and_uri_action():
    ha = _FakeHA()
    app = {"ha_client": ha,
           "gateway_settings": {"notify_service": "notify.mobile_app_bet"},
           "ingress_click_path": "/hassio/ingress/abc_hiris"}
    ok = await gp.notify(app, message="serve conferma", actionable=True, nonce="n1")
    assert ok
    _, _, data = ha.calls[0]
    assert data["data"]["clickAction"] == "/hassio/ingress/abc_hiris"
    assert data["data"]["url"] == "/hassio/ingress/abc_hiris"
    uri = [a for a in data["data"]["actions"] if a.get("action") == "URI"]
    assert uri and uri[0]["uri"] == "/hassio/ingress/abc_hiris"
    # le azioni di approvazione restano
    assert any(a["action"].endswith("approve:n1") for a in data["data"]["actions"])


@pytest.mark.asyncio
async def test_pending_notify_non_actionable_still_deeplinks():
    """Un pending rosso/OTP-only (non actionable) prima NON aveva `data` affatto
    -> nessun deep-link. Ora lo porta comunque (con canale), senza pulsanti."""
    ha = _FakeHA()
    app = {"ha_client": ha,
           "gateway_settings": {"notify_service": "notify.mobile_app_bet"},
           "ingress_click_path": "/hassio/ingress/abc_hiris"}
    ok = await gp.notify(app, message="serve OTP", actionable=False, nonce="n2")
    assert ok
    _, _, data = ha.calls[0]
    assert data["data"]["clickAction"] == "/hassio/ingress/abc_hiris"
    assert data["data"]["channel"] == "HIRIS"
    assert "actions" not in data["data"]


@pytest.mark.asyncio
async def test_pending_notify_without_click_path_omits_uri_action():
    """Senza slug (Supervisor irraggiungibile) niente deep-link e niente
    pulsante 'Apri HIRIS' rotto -- solo Approva/Nega."""
    ha = _FakeHA()
    app = {"ha_client": ha,
           "gateway_settings": {"notify_service": "notify.mobile_app_bet"}}
    ok = await gp.notify(app, message="serve conferma", actionable=True, nonce="n3")
    assert ok
    _, _, data = ha.calls[0]
    assert "clickAction" not in data["data"]
    assert all(a.get("action") != "URI" for a in data["data"]["actions"])
    assert data["data"]["channel"] == "HIRIS"
