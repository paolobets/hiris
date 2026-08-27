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
from datetime import UTC, datetime, timedelta

import pytest

from hiris.app.casa.tempo import (
    MAX_PUNTI_IN_RISPOSTA,
    _coperta,
    andamento,
    epoch_istante,
)

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
    # M5: un refuso su "hour" o nel calcolo dei giorni passerebbe inosservato
    # se nessuno guardasse cosa arriva davvero a `ha.statistiche`.
    assert ha.chiamate[0][2] == "hour"
    assert ha.chiamate[0][3] == int(48 / 24) + 1


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


@pytest.mark.asyncio
async def test_la_finestra_coperta_riscrive_il_fuso_dal_sorgente_UTC():
    """I3: le statistiche di Home Assistant tornano SEMPRE in UTC -- e' il
    caso NORMALE, non l'eccezione. Nessuno degli altri test lo esercita: se
    la riscrittura del fuso in `_coperta` sparisse, nessuno se ne
    accorgerebbe, perche' gli altri test partono gia' da un sorgente in
    +02:00. 13:00 UTC di agosto sono 15:00 a Roma (CEST, +02:00)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["finestra_coperta"]["da"] == "2026-08-23T15:00:00+02:00"


@pytest.mark.asyncio
async def test_le_fasce_oltre_il_massimo_si_campionano_come_il_dettaglio():
    """C2: uno slice secco (`fasce[-N:]`) sposta `punti[0]` avanti nel tempo
    mentre `finestra_coperta` restava calcolata sull'elenco INTERO -- una
    copertura dichiarata e mai consegnata. Il ramo statistiche deve
    campionare come il gemello del dettaglio (`_assottiglia`, primo e ultimo
    sempre compresi) e dichiarare il numero VERO di fasce quando riduce.

    Il confronto fra `punti[0]["inizio"]` e `finestra_coperta["da"]` passa
    per `epoch_istante`, non per l'uguaglianza di stringa: le fasce tornano
    in UTC (`+00:00`) mentre `finestra_coperta` e' riscritta nel fuso della
    casa (`+02:00`) -- stesso istante, offset diverso, stessa fondamenta 3
    del test precedente."""
    base = datetime(2026, 8, 15, 9, 0, 0, tzinfo=UTC)
    fasce = [{"inizio": (base + timedelta(hours=i)).isoformat(),
              "minimo": 20.0, "massimo": 21.0, "media": 20.5}
             for i in range(200)]
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": fasce}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=240, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert len(esito["punti"]) <= MAX_PUNTI_IN_RISPOSTA
    assert epoch_istante(esito["punti"][0]["inizio"]) == \
        epoch_istante(esito["finestra_coperta"]["da"])
    assert "200" in esito["nota"]  # il numero VERO delle fasce, non «molte»


# -- F1 (onda finale): un istante non leggibile e' un guasto, non un vuoto --

@pytest.mark.asyncio
async def test_fascia_con_inizio_numerico_fallisce_rumorosamente():
    """Alcune versioni del recorder rendono `start` come epoch in
    millisecondi (un numero), non come stringa ISO -- mai misurato dal vivo
    su questo prodotto (spec S7). Prima della correzione l'`or 0.0` faceva
    scambiare questo caso per «prima della finestra»: la fascia spariva in
    silenzio e la risposta diceva con sicurezza «nessuna registrazione» per
    un'entita' che invece aveva dati veri."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": 1787569200000, "minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "punti" not in esito
    assert "errore" in esito
    # Non e' la nota del terzo esito (§3.3): un guasto non e' un vuoto.
    assert "non ha registrazioni" not in esito["errore"]


@pytest.mark.asyncio
async def test_fascia_senza_inizio_fallisce_rumorosamente():
    """Lo stesso guasto, ma con la chiave assente invece che di un tipo
    inatteso: anche qui `epoch_istante` torna `None`, e deve fermare la
    risposta invece di essere confuso con un vuoto legittimo."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "punti" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_statistiche_davvero_vuote_restano_lesito_nessuna_registrazione():
    """Regressione: senza NESSUNA fascia (non un problema di forma, un vuoto
    vero) l'esito resta il terzo del §3.3, non un errore -- la correzione di
    F1 non deve trasformare ogni assenza in un guasto."""
    ha = _FintoHA(statistiche={"serie": {}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "errore" not in esito
    assert esito["punti"] == []
    assert "esclusa" in esito["nota"]


def test_coperta_con_istante_non_leggibile_ha_tipi_coerenti():
    """`_coperta` non deve mescolare tipi nella stessa coppia: se l'istante
    grezzo non si legge, sia `da` sia `a` restano stringhe -- un `da`
    numerico accanto a un `a` ISO e' la stessa famiglia di difetto di una
    grana taciuta."""
    risultato = _coperta([{"quando": 1787569200000}], "quando",
                         "2026-08-24T14:00:00+02:00")
    assert isinstance(risultato["da"], str)
    assert risultato["da"] == "1787569200000"


def test_coperta_con_istante_assente_resta_none():
    """Il caso degenere: nessuna chiave a cui appoggiarsi resta `None`, non
    la stringa letterale "None"."""
    risultato = _coperta([{}], "quando", "2026-08-24T14:00:00+02:00")
    assert risultato["da"] is None


# -- F2 (onda finale): il troncamento del CLIENT diventa un pavimento -------

@pytest.mark.asyncio
async def test_il_troncamento_del_client_diventa_un_pavimento_dichiarato():
    """`ha.storico` promette `troncato` SEMPRE, apposta perche' «chi legge
    deve poter sapere che e' scattato». Se `tempo.andamento` non lo legge, il
    conteggio nella nota e' un pavimento spacciato per esatto: su 12.000
    cambi veri direbbe «5000 cambi», non «almeno 5000»."""
    punti = [{"quando": f"2026-08-24T00:{m:02d}:00+02:00", "valore": "x"}
             for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}, "troncato": True})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita=None,
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert f"almeno {len(punti)}" in esito["nota"]
    assert "piu' corta" in esito["nota"] or "piu' vecchi" in esito["nota"]


@pytest.mark.asyncio
async def test_senza_troncamento_il_conteggio_resta_esatto():
    """Regressione: senza `troncato`, la nota non deve mai dire «almeno»."""
    punti = [{"quando": f"2026-08-24T00:{m:02d}:00+02:00", "valore": "x"}
             for m in range(60)]
    ha = _FintoHA(storico={"serie": {"sensor.camera": punti}, "troncato": False})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=2, unita=None,
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert "almeno" not in (esito["nota"] or "")


@pytest.mark.asyncio
async def test_i_punti_escono_nello_STESSO_fuso_della_finestra_coperta():
    """Visto dal vivo il 24/08/2026: `finestra_coperta` diceva
    `2026-08-24T14:18+02:00` e `punti[0]` diceva `2026-08-24T12:18+00:00`.
    Sono lo STESSO istante, ma dentro un dizionario solo, e chi legge puo'
    concluderne che i dati cominciano due ore dopo l'apertura della finestra
    -- che e' falso. Lo storico di Home Assistant torna in UTC, la finestra
    nasce nel fuso della casa: e' la fondamenta 3 dentro una risposta sola.
    """
    ha = _FintoHA(storico={"serie": {"sensor.camera": [
        {"quando": "2026-08-24T10:18:50+00:00", "valore": "25.5"},
        {"quando": "2026-08-24T11:00:00+00:00", "valore": "25.6"},
    ]}, "troncato": False})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=6, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["punti"][0]["quando"] == "2026-08-24T12:18:50+02:00"
    assert esito["punti"][1]["quando"] == "2026-08-24T13:00:00+02:00"
    assert esito["finestra_coperta"]["da"] == esito["punti"][0]["quando"]


@pytest.mark.asyncio
async def test_anche_le_fasce_escono_nel_fuso_della_casa():
    """Il gemello del test qui sopra sul ramo delle statistiche: stessa
    domanda, stessa forma della risposta (fondamenta 3)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "minimo": 25.9,
         "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["punti"][0]["inizio"] == "2026-08-23T15:00:00+02:00"
    assert esito["finestra_coperta"]["da"] == esito["punti"][0]["inizio"]


@pytest.mark.asyncio
async def test_la_fine_di_una_fascia_esce_nello_STESSO_fuso_dell_inizio():
    """Punto 5 del mandato «il bilancio dell'energia» (BASSO, 27/08/2026):
    la traduzione unificata (`HAClient._richiedi_statistiche`) ha aggiunto
    la chiave `fine` a ogni fascia, ma `andamento` riscriveva nel fuso della
    casa SOLO `inizio` -- lo stesso punto usciva con `inizio` a +02:00 e
    `fine` ancora a +00:00, due fusi nella stessa risposta (fondamenta 3
    rotta dentro un dizionario solo, gli stessi commenti di questo modulo la
    denunciano per `finestra_coperta`/`punti` e non se ne accorgevano per
    `fine`)."""
    ha = _FintoHA(statistiche={"serie": {"sensor.camera": [
        {"inizio": "2026-08-23T13:00:00+00:00", "fine": "2026-08-23T14:00:00+00:00",
         "minimo": 25.9, "massimo": 27.1, "media": 26.5},
    ]}})
    esito = await andamento(ha=ha, entita="sensor.camera", ore=48, unita="°C",
                            ha_statistiche=True, adesso_ts=ADESSO, fuso="Europe/Rome")
    assert esito["punti"][0]["inizio"] == "2026-08-23T15:00:00+02:00"
    assert esito["punti"][0]["fine"] == "2026-08-23T16:00:00+02:00"
