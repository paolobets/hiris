"""La verifica: la parte che dice di no, e dice perche'.

Task 3 della fetta «comandare». Copre i sette controlli della tabella del
brief, uno per uno, piu' i tre rami che il codice ha e che la tabella non
elenca (il servizio senza dettaglio, l'entita' passata come stringa, `dati`
che non e' un oggetto).

Nessun Home Assistant, nessuna rete, nessun mock di rete: `verifica` e' una
funzione pura, e questo file e' la dimostrazione che la parte che decide se
toccare la casa non ha bisogno della casa per essere provata.

Ogni test qui e' stato provato per mutazione -- tolto il controllo che
difende, il test cade. L'esito e' nel rapporto del task.
"""
import pytest

from hiris.app.azione.registro import RegistroServizi
from hiris.app.azione.verifica import verifica

RISPOSTA_HA = [
    {"domain": "light", "services": {
        "turn_on": {"fields": {"brightness_pct": {}, "transition": {}}},
        "turn_off": {"fields": {"transition": {}}},
    }},
    {"domain": "switch", "services": {"turn_on": {"fields": {}}}},
    {"domain": "homeassistant", "services": {"turn_off": {"fields": {}}}},
]

STATI = {
    "light.salotto": {"state": "on", "attributes": {}},
    "switch.presa": {"state": "off", "attributes": {}},
}


class FintoClient:
    def __init__(self, risposta=None):
        self.risposta = RISPOSTA_HA if risposta is None else risposta

    async def get_services(self):
        return self.risposta


# NON una fixture asincrona: la suite gira in modalita' `strict` di
# pytest-asyncio (nessun `asyncio_mode = auto` nella configurazione, e ogni
# test async porta il suo `@pytest.mark.asyncio`). In strict mode una
# `@pytest.fixture` su una funzione async consegna al test una COROUTINE, non
# il valore -- un helper atteso dentro il test e' l'unica forma che non
# dipende dalla versione di pytest-asyncio installata.
async def _registro_pronto(risposta=None) -> RegistroServizi:
    r = RegistroServizi()
    await r.aggiorna(FintoClient(risposta))
    return r


@pytest.mark.asyncio
async def test_una_chiamata_sana_passa():
    v = verifica({"servizio": "light.turn_off",
                  "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is True
    assert v.dominio == "light" and v.servizio == "turn_off"
    assert v.entita == ("light.salotto",)


@pytest.mark.asyncio
async def test_servizio_scritto_male():
    v = verifica({"servizio": "spegni", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "dominio.servizio" in v.motivo


@pytest.mark.asyncio
async def test_dominio_inesistente_elenca_quelli_veri():
    """Controllo 2. Senza di lui il rifiuto arriverebbe lo stesso -- ma dal
    controllo 3, che direbbe «lock.turn_off non esiste, i servizi di lock
    sono: (niente)» invece di «il dominio lock non esiste in questa casa».
    Il motivo giusto e' meta' del lavoro: il modello legge questo e sceglie
    fra correggere il servizio e cercare un'altra strada."""
    v = verifica({"servizio": "lock.turn_off", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "lock" in v.motivo
    assert "light" in v.motivo and "switch" in v.motivo, (
        "il rifiuto deve dire quali domini esistono, non solo che quello chiesto no")


@pytest.mark.asyncio
async def test_servizio_inesistente_elenca_quelli_veri():
    v = verifica({"servizio": "light.esplodi", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "turn_on" in v.motivo and "turn_off" in v.motivo, (
        "il rifiuto deve dire cosa esiste, non solo cosa non esiste")


@pytest.mark.asyncio
async def test_servizio_senza_dettaglio_e_comunque_esistente():
    """La trappola lasciata dal Task 1, pinnata.

    `registro.servizio()` risponde `{}` -- **falso in booleano** -- per un
    servizio che esiste ma non dichiara ne' campi ne' bersaglio. Il contratto
    e' `is None`, mai la verita' booleana: un `if registro.servizio(...)`
    rifiuterebbe questa chiamata legittima, e col motivo sbagliato («non
    esiste» invece di niente).
    """
    registro = await _registro_pronto(
        [{"domain": "scene", "services": {"turn_on": {}}}])
    assert registro.servizio("scene", "turn_on") == {}, (
        "premessa del test: il dettaglio e' il dict vuoto, falso in booleano")
    v = verifica({"servizio": "scene.turn_on",
                  "bersaglio": {"entita": ["scene.serata"]}},
                 registro, {"scene.serata": {"state": "unknown", "attributes": {}}})
    assert v.ok is True, "un servizio senza dettaglio esiste: `is None`, non `if`"


@pytest.mark.asyncio
async def test_entita_inesistente():
    v = verifica({"servizio": "light.turn_off", "bersaglio": {"entita": ["light.fantasma"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "light.fantasma" in v.motivo


@pytest.mark.asyncio
async def test_dominio_incrociato_rifiutato():
    v = verifica({"servizio": "light.turn_off", "bersaglio": {"entita": ["switch.presa"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "switch.presa" in v.motivo


@pytest.mark.asyncio
async def test_homeassistant_si_applica_a_tutto():
    v = verifica({"servizio": "homeassistant.turn_off",
                  "bersaglio": {"entita": ["switch.presa", "light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is True, "i servizi del dominio homeassistant valgono per ogni dominio"


@pytest.mark.asyncio
async def test_parametro_inventato_rifiutato_con_l_elenco_dei_veri():
    v = verifica({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"luminosita": 50}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "brightness_pct" in v.motivo


@pytest.mark.asyncio
async def test_dati_che_non_e_un_oggetto_rifiutato_per_quello_che_e():
    """Senza il controllo di tipo la lista verrebbe iterata lo stesso, e il
    rifiuto direbbe «brightness_pct non e' un parametro» -- vero ma inutile:
    il modello correggerebbe il nome del parametro invece della forma."""
    v = verifica({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": ["brightness_pct"]},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "dati" in v.motivo


@pytest.mark.asyncio
async def test_una_entita_sola_puo_essere_una_stringa():
    """Il modello che propone una sola entita' scrive spesso la stringa nuda
    invece della lista di uno. E' una forma legittima, non un errore: va
    accolta, o HIRIS rifiuterebbe per punteggiatura."""
    v = verifica({"servizio": "light.turn_off",
                  "bersaglio": {"entita": "light.salotto"}},
                 await _registro_pronto(), STATI)
    assert v.ok is True
    assert v.entita == ("light.salotto",)


@pytest.mark.asyncio
async def test_senza_bersaglio_rifiutato():
    v = verifica({"servizio": "light.turn_off"}, await _registro_pronto(), STATI)
    assert v.ok is False
    assert "entit" in v.motivo.lower()


# --- cio' che il registro non ha saputo leggere -----------------------------
#
# R-1 e R-2 visti da qui: la verifica e' l'unico lettore di `fields`, e le due
# forme che nessuno aveva misurato le incontrava lei.

@pytest.mark.asyncio
async def test_un_parametro_dentro_una_sezione_e_un_parametro_vero():
    """R-2, end-to-end fino al verdetto: il registro appiattisce, la verifica
    accetta. Prima di questa passata «metti la luce in bianco freddo»
    riceveva «`rgbw_color` non e' un parametro di `light.turn_on`»."""
    risposta = [{"domain": "light", "services": {"turn_on": {"fields": {
        "brightness_pct": {},
        "advanced_fields": {"collapsed": True, "fields": {"rgbw_color": {}}},
    }}}}]
    registro = await _registro_pronto(risposta)
    v = verifica({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"rgbw_color": [255, 255, 255, 255]}}, registro, STATI)
    assert v.ok is True, v.motivo

    # e il nome della sezione non e' diventato un parametro accettabile
    no = verifica({"servizio": "light.turn_on",
                   "bersaglio": {"entita": ["light.salotto"]},
                   "dati": {"advanced_fields": 1}}, registro, STATI)
    assert no.ok is False
    assert "advanced_fields" not in no.motivo.split("Quelli veri sono:")[1]


@pytest.mark.asyncio
async def test_un_fields_illeggibile_non_solleva_e_non_rifiuta():
    """R-1. Due cose insieme, e la seconda conta quanto la prima.

    Non solleva: prima, `set(definizione.get("fields") or {})` su una lista di
    oggetti faceva risalire un `TypeError` fino al modello, che leggeva
    «unhashable type: 'dict'» come motivo del rifiuto. La promessa «la porta
    non solleva mai» era mantenuta solo dal `try/except` del suo chiamante
    attuale -- lo schedulatore di domani la prenderebbe in faccia.

    E non rifiuta: su cio' che non si e' potuto misurare non si dice «non
    accetta parametri». Se la forma vera di `/api/services` fosse quella, quel
    rifiuto varrebbe per OGNI servizio della casa."""
    registro = await _registro_pronto(
        [{"domain": "light", "services": {"turn_on": {"fields": [{"name": "brightness_pct"}]}}}])
    v = verifica({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"brightness_pct": 50}}, registro, STATI)
    assert v.ok is True, v.motivo


def test_un_fields_illeggibile_non_solleva_nemmeno_saltando_il_registro():
    """La verifica e' pura e chiunque puo' costruirle un registro: il
    controllo di forma dev'essere anche qui, o la promessa della porta
    tornerebbe a dipendere da chi la chiama."""
    class RegistroACaso:
        def domini(self): return ["light"]
        def servizi_di(self, d): return ["turn_on"]
        def servizio(self, d, n): return {"fields": [{"name": "brightness_pct"}]}

    v = verifica({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"brightness_pct": 50}}, RegistroACaso(), STATI)
    assert v.ok is True


@pytest.mark.asyncio
async def test_un_servizio_senza_parametri_rifiuta_ancora_quello_in_piu():
    """Il complemento: `{}` («letto: nessun parametro») e `None` («non l'ho
    letto») non devono collassare l'uno nell'altro, o allargare la difesa di
    R-1 avrebbe spento un controllo che funzionava."""
    v = verifica({"servizio": "switch.turn_on",
                  "bersaglio": {"entita": ["switch.presa"]},
                  "dati": {"colore_del_mercoledi": "blu"}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "non accetta parametri" in v.motivo
