# tests/test_lovelace_disinstallazione.py
"""La card Lovelace esce dal prodotto: qui si pinna che si **disinstalli**.

fetta E5 Task 5. Questo file sostituisce `tests/test_lovelace_registration.py`,
che difendeva l'installazione: la copia del JS in `<config-ha>/www/{slug}/`,
la scrittura di `hiris-ingress.json` e la registrazione della risorsa
Lovelace. Nessuno di quei tre comportamenti esiste piu' -- i 22 test che li
difendevano fallivano per costruzione (ImportError su `_register_lovelace_card`
e `_deploy_card_to_www`, FileNotFoundError su `hiris-chat-card.js`), verificato
prima di cancellarli. I 3 test su `_find_ha_config_dir` invece **passavano**:
quella funzione sopravvive (la usa la sentinella del comportamento) e i suoi
test si sono spostati qui, non buttati.

Cosa difendono i test nuovi -- le tre regole di
`server._disinstalla_card_lovelace`:
  1. tocca **solo** le risorse che l'add-on stesso aveva registrato;
  2. e' **idempotente**: al secondo avvio non trova niente e non fa niente;
  3. **non fa cadere l'avvio** e **non tace**: se Home Assistant non risponde
     o rifiuta, la funzione torna dichiarando nel log l'URL da togliere a mano.
"""
import os
import contextlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


SLUG = "hiris"
TOKEN = "test-token"
URL_INGRESS_VECCHIO = f"/api/hassio_ingress/{SLUG}/static/hiris-chat-card.js"
URL_LOCALE_NUDO = f"/local/{SLUG}/hiris-chat-card.js"
URL_LOCALE_VERSIONATO = f"/local/{SLUG}/hiris-chat-card.js?v=0.4.0"


# ---------------------------------------------------------------------------
# Finti WebSocket (stessa impalcatura del file che questo sostituisce)
# ---------------------------------------------------------------------------

def _make_ws_mock(messages: list[dict]):
    """WebSocket finto: `receive_json()` restituisce i messaggi in sequenza."""
    it = iter(messages)

    async def _receive_json():
        return next(it)

    ws = AsyncMock()
    ws.receive_json = _receive_json
    ws.send_json = AsyncMock()
    ws.__aenter__ = AsyncMock(return_value=ws)
    ws.__aexit__ = AsyncMock(return_value=False)
    return ws


def _make_session_ws(ws_mock):
    session = AsyncMock()
    session.ws_connect = MagicMock(return_value=ws_mock)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


_AUTH_REQUIRED = {"type": "auth_required"}
_AUTH_OK = {"type": "auth_ok"}
_AUTH_INVALID = {"type": "auth_invalid"}


def _ws_elenco_ok(risorse: list) -> dict:
    return {"id": 1, "type": "result", "success": True, "result": risorse}


def _ws_elenco_ko() -> dict:
    return {"id": 1, "type": "result", "success": False,
            "error": {"code": "not_supported", "message": "Not in storage mode"}}


def _ws_delete_ok(msg_id: int) -> dict:
    return {"id": msg_id, "type": "result", "success": True, "result": None}


def _ws_delete_ko(msg_id: int) -> dict:
    return {"id": msg_id, "type": "result", "success": False,
            "error": {"code": "not_found", "message": "resource not found"}}


def _msgs(ws) -> list[dict]:
    return [c[0][0] for c in ws.send_json.call_args_list]


def _cancellazioni(ws) -> list[dict]:
    return [m for m in _msgs(ws) if m.get("type") == "lovelace/resources/delete"]


@contextlib.contextmanager
def _sessione(ws):
    with patch("hiris.app.server.aiohttp.ClientSession",
               return_value=_make_session_ws(ws)):
        yield


# ---------------------------------------------------------------------------
# Regola 1 — tocca solo cio' che l'add-on aveva installato
# ---------------------------------------------------------------------------

def test_riconosce_solo_gli_url_che_l_addon_sapeva_creare():
    """Il predicato e' l'inverso esatto di quello che usava la registrazione."""
    from hiris.app.server import _e_risorsa_della_card
    assert _e_risorsa_della_card(URL_INGRESS_VECCHIO, SLUG)
    assert _e_risorsa_della_card(URL_LOCALE_NUDO, SLUG)
    assert _e_risorsa_della_card(URL_LOCALE_VERSIONATO, SLUG)
    # Roba dell'utente, o di un altro add-on: non e' nostra.
    assert not _e_risorsa_della_card("/local/community/mini-graph-card.js", SLUG)
    assert not _e_risorsa_della_card("/hacsfiles/button-card/button-card.js", SLUG)
    assert not _e_risorsa_della_card("/local/hiris/altro.js", SLUG)
    # Un altro slug: e' un'altra installazione, non la nostra.
    assert not _e_risorsa_della_card("/local/hiris-test/hiris-chat-card.js", SLUG)


@pytest.mark.asyncio
async def test_cancella_le_tre_forme_di_url_e_lascia_stare_le_altre():
    """Le tre risorse della card se ne vanno; quelle dell'utente restano."""
    risorse = [
        {"id": "r1", "url": URL_INGRESS_VECCHIO, "type": "module"},
        {"id": "r2", "url": "/local/community/mini-graph-card.js", "type": "module"},
        {"id": "r3", "url": URL_LOCALE_NUDO, "type": "module"},
        {"id": "r4", "url": URL_LOCALE_VERSIONATO, "type": "module"},
        {"id": "r5", "url": "/hacsfiles/button-card/button-card.js", "type": "module"},
    ]
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK, _ws_elenco_ok(risorse),
        _ws_delete_ok(2), _ws_delete_ok(3), _ws_delete_ok(4),
    ])
    with _sessione(ws):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG)

    cancellati = [m["resource_id"] for m in _cancellazioni(ws)]
    assert cancellati == ["r1", "r3", "r4"]
    assert "r2" not in cancellati and "r5" not in cancellati


@pytest.mark.asyncio
async def test_non_registra_piu_niente():
    """Nessun `lovelace/resources/create`: la card non si reinstalla da sola."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_elenco_ok([{"id": "r1", "url": URL_LOCALE_VERSIONATO, "type": "module"}]),
        _ws_delete_ok(2),
    ])
    with _sessione(ws):
        from hiris.app.server import _deregistra_risorsa_card
        await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG)

    assert not [m for m in _msgs(ws) if m.get("type") == "lovelace/resources/create"]


# ---------------------------------------------------------------------------
# Regola 2 — idempotenza
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_al_secondo_avvio_non_cancella_niente():
    """Elenco senza risorse della card: nessuna delete, nessun errore."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_elenco_ok([{"id": "r2", "url": "/local/community/x.js", "type": "module"}]),
    ])
    with _sessione(ws):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG)
    assert _cancellazioni(ws) == []


def test_file_gia_assenti_non_si_rimuovono_due_volte(tmp_path):
    """Secondo giro su una cartella gia' pulita: nessun `os.remove`."""
    with patch("hiris.app.server._find_ha_config_dir", return_value=str(tmp_path)), \
         patch("hiris.app.server.os.remove") as rimuovi:
        from hiris.app.server import _rimuovi_file_card
        _rimuovi_file_card(SLUG)
    rimuovi.assert_not_called()


# ---------------------------------------------------------------------------
# Regola 3 — non fa cadere l'avvio, e non tace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_home_assistant_irraggiungibile_non_solleva_e_lo_dichiara(caplog):
    """Rete giu': la funzione torna False e scrive nel log l'URL da togliere."""
    def _esplode(*a, **k):
        raise OSError("connection refused")

    with patch("hiris.app.server.aiohttp.ClientSession", side_effect=_esplode), \
         caplog.at_level("WARNING"):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG) is False

    testo = caplog.text
    assert URL_LOCALE_NUDO in testo, "il log deve dire QUALE risorsa e' rimasta"
    assert "Risorse" in testo, "e dove togliersela: il percorso nell'interfaccia HA"


@pytest.mark.asyncio
async def test_auth_rifiutata_non_solleva_e_lo_dichiara(caplog):
    """Token non valido: nessuna eccezione, e il silenzio non e' ammesso."""
    ws = _make_ws_mock([_AUTH_REQUIRED, _AUTH_INVALID])
    with _sessione(ws), caplog.at_level("WARNING"):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG) is False
    assert "Risorse" in caplog.text
    assert _cancellazioni(ws) == []


@pytest.mark.asyncio
async def test_lovelace_in_modalita_yaml_lo_dice_senza_fallire(caplog):
    """In modalita' YAML le risorse non si gestiscono: si dice all'utente."""
    ws = _make_ws_mock([_AUTH_REQUIRED, _AUTH_OK, _ws_elenco_ko()])
    with _sessione(ws), caplog.at_level("INFO"):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG)
    assert "lovelace.yaml" in caplog.text


@pytest.mark.asyncio
async def test_una_delete_rifiutata_lo_dichiara_con_l_url(caplog):
    """Se HA rifiuta la cancellazione, l'utente sa cosa gli e' rimasto."""
    ws = _make_ws_mock([
        _AUTH_REQUIRED, _AUTH_OK,
        _ws_elenco_ok([{"id": "r1", "url": URL_LOCALE_VERSIONATO, "type": "module"}]),
        _ws_delete_ko(2),
    ])
    with _sessione(ws), caplog.at_level("WARNING"):
        from hiris.app.server import _deregistra_risorsa_card
        assert await _deregistra_risorsa_card("http://supervisor/core", TOKEN, SLUG) is False
    assert URL_LOCALE_VERSIONATO in caplog.text


@pytest.mark.asyncio
async def test_i_file_si_tolgono_anche_se_la_deregistrazione_fallisce():
    """Ordine: prima la risorsa, poi i file -- ma il fallimento non blocca."""
    with patch("hiris.app.server._deregistra_risorsa_card",
               AsyncMock(return_value=False)) as dereg, \
         patch("hiris.app.server._rimuovi_file_card") as rimuovi:
        from hiris.app.server import _disinstalla_card_lovelace
        await _disinstalla_card_lovelace("http://supervisor/core", TOKEN, SLUG)
    dereg.assert_awaited_once()
    rimuovi.assert_called_once_with(SLUG)


# ---------------------------------------------------------------------------
# I due file dentro <config-ha>/www/{slug}/
# ---------------------------------------------------------------------------

def test_toglie_i_due_file_della_card(tmp_path, caplog):
    """`hiris-chat-card.js` e `hiris-ingress.json`: entrambi, e lo dice."""
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")
    (cartella / "hiris-ingress.json").write_text("{}", encoding="utf-8")

    with patch("hiris.app.server._find_ha_config_dir", return_value=str(tmp_path)), \
         caplog.at_level("INFO"):
        from hiris.app.server import _rimuovi_file_card
        _rimuovi_file_card(SLUG)

    assert not (cartella / "hiris-chat-card.js").exists()
    assert not (cartella / "hiris-ingress.json").exists()
    assert not cartella.exists(), "la cartella rimasta vuota si toglie"
    assert "hiris-chat-card.js" in caplog.text


def test_la_cartella_con_roba_dell_utente_non_si_tocca(tmp_path):
    """Se l'utente ci ha messo un file suo, la cartella resta con dentro il suo."""
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")
    (cartella / "sfondo-cucina.png").write_bytes(b"\x89PNG")

    with patch("hiris.app.server._find_ha_config_dir", return_value=str(tmp_path)):
        from hiris.app.server import _rimuovi_file_card
        _rimuovi_file_card(SLUG)

    assert not (cartella / "hiris-chat-card.js").exists()
    assert (cartella / "sfondo-cucina.png").exists()
    assert cartella.is_dir()


def test_cartella_ha_non_montata_non_solleva():
    """Senza volume di configurazione non c'e' niente da togliere."""
    with patch("hiris.app.server._find_ha_config_dir", return_value=None), \
         patch("hiris.app.server.os.remove") as rimuovi:
        from hiris.app.server import _rimuovi_file_card
        _rimuovi_file_card(SLUG)
    rimuovi.assert_not_called()


def test_file_non_cancellabile_lo_dichiara_e_non_solleva(tmp_path, caplog):
    """Cartella in sola lettura: si dice all'utente, non si esplode all'avvio."""
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")

    with patch("hiris.app.server._find_ha_config_dir", return_value=str(tmp_path)), \
         patch("hiris.app.server.os.remove", side_effect=PermissionError("read-only")), \
         caplog.at_level("WARNING"):
        from hiris.app.server import _rimuovi_file_card
        _rimuovi_file_card(SLUG)
    assert "a mano" in caplog.text


# ---------------------------------------------------------------------------
# `_find_ha_config_dir` — sopravvive alla card: i suoi test si sono SPOSTATI
# qui, non cancellati. La usa anche la sentinella del comportamento
# (`server.py`, `sentinella_comportamento`).
# ---------------------------------------------------------------------------

def _patch_ha_mounted(ha_config_dir: str | None = "/config"):
    """Simula il volume di configurazione HA montato nel percorso dato."""
    def _exists(path):
        if ha_config_dir is None:
            return False
        return path == os.path.join(ha_config_dir, "configuration.yaml")

    def _isdir(path):
        if ha_config_dir is None:
            return False
        return path == os.path.join(ha_config_dir, ".storage")

    return (
        patch("hiris.app.server.os.path.exists", side_effect=_exists),
        patch("hiris.app.server.os.path.isdir", side_effect=_isdir),
    )


def test_find_ha_config_dir_config_path():
    """_find_ha_config_dir restituisce /config se lì c'e' configuration.yaml."""
    exists_patch, isdir_patch = _patch_ha_mounted("/config")
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() == "/config"


def test_find_ha_config_dir_homeassistant_fallback():
    """Ripiega su /homeassistant se /config non ha i file di Home Assistant."""
    exists_patch, isdir_patch = _patch_ha_mounted("/homeassistant")
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() == "/homeassistant"


def test_find_ha_config_dir_not_mounted():
    """None quando nessuno dei due percorsi somiglia alla configurazione HA."""
    exists_patch, isdir_patch = _patch_ha_mounted(None)
    with exists_patch, isdir_patch:
        from hiris.app.server import _find_ha_config_dir
        assert _find_ha_config_dir() is None
