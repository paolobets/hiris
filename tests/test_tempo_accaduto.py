"""«Cosa e' successo, e per mano di chi».

Due fatti diversi che non vanno mai fusi (spec §2.2): cosa e' successo in casa
(il diario di Home Assistant) e cosa ha fatto HIRIS (la cronaca). Restano due
case, e si uniscono al momento della LETTURA.

L'abbinamento e' **probabile e lo dice**. Home Assistant non mette un nostro
identificatore nel logbook: l'unico aggancio e' entita' + istante vicino. Un
prodotto che dicesse «l'ho accesa io» sulla base di una coincidenza temporale,
senza dichiararlo, mentirebbe con sicurezza -- il difetto che questo progetto
paga piu' caro di ogni altro.
"""
import pytest

from hiris.app.casa.tempo import accaduto

ADESSO = 1787572800.0  # 24 agosto 2026, 12:00 UTC


class _FintoHA:
    def __init__(self, risposta):
        self._risposta = risposta

    async def diario(self, entita, ore):
        return self._risposta


class _FintaCronaca:
    def __init__(self, righe):
        self._righe = righe
        self.chiamate = []

    def elenca(self, *, da_ts, a_ts, entita=None, limite=200):
        self.chiamate.append((da_ts, a_ts, entita))
        return list(self._righe)


def _voce(quando, messaggio="acceso", entita="light.cucina"):
    return {"quando": quando, "nome": "Cucina", "messaggio": messaggio,
            "entita": entita}


@pytest.mark.asyncio
async def test_un_atto_di_hiris_si_riconosce_e_si_dichiara_probabile():
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0,  # 11:00:00 UTC, lo stesso istante
        "origine": "chat", "servizio": "light.turn_on",
        "entita": ["light.cucina"], "eseguito": True, "genere": "comando",
        "cambiato": None, "errore": None, "avviso": None, "oggetto": None}])
    esito = await accaduto(ha=ha, cronaca=cronaca, entita="light.cucina",
                           ore=24, adesso_ts=ADESSO)
    voce = esito["voci"][0]
    assert voce["per_mano_di"] == "HIRIS"
    assert voce["abbinamento"] == "probabile"
    assert voce["atto"]["servizio"] == "light.turn_on"


@pytest.mark.asyncio
async def test_una_voce_lontana_nel_tempo_non_si_abbina():
    """Mezz'ora dopo non e' lo stesso gesto. Senza tolleranza, ogni atto di
    HIRIS si prenderebbe il merito di tutto cio' che quella lampada ha fatto
    nella giornata."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:30:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0, "origine": "chat",
        "servizio": "light.turn_on", "entita": ["light.cucina"],
        "eseguito": True, "genere": "comando", "cambiato": None,
        "errore": None, "avviso": None, "oggetto": None}])
    esito = await accaduto(ha=ha, cronaca=cronaca, entita="light.cucina",
                           ore=24, adesso_ts=ADESSO)
    assert "per_mano_di" not in esito["voci"][0]


@pytest.mark.asyncio
async def test_un_atto_su_un_altra_entita_non_si_abbina():
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([{
        "id": "abc", "quando_ts": 1787569200.0, "origine": "chat",
        "servizio": "light.turn_on", "entita": ["light.salotto"],
        "eseguito": True, "genere": "comando", "cambiato": None,
        "errore": None, "avviso": None, "oggetto": None}])
    esito = await accaduto(ha=ha, cronaca=cronaca, entita="light.cucina",
                           ore=24, adesso_ts=ADESSO)
    assert "per_mano_di" not in esito["voci"][0]


@pytest.mark.asyncio
async def test_senza_abbinamento_la_voce_resta_intera_e_onesta():
    """«L'ha accesa qualcuno e non so chi» e' una risposta buona. Non lo e'
    tacere la voce perche' non sappiamo attribuirla."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    esito = await accaduto(ha=ha, cronaca=_FintaCronaca([]), entita="light.cucina",
                           ore=24, adesso_ts=ADESSO)
    assert len(esito["voci"]) == 1
    assert "per_mano_di" not in esito["voci"][0]


@pytest.mark.asyncio
async def test_un_guasto_del_diario_non_e_una_giornata_tranquilla():
    ha = _FintoHA({"errore": "Home Assistant ha risposto 503"})
    esito = await accaduto(ha=ha, cronaca=_FintaCronaca([]), entita=None,
                           ore=24, adesso_ts=ADESSO)
    assert "voci" not in esito and "503" in esito["errore"]


@pytest.mark.asyncio
async def test_il_troncamento_del_diario_arriva_fino_alla_nota():
    """Una lista tagliata che non dichiara il taglio fa concludere al modello
    «non e' successo altro»."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": True, "ore": 168})
    esito = await accaduto(ha=ha, cronaca=_FintaCronaca([]), entita=None,
                           ore=1000, adesso_ts=ADESSO)
    assert "piu' vecchie" in esito["nota"]
    assert esito["ore"] == 168


@pytest.mark.asyncio
async def test_la_cronaca_si_interroga_sulla_stessa_finestra_del_diario():
    """Due finestre diverse produrrebbero atti senza voce e voci senza atto,
    in modo invisibile."""
    ha = _FintoHA({"voci": [], "troncato": False, "ore": 24})
    cronaca = _FintaCronaca([])
    await accaduto(ha=ha, cronaca=cronaca, entita="light.cucina", ore=24,
                   adesso_ts=ADESSO)
    da_ts, a_ts, entita = cronaca.chiamate[0]
    assert a_ts == ADESSO
    assert da_ts == pytest.approx(ADESSO - 24 * 3600)
    assert entita == "light.cucina"


@pytest.mark.asyncio
async def test_senza_cronaca_l_accaduto_risponde_lo_stesso():
    """`cronaca=None` e' legittimo (il dispatcher e' SEMPRE costruibile): si
    perde l'attribuzione, non la risposta."""
    ha = _FintoHA({"voci": [_voce("2026-08-24T11:00:00+00:00")],
                   "troncato": False, "ore": 24})
    esito = await accaduto(ha=ha, cronaca=None, entita=None, ore=24,
                           adesso_ts=ADESSO)
    assert len(esito["voci"]) == 1
