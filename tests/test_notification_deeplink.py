"""Fase 2.5 live-verify issue #1: le notifiche Companion aprivano la Dashboard
home (nessun clickAction) ed erano poco leggibili. Ora ogni push HIRIS porta un
deep-link alla UI ingress dell'add-on (`/hassio/ingress/<slug>`) sul tap del
corpo, un canale dedicato e, per il testo lungo, un `subject` leggibile.

Bug in produzione (iPhone): la Companion iOS accetta nel campo `url` solo path
relativi di dashboard Lovelace o URL assoluti, quindi `/hassio/ingress/<slug>`
finiva al sistema operativo (selettore "salva il sito" + pagina nera). Il campo
iOS porta ora il collegamento proprio della Companion
`homeassistant://navigate/<path>?server=default`, che apre l'app e naviga nel
frontend; il campo Android `clickAction` resta il path relativo, che la
Companion Android risolve nativamente."""
import pytest

from hiris.app.notifiche import (
    build_app_deeplink, build_push_data, send_notification)

_PATH = "/hassio/ingress/abc_hiris"
_DEEPLINK = "homeassistant://navigate/hassio/ingress/abc_hiris?server=default"


# --- build_app_deeplink (pura) ----------------------------------------------

def test_build_app_deeplink_wraps_frontend_path():
    assert build_app_deeplink(_PATH) == _DEEPLINK


def test_build_app_deeplink_normalizes_missing_leading_slash():
    assert build_app_deeplink("hassio/ingress/abc_hiris") == _DEEPLINK


def test_build_app_deeplink_keeps_an_existing_query():
    assert build_app_deeplink("/hassio/ingress/x?a=1") == (
        "homeassistant://navigate/hassio/ingress/x?a=1&server=default")


@pytest.mark.parametrize("assente", [None, "", "   "])
def test_build_app_deeplink_without_path_returns_none(assente):
    """Senza path (Supervisor irraggiungibile, slug assente) il collegamento
    va omesso: meglio la Dashboard home che una pagina rotta."""
    assert build_app_deeplink(assente) is None


class _FakeHA:
    def __init__(self):
        self.calls = []

    async def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))
        return True


# --- build_push_data (pura) -------------------------------------------------

def test_build_push_data_deeplinks_when_click_path_present():
    d = build_push_data({"ingress_click_path": _PATH}, "ciao")
    assert d["clickAction"] == _PATH        # Android: path frontend relativo
    assert d["url"] == _DEEPLINK            # iOS: collegamento della Companion
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
         "ingress_click_path": _PATH},
        title="HIRIS")
    assert ok
    domain, service, data = ha.calls[0]
    assert (domain, service) == ("notify", "mobile_app_bet")
    assert data["message"] == "messaggio"
    assert data["title"] == "HIRIS"
    assert data["data"]["clickAction"] == _PATH
    assert data["data"]["url"] == _DEEPLINK
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
