"""Il lettore della casa: i registri di Home Assistant diventano l'anagrafe
**senza passare da una copia**, e senza buttare via niente.

Le righe di registro di queste prove sono **quelle vere**, misurate sulla casa
il 10/09/2026 con `config/entity_registry/list`: portano `translation_key`,
`unique_id`, `original_name`, `has_entity_name` — e **non portano
`device_class`**, che in quella risposta non esiste (`RegistryEntry.
as_partial_dict`). Una finta che lo scrivesse li' dentro sarebbe una finta che
non sa produrre il difetto: e' esattamente cosi' che il bilancio dell'energia
e' rimasto a zero per quindici giorni senza che nessuna prova se ne accorgesse.
"""
from hiris.app.home_space.reader import HomeSpace, build_home_space
from hiris.app.home_space.store import HomeSpaceStore

# Misurata il 10/09/2026 su `sensor.ze1es030n5e528_energia_prodotta_oggi`:
# copiata campo per campo dalla risposta vera, non inventata.
_ENTITA_VERA = {
    "area_id": None,
    "categories": {},
    "config_entry_id": "01K2MQXKKS49N9S8F8P4FHBK41",
    "config_subentry_id": None,
    "created_at": 1755190656.991824,
    "device_id": "513a6661274641ecf291c1be4121d9fa",
    "disabled_by": None,
    "entity_category": None,
    "entity_id": "sensor.ze1es030n5e528_energia_prodotta_oggi",
    "has_entity_name": True,
    "hidden_by": None,
    "icon": None,
    "id": "b792e5245b83dabbf3ddf7c9bccc6ed4",
    "labels": [],
    "modified_at": 1755190672.290234,
    "name": None,
    "options": {"sensor": {"suggested_display_precision": 2}},
    "original_name": "Energia prodotta oggi",
    "platform": "zcsazzurro",
    "translation_key": "energy_generating_today",
    "unique_id": "energy_generating_today-ZE1ES030N5E528",
}

_DISPOSITIVO_VERO = {
    "id": "513a6661274641ecf291c1be4121d9fa",
    "name": "ZE1ES030N5E528",
    "name_by_user": "SOLARE",
    "manufacturer": "ZCS Azzurro",
    "model": "Inverter ibrido",
    "area_id": None,
    "disabled_by": None,
    "labels": [],
}

_REGISTRI = {
    "piani": [], "aree": [], "etichette": [], "categorie": [], "integrazioni": [],
    "dispositivi": [_DISPOSITIVO_VERO],
    "entita": [_ENTITA_VERA],
}


def _entita(home_space, entity_id):
    return next(e for e in home_space["entita"] if e["id"] == entity_id)


def test_la_classe_viene_dallo_specchio_vivo_perche_il_registro_non_la_manda():
    """**La prova che il bilancio non aveva.** Il registro delle entita' non
    porta `device_class` — misurato: assente su 1.227 righe su 1.227 — e lo
    specchio dello stato lo porta per ogni entita'. Se il lettore leggesse solo
    il registro, `classe` resterebbe `None` su OGNI entita' di OGNI casa, e
    ogni lettore che decide su quel campo (`server.build_balances`,
    `memoria/interpretation`) sarebbe inerte in produzione.

    Mutazione che la uccide: in `build_home_space`, leggere la classe dalla
    sola riga di registro (`e.get("device_class")`) invece che da
    `actual_class(dichiarata, viva)`.
    """
    home_space = build_home_space(
        _REGISTRI,
        live_classes={"sensor.ze1es030n5e528_energia_prodotta_oggi": "energy"},
        live_units={"sensor.ze1es030n5e528_energia_prodotta_oggi": "kWh"})

    entita = _entita(home_space, "sensor.ze1es030n5e528_energia_prodotta_oggi")
    assert entita["classe"] == "energy"
    assert entita["unita"] == "kWh"


# Righe VERE, misurate il 10/09/2026 con i comandi che HIRIS usa davvero
# (`config/floor_registry/list`, `config/area_registry/list`,
# `config/device_registry/list`, `config_entries/get`): copiate, non inventate.
_REGISTRI_COMPLETI = {
    "piani": [{"aliases": [], "created_at": 1754923273.049191, "floor_id": "terra",
               "icon": "mdi:home-floor-0", "level": 0, "name": "Terra",
               "modified_at": 1754923273.049312}],
    "aree": [{"aliases": [], "area_id": "bagno_primo_piano", "floor_id": "terra",
              "humidity_entity_id": None, "icon": "mdi:toilet", "labels": [],
              "name": "Bagnetto", "picture": None, "temperature_entity_id": None,
              "created_at": 1756992895.248167, "modified_at": 1757059016.146056}],
    "dispositivi": [_DISPOSITIVO_VERO],
    "entita": [_ENTITA_VERA],
    "etichette": [{"label_id": "casa", "name": "Casa", "color": "blue", "icon": None}],
    "categorie": [{"category_id": "energia", "name": "Energia", "ambito": "automation"}],
    "integrazioni": [{"entry_id": "01K27AMNYXJVJRAENZ64TRDV28", "domain": "sun",
                      "title": "Sun", "source": "import", "state": "loaded",
                      "reason": None, "error_reason_translation_key": None}],
}

#: Cio' che il lettore porta IN PIU' della copia (spec §4). Si tolgono prima
#: del confronto con l'archivio, che non poteva tenerli.
_CAMPI_NUOVI = ("translation_key", "unique_id", "original_name", "nome_utente")


def test_l_anagrafe_del_lettore_ha_la_stessa_forma_di_quella_dell_archivio(tmp_path):
    """**Il contratto di compatibilita' della fetta.** I lettori dell'anagrafe
    -- `hierarchy`, `search`, `view`, il nucleo -- non cambiano una riga:
    devono ricevere lo stesso dizionario di prima. Questa prova lo pinza
    tabella per tabella, confrontando col fornitore VERO (`HomeSpaceStore`),
    non con una forma riscritta a mano qui dentro.

    Si confronta a meno dei campi nuovi (`_CAMPI_NUOVI`) e di `classe`/`unita`,
    che ora vengono dallo specchio vivo e nella copia erano `None` per
    costruzione.

    **Questa prova muore con `store.py`** (Fetta 1-bis): esiste per il
    passaggio, non per sempre.

    Mutazione che la uccide: in `build_home_space`, dimenticare una tabella
    (es. non costruire `integrazioni`) -- il confronto trova una chiave in
    meno.
    """
    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        archivio.replace(_REGISTRI_COMPLETI, [])
        atteso = archivio.read()
    finally:
        archivio.close()

    ottenuto = build_home_space(_REGISTRI_COMPLETI)

    def confrontabile(righe):
        fuori = (*_CAMPI_NUOVI, "classe", "unita")
        return [{k: v for k, v in riga.items() if k not in fuori} for riga in righe]

    assert set(ottenuto) == set(atteso), "le tabelle esposte sono le stesse"
    for tabella, righe_attese in atteso.items():
        assert confrontabile(ottenuto[tabella]) == confrontabile(righe_attese), \
            f"tabella «{tabella}»"


def test_cio_che_home_assistant_dichiara_non_si_butta():
    """Il registro porta `translation_key`, `unique_id` e `original_name` su
    quasi ogni entita' -- misurato sulla casa vera il 10/09/2026: `unique_id`
    sul **100%** delle 833 entita' vive, `original_name` sull'**89%**,
    `translation_key` sul **64%**, e **nessuna e' priva di tutte e tre**. La
    copia li buttava tutti e tre.

    `translation_key` e' il campo su cui si regge l'intero sprint: e' cio' che
    l'integrazione dichiara di se' (`energy_generating_today`), ed e' la
    ragione per cui il riconoscimento non era il problema.

    Mutazione che la uccide: toglierne uno dalla costruzione di `_entity`.
    """
    entita = _entita(build_home_space(_REGISTRI),
                     "sensor.ze1es030n5e528_energia_prodotta_oggi")

    assert entita["translation_key"] == "energy_generating_today"
    assert entita["unique_id"] == "energy_generating_today-ZE1ES030N5E528"
    assert entita["original_name"] == "Energia prodotta oggi"


def test_il_nome_originale_non_diventa_il_nome_quando_l_utente_non_ha_rinominato():
    """`nome` e `original_name` restano due campi: il primo e' come si chiama
    questa cosa, il secondo e' **chi l'ha chiamata cosi'**. Su questa entita'
    l'utente non ha rinominato niente (`name: null`), quindi i due coincidono
    nel VALORE -- e devono restare due chiavi, o si perde la differenza fra
    «l'ha chiamata l'integrazione» e «l'ha chiamata il proprietario».
    """
    entita = _entita(build_home_space(_REGISTRI),
                     "sensor.ze1es030n5e528_energia_prodotta_oggi")

    assert entita["nome"] == "Energia prodotta oggi"
    assert entita["original_name"] == "Energia prodotta oggi"


def test_il_dispositivo_dice_se_e_stato_rinominato_dall_utente():
    """`nome_utente` accanto a `nome`: l'inverter si chiama `SOLARE` perche'
    il proprietario l'ha rinominato -- l'integrazione lo chiamava
    `ZE1ES030N5E528`. Senza il campo, «SOLARE» e «Sun» sarebbero
    indistinguibili come provenienza.

    Mutazione che la uccide: far scrivere a `nome_utente` lo stesso
    `name_by_user or name` di `nome` -- un dispositivo mai rinominato
    direbbe di esserlo.
    """
    dispositivo = next(d for d in build_home_space(_REGISTRI)["dispositivi"])

    assert dispositivo["nome"] == "SOLARE"
    assert dispositivo["nome_utente"] == "SOLARE"
    assert dispositivo["produttore"] == "ZCS Azzurro"
    assert dispositivo["modello"] == "Inverter ibrido"

    mai_rinominato = build_home_space(
        {"dispositivi": [{"id": "d2", "name": "Sun", "name_by_user": None}]})
    assert mai_rinominato["dispositivi"][0]["nome"] == "Sun"
    assert mai_rinominato["dispositivi"][0]["nome_utente"] is None


def test_l_anagrafe_tenuta_a_memoria_risponde_come_rispondeva_dal_disco(tmp_path):
    """`HomeSpace` tiene l'ultima lettura e la serve dalla stessa superficie che
    i suoi chiamanti gia' usano -- `read()`, `reference_frame()`,
    `unavailable()`, `updated_at()`. Nessun chiamante cambia.

    Mutazione che la uccide: far tornare a `read()` un dizionario vuoto invece
    di quello tenuto.
    """
    casa = HomeSpace(str(tmp_path / "casa.db"))
    try:
        anagrafe = build_home_space(_REGISTRI_COMPLETI)
        casa.hold(anagrafe, ["etichette"], reference_frame={"fuso": "Europe/Rome"})

        assert casa.read() == anagrafe
        assert casa.unavailable() == ["etichette"]
        assert casa.reference_frame() == {"fuso": "Europe/Rome"}
        assert casa.updated_at() is not None
    finally:
        casa.close()


def test_prima_della_prima_lettura_la_casa_dice_di_non_esserci_non_di_essere_vuota(tmp_path):
    """**Cio' che si perde con la copia, dichiarato invece che scoperto.**
    Finche' Home Assistant non ha risposto nemmeno una volta, HIRIS non sa
    com'e' fatta la casa -- e prima teneva l'ultima copia buona su disco.

    Le due cose non devono confondersi: `updated_at()` a `None` dice «non l'ho
    ancora letta», e una casa senza aree direbbe `[]` con una data accanto. Chi
    legge deve poterle distinguere, o mostrera' «nessuna area» a chi ha
    quindici stanze.

    Mutazione che la uccide: far nascere `HomeSpace` con una data di
    aggiornamento (es. l'istante della costruzione).
    """
    casa = HomeSpace(str(tmp_path / "casa.db"))
    try:
        assert casa.updated_at() is None
        assert casa.read() == {}
        assert casa.reference_frame() == {}
    finally:
        casa.close()
