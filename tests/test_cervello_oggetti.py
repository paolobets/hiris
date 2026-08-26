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
from hiris.app.cervello.oggetti import GENERI, aggrega_giorno, genere_di

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
    dichiarato; un fuso inventato sposterebbe i giorni senza dirlo."""
    archivio.annota(quando_ts=ts(15), fonte="entita",
                    soggetto="climate.camera_t", da="off", a="heat")
    assert aggrega_giorno(archivio=archivio, giorno="2026-08-23",
                                fuso=None) == 1


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

def test_il_genere_conosce_tutte_e_sei_le_gambe():
    """Le nature risolvibili dal solo dominio -- serratura, pannello
    dell'allarme, sirena -- e i rilevatori (quando la gamba e' nota) diventano
    un guasto: sono una minaccia, non un funzionamento normale, e hanno la
    stessa forma di una condizione di sistema -- nate, durate, chiuse o
    ancora aperte. Un `else` che le mandasse a vuoto sarebbe il buco che la
    review del primo task ha gia' trovato una volta (§4 della spec)."""
    assert genere_di("lock.porta_ingresso", "sicurezza") == "guasto"
    assert genere_di("alarm_control_panel.casa", "sicurezza") == "guasto"
    assert genere_di("siren.sirena_esterna", "sicurezza") == "guasto"
    assert genere_di("binary_sensor.fumo_cucina", "sicurezza") == "guasto"
    assert genere_di("sensor.co_soggiorno", "sicurezza") == "guasto"


def test_una_sirena_che_suona_e_rientra_e_un_guasto(archivio):
    """Lo scenario che la spec §4 chiama il buco peggiore possibile: un
    allarme che scatta e rientra deve diventare un oggetto con la sua durata,
    non sparire come sarebbe successo prima che la sesta gamba esistesse."""
    archivio.annota(quando_ts=ts(3, 15), fonte="entita",
                    soggetto="siren.sirena_esterna", da="off", a="on")
    archivio.annota(quando_ts=ts(3, 20), fonte="entita",
                    soggetto="siren.sirena_esterna", da="on", a="off")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "guasto"
    assert o["inizio_ts"] == ts(3, 15)
    assert o["fine_ts"] == ts(3, 20)


def test_una_serratura_sbloccata_e_richiusa_e_un_guasto(archivio):
    """Lock e pannello dell'allarme non usano il vocabolario on/off: qui la
    prova che «locked» chiude l'episodio esattamente come «off» lo fa per gli
    altri, e che «unlocked» lo tiene aperto."""
    archivio.annota(quando_ts=ts(22, 0), fonte="entita",
                    soggetto="lock.porta_ingresso", da="locked", a="unlocked")
    archivio.annota(quando_ts=ts(22, 5), fonte="entita",
                    soggetto="lock.porta_ingresso", da="unlocked", a="locked")
    assert aggrega_giorno(archivio=archivio, giorno=G, fuso="Europe/Rome") == 1
    o = archivio.oggetti(giorno=G)[0]
    assert o["genere"] == "guasto"
    assert o["inizio_ts"] == ts(22, 0)
    assert o["fine_ts"] == ts(22, 5)
