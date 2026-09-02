"""«C'e' qualcosa che non va in casa?»

Fino a questa fetta HIRIS sapeva contare le entita' non disponibili. Home
Assistant tiene un registro dei problemi che ha GIA' diagnosticato, con la
severita', se sa ripararli da solo e in quale versione qualcosa si rompera':
`repairs/list_issues`, letto da `HAClient.problems()`.

Queste prove sorvegliano tre difetti, e sono tre difetti diversi:

1. **il silenzio** -- un guasto diagnosticato che non arriva al modello, o un
   guasto di LETTURA raccontato come una casa sana;
2. **il rumore** -- due o tre `repairs` innocui ripetuti in ogni prompt, che
   insegnano a chi legge a saltare quella riga e rendono invisibile il guasto
   vero il giorno che arriva;
3. **il filtro silenzioso** -- tacere senza dire quanto si e' taciuto, che e'
   solo un modo piu' educato di mentire.

Ognuna di queste prove sa PRODURRE il difetto che sorveglia: togliere il filtro
fa fallire il gruppo 2, togliere il conteggio fa fallire il gruppo 3, togliere
il ramo dell'errore fa fallire il gruppo 1.
"""
import asyncio

import pytest

from hiris.app.api.handlers_home_space import compose_briefing
from hiris.app.home_space.briefing import compose
from hiris.app.proxy.ha_client import HAClient
from hiris.app.server import reread_ha_problems


def _nucleo(problemi):
    """Il nucleo di una casa vuota: qui interessa solo la sezione dei guasti."""
    return compose({"entita": [], "integrazioni": []}, [], [], {},
                   problems=problemi)


def _p(**campi):
    """Una riga del registro dei problemi nella forma in cui HA la manda.

    I nomi dei campi sono quelli veri di `ws_list_issues`
    (`components/repairs/websocket_api.py`), verificati alla fonte: se qualcuno
    li italianizzasse a meta' strada, queste prove smetterebbero di dire
    qualcosa sulla realta'.
    """
    riga = {"domain": "una_integrazione", "issue_id": "un_problema",
            "severity": "error", "is_fixable": False,
            "breaks_in_ha_version": None, "translation_key": None,
            "translation_placeholders": None, "learn_more_url": None}
    riga.update(campi)
    return riga


# --------------------------------------------------------------------------
# 1. Il silenzio
# --------------------------------------------------------------------------

def test_un_guasto_diagnosticato_arriva_al_modello():
    testo, riepilogo = _nucleo({"problemi": [
        _p(domain="zwave_js", issue_id="ozw_migration", severity="critical",
           translation_key="ozw_migration"),
    ]})
    assert "zwave_js" in testo
    assert "ozw_migration" in testo
    assert "critical" in testo
    assert any("zwave_js" in g for g in riepilogo["faults"])


def test_un_guasto_di_lettura_non_e_una_casa_sana():
    """Il difetto peggiore di tutti: HA non risponde, e HIRIS tace come se non
    ci fosse niente di rotto. Un elenco vuoto qui significherebbe «non c'e'
    niente che non va» -- un'affermazione, non un silenzio."""
    testo, riepilogo = _nucleo({"errore": "Home Assistant non ha risposto"})
    assert "Home Assistant non ha risposto" in testo
    assert "non si e' potuto guardare" in testo
    assert any("non si e' potuto guardare" in g for g in riepilogo["faults"])


def test_il_registro_non_letto_non_e_il_registro_vuoto():
    """`None` (nessuno ha chiesto) e `{"errore": ...}` (si e' chiesto e non si
    e' potuto leggere) NON possono produrre lo stesso nucleo: il secondo e' una
    lacuna da dichiarare, il primo no."""
    non_chiesto, riepilogo_non_chiesto = _nucleo(None)
    non_letto, riepilogo_non_letto = _nucleo({"errore": "rifiutato"})
    assert non_chiesto != non_letto
    assert riepilogo_non_chiesto["faults"] == []
    # «Non ho potuto leggere i guasti» e' esso stesso un fatto sulla salute
    # della casa, non un limite generico di cio' che HIRIS sa: sta fra i
    # guasti, dove chi chiede «come sta la casa» lo trova.
    assert any("rifiutato" in g for g in riepilogo_non_letto["faults"])


def test_una_severita_che_non_si_sa_giudicare_non_si_tace():
    """`severity` e' `IssueSeverity | None` (`helpers/issue_registry.py`,
    verificato): puo' mancare, e Home Assistant puo' aggiungerne di nuove.

    La soglia e' scritta come «cosa si tace» proprio per questo. Se fosse un
    elenco di severita' da DIRE, tutto cio' che non conosciamo finirebbe
    silenziato di default -- un problema taciuto perche' non lo si e' saputo
    leggere e' la stessa bugia che questa fetta chiude."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="mqtt", issue_id="silenzio", severity=None),
        _p(domain="hue", issue_id="novita", severity="catastrophic"),
    ]})
    assert "mqtt" in testo and "silenzio" in testo
    assert "hue" in testo and "novita" in testo
    assert "severita' non dichiarata" in testo


# --------------------------------------------------------------------------
# 2. Il rumore
# --------------------------------------------------------------------------

def test_i_warning_innocui_non_si_elencano_a_ogni_messaggio():
    """Molte case hanno stabilmente due o tre `repairs` aperti e innocui. Se il
    nucleo li ripete per nome in ogni prompt, chi legge smette di leggerli."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="hue", issue_id="deprecated_yaml", severity="warning"),
        _p(domain="tuya", issue_id="deprecated_yaml", severity="warning"),
        _p(domain="mqtt", issue_id="deprecated_yaml", severity="warning"),
    ]})
    assert "hue" not in testo
    assert "tuya" not in testo
    assert "deprecated_yaml" not in testo


def test_un_registro_vuoto_non_produce_nessuna_riga():
    """L'altra meta' del rumore: una casa senza guasti non deve spendere una
    riga per dirlo. Stessa scelta di `_integrations_notice` su una casa sana."""
    testo, riepilogo = _nucleo({"problemi": []})
    assert "Riparazioni" not in testo
    assert riepilogo["faults"] == []


def test_i_guasti_hanno_una_SEZIONE_PROPRIA_prima_di_notevole_adesso():
    """Non fra le lacune, e non in «Notevole adesso».

    Sono CONDIZIONI, non eventi: restano vere finche' qualcuno non le ripara,
    e in «Notevole adesso» annuncerebbero a ogni messaggio una cosa che non e'
    successa adesso.

    Ma NEMMENO sotto «Cio' che HIRIS ignora», dov'erano fino al 2026-08-18: un
    modello che legge quel titolo capisce «roba che non so, non da riferire».
    Davanti a una casa vera con 77 entita' mute e nove integrazioni cadute --
    col motivo scritto -- ha riportato il SINTOMO e taciuto la CAUSA. Non era
    un errore suo: era il titolo a dire il falso. Nove integrazioni rotte non
    sono cio' che HIRIS ignora, sono cio' che HIRIS SA e deve dire.

    L'ordine di lettura e': com'e' fatta la casa -> cosa e' rotto -> cosa sta
    succedendo.
    """
    testo, _ = _nucleo({"problemi": [
        _p(domain="reolink", issue_id="autenticazione", severity="error"),
    ]})
    assert "## Cosa non va in casa" in testo
    prima_dei_guasti, dai_guasti = testo.split("## Cosa non va in casa")
    assert "reolink" in dai_guasti
    assert "reolink" not in prima_dei_guasti

    # PRIMA di «Notevole adesso», DOPO «La casa».
    assert testo.index("## La casa") < testo.index("## Cosa non va in casa")
    assert testo.index("## Cosa non va in casa") < testo.index("## Notevole adesso")

    # E NON fra le lacune: e' li' che si perdeva.
    lacune = testo.split("## Cio' che HIRIS ignora")[1]
    assert "reolink" not in lacune


def test_una_casa_sana_non_ha_la_sezione_dei_guasti():
    """Il contrario, e serve quanto l'altra: un'intestazione «Cosa non va in
    casa» che compare sempre -- vuota o con dentro un «nessun problema» --
    e' una domanda posta a ogni messaggio a cui la risposta e' sempre no.
    Smette di essere letta, e il giorno del guasto vero non si distingue."""
    testo, riepilogo = _nucleo({"problemi": []})
    assert "## Cosa non va in casa" not in testo
    assert riepilogo["faults"] == []


def test_il_tetto_conta_cio_che_non_elenca():
    """Gli avvisi non passano per il taglio di `compose()`: venti guasti gravi
    produrrebbero un avviso che niente puo' accorciare, dentro un nucleo che ha
    seimila caratteri in tutto. Si citano i primi, si CONTANO gli altri."""
    testo, _ = _nucleo({"problemi": [
        _p(domain=f"integrazione_{n}", issue_id=f"guasto_{n}", severity="error")
        for n in range(9)
    ]})
    assert "Home Assistant ha gia' diagnosticato 9 problemi" in testo
    assert "e altri 4 problemi della stessa lista, non elencati" in testo
    assert "integrazione_8" not in testo


def test_i_piu_gravi_non_finiscono_sotto_il_tetto():
    """Il tetto taglia dalla coda: senza un ordine per gravita', cinque
    `warning` in scadenza arrivati prima nasconderebbero il `critical`.

    L'ordine non e' riscritto nel nucleo -- e' `HAClient.PROBLEM_SEVERITY`,
    che dichiara di essere ordinata dalla piu' grave."""
    assert HAClient.PROBLEM_SEVERITY[0] == "critical"
    testo, _ = _nucleo({"problemi": [
        _p(domain=f"rumore_{n}", issue_id=f"scadenza_{n}", severity="warning",
           breaks_in_ha_version="2027.1")
        for n in range(6)
    ] + [
        _p(domain="caldaia", issue_id="la_cosa_grave", severity="critical"),
    ]})
    assert "la_cosa_grave" in testo


def test_due_letture_identiche_producono_lo_stesso_nucleo():
    """HA manda le righe in ordine arbitrario. Un nucleo che cambia a ogni
    lettura senza che la casa sia cambiata butta via la cache del prompt e
    fa sembrare successo qualcosa che non e' successo."""
    righe = [
        _p(domain="beta", issue_id="uno", severity="error"),
        _p(domain="alfa", issue_id="due", severity="error"),
        _p(domain="alfa", issue_id="tre", severity="error"),
    ]
    primo, _ = _nucleo({"problemi": list(righe)})
    secondo, _ = _nucleo({"problemi": list(reversed(righe))})
    assert primo == secondo


# --------------------------------------------------------------------------
# 3. Il filtro silenzioso
# --------------------------------------------------------------------------

def test_quanti_se_ne_sono_taciuti_si_dichiara_sempre():
    """Filtrare e' giusto; filtrare in silenzio e' un altro modo di mentire.
    Il modello perde il TESTO del warning, non la possibilita' di sapere che
    esiste -- ed e' esattamente la priorita' che il modulo dichiara."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="hue", issue_id="a", severity="warning"),
        _p(domain="tuya", issue_id="b", severity="warning"),
    ]})
    assert "2 problemi aperti di severita' minore" in testo
    assert "Impostazioni -> Riparazioni" in testo


def test_i_taciuti_si_dichiarano_anche_accanto_a_un_guasto_grave():
    """Il caso che si dimentica: c'e' qualcosa di grave da dire, e la coda dei
    taciuti sparisce dietro di esso."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="caldaia", issue_id="grave", severity="critical"),
        _p(domain="hue", issue_id="a", severity="warning"),
        _p(domain="tuya", issue_id="b", severity="warning"),
        _p(domain="mqtt", issue_id="c", severity="warning"),
    ]})
    assert "grave" in testo
    assert "Altri 3 problemi di severita' minore non sono elencati" in testo


def test_al_singolare_la_frase_concorda_per_intero():
    """Non e' pignoleria: concordare una desinenza per volta produce «Altri 1
    problema non sono elencato», che e' il nucleo che sembra rotto proprio
    mentre parla di cose rotte. Stessa disciplina di `_cut_notice`."""
    solo_taciuto, _ = _nucleo({"problemi": [
        _p(domain="hue", issue_id="a", severity="warning"),
    ]})
    assert "1 problema aperto di severita' minore" in solo_taciuto
    assert "non e' elencato qui, si legge in" in solo_taciuto

    uno_grave, _ = _nucleo({"problemi": [
        _p(domain="caldaia", issue_id="grave", severity="critical"),
    ]})
    assert "diagnosticato 1 problema:" in uno_grave
    assert "Si legge per esteso e si ripara in" in uno_grave

    uno_oltre_il_tetto, _ = _nucleo({"problemi": [
        _p(domain=f"d{n}", issue_id=f"i{n}", severity="error") for n in range(6)
    ]})
    assert "e un altro problema della stessa lista, non elencato." in uno_oltre_il_tetto

    # Il caso che sfugge: un solo taciuto ACCANTO a qualcosa di grave. E' la
    # coda della frase lunga, non la frase corta di sopra -- sono due rami
    # diversi, e uno solo dei due era coperto.
    grave_piu_un_taciuto, _ = _nucleo({"problemi": [
        _p(domain="caldaia", issue_id="grave", severity="critical"),
        _p(domain="hue", issue_id="a", severity="warning"),
    ]})
    assert ("Un altro problema di severita' minore non e' elencato"
            in grave_piu_un_taciuto)


def test_un_warning_con_una_scadenza_non_e_un_consiglio():
    """`breaks_in_ha_version` cambia la natura del problema: non e' un consiglio,
    e' una data in cui la casa si rompe da sola. L'unico momento in cui saperlo
    serve e' PRIMA, e la severita' da sola non lo direbbe mai."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="template", issue_id="legacy", severity="warning",
           translation_key="formato_vecchio", breaks_in_ha_version="2026.12"),
    ]})
    assert "template" in testo
    assert "formato_vecchio" in testo
    assert "si rompe in 2026.12" in testo
    assert "severita' minore" not in testo


def test_riparabile_da_solo_si_dice_perche_cambia_cosa_si_puo_fare():
    testo, _ = _nucleo({"problemi": [
        _p(domain="reolink", issue_id="riautentica", severity="error",
           is_fixable=True),
    ]})
    assert "Home Assistant sa ripararlo da solo" in testo


def test_is_fixable_assente_non_e_un_no():
    """`is_fixable` e' `bool | None`: `None` significa «HA non lo dice», non
    «no». Si annota solo il si'."""
    testo, _ = _nucleo({"problemi": [
        _p(domain="reolink", issue_id="boh", severity="error", is_fixable=None),
    ]})
    assert "reolink" in testo
    assert "ripararlo da solo" not in testo


# --------------------------------------------------------------------------
# La catena: dall'app fino al testo, senza rete
# --------------------------------------------------------------------------

def test_il_nucleo_legge_i_problemi_dalla_memoria_dell_app():
    """La catena intera: `app["problemi_ha"]` -> `compose_briefing` ->
    `compose`. Senza questo cablaggio la lettura di `server.py` sarebbe un dato
    scritto e mai letto -- la quarta fondamenta al contrario."""
    app = {"problemi_ha": {"problemi": [
        _p(domain="caldaia", issue_id="pressione", severity="critical"),
    ]}}
    testo, _ = compose_briefing(app)
    assert "caldaia" in testo
    assert "pressione" in testo


def test_senza_la_chiave_il_nucleo_non_afferma_che_la_casa_e_sana():
    testo, _ = compose_briefing({})
    assert "Riparazioni" not in testo


def test_rileggi_problemi_mette_la_fotografia_in_ram():
    """Vive in RAM e non in archivio: un `repair` e' momentaneo, e un archivio
    riletto solo sugli eventi dei registri -- che il registro dei problemi NON
    emette -- lo annuncerebbe per ore dopo che l'utente l'ha riparato."""

    class _ClienteFinto:
        async def problems(self):
            return {"problemi": [_p(domain="caldaia", issue_id="x")]}

    app: dict = {}
    esito = asyncio.run(reread_ha_problems(app, _ClienteFinto()))
    assert esito == app["problemi_ha"]
    assert app["problemi_ha"]["problemi"][0]["domain"] == "caldaia"


def test_rileggi_problemi_porta_l_errore_invece_di_inghiottirlo():
    """Un guasto di lettura e' un'informazione da consegnare al modello, non
    un'eccezione da far sparire nello schedulatore."""

    class _ClienteRotto:
        async def problems(self):
            return {"errore": "Home Assistant non ha risposto"}

    app: dict = {}
    asyncio.run(reread_ha_problems(app, _ClienteRotto()))
    assert app["problemi_ha"] == {"errore": "Home Assistant non ha risposto"}
    testo, _ = compose_briefing(app)
    assert "non si e' potuto guardare" in testo


def test_un_client_che_non_sa_leggere_i_problemi_non_scrive_niente():
    """Un finto di prova (o un client vecchio) senza `problemi`: la chiave
    resta assente, e il nucleo tace invece di affermare che la casa e' sana --
    l'unico caso in cui tacere non afferma nulla."""

    class _ClienteVecchio:
        pass

    app: dict = {}
    assert asyncio.run(reread_ha_problems(app, _ClienteVecchio())) is None
    assert "problemi_ha" not in app
    assert asyncio.run(reread_ha_problems(app, None)) is None


@pytest.mark.parametrize("problemi", [
    None,
    {"errore": "rifiutato"},
    {"problemi": [_p(domain="caldaia", issue_id="x", severity="critical")]},
])
def test_componi_resta_pura(problemi):
    """La proprieta' su cui poggiano tutte le prove di `compose()`: i problemi
    arrivano come ARGOMENTO, come `stato` e `sistema_di_riferimento`. Se
    qualcuno ci mettesse dentro una chiamata di rete, questa prova girerebbe
    dentro un loop asyncio gia' in corso e la chiamata esploderebbe."""

    async def _dentro_un_loop():
        return _nucleo(problemi)

    testo, riepilogo = asyncio.run(_dentro_un_loop())
    assert isinstance(testo, str) and "chars" in riepilogo
