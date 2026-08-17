"""Cio' che l'anagrafe SA e non DICE.

Tre fatti che HIRIS legge da Home Assistant, scrive nel proprio archivio, e
poi non fa uscire da nessuna porta. Non e' codice morto -- il dato c'e' ed e'
giusto -- e' conoscenza muta, che e' peggio: costa la lettura e non rende
niente, e chi guarda il database si convince che HIRIS lo sappia dire.

E' la fondamenta dell'AUTONOMIA FUNZIONALE letta al contrario: se non esiste
un modo per chiederlo, non e' conoscenza, e' zavorra.

- `piattaforma`: l'integrazione che fornisce l'entita' (hue, zwave_js,
  template, mqtt). Scritta a ogni ricostruzione, ZERO lettori.
- `etichette`: la tassonomia che l'utente ha scritto a mano in Home Assistant
  -- il significato piu' dichiarato che esista in quella casa. Letta, salvata,
  messa perfino nell'albero da `gerarchia()`, e mai in una risposta.
- l'unita' delle entita' in `deduci_unita`: la legge dal REGISTRO, dove Home
  Assistant la lascia vuota se l'utente non l'ha forzata a mano (misurato:
  NULL su 842 entita' su 842). La funzione non ha quindi mai dedotto niente
  in produzione, e non aveva modo di dirlo.
"""
import pytest

from hiris.app.casa.anagrafe import unita_effettiva
from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.domande import guarda
from hiris.app.memoria.interpretazione import deduci_unita
from hiris.app.memoria.riconoscitore import costruisci_indice

_REGISTRI = {
    "aree": [{"area_id": "cucina", "name": "Cucina", "labels": ["piano_terra"]}],
    "dispositivi": [{"id": "d1", "name": "Frigo", "area_id": "cucina",
                     "labels": ["elettrodomestici"]}],
    "entita": [
        {"entity_id": "sensor.frigo_temp", "name": "Temperatura frigo",
         "device_id": "d1", "area_id": "cucina", "platform": "zwave_js",
         "device_class": "temperature", "labels": ["inverno", "consumi"]},
        {"entity_id": "light.faretto", "name": "Faretto", "area_id": "cucina",
         "platform": "hue"},
    ],
}


@pytest.fixture
def casa(tmp_path):
    a = ArchivioCasa(str(tmp_path / "casa.db"))
    a.sostituisci(_REGISTRI, [])
    letta = a.leggi()
    a.chiudi()
    return letta


# --- la piattaforma: chi fornisce questa entita' --------------------------

def test_guarda_un_entita_dice_da_quale_integrazione_viene(casa):
    """«Questa luce e' una Hue o un template?» e' una domanda che si fa
    davvero -- per capire perche' non risponde, o cosa si puo' chiederle."""
    d = guarda(casa, [], [], {}, "entita", "sensor.frigo_temp")
    assert d["piattaforma"] == "zwave_js"


def test_senza_piattaforma_la_chiave_non_compare(casa):
    """Stessa disciplina di `unita`: una chiave a `null` su ogni entita' e'
    rumore in ogni risposta, e non aggiunge niente a chi legge."""
    casa_senza = {"entita": [{"id": "x.y", "nome": "X"}]}
    d = guarda(casa_senza, [], [], {}, "entita", "x.y")
    assert "piattaforma" not in d


# --- le etichette: la tassonomia scritta a mano dall'utente ---------------

def test_guarda_un_entita_dice_le_sue_etichette(casa):
    d = guarda(casa, [], [], {}, "entita", "sensor.frigo_temp")
    assert d["etichette"] == ["inverno", "consumi"]


def test_guarda_un_area_dice_le_sue_etichette(casa):
    d = guarda(casa, [], [], {}, "area", "cucina")
    assert d["etichette"] == ["piano_terra"]


def test_guarda_un_dispositivo_dice_le_sue_etichette(casa):
    d = guarda(casa, [], [], {}, "dispositivo", "d1")
    assert d["etichette"] == ["elettrodomestici"]


def test_senza_etichette_la_chiave_non_compare(casa):
    """Un'etichetta assente e' il caso NORMALE: `etichette: []` su ogni cosa
    sarebbe rumore, e per giunta indistinguibile da un registro caduto."""
    d = guarda(casa, [], [], {}, "entita", "light.faretto")
    assert "etichette" not in d


def test_si_cerca_per_etichetta(casa):
    """L'etichetta e' una parola che l'utente ha scritto lui: se non porta a
    niente, HIRIS chiede all'utente di ripetere cio' che ha gia' dichiarato."""
    indice = costruisci_indice(casa)
    trovati = indice.trova("inverno")
    candidati = [c for t in trovati for c in t["candidati"]]
    assert {"tipo": "entita", "riferimento": "sensor.frigo_temp"} in candidati


# --- l'unita': la fonte viva, non il registro muto ------------------------

def test_la_regola_dell_unita_sta_in_un_posto_solo():
    """`unita_effettiva` e' l'UNICO punto in cui e' scritto che l'unita' viva
    vince su quella del registro. Prima la stessa decisione era presa a mano
    in due funzioni diverse: la stessa forma di difetto per cui la pagina
    Modelli era vera riga per riga e falsa nel complesso."""
    assert unita_effettiva(None, "C") == "C"
    assert unita_effettiva("F", "C") == "C", "la viva vince: HA converte all'ingresso"
    assert unita_effettiva("F", None) == "F", "senza viva, resta cio' che il registro dice"
    assert unita_effettiva(None, None) is None, "non si inventa"
    assert unita_effettiva("F", "   ") == "F", "una stringa vuota non e' un'unita'"


def test_deduci_unita_usa_la_fonte_viva(casa):
    """Il difetto vero: il registro di Home Assistant NON manda l'unita' (la
    manda solo se l'utente l'ha forzata a mano), quindi questa deduzione non
    e' mai scattata in produzione -- e taceva invece di dirlo."""
    indice = costruisci_indice(casa)
    ancore = [{"tipo": "entita", "riferimento": "sensor.frigo_temp"}]
    assert deduci_unita(ancore, "temperature", indice) is None, (
        "senza fonte viva non c'e' niente da dedurre: e' il caso di oggi")
    assert deduci_unita(ancore, "temperature", indice,
                        {"sensor.frigo_temp": "C"}) == "C"


def test_deduci_unita_da_un_area_usa_la_fonte_viva(casa):
    """Stessa cosa dal ramo `area`, che cerca l'entita' la cui classe combacia
    con la grandezza: se il ramo `entita` guarda la fonte viva e questo no,
    la stessa domanda ha due risposte diverse a seconda dell'ancora."""
    indice = costruisci_indice(casa)
    ancore = [{"tipo": "area", "riferimento": "cucina"}]
    assert deduci_unita(ancore, "temperature", indice,
                        {"sensor.frigo_temp": "C"}) == "C"


# --- la stessa risposta da tutte le porte ---------------------------------

class _SpecchioFinto:
    loaded = True

    def all_states(self):
        return [{"id": "sensor.frigo_temp", "state": "4", "unit": "C",
                 "name": "Temperatura frigo"}]


@pytest.mark.asyncio
async def test_correggere_un_ricordo_dalla_pagina_deduce_la_stessa_unita(
        aiohttp_client, tmp_path):
    """CONSISTENZA: correggere la grandezza di un ricordo dalla pagina deve
    dedurre la stessa unita' che `ricorda` deduce in chat.

    Prima di questa fetta la pagina non leggeva affatto lo specchio dello
    stato: lo stesso ricordo, corretto dalla stessa persona, usciva con
    l'unita' se la correzione passava dalla chat e senza se passava dalla
    pagina. Non un dato mancante -- lo stesso fatto con due forme a seconda
    della porta da cui entri.
    """
    from aiohttp import web

    from hiris.app.api.handlers_memoria import handle_patch_memoria
    from hiris.app.memoria.archivio import ArchivioMemoria

    casa_archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    casa_archivio.sostituisci(_REGISTRI, [])
    memoria = ArchivioMemoria(str(tmp_path / "memoria.db"))
    id_ricordo = memoria.ricorda(
        "il frigo lo tengo fra 3 e 5", detto_da="paolo",
        ancore=[{"tipo": "entita", "riferimento": "sensor.frigo_temp"}],
        grandezza=None, minimo=3.0, massimo=5.0)

    app = web.Application()
    app["archivio_memoria"] = memoria
    app["archivio_casa"] = casa_archivio
    app["entity_cache"] = _SpecchioFinto()
    app.router.add_patch("/api/memoria/{id}", handle_patch_memoria)
    client = await aiohttp_client(app)

    resp = await client.patch(f"/api/memoria/{id_ricordo}",
                              json={"grandezza": "temperature"})
    assert resp.status == 200, await resp.text()
    salvato = next(r for r in memoria.richiama() if r["id"] == id_ricordo)
    assert salvato["unita"] == "C", (
        "la pagina deve dedurre l'unita' dalla stessa fonte viva della chat")
