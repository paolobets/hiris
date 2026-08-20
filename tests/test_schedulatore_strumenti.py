"""I tre strumenti delle promesse, e le verifiche che fanno ALLA NASCITA."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
from hiris.app.schedulatore.archivio import ArchivioPromesse

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
    return (datetime.now(timezone.utc) + timedelta(minutes=minuti)).isoformat()


@pytest.fixture()
def promesse(tmp_path):
    a = ArchivioPromesse(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


def _dispatcher(promesse, **extra):
    """Un dispatcher con i soli pezzi che servono a questi test.

    Gli altri archivi restano `None`: i gestori dichiarano un errore invece di
    sollevare, ed e' il contratto della classe.
    """
    return DispatcherStrumenti(None, None, promesse=promesse, **extra)


def test_i_tre_strumenti_sono_nel_catalogo():
    nomi = {d["name"] for d in STRUMENTI_CONOSCENZA}
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
    assert promesse.elenca(solo_in_sospeso=True)


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
    passava anche se `verifica()` fosse ESPLOSA (il doppio del registro non
    aveva `servizi_di`, che `azione/verifica.py` chiama proprio nel ramo «il
    servizio non esiste» -- vedi `_RegistroFinto` sotto) invece di rifiutare
    col motivo vero. Ora si asserisce il CONTENUTO del messaggio: deve nominare
    il servizio inventato e i servizi che esistono davvero, che e' possibile
    solo se `verifica()` e' arrivata fino in fondo al ramo giusto senza
    sollevare.
    """
    d = _dispatcher(promesse, registro=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.inventato",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" in esito
    assert "light.inventato" in esito["errore"]
    assert "turn_on" in esito["errore"]  # il servizio vero, che il rifiuto elenca
    assert promesse.elenca() == []


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
    assert promesse.elenca() == []


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
    assert d._registro is None
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica la temperatura",
        "quando": _fra(60), "domanda": "e' aumentata?"})
    assert "errore" not in esito
    assert esito["promessa"]["specie"] == "chiedi"


@pytest.mark.asyncio
async def test_un_fai_valido_nasce(promesse):
    d = _dispatcher(promesse, registro=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "fai", "frase": "alle 17 accendi lo studio",
        "quando": _fra(60),
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}}})
    assert "errore" not in esito


@pytest.mark.asyncio
async def test_un_recapito_inesistente_e_rifiutato_alla_nascita(promesse):
    d = _dispatcher(promesse, registro=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": _fra(60),
        "domanda": "e' aumentata?", "recapito": "notify.non_esiste"})
    assert "errore" in esito
    assert "notify" in esito["errore"]


@pytest.mark.asyncio
async def test_l_istantanea_si_prende_adesso_con_l_unita(promesse):
    d = _dispatcher(promesse, registro=_RegistroFinto(), cache=_CacheFinta())
    esito = await d.dispatch("prometti", {
        "specie": "chiedi", "frase": "verifica la temperatura",
        "quando": _fra(60),
        "domanda": "e' aumentata?", "da_confrontare": ["sensor.camera_t"]})
    misure = esito["promessa"]["istantanea"]
    assert misure[0]["entita"] == "sensor.camera_t"
    assert misure[0]["valore"] == "21.4"
    assert misure[0]["unita"] == "°C"      # senza unita' e' il `72` senza scala


@pytest.mark.asyncio
async def test_un_quando_illeggibile_e_un_rifiuto_leggibile(promesse):
    esito = await _dispatcher(promesse).dispatch("prometti", {
        "specie": "chiedi", "frase": "x", "quando": "domani verso sera",
        "domanda": "e' aumentata?"})
    assert "errore" in esito
    assert promesse.elenca() == []


class _RegistroFinto:
    """Il doppio del registro dei servizi (`azione/registro.py::RegistroServizi`).

    Fix review Task 6, Rilievo 1: espone SOLO i metodi che il percorso
    esercitato da questo file legge davvero -- `domini()` e `servizio()`
    (chiamati da `_verifica_ora`/`_verifica_recapito`), e `servizi_di()`, che
    `azione/verifica.py` chiama nel ramo «il servizio non esiste» per
    elencare quelli veri. Senza `servizi_di()` quel ramo faceva sollevare
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
    _SERVIZI = {("light", "turn_on"): {}, ("notify", "mobile_app_x"): {}}

    def domini(self):
        return ["light", "notify"]

    def servizio(self, dominio, nome):
        return self._SERVIZI.get((dominio, nome))

    def servizi_di(self, dominio):
        return sorted(nome for (dom, nome) in self._SERVIZI if dom == dominio)


class _CacheFinta:
    """Il doppio dello specchio dello stato.

    `loaded` guida `inventario_leggibile` (`proxy/entity_cache.py`); il
    metodo che porta gli stati e' `all_states()`, non `get_all()` -- e'
    quello vero di `EntityCache`, lo stesso che legge sia
    `DispatcherStrumenti._specchio` sia `azione/porta.py::Porta._stati`.
    Un doppio con `get_all()` non avrebbe mai potuto produrre il difetto che
    il test del passo 7 chiede di provare: `_stati_grezzi()` avrebbe sempre
    ricevuto una cache "senza `all_states`" e il test sarebbe passato anche
    con `_verifica_ora` saltata per intero.
    """
    loaded = True

    def all_states(self):
        return [
            {"id": "light.studio", "state": "off", "attributes": {}},
            {"id": "sensor.camera_t", "state": "21.4",
             "attributes": {"unit_of_measurement": "°C"}},
        ]
