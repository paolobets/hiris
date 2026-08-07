import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherConoscenza
from hiris.app.memoria.archivio import ArchivioMemoria
from tests.test_nucleo import _CASA, _COMPORTAMENTO

# _CASA/_COMPORTAMENTO sono di tests/test_nucleo.py, importati invece di
# ricopiati -- stessa casa che gia' esercita nucleo.py e domande.py (vedi
# tests/test_domande.py, stessa convenzione).
#
# `_CASA` e' gia' nella forma "post-lettura" (id/nome/piano_id/alias/...),
# la stessa che `ArchivioCasa.leggi()` restituisce: si scrive direttamente
# nelle tabelle SQLite invece di passare da `sostituisci()` (che si aspetta
# i registri grezzi di Home Assistant, floor_id/name/... -- tradurli qui
# sarebbe solo rumore, i test di `ArchivioCasa` gia' coprono quella strada
# in tests/test_casa_archivio.py).


def _semina_casa(tmp_path, casa=_CASA, comportamento=_COMPORTAMENTO):
    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    conn = archivio._conn  # unico modo per seminare la forma "letta" senza duplicare sostituisci()
    conn.execute("BEGIN")
    for piano in casa["piani"]:
        conn.execute("INSERT INTO piani (id, nome, livello) VALUES (?,?,?)",
                     (piano["id"], piano["nome"], piano.get("livello")))
    for area in casa["aree"]:
        conn.execute(
            "INSERT INTO aree (id, nome, piano_id, alias, etichette) VALUES (?,?,?,?,?)",
            (area["id"], area["nome"], area.get("piano_id"), "[]", "[]"))
    for entita in casa["entita"]:
        conn.execute(
            "INSERT INTO entita (id, nome, area_id, dispositivo_id, classe, unita, "
            "disabilitata, alias, etichette) VALUES (?,?,?,?,?,?,?,?,?)",
            (entita["id"], entita.get("nome"), entita.get("area_id"),
             entita.get("dispositivo_id"), entita.get("classe"), entita.get("unita"),
             1 if entita.get("disabilitata") else 0, "[]", "[]"))
    conn.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES ('aggiornata_il', '2026-01-01')")
    conn.execute("INSERT OR REPLACE INTO meta (chiave, valore) VALUES ('non_disponibili', '[]')")
    conn.commit()
    if comportamento:
        archivio.sostituisci_comportamento(comportamento)
    return archivio


@pytest.fixture
def archivio_casa(tmp_path):
    a = _semina_casa(tmp_path)
    yield a
    a.chiudi()


@pytest.fixture
def archivio_casa_ambiguo(tmp_path):
    """Due «Bagno» su piani diversi -- la stessa ambiguita' gia' coperta in
    tests/test_domande.py per Indice.trova(), qui alla superficie del
    dispatcher."""
    casa = {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0},
                  {"id": "primo", "nome": "Primo piano", "livello": 1}],
        "aree": [{"id": "bagno_terra", "nome": "Bagno", "piano_id": "terra"},
                 {"id": "bagno_primo", "nome": "Bagno", "piano_id": "primo"}],
        "entita": [],
    }
    a = _semina_casa(tmp_path, casa=casa, comportamento=[])
    yield a
    a.chiudi()


@pytest.fixture
def memoria(tmp_path):
    m = ArchivioMemoria(str(tmp_path / "memoria.db"))
    yield m
    m.chiudi()


@pytest.fixture
def dispatcher(archivio_casa, memoria):
    return DispatcherConoscenza(archivio_casa, memoria)


@pytest.fixture
def dispatcher_ambiguo(archivio_casa_ambiguo, memoria):
    return DispatcherConoscenza(archivio_casa_ambiguo, memoria)


def test_gli_strumenti_sono_quattro_e_nessuno_tocca_la_casa():
    """Da 34 a 4. E nessuno scrive in Home Assistant: la chat della 2.0
    conosce, non agisce."""
    nomi = {s["name"] for s in STRUMENTI_CONOSCENZA}
    assert nomi == {"cerca", "guarda", "ricorda", "richiama"}


def test_ogni_definizione_ha_una_descrizione_utile():
    """Una descrizione vaga e' un tool che il modello usa male: sono quattro,
    possono permettersi di essere spiegati bene."""
    for s in STRUMENTI_CONOSCENZA:
        assert len(s["description"]) > 60
        assert s["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_cerca_dichiara_l_ambiguita(dispatcher_ambiguo):
    """Due «Bagno» su piani diversi: il contratto e' `candidati` sempre lista
    piu' `ambiguo`, e appiattirlo qui rifarebbe un difetto gia' costato un fix."""
    esito = await dispatcher_ambiguo.dispatch("cerca", {"testo": "il bagno"})
    assert esito["trovati"][0]["ambiguo"] is True
    assert len(esito["trovati"][0]["candidati"]) == 2


@pytest.mark.asyncio
async def test_guarda_un_area_da_entita_stati_e_ricordi(dispatcher):
    esito = await dispatcher.dispatch("guarda", {"tipo": "area", "riferimento": "cucina"})
    assert esito["esiste"] is True
    assert esito["entita"]


@pytest.mark.asyncio
async def test_guarda_qualcosa_che_non_esiste_lo_dice(dispatcher):
    esito = await dispatcher.dispatch("guarda", {"tipo": "area", "riferimento": "taverna"})
    assert esito["esiste"] is False


@pytest.mark.asyncio
async def test_ricorda_salva_davvero(dispatcher, memoria):
    """IL difetto da cui e' nato tutto: «preso nota» senza salvare niente."""
    esito = await dispatcher.dispatch("ricorda", {
        "testo": "d'inverno il soggiorno ideale e' 19.5",
        "forza": "preferenza",
        "ancore": [{"tipo": "area", "riferimento": "cucina"}],
    })
    assert esito["salvato"] is True
    assert memoria.richiama()[0]["testo"] == "d'inverno il soggiorno ideale e' 19.5"


@pytest.mark.asyncio
async def test_ricorda_scarta_un_ancora_inventata_e_lo_dice(dispatcher, memoria):
    """Il modello propone, il codice restringe: un'ancora senza riscontro non
    si scrive, e il ricordo resta comunque -- la struttura e' opzionale."""
    esito = await dispatcher.dispatch("ricorda", {
        "testo": "mi piace il caffe' la mattina",
        "ancore": [{"tipo": "area", "riferimento": "taverna"}],
    })
    assert esito["salvato"] is True
    assert esito["problemi"]
    assert memoria.richiama()[0]["ancore"] == []


@pytest.mark.asyncio
async def test_richiama_da_i_ricordi_di_una_parte_della_casa(dispatcher, memoria):
    memoria.ricorda("in cucina niente luci dopo le 23", detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "cucina",
                             "nome_visto": "cucina"}])
    esito = await dispatcher.dispatch("richiama", {"riferimento": "cucina"})
    assert len(esito["ricordi"]) == 1


@pytest.mark.asyncio
async def test_uno_strumento_che_non_esiste_lo_dice(dispatcher):
    """E non accusa il modello di averlo inventato quando gliel'abbiamo dato
    noi: e' un difetto gia' corretto una volta su questo ramo."""
    esito = await dispatcher.dispatch("accendi_la_luce", {})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_argomenti_mancanti_non_esplodono(dispatcher):
    esito = await dispatcher.dispatch("guarda", {})
    assert "errore" in esito


# --- Copertura aggiuntiva, oltre i dieci test del brief -------------------


@pytest.mark.asyncio
async def test_uno_strumento_che_non_esiste_non_accusa_il_modello(dispatcher):
    """Su questo ramo c'e' gia' stato un caso in cui HIRIS diceva al modello
    «non inventare nomi di tool» per uno strumento che gli avevamo dato noi:
    il messaggio deve restare neutro, non un rimprovero."""
    esito = await dispatcher.dispatch("spegni_tutto", {})
    assert "inventat" not in esito["errore"].lower()
    assert "invent" not in esito["errore"].lower()


@pytest.mark.asyncio
async def test_ricorda_senza_testo_non_esplode(dispatcher):
    esito = await dispatcher.dispatch("ricorda", {})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_richiama_senza_riferimento_non_esplode(dispatcher):
    esito = await dispatcher.dispatch("richiama", {})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_guarda_un_automazione_porta_il_corpo(dispatcher):
    esito = await dispatcher.dispatch(
        "guarda", {"tipo": "automazione", "riferimento": "automation.sveglia"})
    assert esito["esiste"] is True
    assert esito["corpo"] == {"trigger": []}


@pytest.mark.asyncio
async def test_guarda_un_ricordo_per_id(dispatcher, memoria):
    ident = memoria.ricorda("mi piace il caffe' la mattina", detto_da="paolo", forza="fatto")
    esito = await dispatcher.dispatch("guarda", {"tipo": "ricordo", "riferimento": ident})
    assert esito["esiste"] is True
    assert esito["testo"] == "mi piace il caffe' la mattina"


@pytest.mark.asyncio
async def test_cerca_senza_testo_non_esplode(dispatcher):
    esito = await dispatcher.dispatch("cerca", {})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_cerca_niente_di_riconoscibile_non_e_un_errore(dispatcher):
    esito = await dispatcher.dispatch("cerca", {"testo": "xyzzy qwerty"})
    assert esito["trovati"] == []
