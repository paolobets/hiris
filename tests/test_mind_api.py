"""Le due rotte della pagina dell'osservatore."""
import json

import pytest

from hiris.app.api.handlers_mind import (
    handle_analysis,
    handle_knowledge,
    handle_report,
    handle_set_objective,
    handle_watching,
)
from hiris.app.home_space.reader import HomeSpace
from hiris.app.mind import knowledge as sap
from hiris.app.mind.store import ATTEMPTS_SHOWN, ObservationsStore
from hiris.app.mind.watcher import Watcher
from hiris.app.proxy.state_translations import StateTranslations
from tests._contracts import assert_stessa_firma


class _FintoOsservatore:
    def watching(self):
        return [{"soggetto": "climate.camera_t", "motivo": "scalda la casa",
                 "autore": "observer", "da_quando_ts": 1787000000.0}]


class _FintoArchivioScope:
    """L'archivio dal lato della pagina dello scope: porta le decisioni,
    l'obiettivo, l'ultima riconsiderazione e il volume del grezzo.

    **Conta le finestre che le vengono chieste**: la pagina mostra il volume
    di piu' giorni, e una finta che ignori gli estremi non potrebbe vedere
    una rotta che chiede sempre lo stesso giorno.
    """

    def __init__(self, *, ultima=None):
        self.finestre = []
        self._ultima = ultima

    def scope(self):
        return {
            "climate.camera_t": {"dentro": True, "motivo": "scalda la casa",
                                 "autore": "observer", "deciso_ts": 1787000000.0},
            "sensor.uptime": {"dentro": False, "motivo": "di servizio, non dice niente"
                                                         " sulla casa",
                              "autore": "observer", "deciso_ts": 1787000001.0},
        }

    def objective(self):
        return {"testo": "tenere la casa calda e spendere poco",
                "scritto_ts": 1787000000.0}

    def last_reconsideration(self):
        return self._ultima

    def recent_attempts(self, limit=ATTEMPTS_SHOWN):
        """**Vuoto e' un esito**: nessuno ci ha ancora provato. La finta lo
        porta perche' l'archivio vero lo porta -- una finta costruita nella
        forma che il codice si aspetta, invece che in quella del fornitore,
        e' il difetto n.3 di questo progetto."""
        return []

    def readings_count(self, *, from_ts, to_ts, source=None):
        self.finestre.append((from_ts, to_ts, source))
        return int(to_ts - from_ts)      # una riga al secondo: distingue i giorni


def _decidi(archivio, *soggetti):
    """Mette nello scope i soggetti che le prove d'insieme fanno passare dal
    rubinetto. Il default e' l'entita' che usano quasi tutte."""
    for soggetto in soggetti or ("climate.bagno_1p_t_bagno_1p_t",):
        archivio.decide_scope(soggetto, inside=True,
                              reason="la prova la guarda", author="observer")


class _FintaCasa:
    """L'anagrafe dal lato di chi legge i nomi: una  e basta."""

    def __init__(self, home_space):
        self._home_space = home_space

    def read(self):
        return self._home_space


def _richiesta(app, query=None):
    class _R:
        def __init__(self):
            self.app = app
            self.query = query or {}
    return _R()


assert_stessa_firma(Watcher.watching, _FintoOsservatore.watching, nome="watching")
assert_stessa_firma(ObservationsStore.recent_attempts,
                    _FintoArchivioScope.recent_attempts, nome="recent_attempts")
for _nome in ("scope", "objective", "last_reconsideration", "readings_count"):
    assert_stessa_firma(getattr(ObservationsStore, _nome),
                        getattr(_FintoArchivioScope, _nome), nome=_nome)


def _pagina(**extra):
    """L'app con tutto cio' che la pagina dello scope legge."""
    app = {"watcher": _FintoOsservatore(), "observations": _FintoArchivioScope()}
    app.update(extra)
    return app


@pytest.mark.asyncio
async def test_osservate_dice_cosa_si_guarda_e_perche():
    r = await handle_watching(_richiesta({"watcher": _FintoOsservatore()}))
    assert r.status == 200


@pytest.mark.asyncio
async def test_osservate_porta_il_perche_e_l_autore_di_ogni_voce():
    """La pagina mostra cosa si guarda, **perche'**, e **chi l'ha deciso**: e'
    da li' che il proprietario toglie qualcosa (spec §5.1/§11). Senza l'autore
    non si distinguerebbe una scelta dell'osservatore da una dell'analista, e
    la seconda non saprebbe di essere una revisione della prima."""
    r = await handle_watching(_richiesta(_pagina()))
    voce = _corpo(r)["watching"][0]
    assert voce["motivo"] == "scalda la casa"
    assert voce["autore"] == "observer"
    assert voce["da_quando_ts"] == 1787000000.0


@pytest.mark.asyncio
async def test_la_pagina_porta_anche_cio_che_e_stato_LASCIATO_FUORI():
    """**Meta' della trasparenza sta qui.** Un elenco di sole cose guardate
    non si puo' usare per decidere: chi legge non sa se un'entita' manca
    perche' e' stata esclusa (e con quale ragione) o perche' nessuno l'ha mai
    considerata. Ed e' da questo secondo elenco che si rimette dentro una
    delle 452 escluse.

    Mutazione che la uccide: mandare solo `dentro`.
    """
    fuori = _corpo(await handle_watching(_richiesta(_pagina())))["fuori"]

    assert [v["soggetto"] for v in fuori] == ["sensor.uptime"]
    assert "di servizio" in fuori[0]["motivo"]
    assert fuori[0]["autore"] == "observer"


@pytest.mark.asyncio
async def test_la_pagina_porta_l_obiettivo_rispetto_a_cui_si_e_deciso():
    """La pagina dello scope **e'** la prova che l'obiettivo e' stato capito
    (spec §11: non sono due pagine). Mostrare le scelte senza la domanda a cui
    rispondono le renderebbe illeggibili."""
    corpo = _corpo(await handle_watching(_richiesta(_pagina())))
    assert corpo["obiettivo"]["testo"] == "tenere la casa calda e spendere poco"


@pytest.mark.asyncio
async def test_la_pagina_dice_quando_si_ricambiera_idea_e_perche_allora():
    """Non basta «riconsidero ogni 84 ore»: quel numero viene dalla memoria
    misurata di Home Assistant, e cambia se il proprietario cambia il
    recorder. La pagina porta **tutti e tre** i numeri -- quando, la finestra,
    la cadenza -- o il lettore dovrebbe crederci sulla parola."""
    ultima = {"quando_ts": 1787000000.0, "finestra_s": 604800.0, "cadenza_s": 302400.0}
    archivio = _FintoArchivioScope(ultima=ultima)

    corpo = _corpo(await handle_watching(_richiesta(_pagina(observations=archivio))))

    assert corpo["riconsiderazione"] == ultima


@pytest.mark.asyncio
async def test_mai_riconsiderato_si_DICHIARA_invece_di_sparire():
    """`null`, non una chiave assente: «non l'ho ancora fatto» e' un fatto
    che la pagina deve poter dire, ed e' vero al primo avvio di ogni casa."""
    corpo = _corpo(await handle_watching(_richiesta(_pagina())))
    assert corpo["riconsiderazione"] is None


@pytest.mark.asyncio
async def test_la_pagina_dice_QUANTO_SCRIVE_al_giorno():
    """**La contropartita onesta dello scope.** Si guarda meno, e questo e'
    quanto costa cio' che si guarda: la spec promette **-83%** (da 29.227 a
    4.951 righe al giorno) e fino all'11/09/2026 nessuna porta lo esponeva --
    la promessa non era verificabile dall'esterno.

    Ogni giorno e' una finestra sua: una rotta che chiedesse sempre lo stesso
    intervallo mostrerebbe sette volte lo stesso numero senza che nessuno se
    ne accorga.

    Mutazione che la uccide: passare gli stessi estremi a ogni giorno.
    """
    archivio = _FintoArchivioScope()

    volume = _corpo(await handle_watching(_richiesta(_pagina(observations=archivio))))["volume"]

    assert len(volume) >= 7
    assert all("giorno" in v and "righe" in v for v in volume)
    assert len({giorno for giorno, _, _ in archivio.finestre}) == len(archivio.finestre)
    assert [v["giorno"] for v in volume] == sorted(v["giorno"] for v in volume)


@pytest.mark.asyncio
async def test_senza_archivio_la_pagina_non_inventa_la_meta_che_manca():
    """L'osservatore c'e' e l'archivio no -- avvio a meta', o un guasto. Un
    obiettivo di fabbrica e un volume a zero sarebbero due affermazioni che
    nessuno ha verificato. Si dichiara la mancanza e la pagina la dice."""
    corpo = _corpo(await handle_watching(_richiesta({"watcher": _FintoOsservatore()})))

    assert corpo["watching"]
    assert corpo["obiettivo"] is None
    assert corpo["volume"] == []
    assert corpo["fuori"] == []


@pytest.mark.asyncio
async def test_senza_osservatore_la_rotta_lo_DICHIARA():
    """Un elenco vuoto direbbe «non guardo niente»; l'osservatore assente e'
    un'altra cosa, ed e' la distinzione che questo prodotto difende ovunque."""
    r = await handle_watching(_richiesta({}))
    assert r.status == 503


def _corpo(response):
    import json
    return json.loads(response.body)


# ---------------------------------------------------------------------------
# La strada vera, per intero: l'evento di Home Assistant -> `Watcher` ->
# l'archivio SQLite -> l'aggregazione -> `GET /api/mind/facts`. Nessuna
# finta in mezzo: e' la prova che il nome ARRIVA alla riga che il
# proprietario legge, non che un pezzo isolato lo sappia trasportare.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lo stato reso (fetta «lo stato», 07/09/2026). Il grezzo resta nell'archivio,
# la resa nasce QUI, al confine -- e i due silenzi («non ho potuto leggere le
# traduzioni» e «questo stato non ha traduzione») non producono la stessa
# risposta.
# ---------------------------------------------------------------------------

# Le chiavi sono quelle MISURATE sulla casa vera il 07/09/2026
# (`frontend/get_translations`, `language: "it"`, `category:
# "entity_component"`), non plausibili.
_RISORSE = {
    "component.climate.entity_component._.state.heat": "Riscaldamento",
    "component.person.entity_component._.state.not_home": "Fuori casa",
    "component.binary_sensor.entity_component.smoke.state.on": "Rilevato",
    "component.binary_sensor.entity_component._.state.on": "Acceso",
}


class _FinteTraduzioni:
    """La cache, con lo stesso contratto della vera: un esito ETICHETTATO."""

    def __init__(self, esito):
        self.esito = esito
        self.chiesto = None

    async def read(self, *, ha_version, language):
        self.chiesto = {"versione_ha": ha_version, "lingua": language}
        return self.esito


class _FintaAnagrafe:
    def __init__(self, frame):
        self._frame = frame

    def reference_frame(self):
        return self._frame


class _ClientCheNonRisponde:
    async def get_translations(self, language, category="entity_component"):
        raise AssertionError("senza lingua non si deve chiedere niente a Home Assistant")


# **La sezione della rotta `api/mind/facts` e' uscita** (spec §13,
# 15/09/2026) insieme allo strato che serviva: gli episodi vivono nella
# cronaca del resoconto, e le prove della resa degli stati sono morte con
# la resa. Restano le due firme qui sotto, che riguardano l'anagrafe e le
# traduzioni -- cose vive, che con gli oggetti non c'entravano.
assert_stessa_firma(StateTranslations.read, _FinteTraduzioni.read, nome="read")
assert_stessa_firma(HomeSpace.reference_frame, _FintaAnagrafe.reference_frame,
                    nome="reference_frame")

# ── I tentativi: «sta funzionando?» e' una domanda diversa da «quand'e'
#    l'ultima volta che ha ripensato la casa» ─────────────────────────────────
#
# Misurato sulla casa vera l'11/09/2026: l'osservatore ha provato e fallito
# quattro volte in quaranta minuti, HIRIS ha smesso di registrare qualunque
# cosa (il cancello di `watcher.watch_reading` **e'** lo scope), e la pagina
# diceva soltanto «non e' mai stata fatta» -- vero alla lettera, falso come
# racconto. Questo modulo dichiara da sempre la regola che quel silenzio
# violava: **un guasto non si appiattisce su un'assenza.**


class _ArchivioCoiTentativi(_FintoArchivioScope):
    def __init__(self, tentativi, **kw):
        super().__init__(**kw)
        self._tentativi = tentativi

    def recent_attempts(self, limit=ATTEMPTS_SHOWN):
        return self._tentativi[:limit]


@pytest.mark.asyncio
async def test_la_pagina_porta_i_TENTATIVI_non_solo_i_giri_riusciti():
    """Mutazione che la uccide: mandare solo `riconsiderazione`."""
    tentativi = [
        {"quando_ts": 1789117844.0, "esito": "accodata",
         "dettaglio": "chiesto al piano: non e' mai stata fatta"},
        {"quando_ts": 1789117244.0, "esito": "non_riuscito",
         "dettaglio": "il modello non ha risposto: RuntimeError"},
    ]
    archivio = _ArchivioCoiTentativi(tentativi)

    corpo = _corpo(await handle_watching(_richiesta(_pagina(observations=archivio))))

    assert corpo["tentativi"] == tentativi
    assert corpo["riconsiderazione"] is None, (
        "un tentativo fallito non e' una riconsiderazione: se lo fosse, la "
        "cadenza scadrebbe come se la casa fosse stata ripensata davvero")


@pytest.mark.asyncio
async def test_senza_archivio_i_tentativi_sono_NULL_come_le_sorelle():
    """**Un elenco vuoto direbbe «nessuno ci ha mai provato», e senza archivio
    non si SA.** Nello stesso payload `obiettivo` e `riconsiderazione` sono
    gia' `None` per questa ragione: un `[]` qui sarebbe la fondamenta 3 rotta
    dentro una risposta sola, e la pagina si salverebbe solo perche' legge
    l'assenza da un altro campo (rilievo della review indipendente,
    11/09/2026 -- la prima stesura di questa prova asseriva `[]` e il suo
    docstring difendeva l'errore).

    Mutazione che la uccide: tornare `[]` senza archivio.
    """
    corpo = _corpo(await handle_watching(_richiesta(_pagina(observations=None))))

    assert corpo["tentativi"] is None
    assert corpo["obiettivo"] is None and corpo["riconsiderazione"] is None


# -- la porta del resoconto (spec §9) ---------------------------------------

class _ArchivioConResoconto:
    """L'archivio, ridotto a cio' che la rotta del resoconto usa."""

    def __init__(self, per_giorno=None):
        self._per_giorno = per_giorno or {}

    def report(self, day):
        return self._per_giorno.get(day)

    def reports(self, *, limit=30):
        return [self._per_giorno[g] for g in sorted(self._per_giorno, reverse=True)][:limit]


_RESOCONTO = {
    "giorno": "2026-09-13",
    "misure": [{"soggetto": "dev1", "nome": "Inverter", "misura": "prodotta",
                "operazione": "somma_periodo", "valore": 23.71,
                "unita": "kWh", "copertura": 1.0}],
    "cronaca": [{"quando_ts": 1789219800.0, "fine_ts": None,
                 "chi": "climate.soggiorno", "cosa": "heat",
                 "nome": "Termostato Soggiorno"}],
}


@pytest.mark.asyncio
async def test_il_resoconto_di_un_giorno_si_chiede_per_data():
    from hiris.app.api.handlers_mind import handle_report

    app = {"observations": _ArchivioConResoconto({"2026-09-13": _RESOCONTO})}
    r = await handle_report(_richiesta(app, query={"day": "2026-09-13"}))

    assert json.loads(r.text)["resoconto"]["misure"][0]["valore"] == 23.71


@pytest.mark.asyncio
async def test_un_giorno_MAI_AGGREGATO_e_404_non_un_resoconto_vuoto():
    """«Quel giorno non e' successo niente» e «quel giorno non l'abbiamo
    guardato» sono due cose diverse, e l'analista deve poterle distinguere.
    Rispondere con un resoconto vuoto le appiattirebbe.

    Mutazione ESEGUITA: tornare `{"resoconto": {...vuoto}}` invece del 404 --
    rossa.
    """
    from hiris.app.api.handlers_mind import handle_report

    app = {"observations": _ArchivioConResoconto()}
    r = await handle_report(_richiesta(app, query={"day": "2026-01-01"}))

    assert r.status == 404


@pytest.mark.asyncio
async def test_SENZA_giorno_tornano_le_MISURE_di_molti_giorni_senza_cronaca():
    """**E' la lettura che serve all'analista**: due dei suoi tre inneschi sono
    confronti nel tempo, e con la cronaca dentro trenta giorni non
    starebbero in un prompt (misurato: 521 KB contro 92).

    Mutazione ESEGUITA: includere anche `cronaca` nella serie -- rossa.
    """
    from hiris.app.api.handlers_mind import handle_report

    app = {"observations": _ArchivioConResoconto({"2026-09-13": _RESOCONTO})}
    r = await handle_report(_richiesta(app))

    [giorno] = json.loads(r.text)["resoconti"]
    assert giorno["giorno"] == "2026-09-13"
    assert giorno["misure"]
    assert "cronaca" not in giorno


@pytest.mark.asyncio
async def test_lo_stesso_giorno_si_puo_chiedere_come_DOCUMENTO():
    from hiris.app.api.handlers_mind import handle_report
    from hiris.app.home_space.type_vocabulary import REPO_JUDGMENTS

    app = {"observations": _ArchivioConResoconto({"2026-09-13": _RESOCONTO}),
           "type_judgments": REPO_JUDGMENTS}
    r = await handle_report(_richiesta(
        app, query={"day": "2026-09-13", "formato": "documento"}))

    assert r.content_type == "text/markdown"
    assert "## Le misure" in r.text


@pytest.mark.asyncio
async def test_il_DOCUMENTO_confronta_la_cronaca_col_giudizio_di_ADESSO():
    """Spec 2026-09-16 §6: il documento dell'analista dice quando un giorno e'
    raccontato con un giudizio diverso da quello attuale. Mutazione ESEGUITA:
    in `handle_report` chiamare `as_document(resoconto)` senza
    `current_fingerprint` -- rossa sulla prima asserzione."""
    from hiris.app.api.handlers_mind import handle_report
    from hiris.app.home_space.type_vocabulary import REPO_JUDGMENTS

    attuale = {**_RESOCONTO, "giudizio": {"impronta": REPO_JUDGMENTS.chronicle_fingerprint()}}
    altro = {**_RESOCONTO, "giudizio": {"impronta": "0000000000000000"}}
    app = {"observations": _ArchivioConResoconto({"2026-09-13": altro, "2026-09-14": attuale}),
           "type_judgments": REPO_JUDGMENTS}
    r = await handle_report(_richiesta(
        app, query={"day": "2026-09-13", "formato": "documento"}))
    assert "giudizio diverso" in r.text
    r = await handle_report(_richiesta(
        app, query={"day": "2026-09-14", "formato": "documento"}))
    assert "giudizio diverso" not in r.text

# ── L'obiettivo si puo' finalmente SCRIVERE ──────────────────────────────────
#
# `store.set_objective` esisteva dal 11/09/2026, provata da dieci prove, e
# **nessun codice di produzione la chiamava**: nessuna rotta, nessun campo
# nella pagina, nessuno strumento in chat. Misurato sulla casa vera il
# 14/09/2026, l'obiettivo era ancora quello di fabbrica -- `scritto_ts: null`
# -- e l'osservatore decideva cosa guardare contro una frase generica, mentre
# la spec lo chiama «obiettivo = prompt».
#
# Il docstring di `set_objective` parla perfino del bottone «salva»: una
# motivazione scritta accanto al codice che il codice smentiva.


def _richiesta_scritta(app, corpo):
    class _R:
        def __init__(self):
            self.app = app
            self.query = {}

        async def json(self):
            if corpo is _ILLEGGIBILE:
                raise ValueError("corpo non leggibile")
            return corpo
    return _R()


_ILLEGGIBILE = object()


@pytest.mark.asyncio
async def test_si_puo_scrivere_l_obiettivo(tmp_path):
    """Mutazione: far tornare a `handle_set_objective` il solo `obiettivo`
    senza chiamare `set_objective` -- rossa."""
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        r = await handle_set_objective(_richiesta_scritta(
            {"observations": archivio}, {"testo": "spendere meno di sera"}))
        assert r.status == 200
        corpo = json.loads(r.text)
        assert corpo["scritto"] is True
        assert corpo["obiettivo"]["testo"] == "spendere meno di sera"
        assert corpo["obiettivo"]["scritto_ts"] is not None
        # E si rilegge da dove lo legge l'osservatore.
        assert archivio.objective()["testo"] == "spendere meno di sera"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_un_obiettivo_vuoto_si_RIFIUTA_e_non_cancella_quello_di_prima(tmp_path):
    """E' l'unica manopola del prodotto: un campo svuotato per errore non deve
    poter lasciare l'osservatore senza criterio. La regola vive gia' in
    `set_objective`; la rotta la riporta a chi chiama con un 400 invece di dire
    «fatto» senza aver fatto niente.

    Mutazione: rispondere 200 su un testo vuoto -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        await handle_set_objective(_richiesta_scritta(
            {"observations": archivio}, {"testo": "quello buono"}))
        r = await handle_set_objective(_richiesta_scritta(
            {"observations": archivio}, {"testo": "   "}))
        assert r.status == 400
        assert "vuoto" in json.loads(r.text)["errore"]
        assert archivio.objective()["testo"] == "quello buono"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_riscrivere_lo_STESSO_obiettivo_non_e_un_cambio(tmp_path):
    """Non sporca la storia: la pagina dice «da quando guardo questa cosa», e
    direbbe che tutto e' cambiato ogni volta che qualcuno preme «salva» senza
    aver toccato niente. La rotta lo dice con `scritto: false`, e **non e' un
    errore**: il campo contiene davvero quello che l'utente voleva.

    Mutazione: tornare `scritto: true` sempre -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        await handle_set_objective(_richiesta_scritta(
            {"observations": archivio}, {"testo": "uguale"}))
        r = await handle_set_objective(_richiesta_scritta(
            {"observations": archivio}, {"testo": "uguale"}))
        assert r.status == 200
        corpo = json.loads(r.text)
        assert corpo["scritto"] is False
        assert corpo["obiettivo"]["testo"] == "uguale"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_un_corpo_storto_e_un_400_non_un_500(tmp_path):
    """Mutazione: leggere `body["testo"]` senza controllarne il tipo -- 500."""
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for corpo in ({}, {"testo": 12}, {"altro": "x"}, [], _ILLEGGIBILE):
            r = await handle_set_objective(_richiesta_scritta(
                {"observations": archivio}, corpo))
            assert r.status == 400, corpo
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_senza_archivio_e_un_503_e_non_si_perde_niente():
    """L'avvio a meta': l'archivio non c'e' ancora. Stessa dottrina delle altre
    rotte del cervello -- 503, non 500, perche' e' un «riprova», non un guasto
    della richiesta.

    Mutazione: togliere la guardia -- 500.
    """
    r = await handle_set_objective(_richiesta_scritta({}, {"testo": "x"}))
    assert r.status == 503

@pytest.mark.asyncio
async def test_la_SERIE_dei_resoconti_porta_l_obiettivo_di_ogni_giorno(tmp_path):
    """**Difetto trovato dalla live review del 15/09/2026.** La migrazione
    aveva riempito l'obiettivo su tutti e venti i giorni archiviati -- un
    giorno chiesto da solo lo portava -- e la rotta della SERIE lo buttava:
    teneva `giorno` e `misure` e basta.

    E la serie e' **esattamente** la lettura per cui \u00a711 esiste: «chi legge
    trenta giorni di misure in serie deve saperlo, o legge una tendenza dove
    c'e' un cambio di domanda». L'obiettivo era stato messo nel resoconto e
    tolto proprio dove serve.

    Mutazione: togliere `obiettivo` dalla riga della serie -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        archivio.replace_report("2026-09-13", {
            "giorno": "2026-09-13",
            "obiettivo": {"testo": "spendere meno di sera", "scritto_ts": 1.0},
            "misure": [], "forme": [], "cronaca": []})
        r = await handle_report(_richiesta({"observations": archivio}))
        serie = json.loads(r.text)["resoconti"]
        assert serie[0]["obiettivo"] == {"testo": "spendere meno di sera",
                                         "scritto_ts": 1.0}
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_la_serie_NON_porta_la_cronaca_ne_le_forme(tmp_path):
    """L'obiettivo si aggiunge, il resto resta fuori: la cronaca e le forme si
    chiedono un giorno alla volta, ed e' la ragione per cui la serie sta in un
    prompt. Una riga d'obiettivo costa una frase; una cronaca costa migliaia
    di byte per giorno.

    Mutazione: mandare il resoconto intero -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        archivio.replace_report("2026-09-13", {
            "giorno": "2026-09-13", "obiettivo": None, "misure": [],
            "forme": [{"misura": "forma"}], "cronaca": [{"chi": "x"}]})
        r = await handle_report(_richiesta({"observations": archivio}))
        riga = json.loads(r.text)["resoconti"][0]
        assert set(riga) == {"giorno", "obiettivo", "misure"}
    finally:
        archivio.close()

@pytest.mark.asyncio
async def test_l_analisi_si_puo_chiedere(tmp_path):
    """La quarta fondamenta: se un dato c'e' e nessuno puo' chiederlo, non
    esiste. L'analista scrive ogni notte, e senza questa rotta il proprietario
    non lo leggerebbe mai.

    Mutazione: togliere la rotta -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        archivio.replace_analysis("2026-09-15", {"osservazioni": [
            {"cosa": "il prelievo e' salito", "innesco": 1}]})
        r = await handle_analysis(_richiesta({"observations": archivio},
                                             {"day": "2026-09-15"}))
        assert r.status == 200
        assert json.loads(r.text)["analisi"]["osservazioni"][0]["innesco"] == 1
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_un_giorno_MAI_analizzato_e_un_404_non_un_silenzio(tmp_path):
    """\u00abNon ho guardato\u00bb e \u00abho guardato e non c'era niente\u00bb sono due cose
    diverse: la seconda e' un'analisi con zero osservazioni, la prima non c'e'.

    Mutazione: tornare `{"osservazioni": []}` quando manca -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        r = await handle_analysis(_richiesta({"observations": archivio},
                                             {"day": "2026-09-15"}))
        assert r.status == 404
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_senza_giorno_tornano_le_ultime_analisi(tmp_path):
    """Mutazione: tornare solo l'ultima -- rossa."""
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        for g in ("2026-09-14", "2026-09-15"):
            archivio.replace_analysis(g, {"osservazioni": []})
        r = await handle_analysis(_richiesta({"observations": archivio}))
        assert [a["giorno"] for a in json.loads(r.text)["analisi"]] == [
            "2026-09-15", "2026-09-14"]
    finally:
        archivio.close()

@pytest.mark.asyncio
async def test_l_analisi_risolve_i_nomi_che_non_aveva(tmp_path):
    """**La stessa regola della serie, un piano piu' in la'.** L'analisi di un
    giorno si scrive una volta sola, e quella del 15/09/2026 e' nata prima che
    i nomi dei dispositivi arrivassero: porta `nome: null`, e riscriverla
    costerebbe 35.000 token per cambiare un'etichetta.

    L'archivio dice cio' che sapeva; **chi legge risolve cio' che puo' oggi**.
    Un'osservazione che il nome ce l'ha tiene il suo -- e' quello di allora, ed
    e' piu' vero.

    Mutazione: non risolvere -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    casa = _FintaCasa({"dispositivi": [{"id": "dev1", "nome": "SOLARE"},
                                       {"id": "dev2", "nome": "Termostato"}]})
    try:
        archivio.replace_analysis("2026-09-15", {"osservazioni": [
            {"soggetto": "dev1", "nome": None, "misura": "prelievo"},
            {"soggetto": "dev2", "nome": "come si chiamava allora",
             "misura": "comfort"},
            {"soggetto": "sconosciuto", "nome": None, "misura": "x"},
        ]})
        r = await handle_analysis(_richiesta(
            {"observations": archivio, "home_space_store": casa},
            {"day": "2026-09-15"}))
        oss = json.loads(r.text)["analisi"]["osservazioni"]
        assert oss[0]["nome"] == "SOLARE", "il buco si riempie con quello di oggi"
        assert oss[1]["nome"] == "come si chiamava allora", "quello archiviato vince"
        assert oss[2]["nome"] is None, (
            "un dispositivo che non si conosce resta senza nome: "
            "l'identificatore e' la verita', non un buco")
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_le_analisi_SENZA_giorno_risolvono_i_nomi_come_quella_col_giorno(tmp_path):
    """**La stessa porta non puo' rispondere due cose diverse sullo stesso
    fatto.**

    Misurato sulla casa vera il 15/09/2026: `GET /api/mind/analysis?day=...`
    tornava «SOLARE», `GET /api/mind/analysis` tornava `null` per le stesse
    cinque osservazioni. La forma senza giorno passava dall'archivio alla
    risposta senza toccare i nomi, e il changelog della 3.44.2 affermava che
    quella rotta li risolveva: vero su una forma su due.

    Mutazione ESEGUITA: risolvere solo la forma col giorno -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    casa = _FintaCasa({"dispositivi": [{"id": "dev1", "nome": "SOLARE"}]})
    try:
        archivio.replace_analysis("2026-09-15", {"osservazioni": [
            {"soggetto": "dev1", "nome": None, "misura": "prelievo"}]})
        r = await handle_analysis(_richiesta(
            {"observations": archivio, "home_space_store": casa}))
        elenco = json.loads(r.text)["analisi"]
        assert elenco[0]["osservazioni"][0]["nome"] == "SOLARE"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_le_MISURE_di_un_resoconto_portano_il_nome_come_la_cronaca(tmp_path):
    """**Stessa pagina, stesso dispositivo, una lingua sola.**

    Misurato sulla casa vera il 15/09/2026, resoconto del 14: **73 misure,
    zero col nome**, mentre la cronaca dello stesso giorno ne aveva 39 su 44.
    Il proprietario leggeva «SOLARE» nella sezione dell'analista e
    «513a6661274641ecf291c1be4121d9fa» in quella del resoconto -- lo stesso
    dispositivo, due righe piu' su.

    Mutazione ESEGUITA: lasciare le misure come stanno -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    casa = _FintaCasa({"dispositivi": [{"id": "dev1", "nome": "SOLARE"}]})
    try:
        archivio.replace_report("2026-09-14", {
            "giorno": "2026-09-14", "obiettivo": None,
            "misure": [{"soggetto": "dev1", "misura": "prelievo", "valore": 1.0},
                       {"soggetto": "ignoto", "misura": "x", "valore": 2.0}],
            "forme": [{"soggetto": "dev1", "misura": "profilo", "valore": []}],
            "cronaca": []})
        r = await handle_report(_richiesta(
            {"observations": archivio, "home_space_store": casa},
            {"day": "2026-09-14"}))
        resoconto = json.loads(r.text)["resoconto"]
        misure = resoconto["misure"]
        assert misure[0]["nome"] == "SOLARE"
        # **E le forme, che portano lo stesso soggetto**: risolverne una sola
        # rifarebbe dentro la stessa risposta il difetto chiuso fra misure e
        # cronaca. Mutazione ESEGUITA: non risolvere le forme -- rossa.
        assert resoconto["forme"][0]["nome"] == "SOLARE"
        assert misure[1].get("nome") is None, (
            "un dispositivo che l'anagrafe non conosce resta senza nome")
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_anche_la_SERIE_dei_resoconti_porta_i_nomi(tmp_path):
    """La quarta porta. Le tre forme del resoconto e le due dell'analisi
    rispondono con la stessa regola, o la pagina cambia lingua a seconda di
    dove guarda.

    Mutazione ESEGUITA: risolvere solo la forma col giorno -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    casa = _FintaCasa({"dispositivi": [{"id": "dev1", "nome": "SOLARE"}]})
    try:
        archivio.replace_report("2026-09-14", {
            "giorno": "2026-09-14", "obiettivo": None,
            "misure": [{"soggetto": "dev1", "misura": "prelievo", "valore": 1.0}],
            "forme": [], "cronaca": []})
        r = await handle_report(_richiesta(
            {"observations": archivio, "home_space_store": casa}))
        serie = json.loads(r.text)["resoconti"]
        assert serie[0]["misure"][0]["nome"] == "SOLARE"
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_senza_anagrafe_l_analisi_si_legge_lo_stesso(tmp_path):
    """L'avvio a meta': l'anagrafe non c'e' ancora. L'analisi si legge com'e'
    -- un nome mancante e' meno grave di un 503 su un dato che c'e'.

    Mutazione: sollevare, o tornare 503 -- rossa.
    """
    archivio = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        archivio.replace_analysis("2026-09-15", {"osservazioni": [
            {"soggetto": "dev1", "nome": None, "misura": "prelievo"}]})
        r = await handle_analysis(_richiesta({"observations": archivio},
                                             {"day": "2026-09-15"}))
        assert r.status == 200
        assert json.loads(r.text)["analisi"]["osservazioni"][0]["nome"] is None
    finally:
        archivio.close()

class _FintoSapere:
    def __init__(self, riassunto=None, unexplained=None):
        self._riassunto = riassunto or {"totale": 0, "righe": []}
        self._unexplained = unexplained or []

    def summary(self):
        return self._riassunto

    def not_understood(self):
        return list(self._unexplained)

    def judgment_rows(self):
        # `handle_knowledge` porta anche i giudizi (spec 2026-09-16 §7): le
        # prove qui guardano conteggi e non capiti, i giudizi le loro
        # (`tests/test_handlers_mind_judgment.py`).
        return []


assert_stessa_firma(sap.KnowledgeStore.judgment_rows, _FintoSapere.judgment_rows,
                    nome="judgment_rows")


@pytest.mark.asyncio
async def test_il_sapere_si_puo_finalmente_CHIEDERE():
    """**La quarta fondamenta**: se un dato c'e' e nessuno puo' chiederlo, non
    esiste. Il sapere contiene le direzioni dell'energia, i significati delle
    classi, gli attributi che valgono la pena e le ricette dei dispositivi --
    e fino al 15/09/2026 si leggeva da tre punti del codice e da **nessuna
    pagina**.

    Mutazione: togliere la rotta -- 404.
    """
    sapere = _FintoSapere(riassunto={"totale": 3, "righe": [
        {"specie": "tipo", "campo": "significato", "provenienza": "importato",
         "quante": 2},
        {"specie": "dispositivo", "campo": "ricetta", "provenienza": "dedotto",
         "quante": 1}]})
    r = await handle_knowledge(_richiesta({"knowledge": sapere}))
    assert r.status == 200
    corpo = json.loads(r.text)
    assert corpo["conteggi"]["totale"] == 3
    assert corpo["conteggi"]["righe"][0]["quante"] == 2


@pytest.mark.asyncio
async def test_le_righe_NON_CAPITE_viaggiano_con_chi_e_quando():
    """Sono cio' che il proprietario risolverebbe in dieci secondi, e la
    pagina deve poterle mostrare con la loro data: una riga di tre settimane
    fa puo' riguardare un dispositivo che nel frattempo e' cambiato.

    Mutazione: mandare solo il valore -- rossa.
    """
    fatto = sap.Fact(subject_kind="dispositivo", subject="dev1",
                     field="ricetta_non_capita", value="non ho capito cosa misura",
                     provenance="dedotto", evidence="le entita' del dispositivo",
                     verification="non_capito", who="modello (ponte)",
                     when_ts=1787000000.0)
    r = await handle_knowledge(_richiesta({"knowledge": _FintoSapere(unexplained=[fatto])}))
    riga = json.loads(r.text)["non_capito"][0]
    assert riga["soggetto"] == "dev1"
    assert riga["valore"] == "non ho capito cosa misura"
    assert riga["chi"] == "modello (ponte)"
    assert riga["quando_ts"] == 1787000000.0


@pytest.mark.asyncio
async def test_senza_sapere_e_un_503_non_un_sapere_vuoto():
    """«L'archivio non e' collegato» e «il sapere e' vuoto» sono due cose
    diverse: la seconda direbbe che HIRIS non ha capito niente della casa.

    Mutazione: tornare `{"conteggi": {"totale": 0}}` -- rossa.
    """
    r = await handle_knowledge(_richiesta({}))
    assert r.status == 503

# ---------------------------------------------------------------------------
# Le porte esistono DAVVERO, cioe' sono registrate sul router
# ---------------------------------------------------------------------------

def test_le_porte_del_cervello_sono_REGISTRATE_non_solo_scritte():
    """**La quarta fondamenta protetta dove si rompe davvero.**

    Trovato dalla revisione indipendente del 15/09/2026, con la mutazione
    eseguita: si poteva **cancellare** `app.router.add_get("/api/mind/
    knowledge", ...)` da `server.py` e l'intera suite restava verde. Tutte le
    prove di questo file chiamano la funzione del gestore direttamente, senza
    passare dal router: provano che il gestore risponde, non che qualcuno lo
    possa chiamare. «Un dato che nessuno puo' chiedere non esiste» era
    esattamente la proprieta' non protetta.

    Si legge il sorgente e non si costruisce l'applicazione: `create_app()`
    apre archivi, semina e parla con Home Assistant -- qui serve sapere una
    cosa sola, e va saputa senza montare il mondo.

    Mutazione ESEGUITA: togliere una qualunque delle cinque registrazioni --
    rossa.
    """
    import pathlib

    from hiris.app import server

    sorgente = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    for rotta, gestore in (("/api/mind/watching", "handle_watching"),
                           ("/api/mind/report", "handle_report"),
                           ("/api/mind/analysis", "handle_analysis"),
                           ("/api/mind/knowledge", "handle_knowledge")):
        assert f'add_get("{rotta}", {gestore})' in sorgente, (
            f"la porta {rotta} non e' registrata: il gestore esiste ma "
            "nessuno puo' chiamarlo")
    assert 'add_post("/api/mind/objective", handle_set_objective)' in sorgente, (
        "senza questa, l'obiettivo si puo' leggere e non scrivere")
