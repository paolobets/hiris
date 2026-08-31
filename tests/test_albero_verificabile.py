"""L'albero verificabile: HIRIS smette di credere alla propria replica.

Fetta 4 di `docs/design/2026-08-17-piano-i-sette-che-mancano.md`.

**Il difetto che questo file sorveglia.** `casa/anagrafe.gerarchia()` e'
un'AFFERMAZIONE che HIRIS fa sulla casa: la costruisce dai registri, ci ragiona
sopra, e niente la verifica. Se un'area contiene cose che HIRIS non le
attribuisce -- o peggio, se HIRIS le attribuisce cose che non ci sono -- non
c'e' nessun modo di accorgersene, se non sbagliando una risposta davanti
all'utente. Tutte le fette di conoscenza fatte finora hanno reso l'albero piu'
RICCO; questa e' la prima che lo rende CONTROLLABILE.

Il secondo parere e' di Home Assistant su se stesso: `extract_from_target`
(`HAClient.estrai_dal_bersaglio`, fetta 1) RISOLVE un'area invece di dedurla.

Le prove sono in cinque parti:

1. **i tre esiti**, che devono avere tre diciture DIVERSE -- e la prova che
   conta piu' di tutte e' la coppia: una casa che combacia non produce nessun
   avviso, e una che diverge produce quello giusto dei due. Servono entrambi i
   versi, o la prova passa per il motivo sbagliato;
2. **il campione**: quante aree si sono guardate esce sempre, e la rotazione
   copre tutta la casa in un numero dichiarabile di giri;
3. **le regole di Home Assistant NON sono divergenze**: nascoste, entita' di
   servizio e disabilitate hanno regole diverse fra i due alberi, e contarle
   produrrebbe un avviso su ogni casa del mondo -- cioe' una riga che nessuno
   legge piu' il giorno in cui dice qualcosa di vero;
4. **il non letto non e' il combaciato**, per il giro intero e per la singola
   area;
5. **la catena**, dall'app fino al testo e fino a `/api/casa`, senza rete.

Ognuna di queste prove sa PRODURRE il difetto che sorveglia -- verificato per
mutazione, non per fiducia: togliere il ramo di `_avviso_confronto` che tace
quando tutto combacia fa fallire il gruppo 1; togliere `_fuori_dal_confronto`
fa fallire il gruppo 3; togliere la coda del campione fa fallire il gruppo 2;
far ripiegare un'area non letta su liste vuote fa fallire il gruppo 4.
"""
import asyncio

import pytest
from aiohttp import web

from hiris.app.api.handlers_casa import compose_briefing, handle_get_home_space
from hiris.app.casa.anagrafe import (
    choose_sample,
    compare_with_home_assistant,
    hierarchy,
    tree_areas,
)
from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.nucleo import compose
from hiris.app.server import giro_di_confronto_albero

# --------------------------------------------------------------------------
# I finti: l'anagrafe da una parte, cio' che Home Assistant risponde dall'altra
# --------------------------------------------------------------------------

def _entita(identificativo, area=None, dispositivo=None, **campi):
    """Una riga del registro entita' COME LA LEGGE L'ARCHIVIO (colonne
    italiane), che e' la forma in cui `gerarchia()` la riceve davvero."""
    riga = {"id": identificativo, "nome": identificativo, "area_id": area,
            "dispositivo_id": dispositivo, "piattaforma": "demo",
            "categoria": None, "classe": None, "unita": None,
            "disabilitata": 0, "nascosta": 0,
            "alias": [], "etichette": [], "categorie": {}}
    riga.update(campi)
    return riga


def _casa(entita, aree=("cucina", "bagno")):
    return {
        "piani": [{"id": "terra", "nome": "Piano terra", "livello": 0}],
        "aree": [{"id": a, "nome": a.capitalize(), "piano_id": "terra"} for a in aree],
        "dispositivi": [], "entita": list(entita),
        "etichette": [], "categorie": [], "integrazioni": [],
    }


def _risposta(entita=(), aree_mancanti=()):
    """La risposta di `estrai_dal_bersaglio` nella sua forma piena.

    I nomi delle chiavi sono quelli veri di quella funzione -- `entita`,
    `aree_mancanti` -- non quelli di Home Assistant: la traduzione la fa il
    client, e una prova che pinnasse `referenced_entities` qui starebbe
    provando un contratto che questo codice non vede.
    """
    return {"entita": list(entita), "dispositivi": [], "aree": [],
            "dispositivi_mancanti": [], "aree_mancanti": list(aree_mancanti),
            "piani_mancanti": [], "etichette_mancanti": []}


def _confronto(casa, risposte):
    return compare_with_home_assistant(hierarchy(casa), casa, risposte)


def _nucleo(confronto, casa=None):
    """Il nucleo della casa data: qui interessa solo la sezione delle lacune."""
    casa = casa if casa is not None else {"entita": [], "integrazioni": []}
    return compose(casa, [], [], {}, comparison=confronto)


# --------------------------------------------------------------------------
# 1. I tre esiti, tre diciture diverse
# --------------------------------------------------------------------------

def test_una_casa_che_combacia_non_produce_nessun_avviso():
    """LA PROVA CHE CONTA PIU' DI TUTTE, primo verso. Un avviso che compare
    sempre smette di essere letto: il giorno che dice qualcosa di vero non lo
    legge piu' nessuno. Combaciare non si annuncia."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina"])})

    assert esito["guardate"][0]["mancanti"] == []
    assert esito["guardate"][0]["in_piu"] == []
    testo, riepilogo = _nucleo(esito, casa)
    assert "Confronto con Home Assistant" not in testo
    assert not any("Confronto con Home Assistant" in a for a in riepilogo["avvisi"])


def test_hiris_ne_ha_di_meno_si_dichiara():
    """Secondo verso, caso 2: Home Assistant riporta nell'area cose che
    l'albero non le attribuisce. La replica e' vecchia, o un registro e'
    caduto: si dichiara, come si dichiara gia' `non_disponibili`."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina", "switch.forno"])})

    assert esito["guardate"][0]["mancanti"] == ["switch.forno"]
    assert esito["guardate"][0]["in_piu"] == []
    testo, _ = _nucleo(esito, casa)
    assert "switch.forno" in testo
    assert "non ci attribuisce" in testo
    assert "piu' vecchia della casa" in testo


def test_hiris_ne_ha_di_piu_e_il_caso_peggiore():
    """Secondo verso, caso 3: la replica AFFERMA qualcosa che Home Assistant
    non conferma. E' il caso peggiore -- e' quello che produce risposte
    sbagliate dette con sicurezza, il difetto di classe A1 di questo
    progetto -- e il testo deve dirlo, non limitarsi a elencare."""
    casa = _casa([_entita("light.cucina", area="cucina"),
                  _entita("light.fantasma", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina"])})

    assert esito["guardate"][0]["in_piu"] == ["light.fantasma"]
    assert esito["guardate"][0]["mancanti"] == []
    testo, _ = _nucleo(esito, casa)
    assert "light.fantasma" in testo
    assert "non conferma" in testo
    assert "risposta sbagliata detta con sicurezza" in testo


def test_le_due_divergenze_non_si_dicono_con_le_stesse_parole():
    """Tre esiti, tre diciture: se «di meno» e «di piu'» producessero la stessa
    frase, il modello leggerebbe «qualcosa non torna» e non saprebbe di quale
    dei due si tratta -- e sono opposti, con rimedi opposti."""
    casa_meno = _casa([_entita("light.cucina", area="cucina")])
    meno, _ = _nucleo(_confronto(casa_meno,
                                 {"cucina": _risposta(["light.cucina", "switch.forno"])}),
                      casa_meno)
    casa_piu = _casa([_entita("light.cucina", area="cucina"),
                      _entita("light.fantasma", area="cucina")])
    piu, _ = _nucleo(_confronto(casa_piu, {"cucina": _risposta(["light.cucina"])}),
                     casa_piu)

    assert "non conferma" in piu and "non conferma" not in meno
    assert "non ci attribuisce" in meno and "non ci attribuisce" not in piu


def test_i_due_versi_insieme_si_dicono_tutti_e_due():
    """Un'area puo' divergere in entrambi i sensi. Dirne uno solo sarebbe un
    filtro silenzioso, che e' solo un modo piu' educato di mentire."""
    casa = _casa([_entita("light.fantasma", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta(["switch.forno"])})
    testo, _ = _nucleo(esito, casa)

    assert "light.fantasma" in testo
    assert "switch.forno" in testo


def test_un_area_che_in_ha_non_esiste_piu_si_dice_in_una_parola():
    """La forma piu' pura del caso peggiore: HIRIS ha una STANZA che
    l'originale non ha. Dirlo elencando le sue entita' sarebbe la stessa
    notizia detta a pezzi -- ed e' la distinzione fra «l'area e' vuota» e
    «quell'area non c'e'» che `estrai_dal_bersaglio` porta gia'."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta([], aree_mancanti=["cucina"])})

    assert esito["guardate"][0]["assente_in_ha"] is True
    testo, _ = _nucleo(esito, casa)
    assert "non esiste piu' in Home Assistant" in testo


def test_nessuno_ha_chiesto_non_e_un_albero_verificato():
    """`None` = il chiamante non ha chiesto: e' l'unico caso in cui tacere non
    afferma niente. Non va confuso con «guardato e combacia»."""
    testo, riepilogo = _nucleo(None)
    assert "Confronto con Home Assistant" not in testo
    assert riepilogo["avvisi"] == [] or all(
        "Confronto" not in a for a in riepilogo["avvisi"])


# --------------------------------------------------------------------------
# 2. Il campione: dichiarato sempre, e a rotazione
# --------------------------------------------------------------------------

def test_il_campione_si_dichiara_insieme_alla_divergenza():
    """Un campione taciuto fa sembrare completo un controllo parziale: «una
    divergenza in un'area» senza dire che le aree guardate erano una su sedici
    lascia credere che le altre quindici siano state trovate a posto."""
    aree = tuple(f"area{i:02d}" for i in range(16))
    casa = _casa([_entita("light.fantasma", area="area00")], aree=aree)
    esito = _confronto(casa, {"area00": _risposta([])})

    assert esito["aree_totali"] == 16
    testo, _ = _nucleo(esito, casa)
    assert "sulle 16 della casa" in testo


def test_la_rotazione_copre_tutta_la_casa():
    """Il campione e' parziale, ma il suo limite e' DICHIARABILE: ogni area
    viene guardata entro un giro completo. Un campione casuale rigirerebbe due
    volte sulla stessa area e ne lascerebbe un'altra mai guardata."""
    aree = [{"id": f"a{i}", "nome": f"A{i}"} for i in range(7)]
    viste, dopo = [], None
    for _ in range(3):
        campione = choose_sample(aree, 3, dopo)
        viste.extend(a["id"] for a in campione)
        dopo = campione[-1]["id"]
    assert {a["id"] for a in aree} <= set(viste)


def test_la_rotazione_e_riproducibile():
    """Due esecuzioni identiche devono produrre lo stesso nucleo. Un campione
    casuale lo farebbe cambiare senza che sia cambiato niente nella casa."""
    aree = [{"id": f"a{i}", "nome": f"A{i}"} for i in range(7)]
    assert choose_sample(aree, 3, "a2") == choose_sample(aree, 3, "a2")


def test_la_rotazione_riprende_da_capo_alla_fine():
    aree = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert [a["id"] for a in choose_sample(aree, 2, "b")] == ["c", "a"]
    assert [a["id"] for a in choose_sample(aree, 2, "zzz")] == ["a", "b"]


def test_le_pseudo_aree_non_si_confrontano():
    """«Senza area», «Aree non lette», «Area sconosciuta» e «Dispositivi non
    letti» non esistono in Home Assistant: chiedergliene una risponderebbe
    `aree_mancanti`, cioe' una divergenza inventata da noi sull'unico
    contenitore che dichiara gia' di essere una nostra costruzione."""
    casa = _casa([_entita("light.orfana"), _entita("light.cucina", area="cucina")])
    piani = hierarchy(casa)

    nomi = {p["nome"] for p in piani}
    assert "Fuori dalle aree" in nomi  # l'orfana c'e' davvero, nell'albero
    identificativi = {a["id"] for a in tree_areas(piani)}
    assert identificativi == {"cucina", "bagno"}


# --------------------------------------------------------------------------
# 3. Le regole di Home Assistant NON sono divergenze
# --------------------------------------------------------------------------
#
# Verificate alla fonte (`homeassistant/helpers/target.py::_include_entry` e
# `helpers/entity_registry.py`), non ricordate. Se queste tre prove cadessero,
# l'avviso comparirebbe su ogni casa del mondo e la riga smetterebbe di essere
# letta: e' lo stesso rumore che la fetta dei problemi ha filtrato per
# severita'.

@pytest.mark.parametrize("campo, valore", [
    ("nascosta", 1),          # `_include_entry`: hidden_by non nullo -> fuori
    ("categoria", "config"),  # `primary_entities_only` -> fuori le di servizio
    ("categoria", "diagnostic"),
])
def test_cio_che_ha_esclude_per_regola_non_e_una_divergenza(campo, valore):
    casa = _casa([_entita("light.cucina", area="cucina"),
                  _entita("sensor.rssi", area="cucina", **{campo: valore})])
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina"])})

    assert esito["guardate"][0]["in_piu"] == []
    testo, _ = _nucleo(esito, casa)
    assert "Confronto con Home Assistant" not in testo


def test_le_disabilitate_restano_fuori_da_entrambi_i_lati():
    """HA le esclude quando l'area arriva dal dispositivo
    (`get_entries_for_device_id(include_disabled_entities=False)`) e le INCLUDE
    quando l'area e' dell'entita' stessa (`get_entries_for_area_id` non filtra
    niente). Due regole diverse per lo stesso stato: l'esito non puo' dipendere
    da quale delle due strade un'entita' ha preso per arrivare nell'area."""
    casa = _casa([_entita("light.cucina", area="cucina"),
                  _entita("light.rotta", area="cucina", disabilitata=1)])
    # Home Assistant la riporta (ha un'area propria): non e' un «di meno».
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina", "light.rotta"])})
    assert esito["guardate"][0]["mancanti"] == []
    assert esito["guardate"][0]["in_piu"] == []
    # E se non la riportasse (l'area arriva dal dispositivo), non e' un «di
    # piu'»: la stessa entita', lo stesso verdetto.
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina"])})
    assert esito["guardate"][0]["mancanti"] == []
    assert esito["guardate"][0]["in_piu"] == []


def test_un_id_che_l_anagrafe_non_conosce_affatto_resta_una_divergenza():
    """La divergenza piu' netta che esista: Home Assistant nomina un'entita' di
    cui HIRIS non sa niente. Scartarla «per prudenza» insieme alle nascoste
    sarebbe il difetto che questa fetta esiste per chiudere -- il filtro deve
    saper distinguere «so che non si confronta» da «non la conosco»."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    esito = _confronto(casa, {"cucina": _risposta(["light.cucina", "light.mai_vista"])})
    assert esito["guardate"][0]["mancanti"] == ["light.mai_vista"]


# --------------------------------------------------------------------------
# 4. Non letto non e' combaciato
# --------------------------------------------------------------------------

def test_un_area_non_letta_non_e_un_area_che_combacia():
    """Vale per la singola area, non solo per il giro: se un'area non risponde
    e le altre due combaciano, tacere direbbe «tre aree a posto»."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    esito = _confronto(casa, {
        "cucina": _risposta(["light.cucina"]),
        "bagno": {"errore": "Home Assistant non ha rifiutato niente, non ha risposto"},
    })

    guardate = {g["area"]: g for g in esito["guardate"]}
    assert "errore" in guardate["bagno"]
    assert "mancanti" not in guardate["bagno"] and "in_piu" not in guardate["bagno"]
    testo, _ = _nucleo(esito, casa)
    assert "non si e' potuto fare" in testo
    assert "non si sono potute controllare" in testo


def test_il_giro_non_letto_non_e_un_albero_verificato():
    """Il gemello del ramo `errore` di `_avviso_problemi`: non si sta dicendo
    che l'albero combacia, si sta dicendo che non si e' potuto controllare."""
    testo, riepilogo = _nucleo({"errore": "Home Assistant non ha risposto"})
    assert "non si e' potuto controllare" in testo
    assert any("non si e' potuto controllare" in a for a in riepilogo["avvisi"])


def test_un_area_sparita_dall_albero_e_un_confronto_perso():
    """L'anagrafe si e' ricostruita fra la domanda e la risposta. Non e' un
    combaciare: e' un confronto che non si e' potuto chiudere."""
    casa = _casa([])
    esito = _confronto(casa, {"salotto": _risposta([])})
    assert "non e' piu' nell'albero" in esito["guardate"][0]["errore"]


def test_gli_elenchi_lunghi_si_tagliano_dichiarando_il_resto():
    """Gli avvisi non passano per il taglio di `componi()`: un'area che diverge
    di quaranta entita' scriverebbe una riga che niente puo' accorciare. Si
    taglia, ma il numero degli altri resta detto -- mai un elenco accorciato in
    silenzio."""
    fantasmi = [f"light.f{i}" for i in range(9)]
    casa = _casa([_entita(f, area="cucina") for f in fantasmi])
    esito = _confronto(casa, {"cucina": _risposta([])})
    testo, _ = _nucleo(esito, casa)
    assert "e altre 5" in testo


# --------------------------------------------------------------------------
# 5. La catena: dall'app fino al testo, senza rete
# --------------------------------------------------------------------------

class _ClienteFinto:
    """Home Assistant visto da `giro_di_confronto_albero`: risponde per area,
    e per le aree che non conosce restituisce un errore invece di una lista
    corta -- come fa `estrai_dal_bersaglio` davvero."""

    def __init__(self, per_area: dict, guasto: str | None = None) -> None:
        self.per_area = per_area
        self.guasto = guasto
        self.chieste: list[str] = []

    async def estrai_dal_bersaglio(self, target):
        identificativo = target["area_id"][0]
        self.chieste.append(identificativo)
        if self.guasto:
            return {"errore": self.guasto}
        return _risposta(self.per_area.get(identificativo, []))


def _archivio_con_una_casa(tmp_path, entita=(), aree=("cucina", "bagno", "sala")):
    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    archivio.replace({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": a, "name": a.capitalize(), "floor_id": "terra"}
                 for a in aree],
        "dispositivi": [],
        "entita": list(entita),
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    return archivio


def test_il_giro_scrive_la_fotografia_in_ram(tmp_path):
    """Vive in RAM e non in archivio, come i problemi diagnosticati: un
    confronto e' momentaneo due volte -- la casa cambia, e la replica si rifa'
    da sola al primo evento di registro."""
    archivio = _archivio_con_una_casa(tmp_path, [
        {"entity_id": "light.cucina", "name": "Luce", "area_id": "cucina"},
    ])
    app = {"archivio_casa": archivio}
    cliente = _ClienteFinto({"cucina": ["light.cucina"]})

    esito = asyncio.run(giro_di_confronto_albero(app, cliente, quante=1)())
    assert esito is app["confronto_albero"]
    assert app["confronto_albero"]["aree_totali"] == 3
    assert app["confronto_albero"]["letto_il"]
    assert len(app["confronto_albero"]["guardate"]) == 1
    archivio.close()


def test_il_giro_ruota_fra_una_chiamata_e_l_altra(tmp_path):
    archivio = _archivio_con_una_casa(tmp_path)
    cliente = _ClienteFinto({})
    giro = giro_di_confronto_albero({"archivio_casa": archivio}, cliente, quante=1)

    asyncio.run(giro())
    asyncio.run(giro())
    asyncio.run(giro())
    asyncio.run(giro())
    assert cliente.chieste == ["bagno", "cucina", "sala", "bagno"]
    archivio.close()


def test_il_giro_porta_il_guasto_invece_di_inghiottirlo(tmp_path):
    archivio = _archivio_con_una_casa(tmp_path)
    cliente = _ClienteFinto({}, guasto="Home Assistant non ha risposto")
    app = {"archivio_casa": archivio}

    asyncio.run(giro_di_confronto_albero(app, cliente, quante=2)())
    assert all(g["errore"] for g in app["confronto_albero"]["guardate"])
    testo, _ = compose_briefing(app)
    assert "non si sono potute controllare" in testo
    archivio.close()


def test_un_client_che_non_sa_estrarre_non_scrive_niente(tmp_path):
    """Un client vecchio o un finto di prova senza `estrai_dal_bersaglio`: la
    chiave resta assente, e il nucleo tace invece di affermare che l'albero e'
    verificato -- l'unico caso in cui tacere non afferma nulla."""

    class _ClienteVecchio:
        pass

    archivio = _archivio_con_una_casa(tmp_path)
    app = {"archivio_casa": archivio}
    assert asyncio.run(giro_di_confronto_albero(app, _ClienteVecchio())()) is None
    assert asyncio.run(giro_di_confronto_albero(app, None)()) is None
    assert "confronto_albero" not in app
    archivio.close()


def test_il_nucleo_legge_il_confronto_dalla_memoria_dell_app():
    """La catena intera: `app["confronto_albero"]` -> `compose_briefing` ->
    `componi`. Senza questo cablaggio il giro sarebbe un dato scritto e mai
    letto -- la quarta fondamenta al contrario."""
    app = {"confronto_albero": {"aree_totali": 4, "guardate": [
        {"area": "cucina", "nome": "Cucina", "mancanti": [], "in_piu": ["light.fantasma"],
         "assente_in_ha": False},
    ]}}
    testo, _ = compose_briefing(app)
    assert "light.fantasma" in testo
    assert "sulle 4 della casa" in testo


def test_senza_la_chiave_il_nucleo_non_afferma_che_l_albero_e_verificato():
    testo, _ = compose_briefing({})
    assert "Confronto con Home Assistant" not in testo


@pytest.mark.asyncio
async def test_api_casa_mostra_la_divergenza_sull_albero(aiohttp_client, tmp_path):
    """Dove una divergenza serve di piu': la pagina che DISEGNA l'albero. Se il
    modello leggesse nel nucleo una divergenza che la pagina non mostra,
    sarebbero due case diverse a seconda della porta."""
    archivio = _archivio_con_una_casa(tmp_path)
    app = web.Application()
    app["archivio_casa"] = archivio
    app["confronto_albero"] = {"aree_totali": 3, "letto_il": "2026-08-18T10:00:00+00:00",
                               "guardate": [{"area": "cucina", "nome": "Cucina",
                                             "mancanti": [], "in_piu": ["light.fantasma"],
                                             "assente_in_ha": False}]}
    app.router.add_get("/api/casa", handle_get_home_space)
    client = await aiohttp_client(app)

    corpo = await (await client.get("/api/casa")).json()
    assert corpo["confronto"]["guardate"][0]["in_piu"] == ["light.fantasma"]
    assert corpo["confronto"]["aree_totali"] == 3
    archivio.close()


@pytest.mark.asyncio
async def test_api_casa_senza_confronto_dice_none_non_una_lista_vuota(aiohttp_client,
                                                                     tmp_path):
    """`None` e non `{}`: un esito vuoto affermerebbe «guardato, e non c'era
    niente da dire». La stessa distinzione di `non_disponibili`."""
    archivio = _archivio_con_una_casa(tmp_path)
    app = web.Application()
    app["archivio_casa"] = archivio
    app.router.add_get("/api/casa", handle_get_home_space)
    client = await aiohttp_client(app)

    corpo = await (await client.get("/api/casa")).json()
    assert corpo["confronto"] is None
    archivio.close()


@pytest.mark.parametrize("confronto", [
    None,
    {"errore": "rifiutato"},
    {"aree_totali": 2, "guardate": [{"area": "cucina", "nome": "Cucina",
                                     "mancanti": ["switch.forno"], "in_piu": [],
                                     "assente_in_ha": False}]},
])
def test_componi_resta_pura(confronto):
    """La proprieta' su cui poggiano tutte le prove di `componi()`: il confronto
    arriva come ARGOMENTO, come `stato`, `problemi` e `sistema_di_riferimento`.
    Chiedere a Home Assistant cosa contiene un'area e' rete, e la rete sta nel
    chiamante. Se qualcuno la mettesse qui dentro, questa prova girerebbe dentro
    un loop asyncio gia' in corso e la chiamata esploderebbe."""

    async def _dentro_un_loop():
        return _nucleo(confronto)

    testo, riepilogo = asyncio.run(_dentro_un_loop())
    assert isinstance(testo, str) and "caratteri" in riepilogo


def test_gerarchia_resta_pura_e_non_sa_niente_del_confronto():
    """`gerarchia()` non cambia forma: il confronto e' un secondo parere che si
    mette ACCANTO all'albero, non un campo che gli si appende dentro. Un albero
    che portasse il proprio verdetto sarebbe lo stesso fatto in due case.

    `entita_nascoste` (fetta "nascoste fuori dagli elenchi", 2026-08-25) e'
    nella forma attesa: stessa chiave parallela di `entita_disabilitate`, non
    un campo del confronto -- e' per questo che si aggiunge qui invece di
    romperlo."""
    casa = _casa([_entita("light.cucina", area="cucina")])
    piani = hierarchy(casa)
    cucina = piani[0]["aree"][0]
    assert set(cucina) == {"id", "nome", "alias", "etichette", "entita_temperatura",
                           "entita_umidita", "entita", "entita_disabilitate",
                           "entita_nascoste"}
