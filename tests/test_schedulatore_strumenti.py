"""I tre strumenti delle promesse, e le verifiche che fanno ALLA NASCITA."""
import os
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import pytest

from hiris.app.azione.registro import ServiceRegistry
from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS, ToolDispatcher
from hiris.app.proxy.entity_cache import _to_minimal
from hiris.app.schedulatore.archivio import AgendaStore
from tests._contratti import assert_stessa_firma

# NON un `pytestmark` di modulo: a differenza di `test_schedulatore_orologio.py`
# (dove ogni test e' async), qui un test e' sincrono
# (`test_i_tre_strumenti_sono_nel_catalogo`, sul solo catalogo statico) e la
# suite gira in modalita' `strict` di pytest-asyncio -- vedi la stessa nota in
# `test_azione_verifica.py`. Un `pytestmark` di modulo marcherebbe anche lui,
# e pytest-asyncio avvisa (`PytestWarning`) per un mark su una funzione non
# async: un warning nuovo che il resto della suite non ha. Si marca test per
# test, come fa gia' `test_azione_verifica.py`.


def _fra(minuti: int) -> str:
    """Un istante ISO-8601 col fuso, `minuti` da ADESSO -- quello vero.

    Il brief di questo task scriveva `quando` come una data di calendario
    fissa ("2026-08-19T18:00:00+02:00"). `_prometti` confronta `quando` con
    `time.time()` VERO (non un orologio finto passato dal test): una data
    scritta a mano e' un rifiuto "e' gia' passato" in attesa di succedere, e
    difatti e' successo -- questi test fallivano se eseguiti la sera dello
    stesso giorno di calendario, con l'errore sbagliato (il tempo, non cio'
    che il test voleva provare). `_fra()` calcola sempre relativo ad ADESSO,
    quindi la promessa nasce a prescindere da quando gira la suite.
    """
    return (datetime.now(UTC) + timedelta(minutes=minuti)).isoformat()


@pytest.fixture()
def promesse(tmp_path):
    a = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _dispatcher(promesse, **extra):
    """Un dispatcher con i soli pezzi che servono a questi test.

    Gli altri archivi restano `None`: i gestori dichiarano un errore invece di
    sollevare, ed e' il contratto della classe.
    """
    return ToolDispatcher(None, None, agenda=promesse, **extra)


def test_i_tre_strumenti_sono_nel_catalogo():
    nomi = {d["name"] for d in KNOWLEDGE_TOOLS}
    assert {"prometti", "promesse", "disdici"} <= nomi


@pytest.mark.asyncio
async def test_senza_archivio_prometti_dichiara_l_assenza_e_non_solleva():
    esito = await _dispatcher(None).dispatch("prometti", {"specie": "fai"})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_prometti_un_chiedi_crea_la_promessa(promesse):
    d = _dispatcher(promesse)
    esito = await d.dispatch("prometti", {
        "specie": "chiedi",
        "frase": "fra un'ora verifica la temperatura della camera",
        "quando": _fra(60),
        "quando_detto": "fra un'ora",
        "domanda": "e' aumentata rispetto ad adesso?",
    })
    assert "errore" not in esito
    assert esito["promessa"]["specie"] == "chiedi"
    assert promesse.list(solo_in_sospeso=True)


@pytest.mark.asyncio
async def test_promesse_elenca_cio_che_e_in_sospeso(promesse):
    d = _dispatcher(promesse)
    await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?"})
    esito = await d.dispatch("promesse", {})
    assert len(esito["promesse"]) == 1


@pytest.mark.asyncio
async def test_disdici_annulla_e_una_gia_disdetta_lo_dichiara(promesse):
    d = _dispatcher(promesse)
    creata = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?"})
    ident = creata["promessa"]["id"]

    assert "errore" not in await d.dispatch("disdici", {"id": ident})
    secondo = await d.dispatch("disdici", {"id": ident})
    assert "errore" in secondo


@pytest.mark.asyncio
async def test_un_fai_con_un_servizio_inesistente_e_rifiutato_SUBITO(promesse):
    """Il cuore della fetta: il rifiuto arriva ora, non alle 17.

    Fix review Task 6, Rilievo 1: prima asseriva solo `"errore" in esito`, e
    passava anche se `verification()` fosse ESPLOSA (il doppio del registro non
    aveva `services_for`, che `azione/verifica.py` chiama proprio nel ramo «il
    servizio non esiste» -- vedi `_RegistroFinto` sotto) invece di rifiutare
    col motivo vero. Ora si asserisce il CONTENUTO del messaggio: deve nominare
    il servizio inventato e i servizi che esistono davvero, che e' possibile
    solo se `verification()` e' arrivata fino in fondo al ramo giusto senza
    sollevare.
    """
    d = _dispatcher(promesse, registry=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.inventato",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" in esito
    assert "light.inventato" in esito["errore"]
    assert "turn_on" in esito["errore"]  # il servizio vero, che il rifiuto elenca
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_un_fai_senza_registro_e_rifiutato_non_verificato_in_silenzio(promesse):
    """Rilievo 2 della review, deciso dal proprietario: senza registro un
    `fai` si RIFIUTA, non nasce in silenzio.

    Prima del cablaggio del Task 7 il registro e' SEMPRE `None` in
    produzione: se questo strumento tacesse (come faceva prima di questo
    fix), OGGI ogni `fai` nascerebbe senza che il suo servizio sia mai stato
    verificato -- e `PROMETTI_TOOL_DEF` dichiara al modello, senza
    condizioni, «viene VERIFICATA adesso». Stessa guardia di
    `azione/porta.py::_REGISTRO_MUTO`, spostata al momento della promessa.
    """
    d = _dispatcher(promesse)  # nessun registro, nessuna cache
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" in esito
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_un_fai_con_registro_presente_ma_mai_caricato_e_rifiutato_come_senza_registro(
    promesse,
):
    """Il caso limite che il cablaggio del Task 7 rende raggiungibile per la
    prima volta: all'avvio `server.py` costruisce SEMPRE `ServiceRegistry()`
    (mai `None`), ma vuoto -- si carica al primo uso, non all'avvio. Senza la
    guardia su `domains()`, `_verifica_ora` avrebbe proseguito fino a
    `verification()`, che avrebbe rifiutato con «il dominio "light" non esiste in
    questa casa. Domini disponibili: .» -- una frase FALSA detta con
    sicurezza (la casa non e' vuota, e' il registro che non e' stato letto),
    esattamente cio' da cui mette in guardia `azione/porta.py::_MUTE_REGISTRY`.
    """
    # `cache=_CacheFinta()`: senza uno specchio dello stato leggibile
    # `_verifica_ora` si ferma prima (`_stati_grezzi()` -> `None` -> nessun
    # rifiuto), e il test non arriverebbe mai al ramo che questa guardia
    # esiste per chiudere -- vedi `verification()` in `azione/verifica.py`.
    d = _dispatcher(promesse, registry=_RegistroVuoto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" in esito
    assert "Domini disponibili" not in esito["errore"]
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_un_fai_senza_specchio_e_rifiutato_non_verificato_in_silenzio(promesse):
    """Rilievo minore della review finale, terza occorrenza dello stesso
    schema gia' deciso due volte (registro assente: Task 6; recapito: Task
    7): senza uno specchio leggibile `_verifica_ora` tornava `None` -- nessun
    rifiuto -- e la promessa nasceva senza che il suo servizio fosse mai
    stato verificato, mentre `PROMETTI_TOOL_DEF` dichiara al modello «viene
    VERIFICATA adesso» senza condizioni."""
    d = _dispatcher(promesse, registry=_RegistroFinto())  # nessuna cache
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" in esito
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_un_chiedi_nasce_anche_senza_registro(promesse):
    """Il gemello del test sopra: un `chiedi` non passa da `_verifica_ora`
    (non ha `chiamata`), quindi la guardia nuova sul registro non deve
    toccarlo. Non e' un test ridondante con
    `test_prometti_un_chiedi_crea_la_promessa`: quello non dichiara ESPLICITO
    che il dispatcher e' senza registro -- lo e' per omissione dell'argomento
    -- questo lo rende un'asserzione intenzionale, cosi' che un domani in cui
    qualcuno stringesse la guardia a TUTTE le specie se ne accorga subito."""
    d = _dispatcher(promesse)  # nessun registro, apposta
    assert d._registry is None
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica la temperatura",
        "quando": _fra(60), "domanda": "e' aumentata?"})
    assert "errore" not in esito
    assert esito["promessa"]["specie"] == "chiedi"


@pytest.mark.asyncio
async def test_un_fai_valido_nasce(promesse):
    d = _dispatcher(promesse, registry=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" not in esito


@pytest.mark.asyncio
async def test_un_recapito_inesistente_e_rifiutato_alla_nascita(promesse):
    """Registro CARICO, recapito davvero inesistente: il rifiuto vero, non
    quello di «non lo so ancora» -- le due frasi restano distinte (review
    Task 7, Rilievo 1)."""
    d = _dispatcher(promesse, registry=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?", "recapito": "notify.non_esiste"})
    assert "errore" in esito
    assert "notify" in esito["errore"]
    assert "non e' pronto" not in esito["errore"]


@pytest.mark.asyncio
async \
def test_un_recapito_con_registro_presente_ma_mai_caricato_e_rifiutato_come_non_ancora_verificabile(
    promesse,
):
    """Il gemello del test sopra su `_verifica_ora` (review Task 7, Rilievo
    1): prima del fix, un `_RegistroVuoto` (presente, `domains()` vuoto)
    faceva rispondere `service(dominio, nome)` con `None` per QUALUNQUE
    recapito -- «"notify.mobile_app_x" non esiste in questa casa», una frase
    FALSA (il servizio esiste, e' il registro che non e' stato ancora letto).
    Peggio del `fai` equivalente: un recapito sbagliato non fallisce
    rumorosamente, fa si' che la risposta della promessa non arrivi a
    nessuno."""
    d = _dispatcher(promesse, registry=_RegistroVuoto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?", "recapito": "notify.mobile_app_x"})
    assert "errore" in esito
    assert "non e' pronto" in esito["errore"]
    assert "non esiste in questa casa" not in esito["errore"]
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_prometti_scalda_il_registro_vuoto_se_il_canale_ha_c_e(promesse):
    """Il difetto misurato dal vivo su 3.9.1: un add-on appena avviato ha un
    registro PRESENTE ma mai caricato (si carica pigramente alla prima
    azione ESEGUITA, `azione/porta.py::ActionActuator.execute`) -- e prima di questo
    fix `_prometti` interrogava `_registro_non_pronto()` senza mai scaldare
    il registro. L'utente aveva appena chiesto di leggere le otto
    temperature (riuscito: quella lettura passa da un'altra strada, non dal
    registro dei servizi) e poi un `prometti` con recapito veniva rifiutato
    per sempre con "il registro dei servizi non e' pronto", anche se Home
    Assistant era raggiungibile e pronto a rispondere.

    `_HaConServizi` deve saper rispondere `get_services()` per DAVVERO (una
    lista non vuota, nella forma vera di `/api/services`): se rispondesse un
    errore o niente il registro resterebbe vuoto comunque, e questo test
    passerebbe per il motivo sbagliato -- non proverebbe che il registro si
    e' scaldato, solo che non e' esploso.
    """
    ha = _HaConServizi()
    registry = ServiceRegistry()
    assert registry.empty()  # la premessa esatta del difetto: mai caricato
    d = _dispatcher(promesse, registry=registry, ha=ha, cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?", "recapito": "notify.mobile_app_x"})
    assert "errore" not in esito
    assert ha.chiamate_get_services == 1
    assert not registry.empty()  # scaldato per davvero, non solo tollerato


@pytest.mark.asyncio
async def test_prometti_senza_canale_ha_non_tenta_di_scaldare_il_registro(promesse):
    """Il gemello del test sopra (punto 3 del task): senza un canale HA vivo
    il registro non si puo' caricare (`ensure_fresh` vuole un client), e
    deve restare il rifiuto onesto di sempre -- MAI tentare comunque.

    `_RegistroTracciaScaldamento.assicura_fresco` solleva se viene chiamato:
    e' la finta che sa PRODURRE il difetto (fondamenta "test che non possono
    fallire") -- se la guardia sul canale assente sparisse, questa finta lo
    direbbe subito, mentre un'asserzione sul solo messaggio di errore no
    (un `try/except` a monte lo inghiottirebbe comunque in "non e' pronto").
    """
    registry = _RegistroTracciaScaldamento()
    d = _dispatcher(promesse, registry=registry, cache=_CacheFinta())  # nessun ha
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?", "recapito": "notify.mobile_app_x"})
    assert not registry.chiamato  # non si e' nemmeno tentato di scaldarlo
    assert "errore" in esito
    assert "non e' pronto" in esito["errore"]


@pytest.mark.asyncio
async def test_l_istantanea_si_prende_adesso_con_l_unita(promesse):
    d = _dispatcher(promesse, registry=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica la temperatura",
        "quando": _fra(60),
        "domanda": "e' aumentata?", "da_confrontare": ["sensor.camera_t"]})
    misure = esito["promessa"]["istantanea"]
    assert misure[0]["entita"] == "sensor.camera_t"
    assert misure[0]["valore"] == "21.4"
    assert misure[0]["unita"] == "°C"      # senza unita' e' il `72` senza scala


@pytest.mark.asyncio
async def test_un_da_confrontare_con_riferimento_inesistente_e_rifiutato_alla_nascita(promesse):
    """Il cuore della fetta R7: un `chiedi` che nomina un riferimento che lo
    specchio non conosce ("Soggiorno" invece di un entity_id vero, o
    qualunque id inventato) non nasce con `valore: null` e una nota che
    nessuno legge fra un'ora -- si rifiuta SUBITO, come un `fai` con un
    servizio inventato (`test_un_fai_con_un_servizio_inesistente_e_rifiutato_SUBITO`).

    Si asserisce il CONTENUTO del rifiuto (il riferimento nominato + l'invito
    a "cerca"), non solo la sua presenza -- lo stesso rilievo gia' fatto
    su quel test gemello: un rifiuto generico che non nomina nulla
    lascerebbe passare una guardia rotta che rifiuta sempre, a caso.
    """
    d = _dispatcher(promesse, registry=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica il soggiorno",
        "quando": _fra(60),
        "domanda": "e' aumentata?", "da_confrontare": ["sensor.soggiorno_t"]})
    assert "errore" in esito
    assert "sensor.soggiorno_t" in esito["errore"]
    assert "cerca" in esito["errore"]
    assert promesse.list() == []


@pytest.mark.asyncio
async def test_un_chiedi_senza_da_confrontare_resta_legittimo_anche_senza_specchio(promesse):
    """Requisito 2 della spec R7, reso esplicito: un `chiedi` senza
    `da_confrontare` non chiede mai nessuna istantanea, quindi non deve MAI
    toccare lo specchio -- nessuna cache passata al dispatcher, apposta: se
    la guardia nuova leggesse lo specchio anche a lista vuota, questo test lo
    direbbe (il rifiuto "non vedo lo stato di questa casa" comparirebbe)."""
    d = _dispatcher(promesse)  # nessuna cache, apposta
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?"})
    assert "errore" not in esito
    assert esito["promessa"]["istantanea"] == []


@pytest.mark.asyncio
async def test_un_da_confrontare_senza_specchio_leggibile_e_rifiutato_non_verificato_in_silenzio(
    promesse,
):
    """Requisito 3: stessa domanda di `_verifica_ora` sullo specchio cieco
    (`test_un_fai_senza_specchio_e_rifiutato_non_verificato_in_silenzio`), qui
    per `da_confrontare` -- riusa la STESSA forma, non ne inventa una terza:
    senza uno specchio leggibile non si sa se il riferimento esiste, quindi
    non si tace facendo nascere una promessa mai verificata."""
    d = _dispatcher(promesse, registry=_RegistroFinto())  # nessuna cache
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica il soggiorno",
        "quando": _fra(60),
        "domanda": "e' aumentata?", "da_confrontare": ["sensor.soggiorno_t"]})
    assert "errore" in esito
    assert promesse.list() == []


def test_la_cache_finta_riproduce_la_forma_minimale_vera():
    """`_CacheFinta.all_states()` non inventa la forma: deve coincidere,
    campo per campo, con cio' che `_to_minimal()` -- la funzione VERA di
    `proxy/entity_cache.py` -- produce sulle stesse entita' HA grezze.

    Questo e' il test che pinna il doppio (mutazione 2 del task R6): se
    qualcuno rimettesse in `_CacheFinta` la forma HA grezza
    (`attributes.unit_of_measurement` invece di `unit` di primo livello),
    questo confronto fallirebbe SUBITO, invece di lasciare che il doppio si
    allontani in silenzio dal codice vero -- esattamente come e' successo
    con la forma precedente.
    """
    grezzi = [
        {"entity_id": "light.studio", "state": "off",
         "attributes": {"friendly_name": "Studio"}},
        {"entity_id": "sensor.camera_t", "state": "21.4",
         "attributes": {"friendly_name": "Camera T",
                         "unit_of_measurement": "°C",
                         "device_class": "temperature",
                         "state_class": "measurement"}},
    ]
    attesi = [_to_minimal(g) for g in grezzi]
    assert _CacheFinta().all_states() == attesi


@pytest.mark.asyncio
async def test_un_quando_illeggibile_e_un_rifiuto_leggibile(promesse):
    esito = await _dispatcher(promesse).dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": "domani verso sera",
        "domanda": "e' aumentata?"})
    assert "errore" in esito
    assert promesse.list() == []


class _RegistroFinto:
    """Il doppio del registro dei servizi (`azione/registro.py::ServiceRegistry`).

    Fix review Task 6, Rilievo 1: espone SOLO i metodi che il percorso
    esercitato da questo file legge davvero -- `domains()` e `service()`
    (chiamati da `_verifica_ora`/`_verifica_recapito`), e `services_for()`, che
    `azione/verifica.py` chiama nel ramo «il servizio non esiste» per
    elencare quelli veri. Senza `services_for()` quel ramo faceva sollevare
    `AttributeError`, catturato solo dalla rete di sicurezza generica di
    `dispatch()`: il test bandiera passava lo stesso (`"errore" in esito`
    resta vero anche per un'eccezione), ma non perche' la verifica avesse
    rifiutato col motivo giusto -- perche' era esplosa. Un doppio allineato
    «per avere gli stessi nomi» invece che per coprire cio' che viene letto
    davvero.

    `vuoto()` e `assicura_fresco()` (della classe vera, usati da
    `azione/porta.py` prima di eseguire) sono usciti da qui apposta: nessun
    gestore di `DispatcherStrumenti` li chiama, e tenerli avrebbe continuato
    a dare l'illusione di un doppio completo senza che nulla li provasse.
    """
    _SERVIZI: ClassVar[dict[tuple[str, str], dict]] = {
        ("light", "turn_on"): {}, ("notify", "mobile_app_x"): {},
    }

    def domains(self):
        return ["light", "notify"]

    def service(self, domain, name):
        return self._SERVIZI.get((domain, name))

    def services_for(self, domain):
        return sorted(nome for (dom, nome) in self._SERVIZI if dom == domain)


class _RegistroVuoto:
    """Il doppio del registro PRESENTE ma mai caricato da Home Assistant --
    lo stato reale di `app["registro_servizi"]` fra l'avvio e la prima
    `assicura_fresco()`. Solo `domains()`: e' l'UNICO metodo che
    `_verifica_ora` deve poter chiamare su un registro in questo stato, prima
    di rifiutare -- se ne chiamasse un altro (`service()`, `services_for()`)
    solleverebbe `AttributeError` invece di rifiutare col motivo giusto,
    esattamente l'errore che la review del Task 6 aveva trovato nel percorso
    gemello (vedi `_RegistroFinto` sopra)."""

    def domains(self):
        return []


def test_i_registri_finti_combaciano_con_la_firma_vera():
    """Se `ServiceRegistry` cambia firma, questo test cade invece di
    lasciare che i finti imitino un contratto che non esiste piu'."""
    assert_stessa_firma(ServiceRegistry.domains, _RegistroFinto.domains, nome="domains")
    assert_stessa_firma(ServiceRegistry.service, _RegistroFinto.service, nome="service")
    assert_stessa_firma(ServiceRegistry.services_for, _RegistroFinto.services_for,
                        nome="services_for")
    assert_stessa_firma(ServiceRegistry.domains, _RegistroVuoto.domains,
                        nome="domains (vuoto)")
    assert_stessa_firma(ServiceRegistry.ensure_fresh,
                        _RegistroTracciaScaldamento.ensure_fresh, nome="ensure_fresh")


class _HaConServizi:
    """Il doppio del canale HA che risponde a `get_services()` per davvero
    -- quello che `ServiceRegistry.assicura_fresco` chiama per scaldarsi.

    Deve saper PRODURRE il difetto: `light`/`notify` con almeno un
    servizio ciascuno, nella stessa forma di `RISPOSTA_HA`
    (`tests/test_azione_porta.py`) -- una lista vuota o un'eccezione
    lascerebbe il registro vuoto comunque, e nasconderebbe che
    `ensure_fresh` non e' mai stata chiamata invece di provarlo.
    """

    def __init__(self):
        self.chiamate_get_services = 0

    async def get_services(self):
        self.chiamate_get_services += 1
        return [
            {"domain": "light", "services": {
                "turn_on": {"target": {"entity": [{"domain": ["light"]}]}}}},
            {"domain": "notify", "services": {"mobile_app_x": {}}},
        ]


class _RegistroTracciaScaldamento:
    """Il doppio del registro che si accorge se qualcuno ha provato a
    scaldarlo -- e si rifiuta di farlo passare inosservato: solleva.

    Serve al test gemello di quello sopra (canale HA assente): la guardia
    su `_canale_ha() is None` deve impedire la chiamata PRIMA che parta, non
    limitarsi a sperare che un `try/except` a valle la inghiotta -- questa
    finta lo dimostra tenendo il conto (`chiamato`) invece di limitarsi a
    non rompersi.
    """

    def __init__(self):
        self.chiamato = False

    def domains(self):
        return []

    async def ensure_fresh(self, ha_client):
        self.chiamato = True
        raise AssertionError(
            "ensure_fresh non doveva essere chiamato senza un canale HA")


class _CacheFinta:
    """Il doppio dello specchio dello stato.

    `loaded` guida `inventory_is_readable` (`proxy/entity_cache.py`); il
    metodo che porta gli stati e' `all_states()`, non `get_all()` -- e'
    quello vero di `EntityCache`, lo stesso che legge sia
    `DispatcherStrumenti._specchio` sia `azione/porta.py::Porta._stati`.
    Un doppio con `get_all()` non avrebbe mai potuto produrre il difetto che
    il test del passo 7 chiede di provare: `_stati_grezzi()` avrebbe sempre
    ricevuto una cache "senza `all_states`" e il test sarebbe passato anche
    con `_verifica_ora` saltata per intero.

    Il difetto R6: `all_states()` NON e' lo stato grezzo di Home Assistant
    (`entity_id`/`attributes.unit_of_measurement`/`attributes.friendly_name`)
    -- e' cio' che produce `proxy/entity_cache.py::_to_minimal`, che PROIETTA
    quella forma su una diversa: chiave `id` (non `entity_id`), `name` al
    posto di `attributes.friendly_name`, e soprattutto `unit` DI PRIMO
    LIVELLO al posto di `attributes.unit_of_measurement`. Prima di questo
    fix il doppio riproduceva la forma grezza -- `{"attributes":
    {"unit_of_measurement": "°C"}}` -- e cosi' facendo nascondeva il
    disallineamento che il codice vero ha in produzione, invece di provarlo:
    e' il decimo "test che non puo' fallire" di questo progetto (R6 della
    spec 2026-08-20-i-riferimenti).

    Le due voci sotto sono `_to_minimal()` applicata a mano alle stesse
    entita' HA grezze che `test_la_cache_finta_riproduce_la_forma_minimale_vera`
    ricalcola con la funzione vera: se questo elenco tornasse a imitare la
    forma grezza, quel test lo direbbe SUBITO (mutazione 2 del task).
    """
    loaded = True

    def all_states(self):
        return [
            # `_to_minimal({"entity_id": "light.studio", "state": "off",
            #               "attributes": {"friendly_name": "Studio"}})`:
            # dominio "light" senza "brightness"/"color_temp" negli
            # attributi -> nessuna chiave "attributes" nel risultato.
            {"id": "light.studio", "state": "off", "name": "Studio",
             "unit": "", "domain": "light", "device_class": None,
             "state_class": None, "last_changed": None},
            # `_to_minimal({"entity_id": "sensor.camera_t", "state": "21.4",
            #               "attributes": {"friendly_name": "Camera T",
            #                              "unit_of_measurement": "°C",
            #                              "device_class": "temperature",
            #                              "state_class": "measurement"}})`:
            # dominio "sensor" non e' in `_DOMAIN_ATTRS` -> nessuna chiave
            # "attributes" nemmeno qui.
            {"id": "sensor.camera_t", "state": "21.4", "name": "Camera T",
             "unit": "°C", "domain": "sensor", "device_class": "temperature",
             "state_class": "measurement", "last_changed": None},
        ]
