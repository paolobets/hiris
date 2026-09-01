"""Le due porte nuove verso Home Assistant: i legami e i guasti.

Entrambe seguono la stessa disciplina, e la prova che conta e' sempre la
stessa: **un guasto non deve avere la forma di un «niente»**. Un elenco vuoto
significa «questa cosa non la tocca nessuno» o «non c'e' niente che non va»,
che sono affermazioni; un guasto e' un silenzio, e va dichiarato.
"""
import pytest

from hiris.app.proxy.ha_client import HAClient


class _Finto:
    def __init__(self, risposta=None, solleva=False):
        self.risposta = risposta
        self.solleva = solleva
        self.comandi = []

    async def _ws_batch(self, commands, timeout=10.0):
        self.comandi.extend(commands)
        if self.solleva:
            raise OSError("HA muto")
        return [self.risposta]


def _client(finto):
    c = HAClient.__new__(HAClient)
    c._ws_batch = finto._ws_batch
    return c


# --- i legami -------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_legami_arrivano_ordinati():
    """HA manda INSIEMI, che in JSON viaggiano come liste in ordine
    arbitrario: senza ordinare, due letture della stessa casa producono due
    risposte diverse e nessuno capisce perche'."""
    finto = _Finto({"result": {"automation": ["automation.b", "automation.a"],
                               "scene": []}})
    esito = await _client(finto).legami("entity", "light.corridoio")
    assert esito == {"automation": ["automation.a", "automation.b"]}
    assert finto.comandi[0] == ("search/related",
                                {"item_type": "entity", "item_id": "light.corridoio"})


@pytest.mark.asyncio
async def test_un_tipo_che_home_assistant_non_conosce_si_rifiuta_prima():
    """I quattordici tipi sono quelli veri di `ItemType`. Mandarne uno
    inventato produrrebbe un rifiuto di HA che arriva come «errore generico»:
    meglio dire subito qual e' il problema."""
    finto = _Finto({"result": {}})
    esito = await _client(finto).legami("stanza", "cucina")
    assert "errore" in esito
    assert finto.comandi == [], "non si chiama HA per un tipo che non accetta"


@pytest.mark.asyncio
@pytest.mark.parametrize("finto,perche", [
    (_Finto(solleva=True), "connessione caduta"),
    (_Finto({"error": {"message": "non trovato"}}), "HA ha rifiutato"),
    (_Finto({"result": "non un dizionario"}), "forma inattesa"),
])
async def test_un_legame_non_letto_non_diventa_un_elenco_vuoto(finto, perche):
    esito = await _client(finto).legami("entity", "light.x")
    assert "errore" in esito, perche


# --- i guasti -------------------------------------------------------------

@pytest.mark.asyncio
async def test_i_problemi_arrivano_come_home_assistant_li_manda():
    """La scelta di cosa dire e cosa tacere non e' del client: e' di chi
    compone. Qui si legge soltanto -- severita', riparabilita' e la versione
    in cui qualcosa si rompera' restano tutte."""
    finto = _Finto({"result": {"issues": [
        {"domain": "reolink", "issue_id": "x", "severity": "error",
         "is_fixable": True, "breaks_in_ha_version": "2026.9", "ignored": False},
    ]}})
    esito = await _client(finto).problemi()
    assert esito["problemi"][0]["severity"] == "error"
    assert esito["problemi"][0]["breaks_in_ha_version"] == "2026.9"


@pytest.mark.asyncio
async def test_un_problema_IGNORATO_non_esce():
    """L'utente ha gia' detto «non dirmelo», in Home Assistant. Ripeterglielo
    sarebbe disobbedire a una scelta che ha espresso -- ed e' l'unico filtro
    che il client si permette."""
    finto = _Finto({"result": {"issues": [
        {"domain": "a", "issue_id": "1", "severity": "warning", "ignored": True},
        {"domain": "b", "issue_id": "2", "severity": "warning", "ignored": False},
    ]}})
    esito = await _client(finto).problemi()
    assert [p["domain"] for p in esito["problemi"]] == ["b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("finto,perche", [
    (_Finto(solleva=True), "connessione caduta"),
    (_Finto({"error": {"code": "unknown_command"}}), "HA ha rifiutato"),
    (_Finto({"result": {"issues": "non una lista"}}), "forma inattesa"),
])
async def test_un_guasto_di_lettura_non_diventa_una_casa_sana(finto, perche):
    """La prova che conta: `{"problemi": []}` significa «non c'e' niente che
    non va», ed e' la bugia piu' facile da dire davanti a un guasto."""
    esito = await _client(finto).problemi()
    assert "errore" in esito, perche
    assert "problemi" not in esito
