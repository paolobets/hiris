"""Il resoconto **come lo legge la pagina**: il nome sempre, e il primo piano.

Spec `docs/design/2026-09-18-la-pagina-dell-osservatore.md` §3.

**Il resoconto scritto non si tocca.** Nome risolto, marchio «fuori dal solito»
e raggruppamenti nascono quando la pagina legge, e la ragione e' una regola
della fetta dei giudizi: la cronaca salvata si rifa' solo quando cambia il
giudizio, e l'impronta dice quali giorni rifare. Se «esce dal solito» finisse
nella cronaca salvata, il giorno in cui cambiamo idea su cosa merita il primo piano
-- e cambieremo idea -- servirebbe rifare ventidue giorni per una decisione che
col sapere non c'entra.

**Il criterio non e' qui.** `as_page` non contiene nessun elenco di tipi ne' di
generi: chiede al sapere (`TypeJudgments.stato_da_sapere_subito`, la fetta
`2026-09-18-da-sapere-subito.md`) e cita il livello che Home Assistant scrive
da se'. La prova che lo custodisce e'
`test_cambiare_il_GIUDIZIO_cambia_la_primo_piano_senza_toccare_il_codice`.

**Misurato sulla cronaca vera del 17/09/2026** (75 voci, casa alla 3.49.0):
entrano in primo piano **6 righe** -- 4 `guasto` e 2 `avviso`, tutte di sistema -- e
nessun episodio di entita'. L'unica voce di genere `sicurezza` di quel giorno
e' l'allarme `disarmed`, che e' la normalita' di una casa e resta fuori; le
57 voci il cui TIPO e' `notevole: si` (il criterio del *briefing*, un'altra
domanda) sarebbero state la pagina intera.
"""

import pytest

from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.type_judgments import TypeJudgments
from hiris.app.mind.report import as_page


def _giudizi(*righe):
    """Il seme del repo con sopra le righe che la casa scrive.

    **Sostituisce per chiave, non accoda**, come fa l'archivio vero: la chiave
    primaria del sapere e' `(genere, soggetto, campo)`, e due righe sulla
    stessa chiave `from_rows` le rifiuta entrambe. Una finta che accodasse
    renderebbe impossibile provare la CORREZIONE di una riga del seme, che e'
    il caso che conta.
    """
    per_chiave = {(k, s, c): (k, s, c, v)
                  for k, s, c, v in tv.judgment_seed_rows()}
    for k, s, c, v in righe:
        per_chiave[(k, s, c)] = (k, s, c, v)
    return TypeJudgments.from_rows(tuple(per_chiave.values()),
                                   genres=tv.CHRONICLE_GENRES,
                                   absent_forms=tv.ABSENT_STATE_FORMS.value)


def _resoconto(*voci, giorno="2026-09-17"):
    return {"giorno": giorno, "obiettivo": "l'efficientamento energetico",
            "misure": [], "forme": [], "cronaca": list(voci)}


def _guasto(chi, cosa="ERROR", *, quando_ts=1.0, fine_ts=None, titolo=None, dominio=None):
    voce = {"quando_ts": quando_ts, "fine_ts": fine_ts, "chi": chi,
            "genere": "guasto", "cosa": cosa}
    if titolo:
        voce["titolo"] = titolo
    if dominio:
        voce["dominio"] = dominio
    return voce


def _episodio(chi, cosa, *, genere="funzionamento", quando_ts=1.0, fine_ts=None,
              nome=None, classe=None):
    voce = {"quando_ts": quando_ts, "fine_ts": fine_ts, "chi": chi,
            "genere": genere, "cosa": cosa}
    if nome:
        voce["nome"] = nome
    if classe:
        voce["classe"] = classe
    return voce


# ---------------------------------------------------------------------------
# Il nome, sempre. «Nessuna pagina inventa un nome»: chi lo ha lo tiene, chi
# non ce l'ha lo prende da cio' che la voce gia' porta, e chi non ha neanche
# quello resta senza -- l'identificativo grezzo e' la verita', un nome dedotto
# dall'identificatore no.
# ---------------------------------------------------------------------------

def test_una_voce_di_log_prende_il_nome_dal_DOMINIO_che_gia_porta():
    """Misurato il 18/09: 7 voci su 75 senza `nome`, ed erano i 6 guasti e
    l'allarme. La pagina mostrava al loro posto
    `log:homeassistant.components.hassio.handler@components/hassio/handler.py:108`.

    Mutazione: togliere il ramo del dominio -- rossa (nome assente)."""
    pagina = as_page(_resoconto(_guasto(
        "log:homeassistant.components.hydrawise@helpers/update_coordinator.py:447",
        titolo="Timeout fetching hydrawise data",
        dominio="homeassistant.components.hydrawise")), judgments=_giudizi())
    assert pagina["cronaca"][0]["nome"] == "Hydrawise"


def test_un_log_di_componente_CUSTOM_prende_il_nome_dell_integrazione_non_della_piattaforma():
    """`custom_components.alarmo.alarm_control_panel` e' Alarmo, non
    «Alarm control panel»: l'integrazione e' il secondo segmento, la
    piattaforma il terzo. Misurato: la riga vera dell'allarme del 17/09.

    Mutazione: prendere l'ultimo segmento invece dell'integrazione -- rossa."""
    pagina = as_page(_resoconto(_guasto(
        "log:custom_components.alarmo.alarm_control_panel@custom_components/alarmo/x.py:1140",
        cosa="WARNING", titolo="Alarm is triggered!",
        dominio="custom_components.alarmo.alarm_control_panel")), judgments=_giudizi())
    assert pagina["cronaca"][0]["nome"] == "Alarmo"


def test_un_logger_che_non_e_ne_core_ne_custom_resta_il_suo_nome_intero():
    """`aioamazondevices` e' una libreria, non un'integrazione di Home
    Assistant: non c'e' un segmento da estrarre, e inventarne uno sarebbe
    peggio del nome vero. Misurato fra i 39 soggetti tecnici della casa.

    Mutazione: spezzare comunque sul punto -- rossa."""
    pagina = as_page(_resoconto(_guasto(
        "log:aioamazondevices@components/alexa_devices/coordinator.py:191",
        dominio="aioamazondevices")), judgments=_giudizi())
    assert pagina["cronaca"][0]["nome"] == "Aioamazondevices"


def test_un_guasto_del_NUCLEO_di_home_assistant_si_chiama_col_nome_del_prodotto():
    """`homeassistant.helpers.entity` non nomina nessuna integrazione: il
    guasto viene da Home Assistant stesso, e «Homeassistant.helpers.entity»
    non e' il nome di niente. E' una citazione -- il prodotto si chiama cosi'
    -- non una resa inventata. Misurato: la riga WARNING vera del 17/09.

    Mutazione: la regola meccanica senza questo ramo -- rossa."""
    pagina = as_page(_resoconto(_guasto(
        "log:homeassistant.helpers.entity@helpers/entity.py:1265", cosa="WARNING",
        titolo="Updating state for climate.camera_t", dominio="homeassistant.helpers.entity")),
        judgments=_giudizi())
    assert pagina["cronaca"][0]["nome"] == "Home Assistant"


def test_la_riga_della_primo_piano_CITA_lo_stato_con_la_parola_della_cronaca():
    """Lo stato si cita, non si interpreta: «triggered», non «e' scattato»
    (renderli nella lingua della casa e' una fetta sua). E la chiave e' la
    stessa della cronaca -- `cosa` -- o sarebbero due nomi per un dato solo.

    Mutazione: rinominare la chiave -- rossa."""
    pagina = as_page(_resoconto(_episodio("alarm_control_panel.piano_terra", "triggered",
                                          genere="sicurezza", quando_ts=3.0, fine_ts=9.0)),
                     judgments=_giudizi())
    riga, = pagina["primo_piano"]
    assert riga["cosa"] == "triggered"
    assert riga["fine_ts"] == 9.0


def test_il_nome_ARCHIVIATO_vince_su_quello_di_oggi():
    """L'archivio dice cio' che sapeva, e il nome di ALLORA e' piu' vero: un
    dispositivo si puo' rinominare. Stessa regola di `_named` nelle rotte del
    cervello e di `series_of_measures`.

    Mutazione: sovrascrivere col nome vivo -- rossa."""
    pagina = as_page(_resoconto(_episodio("light.studio", "on", nome="Studio")),
                     judgments=_giudizi(), names={"light.studio": "Studio nuovo"})
    assert pagina["cronaca"][0]["nome"] == "Studio"


def test_un_entita_senza_nome_archiviato_prende_quello_VIVO():
    """Mutazione: ignorare `names` -- rossa (nome assente)."""
    pagina = as_page(_resoconto(_episodio("alarm_control_panel.piano_terra", "disarmed",
                                          genere="sicurezza")),
                     judgments=_giudizi(),
                     names={"alarm_control_panel.piano_terra": "Allarme piano terra"})
    assert pagina["cronaca"][0]["nome"] == "Allarme piano terra"


def test_un_entita_che_nessuno_conosce_resta_SENZA_nome():
    """**Nessuna pagina inventa un nome**: la pagina ha gia' la sua regola per
    quando il nome manca -- mostra l'identificativo DICENDO che e' un
    identificativo. Un nome dedotto dall'`entity_id` sarebbe un'invenzione.

    Mutazione: ripiegare su `chi` -- rossa."""
    pagina = as_page(_resoconto(_episodio("light.mai_vista", "on")),
                     judgments=_giudizi(), names={})
    assert "nome" not in pagina["cronaca"][0]


# ---------------------------------------------------------------------------
# Il primo piano: cio' che esce dal solito. Tre sorte -- `guasto`, `avviso`,
# `da_sapere_subito` -- e nessun criterio scritto qui.
# ---------------------------------------------------------------------------

def test_un_ERROR_di_sistema_e_un_guasto_in_primo_piano_con_la_frase_VERA():
    """La frase del guasto e' gia' nel dato (`titolo`, scritto da
    `mind/watcher.py` dal 12/09) e la pagina disegnava `ERROR`. Il titolo e'
    una CITAZIONE: resta nella lingua in cui Home Assistant l'ha scritto.

    Mutazione: mettere il livello al posto del titolo -- rossa."""
    pagina = as_page(_resoconto(_guasto(
        "log:x@a.py:1", titolo="Timeout fetching hydrawise data",
        dominio="homeassistant.components.hydrawise")), judgments=_giudizi())
    riga, = pagina["primo_piano"]
    assert riga["sorta"] == "guasto"
    assert riga["titolo"] == "Timeout fetching hydrawise data"
    assert riga["nome"] == "Hydrawise"


def test_un_WARNING_di_sistema_e_un_AVVISO_non_un_guasto():
    """Il livello lo scrive Home Assistant (`record.levelname`), non noi: qui
    si cita, non si giudica.

    Mutazione: una sorta sola per ogni voce di sistema -- rossa."""
    pagina = as_page(_resoconto(_guasto("log:x@a.py:1", cosa="WARNING",
                                        dominio="homeassistant.components.x")),
                     judgments=_giudizi())
    assert pagina["primo_piano"][0]["sorta"] == "avviso"


def test_un_livello_che_non_conosciamo_NON_si_declassa_ad_avviso():
    """`CRITICAL` non e' un avviso. Un livello ignoto pesa come un guasto: la
    primo piano puo' portare una riga in piu', mai una in meno.

    Mutazione: `avviso` come ripiego -- rossa."""
    pagina = as_page(_resoconto(_guasto("log:x@a.py:1", cosa="CRITICAL",
                                        dominio="homeassistant.components.x")),
                     judgments=_giudizi())
    assert pagina["primo_piano"][0]["sorta"] == "guasto"


def test_l_allarme_DISARMED_non_entra_in_primo_piano():
    """**Il caso vero del 17/09**, e quello che ha fatto scartare una stesura
    intera della spec: l'allarme disinserito e' la normalita' di una casa.

    Mutazione: «il genere sicurezza entra sempre» -- rossa."""
    pagina = as_page(_resoconto(_episodio("alarm_control_panel.piano_terra", "disarmed",
                                          genere="sicurezza")),
                     judgments=_giudizi())
    assert pagina["primo_piano"] == []
    assert "primo_piano" not in pagina["cronaca"][0]


def test_l_allarme_TRIGGERED_entra_in_primo_piano_con_la_RAGIONE_scritta_nel_giudizio():
    """`perche` non e' una frase nostra: e' la ragione che il giudizio
    `lavoro` porta accanto allo stato (`type_vocabulary`, seme).

    Mutazione: scrivere una frase qui -- rossa (non combacia col seme)."""
    pagina = as_page(_resoconto(_episodio("alarm_control_panel.piano_terra", "triggered",
                                          genere="sicurezza")),
                     judgments=_giudizi())
    riga, = pagina["primo_piano"]
    assert riga["sorta"] == "da_sapere_subito"
    assert riga["perche"] == _giudizi().working_of("alarm_control_panel")["triggered"]


def test_una_LUCE_accesa_non_entra_in_primo_piano():
    """Dieci dei ventitre `notevole: si` del seme sono domini interi (`light`,
    `switch`, `cover`…): col criterio del briefing il 17/09 sarebbero finite
    in primo piano 71 voci su 75, e 35 erano accensioni di luce.

    Mutazione: leggere `is_notable` invece di `stato_da_sapere_subito` --
    rossa."""
    pagina = as_page(_resoconto(_episodio("light.studio", "on", nome="Studio")),
                     judgments=_giudizi())
    assert pagina["primo_piano"] == []


def test_la_serratura_INCEPPATA_entra_in_primo_piano_SENZA_ragione():
    """Il primo caso reale di riga notevole **muta**: `lock` porta
    `da_sapere_subito: ["jammed"]`, e un elenco non ha una ragione accanto --
    il `lavoro` della serratura parla di `unlocked`/`locking`, non di `jammed`.
    Una riga senza ragione si disegna lo stesso: e' il primo piano che decide, non
    la prosa.

    Mutazione: pretendere una ragione per entrare -- rossa."""
    pagina = as_page(_resoconto(_episodio("lock.ingresso", "jammed", genere="sicurezza")),
                     judgments=_giudizi())
    riga, = pagina["primo_piano"]
    assert riga["sorta"] == "da_sapere_subito"
    assert "perche" not in riga


def test_la_serratura_SBLOCCATA_non_entra_in_primo_piano():
    """La contropartita della prova qui sopra, e la ragione per cui l'elenco
    esiste: col solo `si` ogni sblocco sarebbe stato la prima riga e
    l'inceppamento no.

    Mutazione: il ramo dell'elenco messo DOPO il lavoro -- rossa."""
    pagina = as_page(_resoconto(_episodio("lock.ingresso", "unlocked", genere="sicurezza")),
                     judgments=_giudizi())
    assert pagina["primo_piano"] == []


def test_cambiare_il_GIUDIZIO_cambia_la_primo_piano_senza_toccare_il_codice():
    """**Il cancello di questa fetta** (spec §3): il criterio vive nei giudizi,
    quindi il proprietario puo' correggerlo dalla scheda «Cosa ho capito».
    Qui la casa dice «le luci accese voglio saperle subito», e la stessa voce
    che sopra resta fuori entra.

    Mutazione: un elenco di tipi o di generi dentro `as_page` -- rossa (la
    riscrittura del giudizio non sposterebbe niente)."""
    casa = _giudizi(("tipo", "light", "da_sapere_subito", "si"))
    pagina = as_page(_resoconto(_episodio("light.studio", "on", nome="Studio")),
                     judgments=casa)
    assert [r["sorta"] for r in pagina["primo_piano"]] == ["da_sapere_subito"]


def test_lo_stesso_guasto_ripetuto_e_UNA_riga_con_le_VOLTE():
    """L'osservatore apre un episodio nuovo a ogni sfarfallio -- misurato:
    25 episodi per UNA sola integrazione. In lettura si raggruppa, o il primo piano
    diventa il rumore che dovrebbe togliere.

    Mutazione: nessun raggruppamento -- rossa (tre righe invece di una)."""
    voci = [_guasto("log:x@a.py:1", titolo="Timeout", dominio="homeassistant.components.x",
                    quando_ts=t, fine_ts=t + 60) for t in (100.0, 200.0, 300.0)]
    pagina = as_page(_resoconto(*voci), judgments=_giudizi())
    riga, = pagina["primo_piano"]
    assert riga["volte"] == 3
    assert riga["quando_ts"] == 100.0
    assert riga["ultimo_ts"] == 300.0


def test_due_guasti_DIVERSI_della_stessa_integrazione_restano_due_righe():
    """Si raggruppa cio' che e' la stessa cosa, non cio' che viene dallo stesso
    posto: due titoli diversi sono due fatti.

    Mutazione: raggruppare per sola integrazione -- rossa."""
    pagina = as_page(_resoconto(
        _guasto("log:x@a.py:1", titolo="Timeout", dominio="homeassistant.components.x"),
        _guasto("log:x@a.py:9", titolo="Client error", dominio="homeassistant.components.x"),
    ), judgments=_giudizi())
    assert len(pagina["primo_piano"]) == 2


def test_la_primo_piano_mette_PRIMA_cio_che_va_saputo_subito_poi_i_guasti_poi_gli_avvisi():
    """«Un allarme scattato e' la prima cosa da sapere; una luce accesa e' la
    seconda, non la prima.» L'ordine e' quello del proprietario, e non e'
    l'ordine di arrivo.

    Mutazione: ordine cronologico -- rossa."""
    pagina = as_page(_resoconto(
        _guasto("log:x@a.py:1", cosa="WARNING", dominio="homeassistant.components.x",
                quando_ts=10.0),
        _guasto("log:y@a.py:1", titolo="Timeout", dominio="homeassistant.components.y",
                quando_ts=20.0),
        _episodio("alarm_control_panel.piano_terra", "triggered", genere="sicurezza",
                  quando_ts=30.0),
    ), judgments=_giudizi())
    assert [r["sorta"] for r in pagina["primo_piano"]] == ["da_sapere_subito", "guasto", "avviso"]


def test_la_voce_di_cronaca_porta_lo_STESSO_marchio_della_primo_piano():
    """La cronaca in fondo disegna le voci in primo piano «con lo stesso aspetto che
    hanno in primo piano» (spec §4A): il marchio sta sulla voce, o la pagina
    dovrebbe ricalcolarlo -- cioe' tornare a decidere.

    Mutazione: marchiare solo il primo piano -- rossa."""
    pagina = as_page(_resoconto(_episodio("alarm_control_panel.piano_terra", "triggered",
                                          genere="sicurezza")),
                     judgments=_giudizi())
    assert pagina["cronaca"][0]["primo_piano"]["sorta"] == "da_sapere_subito"


def test_il_contratto_CRESCE_e_non_perde_nessun_campo():
    """«Chi legge gia' quella rotta continua a funzionare» (spec §3): il
    resoconto torna intero, e ogni voce di cronaca tiene le chiavi che aveva.

    Mutazione: ricostruire la voce invece di aggiungerci sopra -- rossa."""
    voce = _episodio("climate.camera", "heat", quando_ts=5.0, fine_ts=9.0,
                     nome="Termostato", classe="thermostat")
    voce["attributi"] = [{"quando_ts": 6.0, "valori": {"hvac_action": "heating"}}]
    resoconto = _resoconto(voce)
    pagina = as_page(resoconto, judgments=_giudizi())
    assert pagina["giorno"] == "2026-09-17"
    assert pagina["obiettivo"] == "l'efficientamento energetico"
    assert pagina["cronaca"][0].items() >= voce.items()


def test_il_resoconto_di_partenza_non_viene_TOCCATO():
    """«Il resoconto scritto non si tocca»: questo modulo legge, e un archivio
    che cambia sotto chi lo ha letto e' il difetto che la fetta dei giudizi
    ha gia' pagato una volta.

    Mutazione: aggiornare la voce sul posto -- rossa."""
    resoconto = _resoconto(_guasto("log:x@a.py:1", titolo="Timeout",
                                   dominio="homeassistant.components.x"))
    prima = {k: str(v) for k, v in resoconto["cronaca"][0].items()}
    as_page(resoconto, judgments=_giudizi())
    assert {k: str(v) for k, v in resoconto["cronaca"][0].items()} == prima
    assert "primo_piano" not in resoconto


def test_un_giorno_SENZA_niente_da_dire_ha_una_primo_piano_vuota_non_assente():
    """Due giorni su otto non avevano niente in primo piano, ed e' il caso piu'
    frequente. Una chiave assente costringerebbe la pagina a distinguere
    «niente da dire» da «questa rotta non lo calcola».

    Mutazione: omettere la chiave quando e' vuota -- rossa."""
    pagina = as_page(_resoconto(_episodio("light.studio", "on", nome="Studio")),
                     judgments=_giudizi())
    assert pagina["primo_piano"] == []


def test_senza_l_istantanea_dei_giudizi_la_primo_piano_NON_si_inventa():
    """L'istantanea puo' mancare (avvio a meta', archivio non collegato):
    allora la risposta e' «non lo so», non «non c'e' niente da sapere».
    Le voci di sistema restano -- il loro livello lo scrive Home Assistant e
    non dipende dai giudizi -- e gli episodi non entrano.

    Mutazione: `TypeJudgments` obbligatorio -- rossa (solleva)."""
    pagina = as_page(_resoconto(
        _guasto("log:x@a.py:1", titolo="Timeout", dominio="homeassistant.components.x"),
        _episodio("alarm_control_panel.piano_terra", "triggered", genere="sicurezza"),
    ), judgments=None)
    assert [r["sorta"] for r in pagina["primo_piano"]] == ["guasto"]


def test_una_cronaca_assente_non_diventa_un_elenco_vuoto():
    """Un resoconto senza cronaca (le serie di misure) passa di qui senza
    guadagnare una chiave che non aveva: sarebbe un dato inventato.

    Mutazione: `resoconto.setdefault("cronaca", [])` -- rossa."""
    pagina = as_page({"giorno": "2026-09-17", "misure": []}, judgments=_giudizi())
    assert "cronaca" not in pagina
    assert pagina["primo_piano"] == []


@pytest.mark.parametrize("stato", ["unavailable", "unknown"])
def test_uno_stato_NON_LO_SO_non_entra_mai_in_primo_piano(stato):
    """`mind/facts.py` li salta prima di scrivere la cronaca, e
    `stato_da_sapere_subito` lo dichiara come condizione d'uso: se arrivassero
    comunque, un tipo senza `lavoro` li leggerebbe come «non e' un riposo» e
    li farebbe entrare. Qui si custodisce la condizione, invece di fidarsi.

    Mutazione: passare lo stato senza filtro -- rossa."""
    pagina = as_page(_resoconto(_episodio("binary_sensor.fumo_cucina", stato,
                                          genere="sicurezza", classe="smoke")),
                     judgments=_giudizi())
    assert pagina["primo_piano"] == []


# ---------------------------------------------------------------------------
# L'IMPALCATURA di Home Assistant (decisione del proprietario, 20/09/2026:
# «hacs non e' qualcosa da monitorare»).
#
# Misurato sui sette giorni 13-19/09: il primo piano ha portato 42 righe, e
# **12 erano Home Assistant che parla di se'** -- il Supervisor coi timeout
# sugli add-on, HACS, il frontend, il websocket, il bluetooth. L'irrigazione
# ferma e l'allarme scattato erano la minoranza.
#
# **Restano nella cronaca**: sono storia, e l'analista puo' usarle. Non salgono
# in cima.
# ---------------------------------------------------------------------------

def test_una_condizione_dell_IMPALCATURA_non_sale_ma_RESTA_nella_cronaca():
    """Mutazione: non chiedere il giudizio -- rossa (HACS torna in cima).
    Mutazione: toglierla anche dalla cronaca -- rossa (la storia sparisce)."""
    voce = _guasto("log:custom_components.hacs@x.py:1", titolo="GitHub returned 404",
                   dominio="custom_components.hacs")
    pagina = as_page(_resoconto(voce), judgments=_giudizi())

    assert pagina["primo_piano"] == []
    assert pagina["cronaca"][0]["nome"] == "Hacs"
    assert "primo_piano" not in pagina["cronaca"][0]


def test_la_stessa_condizione_di_un_integrazione_di_CASA_sale():
    """La contropartita: senza di lei, un cancello che tace su tutto
    passerebbe la prova qui sopra. Hydrawise e' l'irrigazione.

    Mutazione: `is_scaffolding` che torna sempre vero -- rossa."""
    voce = _guasto("log:homeassistant.components.hydrawise@x.py:1",
                   titolo="Timeout fetching hydrawise data",
                   dominio="homeassistant.components.hydrawise")
    pagina = as_page(_resoconto(voce), judgments=_giudizi())

    assert [r["nome"] for r in pagina["primo_piano"]] == ["Hydrawise"]


def test_i_TRE_logger_di_una_stessa_integrazione_sono_UNA_integrazione():
    """Misurato: il Supervisor ha fatto 6 righe in una settimana da tre logger
    diversi (`hassio.handler`, `hassio.coordinator`, `hassio.http`). Se il
    giudizio si leggesse sul percorso del logger invece che sull'integrazione,
    il proprietario dovrebbe scrivere tre righe per zittire una cosa sola --
    e una quarta il giorno in cui HA aggiunge un modulo.

    Mutazione: chiedere il giudizio col `dominio` intero -- rossa."""
    voci = [_guasto(f"log:homeassistant.components.hassio.{modulo}@x.py:1",
                    titolo=f"Timeout {modulo}",
                    dominio=f"homeassistant.components.hassio.{modulo}")
            for modulo in ("handler", "coordinator", "http")]
    pagina = as_page(_resoconto(*voci), judgments=_giudizi())

    assert pagina["primo_piano"] == []


def test_il_numero_di_versione_del_FRONTEND_non_fa_un_integrazione_nuova():
    """`frontend.js.modern.202608267`: l'ultimo pezzo e' la versione del
    pacchetto e cambia a ogni rilascio di Home Assistant. Se finisse nel
    soggetto del giudizio, la riga scritta oggi smetterebbe di mordere al
    prossimo aggiornamento -- un giudizio che scade da solo.

    Mutazione: prendere piu' di un segmento -- rossa."""
    voce = _guasto("log:frontend.js.modern.202608267@x.py:1", cosa="WARNING",
                   titolo="Uncaught error", dominio="frontend.js.modern.202608267")
    pagina = as_page(_resoconto(voce), judgments=_giudizi())

    assert pagina["primo_piano"] == []


def test_la_casa_puo_RIMETTERE_in_primo_piano_cio_che_il_seme_ha_zittito():
    """**Il cancello di questa mezza fetta**: il criterio vive nei giudizi, e
    il proprietario lo corregge da «Cosa ho capito» senza un rilascio. Se
    l'elenco fosse nel codice, questa riga non sposterebbe niente.

    Mutazione: un elenco di integrazioni dentro `report.py` -- rossa."""
    voce = _guasto("log:custom_components.hacs@x.py:1", titolo="GitHub returned 404",
                   dominio="custom_components.hacs")
    casa = _giudizi(("integrazione", "hacs", "impalcatura", "no"))
    pagina = as_page(_resoconto(voce), judgments=casa)

    assert [r["nome"] for r in pagina["primo_piano"]] == ["Hacs"]


def test_senza_i_giudizi_l_impalcatura_NON_si_indovina():
    """Senza l'istantanea le condizioni di sistema restano (il loro livello lo
    scrive Home Assistant), e nessuna si zittisce: «non lo so» non diventa
    «taci». Meglio una riga in piu' che una in meno.

    Mutazione: zittire per assenza di giudizi -- rossa."""
    voce = _guasto("log:custom_components.hacs@x.py:1", titolo="GitHub returned 404",
                   dominio="custom_components.hacs")
    pagina = as_page(_resoconto(voce), judgments=None)

    assert [r["nome"] for r in pagina["primo_piano"]] == ["Hacs"]
