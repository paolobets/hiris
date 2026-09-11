"""Il cablaggio dell'anello: **chi chiede «è ora?», e cosa succede se sì**.

Quattro inneschi (spec §5.1) -- il primo avvio, l'obiettivo cambiato, qualcosa
di nuovo in casa, la cadenza -- e una sola funzione che li pone tutti e
quattro (`cadence.reason_to_reconsider`). Qui si prova che il giro periodico
la interroghi davvero e agisca di conseguenza: le prove dei singoli inneschi
stanno in `test_mind_impronta.py`, quelle del giro in `test_mind_observer.py`.
"""
import json
import os

import pytest

from hiris.app.mind.scope import OBSERVER
from hiris.app.mind.store import ObservationsStore
from hiris.app.server import reconsideration_round

GIORNO = 86400.0


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


class _Anagrafe:
    def __init__(self, entita):
        self._entita = entita

    def read(self):
        return {"entita": self._entita, "aree": []}


def _entita(eid, **extra):
    riga = {"id": eid, "nome": eid, "classe": None, "unita": None,
            "translation_key": None, "categoria": None,
            "disabilitata": 0, "nascosta": 0, "area_id": None}
    riga.update(extra)
    return riga


class _Modello:
    def __init__(self, risposta="[]"):
        self.risposta = risposta
        self.chiamate = 0

    async def chat(self, user_message, **kw):
        self.chiamate += 1
        return self.risposta


class _Ponte:
    """Il client di Home Assistant, dal lato della misura della memoria."""

    def __init__(self, memoria_s=7 * GIORNO):
        self.memoria_s = memoria_s
        self.sonde = 0

    async def recorded_changes(self, entity_ids, windows):
        self.sonde += len(windows)
        import time
        adesso = time.time()
        return [0 if (adesso - inizio) > self.memoria_s else 9 for inizio, _ in windows]


def _app(archivio, anagrafe, modello):
    return {"observations": archivio, "home_space_store": anagrafe,
            "llm_router": modello}


@pytest.mark.asyncio
async def test_al_primo_avvio_l_osservatore_gira_e_lascia_traccia(archivio):
    modello = _Modello('[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]')
    anagrafe = _Anagrafe([_entita("climate.x")])

    esito = await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert esito == {"decise": 1, "rifiutate": 0, "ignorate": 0, "omesse": 0,
                     "candidate": 1}
    assert modello.chiamate == 1
    assert archivio.scope()["climate.x"]["dentro"] is True
    ultima = archivio.last_reconsideration()
    assert "mai" in ultima["motivo"]


@pytest.mark.asyncio
async def test_la_finestra_si_MISURA_al_giro_e_finisce_nella_traccia(archivio):
    """Il numero non e' una costante e non e' quello di ieri: si rimisura al
    giro che lo usa, e si scrive accanto alla riconsiderazione che ha
    provocato. Il proprietario puo' cambiare il recorder fra un giro e
    l'altro.

    Mutazione che la uccide: scrivere una cadenza fissa.
    """
    ponte = _Ponte(memoria_s=7 * GIORNO)
    anagrafe = _Anagrafe([_entita("climate.x")])

    await reconsideration_round(_app(archivio, anagrafe, _Modello()), ponte)

    ultima = archivio.last_reconsideration()
    assert ponte.sonde > 0
    # La tolleranza e' **mezza giornata, e non e' generosita'**: e' la
    # risoluzione della misura. La scala grossa lascia un tratto di quattro
    # giorni e la seconda raffica lo divide in otto, quindi il risultato cade
    # sempre su un multiplo di mezza giornata -- e il verso e' sempre lo
    # stesso, verso il basso (vedi `cadence.measure_memory_window`: la misura
    # non e' mai piu' LUNGA della memoria vera).
    assert 6.5 * GIORNO <= ultima["finestra_s"] <= 7 * GIORNO
    assert ultima["cadenza_s"] == pytest.approx(ultima["finestra_s"] / 2)


@pytest.mark.asyncio
async def test_se_non_e_ora_NON_si_paga_ne_il_modello_ne_la_sonda(archivio):
    """**Il costo di non fare niente deve essere zero.** Questo giro scatta
    ogni dieci minuti: una misura della memoria a ogni passaggio sarebbero 144
    misure al giorno -- 80 MB di traffico -- per rispondere «non e' ora».

    Mutazione che la uccide: misurare la finestra prima di chiedersi se e' ora.
    """
    import time
    # **L'ordine e' quello vero**: la riconsiderazione segna l'INIZIO della
    # campagna, e le decisioni che ne escono portano un istante successivo.
    # Seminare al contrario descriverebbe uno stato che la produzione non
    # produce -- e farebbe risultare la casa «da rigiudicare» appena finita.
    archivio.record_reconsideration(when_ts=time.time() - 60, window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    modello = _Modello()
    ponte = _Ponte()

    esito = await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), ponte)

    assert esito is None
    assert modello.chiamate == 0
    assert ponte.sonde == 0


@pytest.mark.asyncio
async def test_un_entita_NUOVA_fa_girare_senza_aspettare_la_cadenza(archivio):
    """Una lampadina installata stamattina non resta invisibile fino a
    giovedi': cio' che non e' osservato non esiste piu', e i giorni mancanti
    non tornano."""
    import time
    # **L'ordine e' quello vero**: la riconsiderazione segna l'INIZIO della
    # campagna, e le decisioni che ne escono portano un istante successivo.
    # Seminare al contrario descriverebbe uno stato che la produzione non
    # produce -- e farebbe risultare la casa «da rigiudicare» appena finita.
    archivio.record_reconsideration(when_ts=time.time() - 60, window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    modello = _Modello('[{"id": "light.nuova", "dentro": true, "motivo": "si accende"}]')
    anagrafe = _Anagrafe([_entita("climate.x"), _entita("light.nuova")])

    await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert modello.chiamate == 1
    assert "light.nuova" in archivio.scope()


@pytest.mark.asyncio
async def test_le_entita_di_servizio_non_sono_MAI_novita(archivio):
    """**Il difetto che questo giro avrebbe avuto per sempre.** L'osservatore
    non giudica le entita' di servizio e le nascoste (decisione del
    proprietario, 10/09/2026): quindi nessuna di esse finisce mai nello scope,
    quindi sarebbero «nuove» a ogni singolo giro -- 452 su questa casa -- e
    l'osservatore girerebbe ogni dieci minuti per sempre.

    L'impronta si chiede sulle stesse entita' che si mostrano al modello, non
    sull'anagrafe intera.

    Mutazione che la uccide: passare tutte le entita' a `undecided`.
    """
    import time
    # **L'ordine e' quello vero**: la riconsiderazione segna l'INIZIO della
    # campagna, e le decisioni che ne escono portano un istante successivo.
    # Seminare al contrario descriverebbe uno stato che la produzione non
    # produce -- e farebbe risultare la casa «da rigiudicare» appena finita.
    archivio.record_reconsideration(when_ts=time.time() - 60, window_s=7 * GIORNO,
                                    cadence_s=3.5 * GIORNO, reason="fatta")
    archivio.decide_scope("climate.x", inside=True, reason="pesa", author=OBSERVER)
    modello = _Modello()
    anagrafe = _Anagrafe([_entita("climate.x"),
                          _entita("sensor.wifi", categoria="diagnostic"),
                          _entita("light.vecchia", nascosta=1)])

    esito = await reconsideration_round(_app(archivio, anagrafe, modello), _Ponte())

    assert esito is None
    assert modello.chiamate == 0


@pytest.mark.asyncio
async def test_senza_modello_o_senza_archivio_il_giro_non_solleva(archivio):
    """Gira ogni dieci minuti per sempre: un'eccezione su un avvio a meta'
    fermerebbe lo schedulatore, non solo questo giro."""
    anagrafe = _Anagrafe([_entita("climate.x")])

    assert await reconsideration_round({"observations": archivio,
                                        "home_space_store": anagrafe}, _Ponte()) is None
    assert await reconsideration_round({"llm_router": _Modello()}, _Ponte()) is None
    assert await reconsideration_round({}, None) is None


@pytest.mark.asyncio
async def test_una_memoria_non_misurabile_non_ferma_il_primo_giro(archivio):
    """Home Assistant muto alla sonda non deve lasciare una casa senza scope:
    il giro si fa lo stesso, e la riconsiderazione **dichiara** che la finestra
    non si e' misurata invece di inventarne una.

    Mutazione che la uccide: fermarsi quando la finestra e' `None`.
    """
    class _Muto:
        async def recorded_changes(self, entity_ids, windows):
            return [None] * len(windows)

    modello = _Modello('[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]')

    await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), _Muto())

    assert modello.chiamate == 1
    ultima = archivio.last_reconsideration()
    assert ultima["finestra_s"] is None
    assert ultima["cadenza_s"] is None


# ── Il giro passa dal PONTE quando e' il ponte a rispondere ─────────────────
#
# Fetta «l'osservatore chiede a chi risponde davvero» (11/09/2026). Fino a
# oggi questo giro andava dritto a `llm_router`, dove il Piano Claude Max
# **non e' un anello** (`llm_router._VALID_BACKEND_NAMES`). Misurato sulla
# casa vera l'11/09 alle 11:00:44: l'osservatore cadeva su un modello
# OpenRouter «batch-only» (404) e su una chiave Claude senza credito (400),
# mentre l'abbonamento -- 140 richieste su 140 nella storia di questa casa --
# rispondeva benissimo alla chat, li' accanto. E' lo stesso difetto che
# `steering.py` dichiara di aver chiuso il 22/08 per le promesse, con la frase
# «una terza porta che nascesse domani non potrebbe inventarsene una terza
# senza accorgersene».
#
# Il turno del ponte non torna dentro la stessa chiamata: si accoda, e si
# raccoglie a un giro successivo. Da cui le due meta' provate qui sotto.

from hiris.app.model_resolution import SUBSCRIPTION_TOKEN_VAR
from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture
def coda(tmp_path):
    c = ReasoningQueue(str(tmp_path / "reasoning.db"))
    yield c
    c.close()


@pytest.fixture
def piano_acceso(monkeypatch):
    """Una casa che gira sul Piano Claude Max -- come quella vera."""
    monkeypatch.setenv(SUBSCRIPTION_TOKEN_VAR, "un-token-qualunque")


def _app_ponte_acceso(archivio, anagrafe, modello, coda):
    app = _app(archivio, anagrafe, modello)
    app["reasoning_queue"] = coda
    app["bridge_active"] = True
    app["models_config"] = {"ponte": {"tetto_giornaliero": 150, "scadenza_min": 10}}
    return app


@pytest.mark.asyncio
async def test_piano_acceso_acceso_il_giro_ACCODA_invece_di_chiamare_la_catena(
        archivio, coda, piano_acceso):
    """**Il difetto misurato in produzione l'11/09/2026.** L'osservatore aveva
    una porta sua sul modello, e quella porta non passava dal piano.

    Mutazione che la uccide: chiamare `runner.chat` senza chiedere prima a
    `who_answers`.
    """
    modello = _Modello()
    anagrafe = _Anagrafe([_entita("climate.x")])

    esito = await reconsideration_round(
        _app_ponte_acceso(archivio, anagrafe, modello, coda), _Ponte())

    assert modello.chiamate == 0, "la catena non doveva essere consultata"
    assert esito == {"accodata": True}
    turno = coda.latest("scope")
    assert turno["status"] == "pending"
    assert "climate.x" in turno["context"]["history"][0]["content"]


@pytest.mark.asyncio
async def test_la_risposta_del_ponte_si_raccoglie_al_giro_dopo(
        archivio, coda, piano_acceso):
    """Il ponte risponde da un altro processo, minuti dopo. Chi raccoglie e'
    il giro periodico successivo, e la coda e' l'unico posto in cui il turno
    lo aspetta -- tenerne il `job_id` altrove sarebbe un doppione che non
    sopravvive a un riavvio.

    Mutazione che la uccide: non guardare la coda all'inizio del giro.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]), _Modello(), coda)
    await reconsideration_round(app, _Ponte())

    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": '[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]'},
                now=2.0)

    esito = await reconsideration_round(app, _Ponte())

    assert esito == {"decise": 1, "rifiutate": 0, "ignorate": 0, "omesse": 0,
                     "candidate": 1}
    assert archivio.scope()["climate.x"]["dentro"] is True
    assert archivio.last_reconsideration() is not None


@pytest.mark.asyncio
async def test_la_finestra_MISURATA_alla_domanda_arriva_alla_raccolta(
        archivio, coda, piano_acceso):
    """La sonda si cala quando la domanda parte; la riconsiderazione si scrive
    quando la risposta torna. Fra i due momenti, sul ponte, ci sono minuti e un
    altro processo: il numero viaggia nella **sveglia** del job, che `submit`
    non azzera.

    Senza quel passaggio si rimisurerebbe (pagando due volte una cosa che non
    e' cambiata) o si scriverebbe `None` su una finestra misurata davvero --
    indistinguibile da una casa che non ricorda niente.

    Mutazione che la uccide: raccogliere con `window_s=None`.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]), _Modello(), coda)
    ponte = _Ponte(memoria_s=7 * GIORNO)
    await reconsideration_round(app, ponte)

    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"], {"reply": "[]"}, now=2.0)
    await reconsideration_round(app, ponte)

    ultima = archivio.last_reconsideration()
    assert 6.5 * GIORNO <= ultima["finestra_s"] <= 7 * GIORNO
    assert ultima["cadenza_s"] == pytest.approx(ultima["finestra_s"] / 2)


@pytest.mark.asyncio
async def test_mentre_un_turno_e_in_volo_non_se_ne_accoda_un_secondo(
        archivio, coda, piano_acceso):
    """Questo giro scatta ogni dieci minuti e un turno del piano puo' durarne
    parecchi. Senza questa guardia la casa accumulerebbe un turno ogni dieci
    minuti, ciascuno con 11.500 token di casa dentro, e il tetto giornaliero
    si svuoterebbe in un pomeriggio.

    Mutazione che la uccide: accodare senza guardare se ce n'e' gia' uno.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]), _Modello(), coda)

    await reconsideration_round(app, _Ponte())
    esito = await reconsideration_round(app, _Ponte())

    assert esito is None
    assert coda.count_exchanges_today() == 1


@pytest.mark.asyncio
async def test_un_turno_SCADUTO_non_blocca_l_osservatore_per_sempre(
        archivio, coda, piano_acceso):
    """Il piano puo' non rispondere. Se il turno scaduto restasse «l'ultimo
    turno di scope», il giro lo aspetterebbe per sempre e la casa non sarebbe
    mai osservata -- un guasto silenzioso identico a quello che questa fetta
    ripara.

    Mutazione che la uccide: trattare 'expired' come un turno ancora in volo.
    """
    import time
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]), _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    coda.sweep_expired(now=time.time() + 3600)

    esito = await reconsideration_round(app, _Ponte())

    assert esito == {"accodata": True}
    assert coda.count_exchanges_today() == 2


@pytest.mark.asyncio
async def test_una_risposta_del_ponte_gia_raccolta_non_si_riscrive_ogni_giro(
        archivio, coda, piano_acceso):
    """Il turno resta nella coda dopo essere stato raccolto -- e' li' che la
    contabilita' e la potatura lo trovano. Riapplicarlo a ogni giro
    riscriverebbe le stesse decisioni per sempre e, peggio, sposterebbe avanti
    la riconsiderazione a ogni passaggio: la cadenza non scadrebbe mai.

    Mutazione che la uccide: raccogliere ogni turno 'decided' senza guardare
    se la riconsiderazione e' gia' piu' recente della sua domanda.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]), _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": '[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]'},
                now=2.0)
    await reconsideration_round(app, _Ponte())
    prima = archivio.last_reconsideration()["quando_ts"]

    esito = await reconsideration_round(app, _Ponte())

    assert esito is None
    assert archivio.last_reconsideration()["quando_ts"] == prima


# ── Il tentativo si annota SEMPRE, riuscito o no ────────────────────────────
#
# La seconda meta' del difetto dell'11/09/2026, e quella che l'ha reso lungo
# da trovare: il giro falliva ogni dieci minuti e **nessuna porta lo diceva**.
# La pagina dello scope mostrava «non e' mai stata fatta» -- vero alla lettera
# (nessuna riconsiderazione era avvenuta) e falso come racconto: ci si era
# provato quattro volte. Un guasto non si appiattisce su un'assenza.


@pytest.mark.asyncio
async def test_un_giro_fallito_sulla_catena_LASCIA_DETTO_che_e_fallito(archivio):
    """Mutazione che la uccide: annotare il tentativo solo quando riesce."""
    modello = _Modello("non sono un JSON")

    await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), _Ponte())

    assert archivio.last_reconsideration() is None, (
        "un giro fallito non e' una riconsiderazione: annotarlo come tale "
        "farebbe scadere la cadenza come se la casa fosse stata ripensata")
    tentativo = archivio.recent_attempts()[0]
    assert tentativo["esito"] == "non_riuscito"
    assert "JSON" in tentativo["dettaglio"]


@pytest.mark.asyncio
async def test_un_turno_accodato_al_piano_si_annota_come_IN_ATTESA(
        archivio, coda, piano_acceso):
    """«Ho chiesto e sto aspettando» e' il terzo stato, e la pagina deve poterlo
    dire: senza, dieci minuti di attesa legittima sono indistinguibili da un
    guasto.

    Mutazione che la uccide: annotare l'accodamento come riuscito.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)

    await reconsideration_round(app, _Ponte())

    assert archivio.recent_attempts()[0]["esito"] == "accodata"


@pytest.mark.asyncio
async def test_un_turno_raccolto_si_annota_come_RIUSCITO(
        archivio, coda, piano_acceso):
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": '[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]'},
                now=2.0)

    await reconsideration_round(app, _Ponte())

    assert archivio.recent_attempts()[0]["esito"] == "riuscito"


@pytest.mark.asyncio
async def test_una_risposta_del_piano_inservibile_si_annota_come_FALLITA(
        archivio, coda, piano_acceso):
    """Il piano ha risposto, ma cio' che ha detto non si e' potuto usare. E'
    un guasto, e va detto con le parole di quel guasto -- non con «non e' mai
    stata fatta».

    Mutazione che la uccide: tacere quando la raccolta non produce decisioni.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"], {"reply": "mi spiace, non posso"},
                now=2.0)

    await reconsideration_round(app, _Ponte())

    # Il fallimento resta scritto **in cima**, e il passaggio si chiude li':
    # non si richiede nello stesso giro (vedi il freno, sotto). Se il guasto
    # si limitasse a far ripartire il giro, quaranta minuti di guasto
    # sarebbero di nuovo indistinguibili da quaranta minuti di attesa -- il
    # difetto da cui questa fetta nasce.
    esiti = [t["esito"] for t in archivio.recent_attempts()]
    assert esiti[:2] == ["non_riuscito", "accodata"]
    assert "JSON" in archivio.recent_attempts()[0]["dettaglio"]


# ── Il freno: un osservatore che fallisce non svuota il tetto del piano ─────
#
# Rilievo della review indipendente (11/09/2026), col conto fatto: con la
# scadenza a 10 minuti e il giro ogni 10 minuti, una raccolta fallita che
# riaccoda nello stesso passaggio produce fino a **144 turni al giorno**,
# ciascuno con ~11.500 token di casa dentro. `count_exchanges_today` conta
# **ogni specie**, e il tetto di fabbrica e' 150: un osservatore che fallisce
# sistematicamente **svuota da solo il tetto giornaliero**, la chat perde il
# piano per il resto della giornata, e da li' in poi ogni turno passa ai
# provider a pagamento.


@pytest.mark.asyncio
async def test_dopo_una_raccolta_fallita_NON_si_richiede_nello_stesso_giro(
        archivio, coda, piano_acceso):
    """Il passaggio si chiude annotando il guasto; si richiede al giro dopo,
    quando il freno lo consente.

    Mutazione che la uccide: riaccodare subito dopo la raccolta fallita.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"], {"reply": "non un JSON"}, now=2.0)

    await reconsideration_round(app, _Ponte())

    assert coda.count_exchanges_today() == 1, "il secondo turno non doveva partire"
    assert archivio.recent_attempts()[0]["esito"] == "non_riuscito"


@pytest.mark.asyncio
async def test_la_stessa_risposta_storta_non_si_annota_due_volte(
        archivio, coda, piano_acceso):
    """Un turno gia' letto e trovato inservibile non si rilegge: annotarlo a
    ogni giro gonfierebbe il «sta fallendo da...» con tentativi fantasma, tutti
    sulla stessa risposta.

    Mutazione che la uccide: guardare solo la riconsiderazione, che una
    raccolta fallita non scrive mai.
    """
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"], {"reply": "non un JSON"}, now=2.0)
    await reconsideration_round(app, _Ponte())

    await reconsideration_round(app, _Ponte())
    await reconsideration_round(app, _Ponte())

    falliti = [t for t in archivio.recent_attempts() if t["esito"] == "non_riuscito"]
    assert len(falliti) == 1


@pytest.mark.asyncio
async def test_l_attesa_fra_un_tentativo_e_l_altro_CRESCE_coi_fallimenti(
        archivio, coda, piano_acceso):
    """Due fallimenti di fila non si riprovano al giro dopo: il freno raddoppia
    l'attesa, e senza di lui il tetto giornaliero del piano si svuota in un
    pomeriggio.

    Mutazione che la uccide: togliere il freno (`_retry_hold`).
    """
    import time
    archivio.record_attempt(when_ts=time.time() - 60, outcome="non_riuscito",
                            detail="x")
    archivio.record_attempt(when_ts=time.time() - 30, outcome="non_riuscito",
                            detail="x")
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)

    esito = await reconsideration_round(app, _Ponte())

    assert esito is None
    assert coda.count_exchanges_today() == 0


@pytest.mark.asyncio
async def test_passato_il_freno_si_riprova(archivio, coda, piano_acceso):
    """Il freno rallenta, non spegne: un guasto che passa deve poter essere
    scoperto."""
    import time
    archivio.record_attempt(when_ts=time.time() - 10 * 86400,
                            outcome="non_riuscito", detail="vecchio")
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)

    esito = await reconsideration_round(app, _Ponte())

    assert esito == {"accodata": True}


@pytest.mark.asyncio
async def test_il_giro_annota_da_quale_PORTA_e_passato(archivio):
    """Un giro servito dal piano e uno pagato a consumo non sono la stessa
    cosa, e la pagina deve poterli distinguere: *«un passaggio silenzioso a un
    provider a pagamento si scopre a fine mese»* (proprietario, 13/08/2026,
    citato nel docstring di `steering.py`).

    Mutazione che la uccide: scrivere il dettaglio senza la porta.
    """
    modello = _Modello('[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]')

    await reconsideration_round(
        _app(archivio, _Anagrafe([_entita("climate.x")]), modello), _Ponte())

    assert "catena" in archivio.recent_attempts()[0]["dettaglio"]


@pytest.mark.asyncio
async def test_senza_nessun_modello_a_cui_chiedere_lo_dice(archivio):
    """Il silenzio annotato: senza token del piano e senza nessun provider in
    catena l'osservatore taceva per sempre, con la faccia di «nessuno ha ancora
    provato».

    Mutazione che la uccide: tornare `None` senza annotare.
    """
    app = {"observations": archivio,
           "home_space_store": _Anagrafe([_entita("climate.x")])}

    esito = await reconsideration_round(app, _Ponte())

    assert esito is None
    assert archivio.recent_attempts()[0]["esito"] == "non_riuscito"
    assert "nessun modello" in archivio.recent_attempts()[0]["dettaglio"]


@pytest.mark.asyncio
async def test_il_piano_che_serve_l_osservatore_finisce_nel_REGISTRO_degli_esiti(
        archivio, coda, piano_acceso):
    """Il registro degli esiti e' il solo posto in cui HIRIS osserva come si
    comporta un fornitore davvero, e la pagina Modelli lo legge. La terza
    strada del piano non ci finiva: l'abbonamento poteva servire dieci turni
    dell'osservatore e la pagina avrebbe detto «nessuna osservazione da quando
    l'add-on e' partito».

    Mutazione che la uccide: non toccare il registro nella raccolta.
    """
    from hiris.app.provider_occurrences import OccurrenceRegistry

    registro = OccurrenceRegistry()
    app = _app_ponte_acceso(archivio, _Anagrafe([_entita("climate.x")]),
                            _Modello(), coda)
    app["occurrence_registry"] = registro
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=1.0)
    coda.submit(preso["job_id"], preso["nonce"],
                {"reply": '[{"id": "climate.x", "dentro": true, "motivo": "scalda"}]'},
                now=2.0)

    await reconsideration_round(app, _Ponte())

    assert registro.occurrence("subscription")["tipo"] == "risposto"


# ── La campagna: una riconsiderazione e' PIU' lotti ─────────────────────────
#
# Misurato dal vivo l'11/09/2026: un turno che chiede 381 giudizi produce
# ~30 KB di risposta e la CLI del piano viene uccisa dal tetto di 300 secondi
# (`claude non eseguibile: TimeoutExpired`, due volte, alle 15:44:12 esatte).
# La domanda si spezza in lotti.
#
# **E la riconsiderazione si annota quando la campagna PARTE, non a ogni
# lotto.** Annotarla a ogni lotto soddisferebbe la cadenza dopo il primo, e gli
# altri non partirebbero mai: a ogni cadenza si rigiudicherebbe un quarto di
# casa, e la casa intera in quattro cadenze -- oltre la memoria di Home
# Assistant, cioe' la garanzia che la cadenza esiste per tenere (spec §5.2).


def _entita_molte(quante):
    return [_entita(f"light.n{n}") for n in range(quante)]


@pytest.mark.asyncio
async def test_si_chiede_un_LOTTO_per_volta_non_la_casa_intera(archivio, coda,
                                                               piano_acceso):
    """Mutazione che la uccide: mandare al piano tutte le candidate."""
    from hiris.app.server import SCOPE_BATCH

    anagrafe = _Anagrafe(_entita_molte(SCOPE_BATCH + 50))
    app = _app_ponte_acceso(archivio, anagrafe, _Modello(), coda)

    await reconsideration_round(app, _Ponte())

    chiesto = coda.latest("scope")["context"]["history"][0]["content"]
    righe = [r for r in chiesto.splitlines() if r.startswith("light.n")]
    assert len(righe) == SCOPE_BATCH


@pytest.mark.asyncio
async def test_i_lotti_successivi_partono_SENZA_aspettare_la_cadenza(
        archivio, coda, piano_acceso):
    """La campagna prosegue ai giri successivi finche' la casa e' coperta.

    Mutazione che la uccide: far dipendere anche i lotti successivi dalla
    cadenza -- con la riconsiderazione gia' annotata, non partirebbero mai.
    """
    from hiris.app.server import SCOPE_BATCH

    anagrafe = _Anagrafe(_entita_molte(SCOPE_BATCH + 3))
    app = _app_ponte_acceso(archivio, anagrafe, _Modello(), coda)
    await _lotto_servito(app, coda, archivio)

    esito = await reconsideration_round(app, _Ponte())

    assert esito == {"accodata": True}
    chiesto = coda.latest("scope")["context"]["history"][0]["content"]
    assert len([r for r in chiesto.splitlines() if r.startswith("light.n")]) == 3


@pytest.mark.asyncio
async def test_la_riconsiderazione_si_annota_UNA_volta_per_campagna(
        archivio, coda, piano_acceso):
    """Mutazione che la uccide: annotare a ogni lotto -- la cadenza risulterebbe
    soddisfatta dopo il primo e la casa non verrebbe mai coperta."""
    from hiris.app.server import SCOPE_BATCH

    anagrafe = _Anagrafe(_entita_molte(SCOPE_BATCH + 3))
    app = _app_ponte_acceso(archivio, anagrafe, _Modello(), coda)
    await _lotto_servito(app, coda, archivio)
    prima = archivio.last_reconsideration()["quando_ts"]
    await _lotto_servito(app, coda, archivio)

    assert archivio.last_reconsideration()["quando_ts"] == prima


@pytest.mark.asyncio
async def test_coperta_la_casa_la_campagna_si_ferma(archivio, coda, piano_acceso):
    """Finita la campagna non si chiede piu' niente finche' la cadenza non
    scade: senza questa fermata l'osservatore chiederebbe al piano ogni dieci
    minuti per sempre."""
    from hiris.app.server import SCOPE_BATCH

    anagrafe = _Anagrafe(_entita_molte(SCOPE_BATCH - 10))
    app = _app_ponte_acceso(archivio, anagrafe, _Modello(), coda)
    await _lotto_servito(app, coda, archivio)

    assert await reconsideration_round(app, _Ponte()) is None


async def _lotto_servito(app, coda, archivio):
    """Un giro intero: si accoda, il piano risponde su tutto il lotto, si
    raccoglie."""
    await reconsideration_round(app, _Ponte())
    preso = coda.claim(now=_orologio())
    chiesti = [r.split(" · ")[0] for r in
               preso["context"]["history"][0]["content"].splitlines()
               if r.startswith("light.n")]
    risposta = json.dumps([{"id": e, "dentro": True, "motivo": "la prova dice si"}
                           for e in chiesti])
    coda.submit(preso["job_id"], preso["nonce"], {"reply": risposta},
                now=_orologio())
    return await reconsideration_round(app, _Ponte())


def _orologio():
    import time
    return time.time()
