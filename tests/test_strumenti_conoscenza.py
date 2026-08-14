import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.strumenti import STRUMENTI_CONOSCENZA, DispatcherStrumenti
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
    return DispatcherStrumenti(archivio_casa, memoria)


@pytest.fixture
def dispatcher_ambiguo(archivio_casa_ambiguo, memoria):
    return DispatcherStrumenti(archivio_casa_ambiguo, memoria)


def test_il_catalogo_e_questo_e_uno_solo_di_essi_tocca_la_casa():
    """L'UNICO pin dell'identita' del catalogo: qui i nomi si scrivono a mano
    apposta, cosi' che aggiungerne o toglierne uno sia una decisione e non un
    effetto collaterale. Ovunque altro si DERIVANO da qui.

    Da 34 a 4, e ora 5. Il quinto, `esegui`, e' l'unico che scrive in Home
    Assistant -- e non lo fa da se': chiede alla porta unica
    (`azione/porta.py`), che verifica prima e rilegge dopo. E' la differenza
    con i trentaquattro usciti, dove ciascuno attuava per conto proprio."""
    nomi = {s["name"] for s in STRUMENTI_CONOSCENZA}
    assert nomi == {"cerca", "guarda", "ricorda", "richiama", "esegui"}


def test_ogni_definizione_ha_una_descrizione_utile():
    """Una descrizione vaga e' un tool che il modello usa male: sono pochi,
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


class _CacheFinta:
    """La forma vera di `entity_cache`: chiave "id", non "entity_id"."""

    def __init__(self, stati):
        self._stati = stati

    def all_states(self):
        return [{"id": k, "state": v} for k, v in self._stati.items()]


@pytest.mark.asyncio
async def test_guarda_mostra_lo_stato_vivo(archivio_casa, memoria):
    """Sapere che una luce e' accesa e' CONOSCENZA, non azione: `guarda` legge
    lo specchio dello stato e non lo scrive -- nemmeno adesso che il prodotto
    agisce. Chi scrive e' `esegui`, e passa dalla porta. Prima `guarda`
    restituiva sempre `stato: None` perche' la cache non era cablata --
    onesto ma inutile."""
    cache = _CacheFinta({"light.cucina_1": "on", "light.cucina_2": "off"})
    d = DispatcherStrumenti(archivio_casa, memoria, cache=cache)
    esito = await d.dispatch("guarda", {"tipo": "area", "riferimento": "cucina"})
    stati = {e["id"]: e["stato"] for e in esito["entita"]}
    assert stati["light.cucina_1"] == "on"
    assert stati["light.cucina_2"] == "off"
    assert "stato_non_letto" not in esito


@pytest.mark.asyncio
async def test_senza_inventario_leggibile_lo_stato_si_dichiara_non_letto(archivio_casa, memoria):
    """Ogni `stato: None` sarebbe altrimenti ambiguo fra «l'entita' non ha
    stato» e «non ho potuto guardare»."""
    d = DispatcherStrumenti(archivio_casa, memoria, cache=None)
    esito = await d.dispatch("guarda", {"tipo": "area", "riferimento": "cucina"})
    assert esito["stato_non_letto"] is True


class _CacheGuastaMaDichiarataPronta:
    """`loaded` e' True (la cache si dichiara pronta) ma `all_states()`
    solleva -- il caso che il fix E1-③ chiude: senza di esso
    `inventario_leggibile()` vedrebbe solo `loaded=True` e non
    dichiarerebbe mai `stato_non_letto`, anche con la lettura vera fallita
    e `stato: None` su tutto."""

    loaded = True

    def all_states(self):
        raise RuntimeError("cache corrotta")


@pytest.mark.asyncio
async def test_uno_stato_vivo_che_solleva_si_dichiara_non_letto(archivio_casa, memoria):
    """Fix E1-③: `_stato_vivo` inghiottiva l'eccezione e restituiva `{}`,
    indistinguibile da "nessuna entita' ha stato" -- con la cache che si
    dichiara comunque caricata, `stato_non_letto` non scattava mai."""
    d = DispatcherStrumenti(archivio_casa, memoria, cache=_CacheGuastaMaDichiarataPronta())
    esito = await d.dispatch("guarda", {"tipo": "area", "riferimento": "cucina"})
    assert esito["stato_non_letto"] is True


class _CacheConNomi:
    """Una cache finta che mente come mente la realta': entita' con
    friendly_name, entita' senza, e la chiave "id" (non "entity_id")."""
    loaded = True

    def all_states(self):
        return [{"id": "light.abat_jour_1", "state": "off", "name": "Abat-jour"},
                {"id": "light.x", "state": "on", "name": ""},
                {"id": "sensor.y", "state": "21"},          # senza chiave "name"
                "non un dizionario"]


def test_lo_specchio_restituisce_stato_e_nomi_in_una_lettura(archivio_casa, memoria):
    d = DispatcherStrumenti(archivio_casa, memoria, cache=_CacheConNomi())
    stato, nomi, letto = d._specchio()
    assert letto is True
    assert stato["light.abat_jour_1"] == "off" and stato["sensor.y"] == "21"
    assert nomi == {"light.abat_jour_1": "Abat-jour"}


@pytest.mark.asyncio
async def test_cerca_trova_un_entita_senza_nome_grazie_al_friendly_name(archivio_casa, memoria):
    """Le abat-jour, dal vivo: quattro giri di `cerca` diventano uno."""
    archivio_casa.sostituisci({"entita": [
        {"entity_id": "light.abat_jour_1", "name": None, "original_name": None}]}, [])
    d = DispatcherStrumenti(archivio_casa, memoria, cache=_CacheConNomi())
    esito = await d.dispatch("cerca", {"testo": "accendi l'abat-jour"})
    riferimenti = [c["riferimento"] for v in esito["trovati"] for c in v["candidati"]]
    assert riferimenti == ["light.abat_jour_1"]
    assert "non_ho_potuto_guardare" not in esito


@pytest.mark.asyncio
async def test_guarda_un_entita_senza_nome_dichiara_il_nome_dedotto_dal_dispatcher(
        archivio_casa, memoria):
    """Il test che prova la FETTA, non solo la funzione pura: i tre test di
    `test_domande.py` chiamano `guarda()` direttamente e le passano
    `nomi_di_ripiego` a mano, quindi restano verdi anche se `_guarda` smette
    di inoltrare i nomi vivi dell'archivio -- esattamente il difetto che
    questo task esiste per chiudere. Solo passando da `dispatch()` con una
    cache che porta un `friendly_name` si prova che il collegamento c'e'
    davvero (mutazione che uccide: togliere `nomi_di_ripiego=nomi_vivi`
    dalla chiamata a `_guarda_dettaglio` in `strumenti._guarda`)."""
    archivio_casa.sostituisci({"entita": [
        {"entity_id": "light.abat_jour_1", "name": None, "original_name": None}]}, [])
    d = DispatcherStrumenti(archivio_casa, memoria, cache=_CacheConNomi())
    esito = await d.dispatch("guarda", {"tipo": "entita", "riferimento": "light.abat_jour_1"})
    assert esito["esiste"] is True
    assert esito["nome"] is None
    assert esito["nome_dedotto"] == "Abat-jour"


@pytest.mark.asyncio
async def test_cerca_dichiara_un_registro_caduto_invece_di_restituire_una_lista_vuota_muta(
        archivio_casa, memoria):
    archivio_casa.sostituisci({"aree": [], "entita": []}, ["entita"])
    esito = await DispatcherStrumenti(archivio_casa, memoria).dispatch(
        "cerca", {"testo": "il bagno"})
    assert esito["trovati"] == []
    assert any("entita" in m for m in esito["non_ho_potuto_guardare"])


@pytest.mark.asyncio
async def test_cerca_dichiara_lo_specchio_illeggibile_quando_ci_sono_entita_senza_nome(
        archivio_casa, memoria):
    """Mutazione uccisa: dichiarare lo specchio illeggibile SEMPRE. Su una
    casa in cui tutti hanno un nome, non c'e' niente da dichiarare."""
    archivio_casa.sostituisci({"entita": [
        {"entity_id": "light.senza", "name": None, "original_name": None}]}, [])

    class _NonPronta:
        loaded = False
        def all_states(self): return []

    esito = await DispatcherStrumenti(archivio_casa, memoria, cache=_NonPronta()).dispatch(
        "cerca", {"testo": "abat-jour"})
    assert any("specchio" in m for m in esito["non_ho_potuto_guardare"])


@pytest.mark.asyncio
async def test_su_una_casa_intera_con_lo_specchio_giu_cerca_non_si_lamenta(archivio_casa, memoria):
    archivio_casa.sostituisci({"entita": [
        {"entity_id": "light.c", "name": "Luce cucina"}]}, [])

    class _NonPronta:
        loaded = False
        def all_states(self): return []

    esito = await DispatcherStrumenti(archivio_casa, memoria, cache=_NonPronta()).dispatch(
        "cerca", {"testo": "luce cucina"})
    assert "non_ho_potuto_guardare" not in esito


@pytest.mark.asyncio
async def test_cerca_non_conta_un_entita_disabilitata_senza_nome_come_cecita(archivio_casa, memoria):
    """Mutazione uccisa: contare fra le «senza nome» anche le entita'
    disabilitate. Una disabilitata senza nome non e' cercabile per scelta
    dell'utente, non per un limite di HIRIS -- non deve produrre una scusa."""
    archivio_casa.sostituisci({"entita": [
        {"entity_id": "light.c", "name": "Luce cucina"},
        {"entity_id": "light.disabilitata", "name": None, "original_name": None,
         "disabled_by": "user"}]}, [])
    esito = await DispatcherStrumenti(archivio_casa, memoria).dispatch(
        "cerca", {"testo": "luce cucina"})
    assert "non_ho_potuto_guardare" not in esito


def test_uno_specchio_che_solleva_non_restituisce_nomi_a_meta(archivio_casa, memoria):
    """Fix E1-(3), esteso ai nomi: meta' dei nomi e' peggio di nessuno,
    perche' le entita' mancanti sembrerebbero non esistere."""
    class _Rotta:
        """Cade A META' LETTURA, non prima: una finta che solleva senza aver
        prodotto niente lascia `stato` e `nomi` vuoti comunque, e quindi non
        sa distinguere «restituisco ({}, {}, False)» da «restituisco quello
        che ho raccolto finora». Il difetto che questo test esiste per
        impedire e' proprio il secondo, e una finta che non sa produrlo non
        prova niente."""
        loaded = True
        def all_states(self):
            yield {"id": "light.a", "state": "on", "name": "Luce A"}
            raise RuntimeError("boom")
    stato, nomi, letto = DispatcherStrumenti(archivio_casa, memoria, cache=_Rotta())._specchio()
    assert (stato, nomi, letto) == ({}, {}, False)


def test_senza_cache_lo_specchio_e_vuoto_ma_non_dichiara_un_guasto(archivio_casa, memoria):
    assert DispatcherStrumenti(archivio_casa, memoria, cache=None)._specchio() == ({}, {}, True)


@pytest.mark.asyncio
async def test_richiama_con_tipo_fuori_vocabolario_lo_dice(dispatcher, memoria):
    """Fix E1-②: «richiama» con un `tipo` che non e' area/entita/dispositivo
    restituiva `{"ricordi": []}` -- indistinguibile da "non ti ho detto
    niente", anche quando il ricordo esiste davvero."""
    memoria.ricorda("in cucina niente luci dopo le 23", detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "cucina",
                             "nome_visto": "cucina"}])
    esito = await dispatcher.dispatch("richiama", {"riferimento": "cucina", "tipo": "stanza"})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_richiama_con_tipo_accentato_lo_dice(dispatcher):
    """«entità» con l'accento -- plausibilissimo per un modello italiano che
    non lo sta copiando da uno schema -- non e' lo stesso testo del
    vocabolario vero ("entita", senza accento)."""
    esito = await dispatcher.dispatch("richiama", {"riferimento": "cucina", "tipo": "entità"})
    assert "errore" in esito


@pytest.mark.asyncio
async def test_senza_archivi_dice_cosa_manca_non_un_errore_python():
    """Il dispatcher promette errori LEGGIBILI dal modello. Con gli archivi a
    None il modello riceveva «'NoneType' object has no attribute 'leggi'»: un
    errore Python travestito da risposta, che non gli permette ne' di capire
    ne' di spiegarlo all'utente -- solo di riprovare all'infinito."""
    d = DispatcherStrumenti(None, None, cache=None)
    for nome, argomenti in [
        ("cerca", {"testo": "cucina"}),
        ("guarda", {"tipo": "area", "riferimento": "cucina"}),
        ("ricorda", {"testo": "una frase"}),
        ("richiama", {"riferimento": "cucina"}),
    ]:
        esito = await d.dispatch(nome, argomenti)
        assert "errore" in esito
        assert "NoneType" not in esito["errore"]
        assert "caricat" in esito["errore"]      # dice COSA manca
