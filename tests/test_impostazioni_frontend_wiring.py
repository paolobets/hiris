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


def _senza_commenti_js(testo: str) -> str:
    r"""Il sorgente JS coi commenti a blocco sostituiti da spazi.

    Fix round 1, I-3 (la variante lieve). Queste guardie sono testuali, quindi
    un COMMENTO che nomina la cosa cercata le soddisfa esattamente come il
    codice vero -- lo stesso vizio per cui la guardia su `salva()` e' passata
    all'AST. Qui l'AST non c'e' (non si vuole un parser JavaScript in questa
    suite per tre `assert`), ma togliere i commenti chiude la falla concreta:
    ogni commento di `static/config/*.js` in questo repo e' un blocco
    `/* ... */`, e i due file guardati qui non fanno eccezione.

    Limite dichiarato, non nascosto: i commenti di riga `// ...` NON vengono
    tolti, perche' toglierli con una regex mangerebbe le barre dentro le
    stringhe e i letterali di espressione regolare (`/^#\/impostazioni\/?$/`).
    Se un giorno questi file ne usassero, la guardia tornerebbe soddisfabile
    da un commento di riga. Un `assert` qui sotto lo pinna, cosi' il limite si
    accorge da solo di essere stato superato.
    """
    return re.sub(r"/\*.*?\*/", " ", testo, flags=re.DOTALL)


def _senza_commenti_html(testo: str) -> str:
    """L'HTML coi commenti sostituiti da spazi, stessa ragione di sopra."""
    return re.sub(r"<!--.*?-->", " ", testo, flags=re.DOTALL)


HTML = _senza_commenti_html((BASE / "config.html").read_text(encoding="utf-8"))
MAIN = _senza_commenti_js((BASE / "config" / "main.js").read_text(encoding="utf-8"))
ROUTE = _senza_commenti_js((BASE / "config" / "impostazioni-route.js").read_text(encoding="utf-8"))


def test_i_due_file_guardati_non_usano_commenti_di_riga():
    """Il presupposto di `_senza_commenti_js`, verificato invece che sperato.

    Si cerca `//` a inizio riga (dopo spazi): e' la forma che un commento di
    riga assume in questo stile di codice, e nessuna stringa o regex letterale
    puo' cominciare cosi'."""
    for nome, testo in (("main.js", "config/main.js"),
                        ("impostazioni-route.js", "config/impostazioni-route.js")):
        grezzo = (BASE / testo).read_text(encoding="utf-8")
        righe = [i for i, r in enumerate(grezzo.splitlines(), 1) if r.lstrip().startswith("//")]
        assert not righe, (
            f"{nome} usa commenti di riga alle righe {righe}: le guardie testuali "
            "di questo file tornerebbero soddisfabili da un commento -- vedi "
            "_senza_commenti_js"
        )


def test_lo_script_e_dichiarato_in_config_html():
    """Come ogni altro modulo di config: `<script src>` statico, cosi'
    `_inject_version` (server.py) lo fingerprinta per conto suo e il
    cache-busting per-file funziona senza bump di versione."""
    assert "config/impostazioni-route.js" in HTML


def test_la_voce_di_menu_esiste_e_punta_alla_route():
    # Il tag di apertura non e' piu' scritto per intero nel pattern: pretendeva
    # che gli attributi fossero esattamente quei tre, in quell'ordine, e cadeva
    # appena la voce ne guadagnava uno -- come e' successo quando ogni voce ha
    # preso `title`/`aria-label` (sotto i 1024 px la barra si stringe e le
    # etichette spariscono: senza quei due attributi restano sei icone senza
    # nome). Il soggetto del test resta lo stesso: che la voce esista, che
    # punti a quella route e che porti quel testo.
    voce = re.search(r'<a class="nav-item"[^>]*href="#/impostazioni"[^>]*>.*?</a>', HTML, re.DOTALL)
    assert voce, "senza voce di nav la pagina esisterebbe e nessuno la troverebbe"
    assert 'data-route="impostazioni"' in voce.group(0)
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


def test_la_pagina_nomina_l_unica_rotta_che_usa():
    """fetta "la catena diventa l'unica verita'" (Task 4): erano due. La
    seconda (`api/models`) alimentava il selettore del modello, che scavalcava
    la catena della pagina Modelli ed e' uscito: questa pagina non ha piu'
    nessuna ragione di conoscere i provider. `ROUTE` e' il sorgente SENZA
    commenti a blocco, quindi la menzione di `api/models` nell'intestazione
    del file -- che racconta perche' e' uscita -- non soddisfa questo
    assert."""
    assert "api/impostazioni-chat" in ROUTE
    assert "api/models" not in ROUTE


def test_la_pagina_dice_quando_ha_effetto_il_salvataggio():
    """L'effetto e' immediato (il PUT riassegna `app["impostazioni_chat"]`), e
    va detto in pagina -- non solo nel report del task: senza, l'utente non ha
    modo di sapere se deve riavviare l'add-on."""
    assert "non serve riavviare" in ROUTE
