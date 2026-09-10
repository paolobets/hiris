"""Le categorie: quattro comandi WebSocket, zero lettori (reperto 24).

HIRIS leggeva il registro delle categorie di Home Assistant con QUATTRO
comandi WS a ogni ricostruzione dell'anagrafe -- uno per ambito
(`automation`, `script`, `scene`, `helpers`) -- lo salvava nella tabella
`categorie`, e nessuno lo leggeva. Conoscenza muta: costa la lettura e non
rende niente. E' la fondamenta dell'AUTONOMIA FUNZIONALE letta al contrario.

Peggio: l'ASSEGNAZIONE per-entita' arriva gratis dentro la risposta che HIRIS
gia' riceve -- `categories` e' un campo di `RegistryEntry.as_partial_dict`,
verificato sul sorgente di HA -- e non veniva nemmeno salvata.

Le categorie sono la stessa cosa delle etichette dall'altro capo: una
tassonomia che l'utente scrive a mano. Quindi la stessa strada, e le stesse
due trappole:

1. nei registri HA manda gli IDENTIFICATIVI, non i nomi. Le etichette
   uscivano come `da_controllare` invece di «Da controllare» -- una parola che
   l'utente non ha mai scritto, e che non cambia nemmeno rinominando
   l'etichetta;
2. il registro delle categorie e' partizionato per AMBITO (`scope` e' un
   parametro obbligatorio del comando, verificato in
   `components/config/category_registry.py`) e le righe che torna NON lo
   riportano. Due categorie omonime in ambiti diversi sono cose diverse:
   l'ambito fa parte dell'identita'.
"""
import sqlite3

import pytest

from hiris.app.home_space.queries import view
from hiris.app.home_space.reader import HomeSpace, build_home_space
from hiris.app.home_space.topology import category_names
from hiris.app.memory.resolver import costruisci_indice

# Il campo `ambito` di ogni riga NON viene da Home Assistant: lo mette
# `ha_client.read_registries`, che chiede il registro una volta per ambito e
# marca le righe con quello che ha chiesto (vedi `_CATEGORY_SCOPES`).
# `01luci` compare DUE volte con due nomi diversi apposta: e' cio' che
# distingue una chiave (ambito, id) da una chiave sul solo id.
_REGISTRI = {
    "aree": [{"area_id": "giardino", "name": "Giardino"}],
    "dispositivi": [{"id": "d1", "name": "Centralina", "area_id": "giardino"}],
    "entita": [
        {"entity_id": "automation.luci_giardino", "name": "Luci giardino",
         "area_id": "giardino", "categories": {"automation": "01luci"}},
        {"entity_id": "scene.cena", "name": "Cena", "area_id": "giardino",
         "categories": {"scene": "01luci"}},
        # `categories` e' un campo di `RegistryEntry`: ce l'ha OGNI entita',
        # non solo gli helper. Questa sta su un dispositivo apposta, cosi' la
        # terza porta di `guarda` (quella del dispositivo) e' esercitata.
        {"entity_id": "switch.pompa", "name": "Pompa", "device_id": "d1",
         "area_id": None, "categories": {"automation": "01luci"}},
        # In una categoria che il registro non nomina: un riferimento
        # penzolante, o un ambito caduto -- ne cadono quattro separatamente.
        {"entity_id": "script.irrigazione", "name": "Irrigazione",
         "area_id": "giardino", "categories": {"script": "01sparita"}},
        # `entity_category` (config) E una categoria dell'utente sulla stessa
        # entita': due fatti diversi che non devono confondersi.
        {"entity_id": "input_boolean.vacanza", "name": "Vacanza",
         "area_id": "giardino", "entity_category": "config",
         "categories": {"helpers": "01vac"}},
        # Nessuna categoria: il caso NORMALE.
        {"entity_id": "light.faretto", "name": "Faretto", "area_id": "giardino"},
    ],
    "categorie": [
        {"category_id": "01luci", "name": "Luci esterne", "ambito": "automation"},
        {"category_id": "01luci", "name": "Atmosfere", "ambito": "scene"},
        {"category_id": "01vac", "name": "Vacanza casa", "ambito": "helpers"},
    ],
}


@pytest.fixture
def casa(tmp_path):
    a = HomeSpace(str(tmp_path / "casa.db"))
    a.hold_registries(_REGISTRI, [])
    letta = a.read()
    a.close()
    return letta


# --- l'assegnazione: gratis dentro una risposta che si buttava -------------

def test_l_archivio_salva_l_assegnazione_per_entita(casa):
    """Arrivava gia' dentro `config/entity_registry/list` e finiva nel nulla.

    Resta un DIZIONARIO ambito -> id, non una lista: un'entita' puo' stare in
    una categoria per ambito (`RegistryEntry.categories: dict[str, str]`), e
    appiattirla in una lista di id butterebbe via l'ambito.
    """
    voce = next(e for e in casa["entita"] if e["id"] == "automation.luci_giardino")
    assert voce["categorie"] == {"automation": "01luci"}
    senza = next(e for e in casa["entita"] if e["id"] == "light.faretto")
    assert senza["categorie"] == {}


def test_il_registro_resta_indicizzato_per_coppia(casa):
    """La chiave e' (ambito, id), non l'id.

    Home Assistant partiziona il registro per ambito e non lo riporta nelle
    righe. Su una chiave fatta del solo id, la seconda «01luci» scriverebbe
    sopra la prima e un'automazione si sentirebbe rispondere il nome di una
    scena -- in silenzio, e senza mai piu' cambiare.
    """
    nomi = category_names(casa)
    assert nomi[("automation", "01luci")] == "Luci esterne"
    assert nomi[("scene", "01luci")] == "Atmosfere"


# --- da `guarda`: col NOME, e con l'ambito --------------------------------

def test_guarda_un_entita_dice_le_sue_categorie_COL_NOME(casa):
    """La trappola gia' pagata con le etichette.

    Nei registri HA manda i soli `category_id`. Farli uscire tali e quali
    vorrebbe dire riferire all'utente un identificativo che non ha mai
    scritto, e che non cambia nemmeno rinominando la categoria.
    """
    d = view(casa, [], [], {}, "entita", "automation.luci_giardino")
    assert d["categorie"] == {"automation": "Luci esterne"}


def test_l_ambito_esce_insieme_al_nome(casa):
    """Due categorie omonime in ambiti diversi sono due cose diverse: se
    uscisse il solo nome, chi legge non potrebbe piu' distinguerle.

    Qui i nomi sono diversi ma l'id e' lo STESSO: senza l'ambito nella
    risposta, «Atmosfere» e «Luci esterne» sarebbero due stringhe senza
    niente che dica a quale tassonomia appartengono.
    """
    d = view(casa, [], [], {}, "entita", "scene.cena")
    assert d["categorie"] == {"scene": "Atmosfere"}


def test_una_categoria_che_il_registro_non_nomina_resta_il_suo_id(casa):
    """Un riferimento penzolante -- o uno dei quattro ambiti caduto -- non fa
    sparire l'assegnazione: «sta in una categoria che non so nominare» e' piu'
    vero di «non ha categoria». Stessa scelta di `labels_with_name`."""
    d = view(casa, [], [], {}, "entita", "script.irrigazione")
    assert d["categorie"] == {"script": "01sparita"}


def test_senza_categorie_la_chiave_non_compare(casa):
    """`categorie: {}` su ogni cosa sarebbe rumore in ogni risposta e --
    peggio -- indistinguibile da un registro caduto. Stessa disciplina di
    `etichette` e di `unita`."""
    d = view(casa, [], [], {}, "entita", "light.faretto")
    assert "categorie" not in d


def test_categoria_e_categorie_restano_due_fatti_distinti(casa):
    """`categoria` (singolare) e' l'`entity_category` di Home Assistant --
    `config`/`diagnostic`, decisa dall'INTEGRAZIONE. `categorie` (plurale) e'
    la tassonomia dell'UTENTE. Sulla stessa entita' convivono e non si
    sovrascrivono."""
    d = view(casa, [], [], {}, "entita", "input_boolean.vacanza")
    assert d["categoria"] == "config"
    assert d["categorie"] == {"helpers": "Vacanza casa"}


# --- la stessa forma da tutte le porte ------------------------------------

def test_le_tre_porte_di_guarda_dicono_la_stessa_cosa(casa):
    """CONSISTENZA. `piattaforma` ed `etichette` uscivano da una porta su tre,
    ed e' il difetto per cui `_enrich_entity` e' nata: un campo nuovo che
    entra da un ramo solo lo rifa'."""
    dall_entita = view(casa, [], [], {}, "entita", "switch.pompa")
    dal_dispositivo = view(casa, [], [], {}, "dispositivo", "d1")
    pompa = next(e for e in dal_dispositivo["entita"] if e["id"] == "switch.pompa")
    dall_area = view(casa, [], [], {}, "area", "giardino")
    luci = next(e for e in dall_area["entita"] if e["id"] == "automation.luci_giardino")

    atteso = {"automation": "Luci esterne"}
    assert dall_entita["categorie"] == atteso
    assert pompa["categorie"] == atteso, "la porta del dispositivo tace"
    assert luci["categorie"] == atteso, "la porta dell'area tace"


# --- da `cerca`: la parola che l'utente ha scritto ------------------------

def test_si_cerca_per_nome_di_categoria(casa):
    """Se una categoria non porta a niente, HIRIS chiede all'utente di
    ripetere a parole cio' che aveva gia' dichiarato una volta.

    Si cerca «luci esterne» -- il NOME -- non `01luci`: un identificativo e'
    una stringa che nessuno pronuncera' mai.
    """
    indice = costruisci_indice(casa)
    candidati = [c for t in indice.find("luci esterne") for c in t["candidati"]]
    assert {"tipo": "entita", "riferimento": "automation.luci_giardino"} in candidati
    assert {"tipo": "entita", "riferimento": "switch.pompa"} in candidati


def test_l_identificativo_non_diventa_un_termine_di_ricerca(casa):
    """Il contrario della prova sopra, e serve quanto quella: indicizzare gli
    id avrebbe fatto passare l'altra senza che i nomi entrassero mai."""
    indice = costruisci_indice(casa)
    assert indice.find("01luci") == []


def test_la_categoria_non_diventa_il_nome_di_niente(casa):
    """Entra fra i termini che `find()` riconosce, non fra i nomi: un'entita'
    continua a chiamarsi come la chiama la casa."""
    d = view(casa, [], [], {}, "entita", "automation.luci_giardino")
    assert d["nome"] == "Luci giardino"
    assert "nome_dedotto" not in d


# --- lo schema: un archivio vecchio deve poter risalire -------------------

def test_un_archivio_gia_esistente_guadagna_la_colonna(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` non tocca una tabella che esiste gia'.

    Senza la migrazione 4, il primo `replace` dopo l'aggiornamento
    fallirebbe e la casa smetterebbe di ricostruirsi -- in silenzio, dal
    momento dell'aggiornamento in poi.
    """
    percorso = str(tmp_path / "vecchio.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE entita (id TEXT PRIMARY KEY, nome TEXT, area_id TEXT, "
        "dispositivo_id TEXT, piattaforma TEXT, categoria TEXT, classe TEXT, "
        "unita TEXT, disabilitata INTEGER NOT NULL DEFAULT 0, "
        "nascosta INTEGER NOT NULL DEFAULT 0, alias TEXT NOT NULL DEFAULT '[]', "
        "etichette TEXT NOT NULL DEFAULT '[]');")
    vecchio.commit()
    vecchio.close()

    a = HomeSpace(percorso)
    try:
        a.hold_registries(_REGISTRI, [])
        letta = a.read()
    finally:
        a.close()
    voce = next(e for e in letta["entita"] if e["id"] == "automation.luci_giardino")
    assert voce["categorie"] == {"automation": "01luci"}
    assert view(letta, [], [], {}, "entita", "automation.luci_giardino")["categorie"] == {
        "automation": "Luci esterne"}


def test_un_valore_storto_dal_registro_ripiega_su_un_dizionario():
    """Il ripiego deve avere la FORMA del valore buono: su `[]` -- il ripiego
    di `alias` ed `etichette` -- chiunque faccia `.items()` solleverebbe, e su
    una porta sola, cioe' proprio dove non lo si prova.

    **Il rischio si e' spostato, e la prova lo segue.** Fino al 10/09/2026 il
    valore storto arrivava da una riga di `casa.db` con dentro un JSON
    illeggibile. L'anagrafe non passa piu' da un archivio: il valore storto
    ora arriva **dalla rete**, dove Home Assistant e' l'unico a decidere cosa
    manda -- e una lista al posto di un dizionario e' esattamente cio' che
    `.items()` non sopravvive.

    Mutazione che la uccide: in `reader.clean_categories`, ripiegare su `[]`
    invece che su `{}`.
    """
    registri = dict(_REGISTRI, entita=[
        dict(_REGISTRI["entita"][0], categories=["non un dizionario"])])

    letta = build_home_space(registri)

    voce = next(e for e in letta["entita"] if e["id"] == _REGISTRI["entita"][0]["entity_id"])
    assert voce["categorie"] == {}
    assert "categorie" not in view(letta, [], [], {}, "entita", voce["id"])


def test_l_anagrafe_esce_dall_archivio_di_una_casa_gia_installata(tmp_path):
    """Il percorso VERO dell'aggiornamento, non un archivio nuovo.

    Le case gia' installate hanno le sette tabelle della copia dei registri e
    una `user_version` vecchia. Toglierle dallo schema non le toglie da un file
    che esiste gia': resterebbero li' a occupare spazio e a mentire a chi apre
    il database -- una copia dell'anagrafe **ferma al giorno
    dell'aggiornamento**, che e' la forma peggiore di doppione. La migrazione 8
    le cancella.

    Mutazione che la uccide: togliere `_migration_8_registries_out` da
    `_MIGRATIONS` -- le tabelle restano, e l'assert le trova.
    """
    percorso = str(tmp_path / "installata.db")
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE entita (id TEXT PRIMARY KEY, nome TEXT);"
        "CREATE TABLE aree (id TEXT PRIMARY KEY, nome TEXT);"
        "CREATE TABLE piani (id TEXT PRIMARY KEY, nome TEXT);"
        "CREATE TABLE dispositivi (id TEXT PRIMARY KEY, nome TEXT);"
        "CREATE TABLE etichette (id TEXT PRIMARY KEY, nome TEXT);"
        "CREATE TABLE categorie (id TEXT, nome TEXT, ambito TEXT);"
        "CREATE TABLE integrazioni (entry_id TEXT, dominio TEXT);"
        "INSERT INTO entita (id, nome) VALUES ('light.vecchia', 'Vecchia');"
        "PRAGMA user_version = 7;")
    vecchio.commit()
    vecchio.close()

    casa = HomeSpace(percorso)
    try:
        rimaste = {r[0] for r in casa._behavior._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert rimaste == {"meta", "comportamento", "plance"}
        assert casa._behavior._conn.execute("PRAGMA user_version").fetchone()[0] == 8
    finally:
        casa.close()
