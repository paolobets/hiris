# tests/test_lovelace_uninstall.py
"""La card Lovelace esce dal prodotto: qui si pinna che si **disinstalli**.

fetta E5 Task 5. Questo file sostituisce `tests/test_lovelace_registration.py`,
che difendeva l'installazione: la copia del JS in `<config-ha>/www/{slug}/`,
la scrittura di `hiris-ingress.json` e la registrazione della risorsa
Lovelace. Nessuno di quei tre comportamenti esiste piu' -- i 22 test che li
difendevano fallivano per costruzione (ImportError su `_register_lovelace_card`
e `_deploy_card_to_www`, FileNotFoundError su `hiris-chat-card.js`), verificato
prima di cancellarli. I 3 test sulla ricerca della cartella di Home Assistant invece
**passavano**: quella ricerca sopravvive (la usa la rilettura del
comportamento) e i suoi test si sono spostati qui, non buttati. Dal 03/10/2026
(A-40) la ricerca e' una sola, `home_space.redaction.home_assistant_folder`.

Cosa difendono i test nuovi -- le tre regole di
`action.installation.disinstalla_card_lovelace`:
  1. tocca **solo** le risorse che l'add-on stesso aveva registrato;
  2. e' **idempotente**: al secondo avvio non trova niente e non fa niente;
  3. **non fa cadere l'avvio** e **non tace**: se Home Assistant non risponde
     o rifiuta, la funzione torna dichiarando nel log l'URL da togliere a mano.

Dalla Chiusura (F5, E-01 ed E-06) la disinstallazione passa da `HAClient`
(`lovelace_resources`, `delete_lovelace_resource`) e non apre piu' una sessione
WebSocket sua: le prove fingono il FILO con la casa finta comune
(`scripts/casa_finta.py`), sotto il client vero. E ha una condizione d'uscita
(M-41): dopo un passaggio pulito scrive il segno in `/data` e non chiede piu'
niente a Home Assistant.
"""
import asyncio
import os
import pathlib
import sys
from unittest.mock import AsyncMock, patch

import pytest

from hiris.app.action import installation

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from casa_finta import SILENT, CasaFinta, Refused, in_turn

SLUG = installation.CARD_FOLDER
URL_INGRESS_VECCHIO = f"/api/hassio_ingress/{SLUG}/static/hiris-chat-card.js"
URL_LOCALE_NUDO = f"/local/{SLUG}/hiris-chat-card.js"
URL_LOCALE_VERSIONATO = f"/local/{SLUG}/hiris-chat-card.js?v=0.4.0"


def _casa(risorse=None, *, elenco=None, cancella=None, slug=None) -> CasaFinta:
    """La casa finta con l'elenco delle risorse Lovelace (`risorse`, oppure
    `elenco`: un `Refused` o `SILENT`), la risposta alle cancellazioni
    (`cancella`, di norma `null` come `lovelace/resources/delete`) e, se
    serve, quella del Supervisor allo slug (`slug`)."""
    answers = {"lovelace/resources": (lambda extra: risorse) if elenco is None
               else (lambda extra: elenco),
               "lovelace/resources/delete": cancella or (lambda extra: None)}
    if slug is not None:
        answers["supervisor /addons/self/info"] = lambda extra: slug
    return CasaFinta({}, answers=answers)


def _cancellazioni(ha) -> list[str]:
    return [extra["resource_id"] for t, extra in ha.calls
            if t == "lovelace/resources/delete"]


# ---------------------------------------------------------------------------
# Regola 1 — tocca solo cio' che l'add-on aveva installato
# ---------------------------------------------------------------------------

def test_riconosce_solo_gli_url_che_l_addon_sapeva_creare():
    """Il predicato e' l'inverso esatto di quello che usava la registrazione."""
    from hiris.app.action.installation import _e_risorsa_della_card
    assert _e_risorsa_della_card(URL_INGRESS_VECCHIO, SLUG)
    assert _e_risorsa_della_card(URL_LOCALE_NUDO, SLUG)
    assert _e_risorsa_della_card(URL_LOCALE_VERSIONATO, SLUG)
    # Roba dell'utente, o di un altro add-on: non e' nostra.
    assert not _e_risorsa_della_card("/local/community/mini-graph-card.js", SLUG)
    assert not _e_risorsa_della_card("/hacsfiles/button-card/button-card.js", SLUG)
    assert not _e_risorsa_della_card("/local/hiris/altro.js", SLUG)
    # Un altro slug: e' un'altra installazione, non la nostra.
    assert not _e_risorsa_della_card("/local/hiris-test/hiris-chat-card.js", SLUG)
    # fix round 1, Critical. Il predicato chiudeva con `startswith(locale)` e
    # di forme ne riconosceva infinite: questi tre URL risultavano "nostri".
    # Sono il caso di chi ha tenuto un PROPRIO fork della card con un nome
    # derivato e se lo sarebbe visto deregistrare, con un log che diceva
    # "rimossa" e nessun modo di capire che era suo.
    assert not _e_risorsa_della_card(f"/local/{SLUG}/hiris-chat-card.js.bak", SLUG)
    assert not _e_risorsa_della_card(f"/local/{SLUG}/hiris-chat-card.js-mio.js", SLUG)
    assert not _e_risorsa_della_card(f"/local/{SLUG}/hiris-chat-card.json", SLUG)


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
    ha = _casa(risorse)
    assert await installation._deregistra_risorsa_card(ha, SLUG)

    cancellati = _cancellazioni(ha)
    assert cancellati == ["r1", "r3", "r4"]
    assert "r2" not in cancellati and "r5" not in cancellati


@pytest.mark.asyncio
async def test_non_registra_piu_niente():
    """Nessun `lovelace/resources/create`: la card non si reinstalla da sola."""
    ha = _casa([{"id": "r1", "url": URL_LOCALE_VERSIONATO, "type": "module"}])
    await installation._deregistra_risorsa_card(ha, SLUG)

    assert [t for t, _ in ha.calls] == ["lovelace/resources", "lovelace/resources/delete"]


# ---------------------------------------------------------------------------
# Regola 2 — idempotenza
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_al_secondo_avvio_non_cancella_niente():
    """Elenco senza risorse della card: nessuna delete, nessun errore."""
    ha = _casa([{"id": "r2", "url": "/local/community/x.js", "type": "module"}])
    assert await installation._deregistra_risorsa_card(ha, SLUG)
    assert _cancellazioni(ha) == []


def test_file_gia_assenti_non_si_rimuovono_due_volte(tmp_path):
    """Secondo giro su una cartella gia' pulita: nessun `os.remove`."""
    with patch("hiris.app.action.installation.home_assistant_folder", return_value=str(tmp_path)), \
         patch("hiris.app.action.installation.os.remove") as rimuovi:
        from hiris.app.action.installation import _rimuovi_file_card
        _rimuovi_file_card(SLUG)
    rimuovi.assert_not_called()


# ---------------------------------------------------------------------------
# Regola 3 — non fa cadere l'avvio, e non tace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_home_assistant_irraggiungibile_non_solleva_e_lo_dichiara(caplog):
    """Rete giu', o autenticazione rifiutata (per `_ws_send` sono lo stesso
    silenzio): la funzione torna False e scrive nel log l'URL da togliere."""
    ha = _casa(elenco=SILENT)
    with caplog.at_level("WARNING"):
        assert await installation._deregistra_risorsa_card(ha, SLUG) is False

    testo = caplog.text
    assert URL_LOCALE_NUDO in testo, "il log deve dire QUALE risorsa e' rimasta"
    assert "Risorse" in testo, "e dove togliersela: il percorso nell'interfaccia HA"
    assert _cancellazioni(ha) == []


@pytest.mark.asyncio
async def test_lovelace_in_modalita_yaml_lo_dice_senza_fallire(caplog):
    """In modalita' YAML le risorse non si gestiscono: si dice all'utente."""
    ha = _casa(elenco=Refused("not_supported", "Not in storage mode"))
    with caplog.at_level("INFO"):
        assert await installation._deregistra_risorsa_card(ha, SLUG)
    assert "lovelace.yaml" in caplog.text


@pytest.mark.asyncio
async def test_una_delete_rifiutata_lo_dichiara_con_l_url(caplog):
    """Se HA rifiuta la cancellazione, l'utente sa cosa gli e' rimasto."""
    ha = _casa([{"id": "r1", "url": URL_LOCALE_VERSIONATO, "type": "module"}],
               cancella=lambda extra: Refused("not_found", "resource not found"))
    with caplog.at_level("WARNING"):
        assert await installation._deregistra_risorsa_card(ha, SLUG) is False
    assert URL_LOCALE_VERSIONATO in caplog.text


@pytest.mark.asyncio
async def test_una_delete_rifiutata_non_abbandona_le_successive(caplog):
    """fix round 1, Important 2 -- il caso normale di chi aggiorna da lontano.

    Due risorse della card (l'URL nudo E quello versionato) e la PRIMA delete
    rifiutata: prima il ciclo usciva subito, la seconda non veniva ne' tentata
    ne' nominata, e l'utente toglieva a mano l'unica che aveva letto restando
    con l'altra -- cioe' con l'errore rosso in dashboard.
    """
    risorse = [
        {"id": "r1", "url": URL_LOCALE_NUDO, "type": "module"},
        {"id": "r2", "url": URL_LOCALE_VERSIONATO, "type": "module"},
    ]
    ha = _casa(risorse, cancella=in_turn(Refused("not_found", "resource not found"),
                                         None))
    with caplog.at_level("INFO"):
        esito = await installation._deregistra_risorsa_card(ha, SLUG)

    # La seconda e' stata TENTATA nonostante il fallimento della prima.
    assert _cancellazioni(ha) == ["r1", "r2"]
    # L'esito resta negativo: qualcosa e' rimasto.
    assert esito is False
    # E il riepilogo nomina cio' che e' rimasto, non cio' che e' andato via.
    assert "rimaste da togliere a mano" in caplog.text
    assert URL_LOCALE_NUDO in caplog.text


@pytest.mark.asyncio
async def test_due_delete_rifiutate_finiscono_entrambe_nel_riepilogo(caplog):
    """Il riepilogo deve essere COMPLETO: un elenco monco e' un mezzo silenzio."""
    risorse = [
        {"id": "r1", "url": URL_LOCALE_NUDO, "type": "module"},
        {"id": "r2", "url": URL_LOCALE_VERSIONATO, "type": "module"},
    ]
    ha = _casa(risorse, cancella=lambda extra: Refused("not_found", "resource not found"))
    with caplog.at_level("WARNING"):
        assert await installation._deregistra_risorsa_card(ha, SLUG) is False

    riepilogo = [r for r in caplog.messages if "rimaste da togliere a mano" in r]
    assert len(riepilogo) == 1, "una riga di riepilogo, non una per risorsa"
    assert URL_LOCALE_NUDO in caplog.text and URL_LOCALE_VERSIONATO in caplog.text


# ---------------------------------------------------------------------------
# M-41 — una volta: il segno in /data, e i file anche se la risorsa resta
# ---------------------------------------------------------------------------
# «Non risponde» non appende piu' l'avvio per costruzione: la disinstallazione
# gira nel compito dell'installazione, dopo l'avvio (prove in
# `test_panel_visibility.py`), e il silenzio del client e' quello di
# `_ws_send`, provato in `test_ha_client_invio.py`.

@pytest.mark.asyncio
async def test_i_file_si_tolgono_anche_se_la_deregistrazione_fallisce(tmp_path):
    """Ordine: prima la risorsa, poi i file -- ma il fallimento non blocca. E
    il segno non si scrive: al prossimo avvio si riprova."""
    with patch("hiris.app.action.installation._deregistra_risorsa_card",
               AsyncMock(return_value=False)) as dereg, \
         patch("hiris.app.action.installation._rimuovi_file_card",
               return_value=True) as rimuovi:
        await installation.disinstalla_card_lovelace(_casa([]), str(tmp_path), SLUG)
    dereg.assert_awaited_once()
    rimuovi.assert_called_once_with(SLUG)
    assert not (tmp_path / installation.CARD_UNINSTALLED_MARK).exists()


@pytest.mark.asyncio
async def test_un_passaggio_pulito_scrive_il_segno_e_il_prossimo_avvio_non_chiede_niente(
        tmp_path):
    """La condizione d'uscita che mancava (M-41): fino alla Chiusura la
    disinstallazione chiedeva a Home Assistant le risorse a OGNI avvio, per
    sempre. Dopo un passaggio pulito il segno c'e', e il secondo avvio non
    apre nessuna connessione.

    Mutazione ESEGUITA (13/10/2026): tolto il ritorno anticipato sul segno
    -- rossa (il secondo avvio chiede `lovelace/resources`)."""
    with patch("hiris.app.action.installation.home_assistant_folder", return_value=None):
        primo = _casa([{"id": "r1", "url": URL_LOCALE_NUDO, "type": "module"}])
        await installation.disinstalla_card_lovelace(primo, str(tmp_path), SLUG)
        assert _cancellazioni(primo) == ["r1"]
        segno = tmp_path / installation.CARD_UNINSTALLED_MARK
        assert segno.exists()
        assert "disinstallata" in segno.read_text(encoding="utf-8")

        secondo = _casa([{"id": "r1", "url": URL_LOCALE_NUDO, "type": "module"}])
        await installation.disinstalla_card_lovelace(secondo, str(tmp_path), SLUG)
    assert secondo.calls == [] and secondo.connections == []


@pytest.mark.asyncio
@pytest.mark.parametrize("elenco, cancella, file_puliti", [
    (SILENT, None, True),
    (None, lambda extra: Refused("not_found", "x"), True),
    (None, None, False),
])
async def test_un_passaggio_che_lascia_qualcosa_non_scrive_il_segno(
        tmp_path, elenco, cancella, file_puliti):
    """Home Assistant zitto, una risorsa rimasta, un file rimasto: il segno non
    si scrive, e al prossimo avvio si riprova. Mutazione ESEGUITA (13/10/2026):
    segno scritto sempre -- rossa sui tre casi."""
    ha = _casa([{"id": "r1", "url": URL_LOCALE_NUDO, "type": "module"}],
               elenco=elenco, cancella=cancella)
    with patch("hiris.app.action.installation._rimuovi_file_card",
               return_value=file_puliti):
        await installation.disinstalla_card_lovelace(ha, str(tmp_path), SLUG)
    assert not (tmp_path / installation.CARD_UNINSTALLED_MARK).exists()


# ---------------------------------------------------------------------------
# I due file dentro <config-ha>/www/{slug}/
# ---------------------------------------------------------------------------

def test_toglie_i_due_file_della_card(tmp_path, caplog):
    """`hiris-chat-card.js` e `hiris-ingress.json`: entrambi, e lo dice."""
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")
    (cartella / "hiris-ingress.json").write_text("{}", encoding="utf-8")

    with patch("hiris.app.action.installation.home_assistant_folder", return_value=str(tmp_path)), \
         caplog.at_level("INFO"):
        from hiris.app.action.installation import _rimuovi_file_card
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

    with patch("hiris.app.action.installation.home_assistant_folder", return_value=str(tmp_path)):
        from hiris.app.action.installation import _rimuovi_file_card
        _rimuovi_file_card(SLUG)

    assert not (cartella / "hiris-chat-card.js").exists()
    assert (cartella / "sfondo-cucina.png").exists()
    assert cartella.is_dir()


def test_cartella_ha_non_montata_non_solleva():
    """Senza volume di configurazione non c'e' niente da togliere."""
    with patch("hiris.app.action.installation.home_assistant_folder", return_value=None), \
         patch("hiris.app.action.installation.os.remove") as rimuovi:
        from hiris.app.action.installation import _rimuovi_file_card
        _rimuovi_file_card(SLUG)
    rimuovi.assert_not_called()


def test_file_non_cancellabile_lo_dichiara_e_non_solleva(tmp_path, caplog):
    """Cartella in sola lettura: si dice all'utente, non si esplode all'avvio."""
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")

    with patch("hiris.app.action.installation.home_assistant_folder", return_value=str(tmp_path)), \
         patch("hiris.app.action.installation.os.remove",
               side_effect=PermissionError("read-only")), \
         caplog.at_level("WARNING"):
        from hiris.app.action.installation import _rimuovi_file_card
        assert _rimuovi_file_card(SLUG) is False
    assert "a mano" in caplog.text


# ---------------------------------------------------------------------------
# `home_assistant_folder` — sopravvive alla card: i suoi test si sono SPOSTATI
# qui, non cancellati. La usano anche la rilettura del comportamento
# (`rounds.behavior_reader`) e il sigillo dei segreti
# (`redaction.home_assistant_seal`). Fino al 03/10/2026 questi tre test
# guardavano la copia di `server`, `_find_ha_config_dir` (A-40).
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
        patch("hiris.app.home_space.redaction.os.path.exists", side_effect=_exists),
        patch("hiris.app.home_space.redaction.os.path.isdir", side_effect=_isdir),
    )


def test_home_assistant_folder_config_path():
    """home_assistant_folder restituisce /config se lì c'e' configuration.yaml."""
    exists_patch, isdir_patch = _patch_ha_mounted("/config")
    with exists_patch, isdir_patch:
        from hiris.app.home_space.redaction import home_assistant_folder
        assert home_assistant_folder() == "/config"


def test_home_assistant_folder_homeassistant_fallback():
    """Ripiega su /homeassistant se /config non ha i file di Home Assistant."""
    exists_patch, isdir_patch = _patch_ha_mounted("/homeassistant")
    with exists_patch, isdir_patch:
        from hiris.app.home_space.redaction import home_assistant_folder
        assert home_assistant_folder() == "/homeassistant"


def test_home_assistant_folder_not_mounted():
    """None quando nessuno dei due percorsi somiglia alla configurazione HA."""
    exists_patch, isdir_patch = _patch_ha_mounted(None)
    with exists_patch, isdir_patch:
        from hiris.app.home_space.redaction import home_assistant_folder
        assert home_assistant_folder() is None


# ---------------------------------------------------------------------------
# Il cablaggio: il compito dell'installazione la chiama, dopo il nucleo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l_installazione_disinstalla_la_card_dopo_la_voce_di_menu(monkeypatch,
                                                                       tmp_path):
    """`install` (il compito che `create_app` avvia dopo `_on_startup`) chiama
    la disinstallazione col client dell'app e la cartella dei dati.

    Mutazione ESEGUITA (13/10/2026): tolta da `install` la chiamata a
    `disinstalla_card_lovelace` -- rossa (`Awaited 0 times`)."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token-del-supervisor")
    ha = _casa([])
    ha.ws_ready.set()
    app = {"ha_client": ha, "data_dir": str(tmp_path), "non_admin_access": False}
    ordine = []

    async def voce(_app):
        ordine.append("voce")

    async def card(client, data_dir):
        ordine.append(("card", client, data_dir))

    monkeypatch.setattr(installation, "sync_panel_visibility", voce)
    monkeypatch.setattr(installation, "disinstalla_card_lovelace", card)
    await installation.install(app)

    assert ordine == ["voce", ("card", ha, str(tmp_path))]



@pytest.mark.asyncio
async def test_la_card_aspetta_il_nucleo_anche_quando_la_voce_di_menu_esce_subito(
        monkeypatch, tmp_path):
    """Senza slug la voce di menu esce subito, senza aspettare lei il nucleo.
    La card no: chiede `lovelace/resources` solo a nucleo collegato, o la
    domanda andrebbe a un Home Assistant che non c'e' ancora, il segno non si
    scriverebbe e il tentativo si perderebbe fino all'avvio dopo (N148-2,
    giro 148).

    Mutazione ESEGUITA (13/10/2026): `pass` al posto dell'attesa di
    `ws_ready` in `install` -- rossa (la card chiede le risorse prima)."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "token-del-supervisor")
    ha = _casa([], slug=SILENT)
    app = {"ha_client": ha, "data_dir": str(tmp_path), "non_admin_access": False}

    compito = asyncio.create_task(installation.install(app))
    for _ in range(20):
        await asyncio.sleep(0)
    chieste = [t for t, _ in ha.calls]
    assert "supervisor /addons/self/info" in chieste, "precondizione: lo slug e' stato chiesto"
    assert "lovelace/resources" not in chieste, chieste

    ha.ws_ready.set()
    await asyncio.wait_for(compito, timeout=5)
    assert "lovelace/resources" in [t for t, _ in ha.calls]

# ---------------------------------------------------------------------------
# A-40 (Tappa 2, Task 11) — una cartella sola: quella di `home_space/redaction`
# ---------------------------------------------------------------------------

def test_rimuovi_file_card_cerca_la_cartella_dove_la_cerca_il_sigillo(tmp_path, monkeypatch):
    """La disinstallazione trova la cartella di Home Assistant nello stesso
    posto in cui la trova il sigillo dei segreti: `redaction._FOLDERS`. Fino
    al 03/10/2026 `server` aveva una sua copia della ricerca
    (`_find_ha_config_dir`), e spostare l'elenco in un punto non lo spostava
    nell'altro."""
    from hiris.app.home_space import redaction
    (tmp_path / "configuration.yaml").write_text("", encoding="utf-8")
    cartella = tmp_path / "www" / SLUG
    cartella.mkdir(parents=True)
    (cartella / "hiris-chat-card.js").write_text("// card", encoding="utf-8")
    monkeypatch.setattr(redaction, "_FOLDERS", (str(tmp_path),))

    installation._rimuovi_file_card(SLUG)

    assert not (cartella / "hiris-chat-card.js").exists()
