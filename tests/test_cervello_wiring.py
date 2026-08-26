"""L'osservatore esiste nell'app vera, e nasce DOPO cio' che gli serve.

Meta' di questo file prova il CABLAGGIO e non il comportamento, ed e'
deliberato: questo progetto ha gia' scoperto che uno strumento perfetto e non
cablato e' indistinguibile da uno assente.

L'altra meta' prova i due difetti che il mandato originale del Task 5
avrebbe lasciato nascere (task-5-correzioni.md):

  A. `guarda_sistema` senza nessun chiamante -- codice morto dal primo
     giorno, e la spec §6 diventata una frase falsa;
  A.1. un errore di lettura passato a `guarda_sistema` come lista vuota --
       peggio di non sapere, sapere il falso e scriverlo nell'archivio.
"""
import asyncio
import inspect

from hiris.app import server
from hiris.app.cervello.archivio import CONSERVAZIONE_CAMBI_S
from hiris.app.server import guarda_condizioni_di_sistema


# --------------------------------------------------------------------------
# Il cablaggio dichiarato dal mandato (task-5-brief.md, Step 1)
# --------------------------------------------------------------------------

def test_l_archivio_e_l_osservatore_sono_cablati():
    sorgente = inspect.getsource(server)
    assert 'app["osservazioni"] = ArchivioOsservazioni(' in sorgente
    assert 'app["osservatore"] = Osservatore(' in sorgente


def test_l_osservatore_e_agganciato_allo_STESSO_rubinetto_dello_specchio():
    """Non si apre un secondo rubinetto: due sorgenti degli stessi eventi
    sarebbero due cose che possono divergere."""
    sorgente = inspect.getsource(server)
    assert "ha_client.add_state_listener(app[\"osservatore\"].guarda_cambio)" in sorgente
    assert sorgente.index("ha_client.add_state_listener(entity_cache.on_state_changed)") \
        < sorgente.index("ha_client.add_state_listener(app[\"osservatore\"].guarda_cambio)")


def test_l_osservatore_nasce_dopo_il_suo_archivio():
    sorgente = inspect.getsource(server)
    assert sorgente.index('app["osservazioni"] = ArchivioOsservazioni(') \
        < sorgente.index('app["osservatore"] = Osservatore(')


def test_i_due_lavori_periodici_sono_registrati():
    """L'aggregazione notturna e la potatura. Senza il primo il grezzo si
    accumula e nessun oggetto nasce; senza il secondo l'archivio cresce per
    sempre."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_cervello_aggregazione"' in sorgente
    assert 'id="hiris_cervello_potatura"' in sorgente


def test_l_archivio_si_chiude_nello_spegnimento():
    sorgente = inspect.getsource(server._on_cleanup)
    assert 'if "osservazioni" in app:' in sorgente
    assert 'app["osservazioni"].close()' in sorgente


def test_l_aggregazione_gira_DOPO_la_mezzanotte_della_casa():
    """Aggregare a mezzanotte esatta prenderebbe un giorno ancora aperto.
    L'ora scelta e' dichiarata nel sorgente con la sua ragione."""
    sorgente = inspect.getsource(server)
    blocco = sorgente[sorgente.index('id="hiris_cervello_aggregazione"') - 700:
                      sorgente.index('id="hiris_cervello_aggregazione"') + 200]
    assert "cron" in blocco


# --------------------------------------------------------------------------
# Correzione A: la terza voce che il mandato originale dimenticava --
# `guarda_sistema` deve avere un chiamante vero, non restare morto.
# --------------------------------------------------------------------------

def test_il_terzo_lavoro_periodico_delle_condizioni_e_registrato():
    """Senza questo lavoro `guarda_sistema` non ha nessun chiamante di
    produzione: nasce codice morto lo stesso giorno in cui viene scritto, e
    la spec §6 (i guasti diventano oggetti dal primo giorno) diventa una
    frase falsa (task-5-correzioni.md, punto A)."""
    sorgente = inspect.getsource(server)
    assert 'id="hiris_cervello_condizioni"' in sorgente
    blocco = sorgente[sorgente.index('id="hiris_cervello_condizioni"') - 400:
                      sorgente.index('id="hiris_cervello_condizioni"') + 200]
    assert "minutes=10" in blocco
    assert "guarda_condizioni_di_sistema" in sorgente


def test_le_condizioni_si_leggono_anche_una_volta_all_avvio():
    """«Ogni 10 minuti, e una volta all'avvio» (punto A): senza la prima
    lettura all'avvio, un guasto gia' aperto da prima del boot resterebbe
    invisibile fino a dieci minuti dopo."""
    sorgente = inspect.getsource(server._on_startup)
    assert sorgente.count("guarda_condizioni_di_sistema(app, ha_client)") >= 2


def test_l_osservatore_ricostruisce_le_condizioni_all_avvio():
    """Punto B: senza questa chiamata, a ogni riavvio dell'add-on -- che
    succede a ogni aggiornamento -- i guasti gia' aperti verrebbero
    riscritti come nati adesso, e l'oggetto «guasto» perderebbe la sua unica
    informazione utile: da quando dura."""
    sorgente = inspect.getsource(server._on_startup)
    assert 'app["osservatore"].ricostruisci_condizioni()' in sorgente
    assert sorgente.index('app["osservatore"] = Osservatore(') \
        < sorgente.index('app["osservatore"].ricostruisci_condizioni()') \
        < sorgente.index('guarda_condizioni_di_sistema(app, ha_client)')


def test_la_potatura_non_scrive_a_mano_il_numero_di_giorni():
    """Punto C: la ritenzione vera e' 22 giorni (21 di promessa, il 22esimo
    la guardia), non 21 -- e il messaggio non deve poter mentire quando la
    costante cambia. Non basta che il commento lo dica: e' la RIGA DI LOG a
    dover derivare il numero dalla costante invece di scriverlo a mano, e
    questa prova legge proprio quella riga, non la prosa attorno."""
    sorgente = inspect.getsource(server._on_startup)
    # La riga di log: nessuna cifra letterale, il numero arriva da un
    # argomento (`%s`), non e' scritto nel formato.
    assert '"cervello: %s cambi oltre i %s giorni sono usciti"' in sorgente
    # E quell'argomento e' DERIVATO dalla costante dell'archivio, non un
    # altro numero scritto a mano altrove nella funzione.
    assert "giorni = CONSERVAZIONE_CAMBI_S // 86400" in sorgente
    assert CONSERVAZIONE_CAMBI_S // 86400 == 22


# --------------------------------------------------------------------------
# Correzione A.1: un errore di lettura non e' «tutto a posto». Qui si
# esercita `guarda_condizioni_di_sistema` per davvero, non solo il sorgente.
# --------------------------------------------------------------------------

class _OsservatoreFinto:
    def __init__(self):
        self.chiamate: list[dict] = []

    def guarda_sistema(self, *, problemi, integrazioni):
        self.chiamate.append({"problemi": problemi, "integrazioni": integrazioni})
        return len(problemi) + len(integrazioni)


class _ClienteFinto:
    """Un `HAClient` finto: `problemi_esito` e' cio' che torna `problemi()`,
    `registri_esito` la coppia `(registri, non_disponibili)` di
    `leggi_registri()`."""

    def __init__(self, problemi_esito, registri_esito):
        self._problemi_esito = problemi_esito
        self._registri_esito = registri_esito

    async def problemi(self):
        return self._problemi_esito

    async def leggi_registri(self):
        return self._registri_esito


def test_guarda_condizioni_chiama_guarda_sistema_quando_le_due_letture_riescono():
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"problemi": [{"domain": "hue", "issue_id": "x"}]},
        ({"integrazioni": [{"entry_id": "y", "state": "not_loaded"}]}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito == 2
    assert len(osservatore.chiamate) == 1
    assert osservatore.chiamate[0]["problemi"] == [{"domain": "hue", "issue_id": "x"}]
    assert osservatore.chiamate[0]["integrazioni"] == [{"entry_id": "y", "state": "not_loaded"}]


def test_un_errore_di_problemi_salta_il_giro_per_intero():
    """La prova per mutazione (task-5-correzioni.md, punto A.1): con
    `problemi()` che torna `{"errore": ...}`, `guarda_sistema` non viene
    chiamato. La mutazione (passare `[]` invece di saltare il giro) e' stata
    provata a mano durante l'implementazione e fa arrossire questa prova --
    non e' un'affermazione a vuoto."""
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"errore": "Home Assistant non ha risposto"},
        ({"integrazioni": []}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_le_integrazioni_non_disponibili_saltano_il_giro_per_intero():
    """Identico per `leggi_registri`: se `"integrazioni"` e' in
    `non_disponibili`, quella lista e' vuota per guasto, non perche' vada
    tutto bene -- passarla cosi' com'e' chiuderebbe ogni integrazione gia'
    rotta come se si fosse appena risolta."""
    osservatore = _OsservatoreFinto()
    app = {"osservatore": osservatore}
    cliente = _ClienteFinto(
        {"problemi": []},
        ({"integrazioni": []}, ["integrazioni"]))

    esito = asyncio.run(guarda_condizioni_di_sistema(app, cliente))

    assert esito is None
    assert osservatore.chiamate == []


def test_senza_osservatore_non_scrive_niente():
    """Un `app` senza `"osservatore"` (avvio a meta', o un test che non lo
    costruisce): il giro tace invece di sollevare."""
    cliente = _ClienteFinto({"problemi": []}, ({"integrazioni": []}, []))

    esito = asyncio.run(guarda_condizioni_di_sistema({}, cliente))

    assert esito is None
