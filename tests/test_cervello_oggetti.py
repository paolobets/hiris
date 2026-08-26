"""L'aggregazione: dai cambi agli oggetti.

**E' l'unico posto di questa fetta dove si giudica**, ed e' apposta: un
giudizio qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa,
uno di guardia), uno in scrittura non si corregge piu'.

Un oggetto e' **una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno.
"""
import os

import pytest

from hiris.app.cervello.archivio import ArchivioOsservazioni
from hiris.app.cervello.oggetti import (GENERI, aggrega_giorno, confini_giorno,
                                         genere_di)

# 24 agosto 2026: mezzanotte a Roma e' 22:00 UTC del 23.
G = "2026-08-24"
MEZZANOTTE = 1787522400.0   # 2026-08-23T22:00:00+00:00 = 24/08 00:00 +02:00


def ts(ore, minuti=0):
    return MEZZANOTTE + ore * 3600 + minuti * 60


@pytest.fixture()
def archivio(tmp_path):
    a = ArchivioOsservazioni(os.path.join(str(tmp_path), "o.db"))
    yield a
    a.close()


def test_il_genere_discende_dalla_natura():
    assert genere_di("climate.camera_t", "comfort") == "funzionamento"
    assert genere_di("cover.tapparella", "dispersione") == "funzionamento"
    assert genere_di("person.marta", "chi c'e'") == "presenza"
    assert genere_di("sensor.presa_energia", "consumo") == "consumo"
    assert genere_di("problema:sonos.x", None) == "guasto"
    assert genere_di("sensor.camera_temperatura", "comfort") is None
    for g in GENERI:
        assert isinstance(g, str)


def test_il_genere_di_sicurezza_e_diverso_dal_guasto_di_sistema():
    """Correzione 0.1: 'guasto' resta per le condizioni di SISTEMA
    (problema:/integrazione:, un confine netto); la gamba sicurezza ha un
    genere proprio, 'sicurezza' -- una porta aperta con la chiave e
    un'integrazione Sonos rotta non sono lo stesso genere di fatto."""
    assert genere_di("lock.porta_ingresso", "sicurezza") == "sicurezza"
    assert genere_di("problema:sonos.x", None) == "guasto"
    assert genere_di("integrazione:abc", None) == "guasto"
    assert "sicurezza" in GENERI
    assert len(GENERI) == 5


def test_un_termostato_acceso_e_spento_diventa_UN_oggetto(archivio):
    archivio.annota(quando_ts=ts(15, 30), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(17, 5), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "funzionamento"
    assert o["protagonista"] == "climate.camera_t"
    assert o["inizio_ts"] == ts(15, 30)
    assert o["fine_ts"] == ts(17, 5)


def test_l_oggetto_porta_cosa_ha_fatto_la_temperatura_mentre_durava(archivio):
    """E' il senso dell'esempio fondativo: «la casa e' calda alle 16:30» non e'
    un fatto sul termostato ne' sul sensore -- e' il legame fra i due."""
    archivio.annota(quando_ts=ts(15, 30), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    for ora, valore in ((15, "18.2"), (16, "20.1"), (17, "21.0")):
        archivio.annota(quando_ts=ts(ora, 45), fonte="entita",
                        soggetto="sensor.camera_temperatura", da=None, a=valore)
    archivio.annota(quando_ts=ts(17, 5), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                         comprimari=lambda s: ["sensor.camera_temperatura"])
    corpo = archivio.oggetti(giorno=G)[0]["corpo"]
    assert corpo["comprimari"] == ["sensor.camera_temperatura"]
    assert corpo["misure"]["sensor.camera_temperatura"] == {"da": "18.2", "a": "21.0"}


def test_una_cosa_ancora_in_corso_a_mezzanotte_resta_aperta(archivio):
    archivio.annota(quando_ts=ts(22, 0), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")
    assert archivio.oggetti(giorno=G)[0]["fine_ts"] is None


def test_un_assenza_e_un_oggetto(archivio):
    archivio.annota(quando_ts=ts(8, 10), fonte="entita",
                    soggetto="person.paolo", da="home", a="not_home")
    archivio.annota(quando_ts=ts(17, 34), fonte="entita",
                    soggetto="person.paolo", da="not_home", a="home")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "presenza"
    assert o["corpo"]["stato"] == "not_home"


def test_un_guasto_di_sistema_e_un_oggetto(archivio):
    archivio.annota(quando_ts=ts(9, 0), fonte="sistema",
                    soggetto="problema:sonos.subscriptions_failed", da=None, a="aperto")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "guasto"
    assert o["fine_ts"] is None


def test_i_sensori_da_soli_NON_generano_oggetti(archivio):
    """«La temperatura e' salita» da sola non e' una cosa compiuta: e' il
    CONTESTO di qualcosa che e' successo. Se generasse oggetti, una giornata
    ne produrrebbe migliaia e nessuno sarebbe leggibile."""
    for ora in range(0, 20):
        archivio.annota(quando_ts=ts(ora), fonte="entita",
                        soggetto="sensor.camera_temperatura", da=None, a=str(18 + ora))
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0


def test_rifare_un_giorno_non_raddoppia(archivio):
    """Il grezzo resta 22 giorni proprio perche' l'aggregazione si possa
    rifare. Se rifarla duplicasse, quella possibilita' non esisterebbe."""
    archivio.annota(quando_ts=ts(15), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome")
    assert len(archivio.oggetti(giorno=G)) == 1


def test_il_giorno_e_quello_della_CASA_non_UTC(archivio):
    """Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC
    spezzerebbe ogni serata in due. La fetta dello schedulatore ha gia' pagato
    un difetto di orologi diversi."""
    archivio.annota(quando_ts=ts(23, 30), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1


def test_senza_fuso_noto_non_si_inventa(archivio):
    """`sistema_di_riferimento()` puo' non aver mai letto la casa. UTC e'
    dichiarato; un fuso inventato sposterebbe i giorni senza dirlo.

    Correzione (giro di review, punto 1): la versione precedente usava
    `ts(15)`, mezzogiorno abbondante -- un istante che cade dentro la
    giornata sia in UTC sia in un fuso inventato, quindi il test passava in
    entrambi i casi e provava solo che `fuso=None` non facesse crashare.

    **Cambio a `ts(1)`**: le 23:00Z del 23 agosto, che cade FRA le due
    mezzanotti. In UTC appartiene a "2026-08-23". Con un fuso inventato
    (es. `Europe/Rome`, +02:00) apparterrebbe gia' al 24: il conteggio del 23
    tornerebbe zero. E' la mutazione -- far tornare a `zona_casa(None)` un
    `ZoneInfo("Europe/Rome")` -- che questo test deve rilevare."""
    archivio.annota(quando_ts=ts(1), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    assert aggrega_giorno(archivio=archivio, giorno="2026-08-23", fuso=None) == 1


# -- Correzione B: la finestra di `cambi()` e' semi-aperta -----------------

def test_un_cambio_a_mezzanotte_appartiene_al_giorno_che_comincia(archivio):
    """MEZZANOTTE e' l'istante esatto in cui G comincia. Con la finestra
    semi-aperta di `archivio.cambi` (`[da_ts, a_ts)`) un cambio a quell'
    istante deve finire SOLO in G, mai nel giorno che finisce in quell'
    istante, e mai in entrambi -- altrimenti sarebbe contato due volte."""
    archivio.annota(quando_ts=MEZZANOTTE, fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    assert aggrega_giorno(archivio=archivio, giorno="2026-08-23",
                          fuso="Europe/Rome") == 0
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1


# -- Correzione E: il pavimento ha sei gambe, la sicurezza non e' un buco --
# -- Correzione 0.1: la sicurezza e' un genere proprio, non piu' 'guasto' --

def test_il_genere_conosce_tutte_e_sei_le_gambe():
    """Le nature risolvibili dal solo dominio -- serratura, pannello
    dell'allarme, sirena -- e i rilevatori (quando la gamba e' nota) diventano
    un oggetto di sicurezza: sono una minaccia, non un funzionamento normale,
    e hanno la stessa FORMA di una condizione di sistema -- nate, durate,
    chiuse o ancora aperte -- ma non lo STESSO genere (0.1: una porta aperta
    con la chiave e un'integrazione Sonos rotta non sono la stessa cosa). Un
    `else` che le mandasse a vuoto sarebbe il buco che la review del primo
    task ha gia' trovato una volta (§4 della spec).

    `sensor.co_soggiorno` e' `None` e non `"sicurezza"` da questa correzione
    (giro di review, punto 7): e' un `sensor` che MISURA (una concentrazione
    numerica), non un `binary_sensor` che SCATTA -- vedi il docstring di
    `genere_di` per la ragione per cui resta fuori."""
    assert genere_di("lock.porta_ingresso", "sicurezza") == "sicurezza"
    assert genere_di("alarm_control_panel.casa", "sicurezza") == "sicurezza"
    assert genere_di("siren.sirena_esterna", "sicurezza") == "sicurezza"
    assert genere_di("binary_sensor.fumo_cucina", "sicurezza") == "sicurezza"
    assert genere_di("sensor.co_soggiorno", "sicurezza") is None


def test_una_sirena_che_suona_e_rientra_e_un_oggetto_di_sicurezza(archivio):
    """Lo scenario che la spec §4 chiama il buco peggiore possibile: un
    allarme che scatta e rientra deve diventare un oggetto con la sua durata,
    non sparire come sarebbe successo prima che la sesta gamba esistesse."""
    archivio.annota(quando_ts=ts(3, 15), fonte="entita",
                    soggetto="siren.sirena_esterna", da="off", a="on")
    archivio.annota(quando_ts=ts(3, 20), fonte="entita",
                    soggetto="siren.sirena_esterna", da="on", a="off")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(3, 15)
    assert o["fine_ts"] == ts(3, 20)


def test_una_serratura_sbloccata_e_richiusa_e_un_oggetto_di_sicurezza(archivio):
    """Lock e pannello dell'allarme non usano il vocabolario on/off: qui la
    prova che «locked» chiude l'episodio esattamente come «off» lo fa per gli
    altri, e che «unlocked» lo tiene aperto."""
    archivio.annota(quando_ts=ts(22, 0), fonte="entita",
                    soggetto="lock.porta_ingresso", da="locked", a="unlocked")
    archivio.annota(quando_ts=ts(22, 5), fonte="entita",
                    soggetto="lock.porta_ingresso", da="unlocked", a="locked")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(22, 0)
    assert o["fine_ts"] == ts(22, 5)


# -- Task 3, punto 0: il grezzo porta le tre classi che il pavimento legge --
#
# Prima di questa correzione, `_gamba_del_cambio` chiamava `pavimento.gamba`
# SENZA attributi: per `sensor`/`binary_sensor` (che decidono la gamba dalla
# classe, non dal dominio) la gamba tornava sempre `None`. Conseguenza
# misurata: il genere `consumo` non nasceva MAI, e nemmeno un solo oggetto
# per fumo, gas, monossido, allagamento, manomissione -- la gamba "sicurezza"
# restava raggiungibile solo per serrature, sirene e pannello dell'allarme.

def test_un_binary_sensor_di_fumo_diventa_un_oggetto_di_sicurezza(archivio):
    """La mutazione e' non passare le classi a `gamba` dentro
    `_gamba_del_cambio`: senza `device_class="smoke"`, `pavimento.gamba`
    tornerebbe `None` per un `binary_sensor`, `genere_di` tornerebbe `None`, e
    questo oggetto -- oggi impossibile -- non nascerebbe."""
    archivio.annota(quando_ts=ts(2, 0), fonte="entita",
                    soggetto="binary_sensor.fumo_cucina", da="off", a="on",
                    device_class="smoke")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["protagonista"] == "binary_sensor.fumo_cucina"


def test_un_sensor_di_energia_diventa_un_oggetto_di_consumo(archivio):
    """Il genere `consumo` non nasceva mai (punto 0 del mandato): stessa
    mutazione del test gemello sul fumo, sul dominio `sensor`."""
    archivio.annota(quando_ts=ts(2, 0), fonte="entita",
                    soggetto="sensor.energia_casa", da=None, a="1234.5",
                    device_class="energy")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "consumo"
    assert o["protagonista"] == "sensor.energia_casa"


def test_riga_senza_le_tre_colonne_non_fa_sollevare_l_aggregazione(archivio):
    """Il grezzo gia' in casa, scritto prima di questa correzione, non porta
    le tre classi: le colonne sono annullabili apposta perche' continui a
    rileggersi senza far sollevare `aggrega_giorno`."""
    archivio.annota(quando_ts=ts(2, 0), fonte="entita",
                    soggetto="binary_sensor.fumo_cucina", da="off", a="on")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0


# -- Giro di correzioni dopo la review (2026-08-26) -------------------------

# -- Punto 2: la presenza non deve fabbricare oggetti a ogni riavvio di HA --

def test_un_riavvio_di_ha_non_apre_un_oggetto_di_presenza(archivio):
    """Il ramo `presenza` controllava solo `r["a"] == "home"`: qualunque
    altro valore apriva un oggetto, compresi `unavailable` e `unknown`. A
    ogni riavvio di Home Assistant le `person` ci passano, quindi nasceva un
    oggetto <<presenza, stato unavailable>> di un minuto per ogni persona, a
    ogni riavvio. Mutazione: togliere il filtro `_IGNOTO` dal ramo
    `presenza` -- il conteggio tornerebbe 1 invece di 0."""
    archivio.annota(quando_ts=ts(9, 0), fonte="entita",
                    soggetto="person.paolo", da="home", a="unavailable")
    archivio.annota(quando_ts=ts(9, 1), fonte="entita",
                    soggetto="person.paolo", da="unavailable", a="home")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0


# -- Punto 3b: il riposo di un pannello d'allarme e' ARMATO, non disarmato --

def test_l_allarme_inserito_non_apre_un_oggetto(archivio):
    """Inserire l'allarme la sera e' la cosa che va bene: deve chiudere,
    mai aprire. Mutazione: rimettere "disarmed" in `_SPENTO` e togliere gli
    "armed_*" -- "armed_home" tornerebbe "acceso" e aprirebbe un oggetto che
    non chiuderebbe mai in giornata."""
    archivio.annota(quando_ts=ts(22, 0), fonte="entita",
                    soggetto="alarm_control_panel.casa", da="disarmed",
                    a="armed_home")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0


def test_l_allarme_disinserito_per_otto_ore_apre_un_oggetto(archivio):
    """La casa lasciata senza allarme e' la cosa NOTEVOLE: otto ore da
    "disarmed" a "armed_home" devono produrre un oggetto con quella durata.
    Stessa mutazione del test gemello: con "disarmed" in `_SPENTO` questa
    riga chiuderebbe (nessun oggetto aperto) invece di aprirne uno."""
    archivio.annota(quando_ts=ts(1, 0), fonte="entita",
                    soggetto="alarm_control_panel.casa", da="armed_home",
                    a="disarmed")
    archivio.annota(quando_ts=ts(9, 0), fonte="entita",
                    soggetto="alarm_control_panel.casa", da="disarmed",
                    a="armed_home")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "sicurezza"
    assert o["inizio_ts"] == ts(1, 0)
    assert o["fine_ts"] == ts(9, 0)


# -- Punto 5: le misure non sconfinano nel prossimo episodio, ne' partono --
# -- prima dell'inizio dell'oggetto -----------------------------------------

def test_le_misure_non_sconfinano_nel_prossimo_episodio_dello_stesso_protagonista(archivio):
    """Riscaldamento acceso 15:30-17:05 e di nuovo 19:00-20:00, temperature
    misurate fino alle 23:00: il PRIMO episodio non deve riportare come
    temperatura finale quella delle 23:00 -- e' il clima del secondo
    episodio e oltre. Il limite superiore vero e' l'inizio del prossimo
    oggetto dello STESSO protagonista, non la fine della giornata.
    Mutazione: usare sempre `a_ts` come limite superiore -- il primo
    episodio finirebbe con "a": "17.0" invece di "19.0"."""
    archivio.annota(quando_ts=ts(15, 30), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(16, 0), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="19.0")
    archivio.annota(quando_ts=ts(17, 5), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    archivio.annota(quando_ts=ts(19, 0), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(19, 30), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="20.5")
    archivio.annota(quando_ts=ts(20, 0), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    archivio.annota(quando_ts=ts(23, 0), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="17.0")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                   comprimari=lambda s: ["sensor.camera_temperatura"])
    oggetti = sorted(archivio.oggetti(giorno=G), key=lambda o: o["inizio_ts"])
    assert len(oggetti) == 2
    primo, secondo = oggetti
    assert primo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "19.0", "a": "19.0"}
    assert secondo["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "20.5", "a": "17.0"}


def test_le_misure_non_includono_letture_precedenti_all_inizio_dell_oggetto(archivio):
    """Una misura delle 14:00, prima che il riscaldamento si accenda alle
    15:30, non deve finire come valore INIZIALE dell'episodio: e' il clima
    di prima, non quello di mentre l'oggetto durava. Mutazione: togliere il
    confine inferiore (`e["inizio"] <= t`) -- la misura delle 14:00
    entrerebbe e "da" diventerebbe "14.0" invece di "18.2"."""
    archivio.annota(quando_ts=ts(14, 0), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="14.0")
    archivio.annota(quando_ts=ts(15, 30), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(16, 0), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="18.2")
    archivio.annota(quando_ts=ts(17, 5), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                   comprimari=lambda s: ["sensor.camera_temperatura"])
    o = archivio.oggetti(giorno=G)[0]
    assert o["corpo"]["misure"]["sensor.camera_temperatura"] == {
        "da": "18.2", "a": "18.2"}


# -- Punto 6: un consumo si CHIUDE e porta iniziale/finale/differenza ------

def test_un_consumo_si_chiude_e_porta_iniziale_finale_e_differenza(archivio):
    """Prima di questa correzione un contatore apriva un oggetto al primo
    cambio e non lo chiudeva MAI dentro la giornata: un oggetto
    perennemente aperto, con dentro solo la prima lettura, per ognuno dei
    29 contatori della casa. Mutazione: tornare al vecchio ramo "apri se non
    gia' aperto, mai chiudere" -- `fine_ts` tornerebbe `None` e il corpo
    non porterebbe piu' "valore_iniziale"/"valore_finale"/"differenza"."""
    archivio.annota(quando_ts=ts(1), fonte="entita",
                    soggetto="sensor.energia_casa", da=None, a="100.0",
                    device_class="energy")
    archivio.annota(quando_ts=ts(12), fonte="entita",
                    soggetto="sensor.energia_casa", da=None, a="115.0",
                    device_class="energy")
    archivio.annota(quando_ts=ts(23), fonte="entita",
                    soggetto="sensor.energia_casa", da=None, a="130.5",
                    device_class="energy")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "consumo"
    assert o["inizio_ts"] == ts(1)
    assert o["fine_ts"] == ts(23)
    assert o["corpo"]["valore_iniziale"] == "100.0"
    assert o["corpo"]["valore_finale"] == "130.5"
    assert o["corpo"]["differenza"] == pytest.approx(30.5)


# -- Punto 7: un sensor numerico di monossido non genera un guasto perenne --

def test_un_sensore_co_numerico_non_genera_un_oggetto_di_sicurezza(archivio):
    """Un `sensor` MISURA, non SCATTA: senza una soglia onesta, una
    concentrazione come "0.4" non e' mai in `_SPENTO` e aprirebbe un oggetto
    di sicurezza perennemente aperto al giorno, per ogni sensore CO
    numerico della casa. Mutazione: togliere l'eccezione `dominio ==
    "sensor"` dal ramo sicurezza di `genere_di` -- il conteggio tornerebbe
    1 invece di 0."""
    archivio.annota(quando_ts=ts(2), fonte="entita",
                    soggetto="sensor.co_soggiorno", da=None, a="0.4",
                    device_class="carbon_monoxide")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0


# -- Punto 8: tre finte e un elenco che non sapevano produrre il difetto ---

def _comprimari_per_soggetto(soggetto):
    """Finta che DISCRIMINA per soggetto -- non un `lambda s: [...]`
    costante, che passerebbe anche se `aggrega_giorno` chiamasse
    `comprimari` con il soggetto SBAGLIATO (es. sempre il primo
    protagonista incontrato nel giorno)."""
    return {
        "climate.camera_t": ["sensor.camera_temperatura"],
        "climate.soggiorno_t": ["sensor.soggiorno_temperatura"],
    }.get(soggetto, [])


def test_comprimari_riceve_il_soggetto_giusto_non_uno_qualunque(archivio):
    """Se `aggrega_giorno` chiamasse `comprimari` con un soggetto sbagliato,
    i due oggetti scambierebbero i comprimari: questa finta lo scoprirebbe
    perche' torna elenchi DIVERSI per soggetti diversi, dove una finta
    costante (`lambda s: [...]`) non lo scoprirebbe mai. Mutazione provata:
    dentro `aggrega_giorno`, chiamare `comprimari(soggetto)` passando sempre
    la stringa fissa "climate.camera_t" invece di `e["protagonista"]` --
    l'oggetto di "climate.soggiorno_t" riceverebbe i comprimari sbagliati."""
    archivio.annota(quando_ts=ts(10), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(10, 30), fonte="entita",
                    soggetto="sensor.camera_temperatura", da=None, a="20.0")
    archivio.annota(quando_ts=ts(11), fonte="entita",
                    soggetto="climate.camera_t", da="heat", a="off")
    archivio.annota(quando_ts=ts(12), fonte="entita",
                    soggetto="climate.soggiorno_t", da="off", a="heat")
    archivio.annota(quando_ts=ts(12, 30), fonte="entita",
                    soggetto="sensor.soggiorno_temperatura", da=None, a="22.0")
    archivio.annota(quando_ts=ts(13), fonte="entita",
                    soggetto="climate.soggiorno_t", da="heat", a="off")
    aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome",
                   comprimari=_comprimari_per_soggetto)
    oggetti = {o["protagonista"]: o for o in archivio.oggetti(giorno=G)}
    assert oggetti["climate.camera_t"]["corpo"]["comprimari"] == [
        "sensor.camera_temperatura"]
    assert oggetti["climate.soggiorno_t"]["corpo"]["comprimari"] == [
        "sensor.soggiorno_temperatura"]


def test_il_confine_di_inizio_esclude_l_istante_prima_di_mezzanotte(archivio):
    """MEZZANOTTE - 1 e' l'ultimo istante del giorno che finisce: deve
    restare FUORI da G. Mutazione: `da_ts - 1` dentro `confini_giorno` ("per
    stare sicuri") -- l'istante entrerebbe in G per errore, e il conteggio
    di G tornerebbe 1 invece di 0."""
    archivio.annota(quando_ts=MEZZANOTTE - 1, fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 0
    assert aggrega_giorno(archivio=archivio, giorno="2026-08-23",
                          fuso="Europe/Rome") == 1


def test_gas_sensor_e_gas_rilevatore_non_si_confondono(archivio):
    """La trappola che il pavimento tiene separata per dominio: `sensor`
    classe `gas` e' un CONTATORE (consumo), `binary_sensor` classe `gas` e'
    un RILEVATORE di fuga (sicurezza). Se qualcuno fondesse i due rami per
    sola classe, questo test arrossisce: coppia provata fianco a fianco,
    nello stesso test."""
    archivio.annota(quando_ts=ts(5), fonte="entita",
                    soggetto="sensor.gas_contatore", da=None, a="120.5",
                    device_class="gas")
    archivio.annota(quando_ts=ts(6), fonte="entita",
                    soggetto="binary_sensor.gas_cucina", da="off", a="on",
                    device_class="gas")
    archivio.annota(quando_ts=ts(6, 5), fonte="entita",
                    soggetto="binary_sensor.gas_cucina", da="on", a="off",
                    device_class="gas")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 2
    oggetti = {o["protagonista"]: o for o in archivio.oggetti(giorno=G)}
    assert oggetti["sensor.gas_contatore"]["genere"] == "consumo"
    assert oggetti["binary_sensor.gas_cucina"]["genere"] == "sicurezza"


def test_confini_giorno_ha_25_ore_nel_weekend_di_ottobre():
    """La spec (§3) nomina proprio questo weekend: l'ora torna indietro e il
    giorno dura un'ora in piu'. Mutazione: sommare sempre `timedelta(days=1)`
    in secondi civili fissi (86400) invece che tramite l'aritmetica del
    fuso -- la differenza tornerebbe 86400 invece di 90000."""
    da_ts, a_ts = confini_giorno("2026-10-25", "Europe/Rome")
    assert a_ts - da_ts == 25 * 3600


# -- Punto 9: `_FUNZIONANO` era una lista scritta a mano incompleta --------

def test_domini_aggiunti_a_funzionano_producono_un_funzionamento():
    """`_FUNZIONANO` mancava domini comuni che funzionano come gli altri
    sei, e cadevano in silenzio (nessun oggetto, nessun errore). Mutazione:
    togliere uno dei quattro da `_FUNZIONANO` -- l'assert corrispondente
    tornerebbe `None` invece di "funzionamento"."""
    assert genere_di("humidifier.camera", None) == "funzionamento"
    assert genere_di("vacuum.robot", None) == "funzionamento"
    assert genere_di("valve.giardino", None) == "funzionamento"
    assert genere_di("media_player.soggiorno", None) == "funzionamento"
