"""«Com'e' andata»: i quattro esiti che non si confondono mai.

La spec §3.3 li elenca, e sono il motivo per cui questo file e' lungo:
  - il valore non e' mai cambiato
  - oltre cio' che Home Assistant conserva non resta nulla
  - non ci sono registrazioni (l'entita' potrebbe essere esclusa dal recorder)
  - Home Assistant non ha risposto

Un elenco vuoto che li rappresenta tutti e quattro e' una frase falsa detta
con sicurezza -- ed e' cio' che il prodotto diceva prima di questa fetta.

La finta sa produrre TUTTE queste forme. Una finta che risponde sempre bene
non prova nessuno dei quattro.
"""
import pytest

from hiris.app.casa.tempo import MAX_PUNTI_IN_RISPOSTA, andamento

ADESSO = 1787572800.0  # 24 agosto 2026, 12:00 UTC = 14:00 a Roma


class _FintoHA:
    """Sa rispondere bene, sa restituire il vuoto, e sa guastarsi -- perche'
    la meta' che conta di questi test riguarda i due esiti che si somigliano
    e non sono la stessa cosa."""

    def __init__(self, *, storico=None, statistiche=None):
        self._storico = storico if storico is not None else {"serie": {}}
        self._statistiche = statistiche if statistiche is not None else {"serie": {}}
        self.chiamate = []

    async def storico(self, entita, da_iso, a_iso):
        self.chiamate.append(("storico", tuple(entita), da_iso, a_iso))
        return self._storico

    async def statistiche(self, identificatori, periodo, giorni):
        self.chiamate.append(("statistiche", tuple(identificatori), periodo, giorni))
        return self._statistiche


@pytest.mark.asyncio
async def test_finestra_corta_legge_i_cambi_veri():
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T12:00:00+02:00", "valore": "21.0"},
        {"quando": "2026-08-24T13:00:00+02:00", "valore": "21.4"},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["grana"] == "dettaglio"
    assert esito["unita"] == "°C"
    assert len(esito["punti"]) == 2
    assert ha.chiamate[0][0] == "storico"


@pytest.mark.asyncio
async def test_quarantotto_ore_di_un_sensore_ricevono_le_fasce_orarie():
    """La domanda da cui la fetta nasce. Cade SOPRA la soglia e riceve fasce:
    la spec §4.1 lo dichiara, e questo test e' il posto in cui quella scelta
    e' visibile invece che sepolta in una costante."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["grana"] == "oraria"
    assert esito["punti"][0]["media"] == 26.5
    assert ha.chiamate[0][0] == "statistiche"


@pytest.mark.asyncio
async def test_la_grana_oraria_e_dichiarata_nella_nota():
    """Una media oraria presentata come una misura e' una frase vera che
    significa una cosa falsa (spec §3.2)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "orarie" in esito["nota"]


@pytest.mark.asyncio
async def test_un_guasto_non_e_un_valore_mai_cambiato():
    ha = _FintoHA(storico={"errore": "Home Assistant ha risposto 502"})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "punti" not in esito
    assert "502" in esito["errore"]


@pytest.mark.asyncio
async def test_nessuna_registrazione_dichiara_il_dubbio_sul_recorder():
    """Un elenco vuoto DAVVERO vuoto (non un guasto) non e' «non e' mai
    cambiata»: potrebbe essere un'entita' esclusa dalla registrazione, e per
    quelle lo storico e' vuoto per sempre. Non lo sappiamo con certezza, e la
    risposta lo dice cosi': dichiarando il dubbio, non affermando."""
    ha = _FintoHA(storico={"serie": {}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita="°C",
                            ha_statistiche=False, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["punti"] == []
    assert "esclusa" in esito["nota"]
    assert "mai cambiat" not in esito["nota"]


@pytest.mark.asyncio
async def test_un_solo_punto_e_un_valore_fermo_non_un_vuoto():
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T12:00:00+02:00", "valore": "21.0"},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert len(esito["punti"]) == 1
    assert "non e' mai cambiato" in esito["nota"]


@pytest.mark.asyncio
async def test_la_finestra_coperta_si_MISURA_non_si_assume():
    """`purge_keep_days` non e' leggibile da nessuna API. Se i dati cominciano
    dopo l'inizio della finestra chiesta, la finestra coperta e' quella dei
    dati -- misurata, non dedotta da una costante che potrebbe essere falsa su
    questa casa."""
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T13:30:00+02:00", "valore": "21.0"},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=24, unita="°C",
                            ha_statistiche=False, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["finestra_coperta"]["da"] == "2026-08-24T13:30:00+02:00"
    assert esito["finestra_chiesta_ore"] == 24.0


@pytest.mark.asyncio
async def test_il_volume_si_riassume_e_lo_dichiara():
    punti = [{"quando": f"2026-08-24T{h:02d}:{m:02d}:00+02:00", "valore": str(20 + m % 5)}
             for h in range(14) for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=24, unita="°C",
                            ha_statistiche=False, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert len(esito["punti"]) <= MAX_PUNTI_IN_RISPOSTA
    assert "840" in esito["nota"]  # il numero VERO dei cambi, non «molti»


@pytest.mark.asyncio
async def test_senza_statistiche_una_finestra_lunga_resta_sul_dettaglio():
    ha = _FintoHA(storico={"serie": {"binary_sensor.porta": [
        {"quando": "2026-08-23T20:00:00+02:00", "valore": "on"},
    ]}})
    esito = await andamento(ha=ha, entita="binary_sensor.porta", ore=72, unita=None,
                            ha_statistiche=False, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["grana"] == "dettaglio"
    assert ha.chiamate[0][0] == "storico"
