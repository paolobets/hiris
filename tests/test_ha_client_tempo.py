"""Le tre primitive del tempo: storico, statistiche, diario.

La ragione per cui questo file esiste NON e' che le tre chiamate funzionino:
e' che sappiano distinguere «non e' successo niente» da «non ho potuto
chiedere». Prima di questa fetta `get_logbook` restituiva `[]` per entrambi e
`get_statistics` restituiva `{}`: due dei quattro esiti che la spec §3.3
pretende mai confusi erano indistinguibili ALLA FONTE, e nessun chiamante
avrebbe potuto ricostruirli.

**La forma vera delle risposte di Home Assistant qui e' IMMAGINATA.** Nessuna
delle tre e' mai girata contro una casa vera (spec §7.1-7.2). Questi test
pinnano il CONTRATTO che il resto della fetta si aspetta, non la verita' su
Home Assistant: quella si misura dal vivo, e se la forma vera fosse diversa
sono questi test a doversi correggere, non il codice a doversi difendere.
"""
import pytest

from hiris.app.proxy.ha_client import HAClient


class _FintaRisposta:
    def __init__(self, status, corpo=None, solleva=None):
        self.status = status
        self._corpo = corpo
        self._solleva = solleva

    async def __aenter__(self):
        if self._solleva is not None:
            raise self._solleva
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self._corpo


class _FintaSessione:
    """Registra gli URL chiesti: meta' delle prove qui riguardano cosa NON si
    e' chiesto (una finestra non clampata, un filtro non passato)."""

    def __init__(self, risposte):
        self._risposte = list(risposte)
        self.url_chiesti = []

    def get(self, url):
        self.url_chiesti.append(url)
        return self._risposte.pop(0)


def _client(risposte):
    c = HAClient("http://ha.local", "token")
    c._session = _FintaSessione(risposte)
    return c


@pytest.mark.asyncio
async def test_storico_restituisce_una_serie_per_entita():
    # La forma di /api/history/period: una lista di liste, una per entita'.
    # Con `minimal_response` solo il PRIMO elemento porta `entity_id`: gli
    # altri sono {state, last_changed} e l'entita' va portata avanti.
    corpo = [[
        {"entity_id": "sensor.camera", "state": "21.0", "last_changed": "2026-08-24T08:00:00+00:00"},
        {"state": "21.4", "last_changed": "2026-08-24T09:00:00+00:00"},
    ]]
    c = _client([_FintaRisposta(200, corpo)])
    esito = await c.storico(["sensor.camera"], "2026-08-24T08:00:00+00:00",
                            "2026-08-24T10:00:00+00:00")
    assert esito == {"serie": {"sensor.camera": [
        {"quando": "2026-08-24T08:00:00+00:00", "valore": "21.0"},
        {"quando": "2026-08-24T09:00:00+00:00", "valore": "21.4"},
    ]}}


@pytest.mark.asyncio
async def test_storico_un_guasto_non_e_una_serie_vuota():
    """Il cuore di questo file. `{"serie": {}}` direbbe «il valore non e' mai
    cambiato»: e' un'affermazione, e nessuno ha il diritto di farla quando la
    domanda non e' nemmeno arrivata."""
    c = _client([_FintaRisposta(500)])
    esito = await c.storico(["sensor.camera"], "2026-08-24T08:00:00+00:00",
                            "2026-08-24T10:00:00+00:00")
    assert "serie" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_storico_un_guasto_di_trasporto_non_solleva():
    c = _client([_FintaRisposta(200, solleva=OSError("connessione rifiutata"))])
    esito = await c.storico(["sensor.camera"], "2026-08-24T08:00:00+00:00",
                            "2026-08-24T10:00:00+00:00")
    assert "serie" not in esito
    assert "errore" in esito


@pytest.mark.asyncio
async def test_storico_chiede_solo_le_entita_domandate():
    c = _client([_FintaRisposta(200, [])])
    await c.storico(["sensor.a", "sensor.b"], "2026-08-24T08:00:00+00:00",
                    "2026-08-24T10:00:00+00:00")
    url = c._session.url_chiesti[0]
    assert "filter_entity_id=sensor.a%2Csensor.b" in url
    # `minimal_response` e `no_attributes`: senza, HA rimanda l'intero
    # dizionario degli attributi a OGNI cambio di stato -- megabyte per una
    # domanda a cui rispondono due colonne.
    assert "minimal_response" in url and "no_attributes" in url


@pytest.mark.asyncio
async def test_storico_tetto_sui_punti_e_dichiarato():
    corpo = [[{"entity_id": "sensor.x", "state": str(i),
               "last_changed": f"2026-08-24T00:00:{i % 60:02d}+00:00"}
              for i in range(6000)]]
    c = _client([_FintaRisposta(200, corpo)])
    esito = await c.storico(["sensor.x"], "2026-08-24T00:00:00+00:00",
                            "2026-08-24T10:00:00+00:00")
    assert len(esito["serie"]["sensor.x"]) == 5000
    assert esito["troncato"] is True


@pytest.mark.asyncio
async def test_diario_distingue_il_silenzio_dal_guasto():
    c = _client([_FintaRisposta(200, [])])
    assert await c.diario(None, 24) == {"voci": [], "troncato": False, "ore": 24}
    c = _client([_FintaRisposta(503)])
    esito = await c.diario(None, 24)
    assert "voci" not in esito and "errore" in esito


@pytest.mark.asyncio
async def test_diario_clampa_la_finestra_e_lo_dichiara():
    """`ore` arriva da una tool-call del modello: puo' essere qualunque cosa.
    Il valore CLAMPATO torna al chiamante, altrimenti chi compone la risposta
    direbbe «nell'ultimo mese» avendo guardato una settimana."""
    c = _client([_FintaRisposta(200, [])])
    esito = await c.diario(None, 100000)
    assert esito["ore"] == 168


@pytest.mark.asyncio
async def test_statistiche_distinguono_il_vuoto_dal_guasto(monkeypatch):
    c = HAClient("http://ha.local", "token")

    async def _ok(_tipo, extra=None, timeout=10.0):
        return {"sensor.camera": [
            {"start": "2026-07-24T13:00:00+00:00", "mean": 26.5, "min": 26.0, "max": 27.1},
        ]}

    monkeypatch.setattr(c, "_ws_request", _ok)
    esito = await c.statistiche(["sensor.camera"], "hour", 30)
    assert esito["serie"]["sensor.camera"][0]["media"] == 26.5
    assert esito["serie"]["sensor.camera"][0]["inizio"] == "2026-07-24T13:00:00+00:00"

    async def _giu(_tipo, extra=None, timeout=10.0):
        return None  # il websocket non ha risposto

    monkeypatch.setattr(c, "_ws_request", _giu)
    esito = await c.statistiche(["sensor.camera"], "hour", 30)
    assert "serie" not in esito and "errore" in esito
