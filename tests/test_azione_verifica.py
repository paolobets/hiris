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

from hiris.app.azione.registro import ServiceRegistry
from hiris.app.azione.verifica import verification
from tests._contratti import assert_stessa_firma

RISPOSTA_HA = [
    {"domain": "light", "services": {
        # `target`, scritto a mano nella forma plausibile di /api/services
        # (NON misurato su un'installazione vera -- vedi la nota sopra
        # `_DOMINI_UNIVERSALI` in `azione/verifica.py`: quel dato non c'e'
        # ancora). Senza, `test_senza_bersaglio_rifiutato` sotto passerebbe
        # per il motivo sbagliato dopo la review finale (rilievo CRITICO ①)
        # -- non perche' «serve un bersaglio», ma perche' nessun servizio di
        # questo fixture ne dichiarava mai uno.
        "turn_on": {"fields": {"brightness_pct": {}, "transition": {}},
                    "target": {"entity": [{"domain": ["light"]}]}},
        "turn_off": {"fields": {"transition": {}},
                     "target": {"entity": [{"domain": ["light"]}]}},
    }},
    {"domain": "switch", "services": {"turn_on": {"fields": {}, "target": {}}}},
    {"domain": "homeassistant", "services": {
        "turn_off": {"fields": {}},
        # senza `target`, come `notify.*` -- ma "homeassistant" non e' un
        # recapito: serve alla famiglia sotto (review indipendente, punto ①)
        "restart": {"fields": {}},
    }},
    # Un servizio SENZA `target`, come i `notify.*` veri: la review finale
    # (rilievo CRITICO ①) l'aggiunge apposta per provare che un bersaglio
    # vuoto e' legittimo qui e SOLO qui.
    {"domain": "notify", "services": {
        "mobile_app_x": {"fields": {"message": {}, "title": {}}}}},
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
async def _registro_pronto(risposta=None) -> ServiceRegistry:
    r = ServiceRegistry()
    await r.refresh(FintoClient(risposta))
    return r


@pytest.mark.asyncio
async def test_una_chiamata_sana_passa():
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is True
    assert v.domain == "light" and v.service == "turn_off"
    assert v.entity == ("light.salotto",)


@pytest.mark.asyncio
async def test_servizio_scritto_male():
    v = verification({"servizio": "spegni", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "dominio.servizio" in v.reason


@pytest.mark.asyncio
async def test_dominio_inesistente_elenca_quelli_veri():
    """Controllo 2. Senza di lui il rifiuto arriverebbe lo stesso -- ma dal
    controllo 3, che direbbe «lock.turn_off non esiste, i servizi di lock
    sono: (niente)» invece di «il dominio lock non esiste in questa casa».
    Il motivo giusto e' meta' del lavoro: il modello legge questo e sceglie
    fra correggere il servizio e cercare un'altra strada."""
    v = verification({"servizio": "lock.turn_off", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "lock" in v.reason
    assert "light" in v.reason and "switch" in v.reason, (
        "il rifiuto deve dire quali domini esistono, non solo che quello chiesto no")


@pytest.mark.asyncio
async def test_servizio_inesistente_elenca_quelli_veri():
    v = verification({"servizio": "light.esplodi", "bersaglio": {"entita": ["light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "turn_on" in v.reason and "turn_off" in v.reason, (
        "il rifiuto deve dire cosa esiste, non solo cosa non esiste")


@pytest.mark.asyncio
async def test_servizio_senza_dettaglio_e_comunque_esistente():
    """La trappola lasciata dal Task 1, pinnata.

    `registro.service()` risponde `{}` -- **falso in booleano** -- per un
    servizio che esiste ma non dichiara ne' campi ne' bersaglio. Il contratto
    e' `is None`, mai la verita' booleana: un `if registro.service(...)`
    rifiuterebbe questa chiamata legittima, e col motivo sbagliato («non
    esiste» invece di niente).
    """
    registro = await _registro_pronto(
        [{"domain": "scene", "services": {"turn_on": {}}}])
    assert registro.service("scene", "turn_on") == {}, (
        "premessa del test: il dettaglio e' il dict vuoto, falso in booleano")
    v = verification({"servizio": "scene.turn_on",
                  "bersaglio": {"entita": ["scene.serata"]}},
                 registro, {"scene.serata": {"state": "unknown", "attributes": {}}})
    assert v.ok is True, "un servizio senza dettaglio esiste: `is None`, non `if`"


@pytest.mark.asyncio
async def test_entita_inesistente():
    v = verification({"servizio": "light.turn_off", "bersaglio": {"entita": ["light.fantasma"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "light.fantasma" in v.reason


@pytest.mark.asyncio
async def test_dominio_incrociato_rifiutato():
    v = verification({"servizio": "light.turn_off", "bersaglio": {"entita": ["switch.presa"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "switch.presa" in v.reason


@pytest.mark.asyncio
async def test_homeassistant_si_applica_a_tutto():
    v = verification({"servizio": "homeassistant.turn_off",
                  "bersaglio": {"entita": ["switch.presa", "light.salotto"]}},
                 await _registro_pronto(), STATI)
    assert v.ok is True, "i servizi del dominio homeassistant valgono per ogni dominio"


@pytest.mark.asyncio
async def test_parametro_inventato_rifiutato_con_l_elenco_dei_veri():
    v = verification({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"luminosita": 50}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "brightness_pct" in v.reason


@pytest.mark.asyncio
async def test_dati_che_non_e_un_oggetto_rifiutato_per_quello_che_e():
    """Senza il controllo di tipo la lista verrebbe iterata lo stesso, e il
    rifiuto direbbe «brightness_pct non e' un parametro» -- vero ma inutile:
    il modello correggerebbe il nome del parametro invece della forma."""
    v = verification({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": ["brightness_pct"]},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "dati" in v.reason


@pytest.mark.asyncio
async def test_una_entita_sola_puo_essere_una_stringa():
    """Il modello che propone una sola entita' scrive spesso la stringa nuda
    invece della lista di uno. E' una forma legittima, non un errore: va
    accolta, o HIRIS rifiuterebbe per punteggiatura."""
    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"entita": "light.salotto"}},
                 await _registro_pronto(), STATI)
    assert v.ok is True
    assert v.entity == ("light.salotto",)


@pytest.mark.asyncio
async def test_senza_bersaglio_rifiutato():
    v = verification({"servizio": "light.turn_off"}, await _registro_pronto(), STATI)
    assert v.ok is False
    assert "entit" in v.reason.lower()


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
    v = verification({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"rgbw_color": [255, 255, 255, 255]}}, registro, STATI)
    assert v.ok is True, v.reason

    # e il nome della sezione non e' diventato un parametro accettabile
    no = verification({"servizio": "light.turn_on",
                   "bersaglio": {"entita": ["light.salotto"]},
                   "dati": {"advanced_fields": 1}}, registro, STATI)
    assert no.ok is False
    assert "advanced_fields" not in no.reason.split("Quelli veri sono:")[1]


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
    v = verification({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"brightness_pct": 50}}, registro, STATI)
    assert v.ok is True, v.reason


def test_un_fields_illeggibile_non_solleva_nemmeno_saltando_il_registro():
    """La verifica e' pura e chiunque puo' costruirle un registro: il
    controllo di forma dev'essere anche qui, o la promessa della porta
    tornerebbe a dipendere da chi la chiama."""
    class RegistroACaso:
        def domains(self): return ["light"]
        def services_for(self, domain): return ["turn_on"]
        def service(self, domain, name): return {"fields": [{"name": "brightness_pct"}]}

    # Se `ServiceRegistry` cambia firma, questa riga cade invece di
    # lasciare che il finto imiti un contratto che non esiste piu'.
    assert_stessa_firma(ServiceRegistry.domains, RegistroACaso.domains, nome="domains")
    assert_stessa_firma(ServiceRegistry.services_for, RegistroACaso.services_for,
                        nome="services_for")
    assert_stessa_firma(ServiceRegistry.service, RegistroACaso.service, nome="service")

    v = verification({"servizio": "light.turn_on",
                  "bersaglio": {"entita": ["light.salotto"]},
                  "dati": {"brightness_pct": 50}}, RegistroACaso(), STATI)
    assert v.ok is True


@pytest.mark.asyncio
async def test_un_servizio_senza_parametri_rifiuta_ancora_quello_in_piu():
    """Il complemento: `{}` («letto: nessun parametro») e `None` («non l'ho
    letto») non devono collassare l'uno nell'altro, o allargare la difesa di
    R-1 avrebbe spento un controllo che funzionava."""
    v = verification({"servizio": "switch.turn_on",
                  "bersaglio": {"entita": ["switch.presa"]},
                  "dati": {"colore_del_mercoledi": "blu"}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "non accetta parametri" in v.reason


# --- i servizi senza bersaglio -----------------------------------------------
#
# Review finale, rilievo CRITICO ①. Fino a questa passata un bersaglio vuoto
# era SEMPRE un rifiuto -- anche per un servizio come `notify.*` che non
# accetta un `target` -- e questo significava che una promessa «chiedi» non
# poteva MAI notificare: `schedulatore/sweeper.py::_keep_chiedi`
# costruisce la sua chiamata con `"bersaglio": {}`, e questa funzione la
# rifiutava incondizionatamente, prima ancora di guardare il servizio.
#
# La prova per mutazione di questa famiglia: rimettere `if not bersaglio_ha:`
# incondizionato (senza `and _declare_target(definizione)`) fa cadere
# `test_un_servizio_senza_target_accetta_un_bersaglio_vuoto`.

@pytest.mark.asyncio
async def test_un_servizio_senza_target_accetta_un_bersaglio_vuoto():
    v = verification({"servizio": "notify.mobile_app_x",
                  "bersaglio": {},
                  "dati": {"message": "ciao", "title": "HIRIS"}},
                 await _registro_pronto(), STATI)
    assert v.ok is True, v.reason
    assert v.entity == ()
    assert v.target == {}
    assert v.no_target is True


@pytest.mark.asyncio
async def test_un_servizio_senza_target_accetta_anche_bersaglio_del_tutto_assente():
    """«Bersaglio assente» e «bersaglio: {}» sono la stessa cosa per
    `translate_target` (vedi il suo docstring): devono restare la stessa
    cosa anche qui."""
    v = verification({"servizio": "notify.mobile_app_x",
                  "dati": {"message": "ciao"}},
                 await _registro_pronto(), STATI)
    assert v.ok is True, v.reason
    assert v.no_target is True


@pytest.mark.asyncio
async def test_un_servizio_col_target_resta_rifiutato_senza_bersaglio():
    """Il rifiuto di sempre non deve sparire per il servizio sbagliato: qui
    `light.turn_off` DICHIARA un `target` (vedi `RISPOSTA_HA`), quindi un
    bersaglio vuoto resta un errore -- identico a prima, parola per parola.
    E' il test gemello di `test_senza_bersaglio_rifiutato`, con l'assert piu'
    stretto sul motivo esatto."""
    v = verification({"servizio": "light.turn_off"}, await _registro_pronto(), STATI)
    assert v.ok is False
    assert v.reason == ("serve un bersaglio: «entita» con gli id esatti, oppure "
                        "«aree», «piani», «etichette» o «dispositivi» -- Home "
                        "Assistant risolve da se' cosa contengono, e non serve "
                        "elencare le entita' a mano.")


@pytest.mark.asyncio
async def test_un_target_vuoto_ma_dichiarato_resta_rifiutato_senza_bersaglio():
    """`target: {}` (dichiarato, ma senza restrizioni -- il caso vero di
    `switch.turn_on` in `RISPOSTA_HA`) NON e' «nessun target»: e' un `target`
    che accetta di tutto. Il verso prudente di `_declare_target` tratta
    qualunque `dict`, anche vuoto, come «lo dichiara»."""
    v = verification({"servizio": "switch.turn_on"}, await _registro_pronto(), STATI)
    assert v.ok is False
    assert "serve un bersaglio" in v.reason


@pytest.mark.asyncio
async def test_un_servizio_di_sistema_senza_target_resta_rifiutato_senza_bersaglio():
    """Decisione del proprietario (review indipendente, punto ①): il criterio
    iniziale («senza target ⇒ bersaglio vuoto ammesso») era troppo largo --
    rendeva raggiungibili dalla porta anche `homeassistant.restart`,
    `hassio.host_reboot`, `recorder.purge`, `automation.reload`,
    `shell_command.*`, oggi DI FATTO irraggiungibili perche' un bersaglio
    vuoto era sempre un rifiuto e non esiste nessuna lista nera che li fermi
    altrimenti. Il bersaglio vuoto resta ammesso SOLO per i recapiti
    (`notify`, `persistent_notification`): `homeassistant.restart` non
    dichiara un `target` (come i notify.*, vedi `RISPOSTA_HA`) ma non e' un
    recapito, e deve restare rifiutato esattamente come prima.

    Prova per mutazione: togliendo il controllo sulla famiglia da
    `_allows_empty_target` (tornando a `not _declare_target(...)`
    da solo) questo test diventa rosso.
    """
    v = verification({"servizio": "homeassistant.restart"}, await _registro_pronto(), STATI)
    assert v.ok is False
    assert v.reason == ("serve un bersaglio: «entita» con gli id esatti, oppure "
                        "«aree», «piani», «etichette» o «dispositivi» -- Home "
                        "Assistant risolve da se' cosa contengono, e non serve "
                        "elencare le entita' a mano.")


@pytest.mark.asyncio
async def test_un_servizio_senza_target_verifica_comunque_i_parametri():
    """Il bypass del bersaglio non e' un bypass di tutto: un parametro
    inventato resta un rifiuto, come per ogni altro servizio."""
    v = verification({"servizio": "notify.mobile_app_x",
                  "dati": {"colore_del_mercoledi": "blu"}},
                 await _registro_pronto(), STATI)
    assert v.ok is False
    assert "non e' un parametro" in v.reason


@pytest.mark.asyncio
async def test_la_chiamata_dello_schedulatore_per_una_notifica_e_accettata():
    """La giuntura che nessuna review per-task attraversava (CRITICO). La
    forma esatta che `schedulatore/sweeper.py::_keep_chiedi` costruisce
    per notificare -- bersaglio vuoto, servizio `notify.*` -- passata alla
    verifica VERA con un registro che contiene un `notify.*` vero: deve
    risultare accettata. Se qualcuno domani rimettesse il rifiuto
    incondizionato su bersaglio vuoto, questo test torna rosso."""
    chiamata_dello_schedulatore = {
        "servizio": "notify.mobile_app_x", "bersaglio": {},
        "dati": {"message": "e' salita di 2 gradi", "title": "HIRIS"},
    }
    v = verification(chiamata_dello_schedulatore, await _registro_pronto(), STATI)
    assert v.ok is True, v.reason


# --- T8 (R2): dal nome di un'etichetta al label_id a un esegui verificato --
#
# Requisito 4 del brief: il giro intero che chiude il vicolo cieco piu'
# radicale della famiglia (R2, docs/design/2026-08-20-i-riferimenti.md) --
# dal NOME che l'utente ha scritto in Home Assistant, per `cerca`, al
# `label_id`, a un bersaglio di `esegui` che `verification()` ACCETTA. Non si
# esegue: basta che il verdetto sia positivo con un id che, fino a questa
# fetta, nessuna porta faceva uscire.

_CASA_CON_ETICHETTA = {
    "piani": [], "aree": [], "dispositivi": [], "entita": [],
    "categorie": [], "integrazioni": [],
    "etichette": [{"id": "da_controllare", "nome": "Da controllare"}],
}


@pytest.mark.asyncio
async def test_dal_nome_di_un_etichetta_al_label_id_a_una_verifica_che_passa():
    from hiris.app.casa.domande import search
    from hiris.app.memoria.resolver import costruisci_indice

    indice = costruisci_indice(_CASA_CON_ETICHETTA)
    trovati = search(indice, "da controllare")
    candidato = next(c for t in trovati for c in t["candidati"]
                     if c["tipo"] == "etichetta")
    assert candidato["riferimento"] == "da_controllare"

    v = verification({"servizio": "light.turn_off",
                  "bersaglio": {"etichette": [candidato["riferimento"]]}},
                 await _registro_pronto(), STATI,
                 resolved={"entita": ["light.salotto"], "dispositivi": [], "aree": [],
                          "dispositivi_mancanti": [], "aree_mancanti": [],
                          "piani_mancanti": [], "etichette_mancanti": []})
    assert v.ok is True, v.reason
    assert v.entity == ("light.salotto",)
