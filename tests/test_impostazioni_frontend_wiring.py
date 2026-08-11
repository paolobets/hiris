"""fetta E5 Task 2: la pagina `#/impostazioni` esiste E si raggiunge.

Guardie di WIRING (testo sul sorgente), stessa forma di
`tests/test_models_frontend_wiring.py` e famiglia. La copertura
COMPORTAMENTALE (mount, GET che popola i campi, Salva che manda il PUT con
l'header, l'errore che si vede) vive in `tests/js/impostazioni-route.test.mjs`
sotto `npm test`.

Il motivo per cui questo file esiste separato dai test dell'API: una rotta che
salva e una pagina che la chiama non servono a niente se la pagina non e'
raggiungibile. Le tre cose che la rendono raggiungibile -- lo `<script src>`,
la voce di nav, la `HirisRouter.register` -- stanno in tre file diversi, e
dimenticarne una non fa fallire nessun altro test.
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"
HTML = (BASE / "config.html").read_text(encoding="utf-8")
MAIN = (BASE / "config" / "main.js").read_text(encoding="utf-8")
ROUTE = (BASE / "config" / "impostazioni-route.js").read_text(encoding="utf-8")


def test_lo_script_e_dichiarato_in_config_html():
    """Come ogni altro modulo di config: `<script src>` statico, cosi'
    `_inject_version` (server.py) lo fingerprinta per conto suo e il
    cache-busting per-file funziona senza bump di versione."""
    assert "config/impostazioni-route.js" in HTML


def test_la_voce_di_menu_esiste_e_punta_alla_route():
    voce = re.search(r'<a class="nav-item" href="#/impostazioni" data-route="impostazioni">'
                     r'.*?</a>', HTML, re.S)
    assert voce, "senza voce di nav la pagina esisterebbe e nessuno la troverebbe"
    assert "Impostazioni chat" in voce.group(0)


def test_main_registra_la_route_e_monta_il_modulo():
    assert re.search(r"HirisRouter\.register\(/\^#\\/impostazioni", MAIN), \
        "la route #/impostazioni deve essere registrata in main.js"
    assert "HirisImpostazioniRoute.mount()" in MAIN


def test_updatenavactive_conosce_impostazioni_e_non_ha_piu_il_ramo_orfano():
    """Il ramo `settings` di `updateNavActive()` era orfano: nessuna voce di
    nav con `data-route="settings"` (tolta in v0.10.5) e nessuna route
    `#/settings` registrata. Diventa il ramo di `impostazioni`; non ne restano
    due."""
    assert "route === 'impostazioni'" in MAIN
    assert "route === 'settings'" not in MAIN
    assert 'data-route="settings"' not in HTML


def test_la_pagina_non_dipende_dai_moduli_che_escono_al_task_6():
    """`editor-kit.js`, `entity-picker.js` e `templates.js` escono al Task 6 di
    questa fetta: una pagina nuova che ci si appoggiasse nascerebbe gia'
    condannata."""
    for morituro in ("HirisEditorKit", "HirisEntityPicker", "TOOLS", "KNOWLEDGE_KINDS"):
        assert morituro not in ROUTE, f"{morituro} esce al Task 6: la pagina non deve usarlo"


def test_la_pagina_manda_l_header_csrf_su_ogni_scrittura():
    """Senza `X-Requested-With` il PUT si prende un 403 da `csrf_middleware`.
    L'header e' impostato in un punto solo (`api()`), e i `fetch` diretti non
    devono esistere: e' il modo esatto in cui questa pagina smetterebbe di
    salvare."""
    assert "'X-Requested-With': 'fetch'" in ROUTE
    assert "fetch(" in ROUTE
    # L'unico `fetch(` diretto ammesso e' quello DENTRO il wrapper api().
    assert len(re.findall(r"\bfetch\(", ROUTE)) == 1


def test_la_pagina_nomina_le_due_rotte_che_usa():
    assert "api/impostazioni-chat" in ROUTE
    assert "api/models" in ROUTE


def test_la_pagina_dice_quando_ha_effetto_il_salvataggio():
    """L'effetto e' immediato (il PUT riassegna `app["impostazioni_chat"]`), e
    va detto in pagina -- non solo nel report del task: senza, l'utente non ha
    modo di sapere se deve riavviare l'add-on."""
    assert "non serve riavviare" in ROUTE
