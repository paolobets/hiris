"""Le cinque rotte: guardare, guardarne una, confermare, rimettere com'era, rifiutare."""
import os
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import web

from hiris.app.action.construction.revisions import CONSTRUCTIONS_KEY
from hiris.app.action.construction.workshop import WORKSHOP_KEY
from hiris.app.action.journal import JOURNAL_KEY
from hiris.app.api.middleware_internal_auth import INGRESS_CIDRS_KEY
from hiris.app.api.soffitto import ROLES_KEY
from hiris.app.mind.store import OBSERVATIONS_KEY
from hiris.app.proxy.ha_client import HA_CLIENT_KEY

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta, Refused

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.journal import Journal
from hiris.app.action.write_outcome import refused
from hiris.app.api.handlers_constructions import (
    construction_words,
    handle_confirm_construction,
    handle_get_construction,
    handle_get_constructions,
    handle_reject_construction,
    handle_restore_construction,
)
from hiris.app.chat_thread import ChatThread
from hiris.app.server import create_app
from hiris.app.startup import live_values
from tests._casa_sintetica import synthetic_inputs
from tests._contracts import assert_stessa_firma
from tests.test_construction_workshop import WorkshopHouse

# Fixture generica (annulla la valvola `HIRIS_ALLOW_NO_CSRF` che conftest.py
# mette per l'intera suite), senza niente di specifico alle impostazioni:
# stesso riuso cross-file gia' praticato da `test_agenda_api.py`.
from tests.test_settings_api import csrf_stretto  # noqa: F401


class FintoArchivio:
    def __init__(self, righe=None):
        self._righe = righe or []
        self.disdette = []

    def list(self, *, now, pending_only=False, limit=200):
        if pending_only:
            return [r for r in self._righe if r["stato"] == "in_attesa"]
        return list(self._righe)

    def count(self, *, now, pending_only=False):
        return len(self.list(now=now, pending_only=pending_only))

    def read(self, ident, *, now):
        for r in self._righe:
            if r["id"] == ident:
                return r
        return None

    def mark_cancelled(self, ident, *, now):
        self.disdette.append(ident)
        return {"id": ident, "stato": "disdetta"}


class FintaOfficina:
    def __init__(self, esito, esito_no=None):
        self.esito = esito
        self.chiamate = []
        self._esito_no = esito_no

    def reject(self, proposal_id, *, now):
        self.chiamate.append(("reject", proposal_id))
        return self._esito_no or {"id": proposal_id, "stato": "disdetta"}

    async def apply(self, proposta_id, *, actor, exchange, now, subject=None,
                    confirm_phrase=None, thread=None):
        self.chiamate.append(("apply", proposta_id, actor, exchange))
        return self.esito

    async def restore(self, costruzione_id, *, actor, exchange, now, subject=None):
        self.chiamate.append(("restore", costruzione_id, actor, exchange))
        return self.esito


def test_i_finti_combaciano_con_la_firma_vera():
    """Se `ConstructionStore`/`Workshop` cambiano firma, questo test cade
    invece di lasciare che i finti imitino un contratto che non esiste
    piu'."""
    assert_stessa_firma(ConstructionStore.list, FintoArchivio.list, nome="list")
    assert_stessa_firma(ConstructionStore.read, FintoArchivio.read, nome="read")
    assert_stessa_firma(ConstructionStore.mark_cancelled, FintoArchivio.mark_cancelled,
                        nome="mark_cancelled")
    assert_stessa_firma(Workshop.apply, FintaOfficina.apply, nome="apply")
    assert_stessa_firma(Workshop.restore, FintaOfficina.restore, nome="restore")
    assert_stessa_firma(Workshop.reject, FintaOfficina.reject, nome="reject")


#: Chi sta confermando, in queste prove. Dal 21/09/2026 (invariante I-1) la
#: porta della configurazione chiede CHI: una richiesta senza soggetto vuol dire
#: che il confine non e' passato, ed e' un rifiuto. Queste prove parlano della
#: semantica della porta -- l'origine umana, 409 contro 503 -- non del soffitto,
#: che ha il suo file: quindi dichiarano la premessa invece di subirla.
AMMINISTRATORE = {"specie": "persona", "id": "u-admin", "nome": "Paolo",
                  "utente": "paolo"}


#: La sua riga grezza di `config/auth/list` (la forma che `HAClient._user_row`
#: legge): il proprietario, amministratore per Home Assistant.
_ADMIN = {"id": "u-admin", "name": "Paolo", "is_owner": True, "is_active": True,
          "system_generated": False, "group_ids": ["system-admin"]}


def _admin_house() -> CasaFinta:
    """La casa che sa chi amministra: il client vero, e `config/auth/list`
    servito con la riga dell'amministratore."""
    return CasaFinta(synthetic_inputs(),
                     answers={"config/auth/list": lambda extra: [_ADMIN]})


def _app(archivio=None, officina=None):
    app = web.Application()
    app.update(live_values())
    if archivio is not None:
        app[CONSTRUCTIONS_KEY] = archivio
    if officina is not None:
        app[WORKSHOP_KEY] = officina
    app[HA_CLIENT_KEY] = _admin_house()
    app[ROLES_KEY] = {"quando": 0.0, "per_id": {}}
    return app


class FintaRichiesta:
    """Quanto basta di una `web.Request` per queste rotte.

    **E' anche una mappa**, come quella vera: aiohttp lascia che i middleware
    ci depositino dentro cio' che hanno stabilito (`auth_via`, `soggetto`), e
    una finta che non lo fosse costringerebbe il codice di produzione a
    difendersi da una scorciatoia dei test invece che dal mondo.
    """

    def __init__(self, app, ident=None, query=None, soggetto=None):
        self.app = app
        self.match_info = {"id": ident} if ident else {}
        self.query = query or {}
        self.method, self.path = "GET", "/api/constructions"
        # Dal 26/09/2026 ogni rotta di questa pagina e' di chi costruisce
        # (spec 2026-09-26 §3, decisione 5): la richiesta di queste prove e'
        # dell'amministratore, dichiarato qui una volta. Il cancello ha le
        # sue prove in `test_chi_costruisce.py`. Come il confine la lascia:
        # dall'ingress, col ruolo che il cancello al confine ha letto
        # (`soffitto.request_role`).
        self._deposito = {"soggetto": soggetto or AMMINISTRATORE,
                          "auth_via": "ingress", "ruolo": "amministratore"}

    def get(self, chiave, predefinito=None):
        return self._deposito.get(chiave, predefinito)

    def __getitem__(self, chiave):
        return self._deposito[chiave]

    def __setitem__(self, chiave, valore):
        self._deposito[chiave] = valore


def _corpo(risposta) -> dict:
    """Il corpo PARSATO, non la sua serializzazione.

    Questo aiutante nasce da un difetto vero, e la genealogia va scritta perche'
    non torni. Prima si asseriva `b'"b"' in risposta.body`: una SOTTOSTRINGA
    del corpo serializzato, che vede gli id dentro l'elenco e **non vede il nome
    dell'involucro che li contiene**. Provato per mutazione durante la review
    della fetta «la rinomina»: rinominato l'involucro di questa rotta da
    `constructions` a `costruzioni`, tutti e quattro i cancelli restavano verdi
    (ruff, 3001 test, npm 300/300, oxlint) mentre la pagina non sapeva piu'
    leggere la risposta.

    L'altro lato non poteva prenderlo: la finta di `tests/js/
    constructions-route.test.mjs` fornisce quella chiave DA SE', quindi nessuno
    dei due lati la pinzava. Da qui in poi la pinza questo.
    """
    import json
    return json.loads(risposta.body)


@pytest.mark.asyncio
async def test_l_elenco_di_default_da_tutto_e_col_filtro_solo_le_aperte():
    righe = [{"id": "a", "stato": "in_attesa"}, {"id": "b", "stato": "applicata"}]
    archivio = FintoArchivio(righe)
    app = _app(archivio)
    tutte = _corpo(await handle_get_constructions(FintaRichiesta(app)))
    # L'INVOLUCRO, per nome: e' il contratto che la pagina legge
    # (`static/config/constructions-route.js::dati.constructions`), e nessun
    # altro test di questa rotta lo nomina. `total`/`shown` dichiarano la
    # finestra dal 13/10/2026 (C-14).
    assert set(tutte) == {"constructions", "total", "shown"}
    assert [c["id"] for c in tutte["constructions"]] == ["a", "b"]
    aperte = _corpo(await handle_get_constructions(
        FintaRichiesta(app, query={"pending_only": "1"})))
    assert set(aperte) == {"constructions", "total", "shown"}
    assert [c["id"] for c in aperte["constructions"]] == ["a"]


@pytest.mark.asyncio
async def test_senza_archivio_si_dichiara_indisponibile_e_non_si_finge_vuoto():
    risposta = await handle_get_constructions(FintaRichiesta(_app()))
    assert risposta.status == 503


@pytest.mark.asyncio
async def test_una_costruzione_che_non_esiste_da_404():
    app = _app(FintoArchivio([]))
    risposta = await handle_get_construction(FintaRichiesta(app, ident="zzz"))
    assert risposta.status == 404


@pytest.mark.asyncio
async def test_una_costruzione_che_esiste_esce_nel_suo_involucro():
    """Il caso RIUSCITO di `GET /api/constructions/{id}`, che non era coperto.

    Aveva solo il test del 404: il ramo che risponde 200 non era esercitato da
    nessuno, e l'involucro `construction` (singolare, distinto da
    `constructions` della lista) non era nominato da nessuna parte. Misurato
    con una batteria di mutazioni a fine fetta «la rinomina»: rimesso a
    `costruzione`, tutti e quattro i cancelli restavano verdi.

    **Questa rotta non ha lettori nel frontend** (`constructions-route.js` prende
    l'elenco intero e filtra in locale), quindi non c'e' una pagina che possa
    andare rossa al posto suo: questo test e' l'unica cosa che pinza il suo
    contratto. E' anche il motivo per cui la rotta e' nella tabella del debito.
    """
    import json

    riga = {"id": "p1", "stato": "in_attesa", "gesto": "crea"}
    app = _app(FintoArchivio([riga]))
    risposta = await handle_get_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    corpo = json.loads(risposta.body)
    assert set(corpo) == {"construction"}
    assert corpo["construction"]["id"] == "p1"


@pytest.mark.asyncio
async def test_le_parole_della_costruzione_escono_uguali_dalle_due_porte():
    """C-10 (Chiusura, F2): il nome del dominio, l'articolo, la parola del
    gesto e se tocca un oggetto che c'era li manda il server, e la pagina non
    ne tiene una copia. Elenco e singola le portano uguali (fondamenta 3).

    Mutazione ESEGUITA (13/10/2026): tolto `**construction_words(row)` dalla
    singola -> rossa."""
    righe = [{"id": "m1", "stato": "applicata", "gesto": "modifica", "dominio": "scene",
              "prima": {"name": "Sera"}},
             {"id": "c1", "stato": "in_attesa", "gesto": "crea", "dominio": "automation"},
             {"id": "x1", "stato": "in_attesa", "gesto": "nuovo_gesto", "dominio": "nuovo"}]
    app = _app(FintoArchivio(righe))
    elenco = {c["id"]: c for c in _corpo(await handle_get_constructions(FintaRichiesta(app)))
              ["constructions"]}
    assert {k: elenco["m1"][k] for k in ("dominio_nome", "articolo", "gesto_leggibile",
                                          "esisteva")} == \
        {"dominio_nome": "Scena", "articolo": "la scena", "gesto_leggibile": "Modificata",
         "esisteva": True}
    assert elenco["c1"]["esisteva"] is False
    # Un dominio o un gesto che le parole non conoscono esce col suo nome.
    assert (elenco["x1"]["dominio_nome"], elenco["x1"]["gesto_leggibile"]) == \
        ("nuovo", "nuovo_gesto")
    for ident, riga in elenco.items():
        singola = _corpo(await handle_get_construction(FintaRichiesta(app, ident=ident)))
        assert {k: singola["construction"][k] for k in ("dominio_nome", "articolo",
                                                         "gesto_leggibile", "esisteva")} == \
            {k: riga[k] for k in ("dominio_nome", "articolo", "gesto_leggibile", "esisteva")}


@pytest.mark.asyncio
async def test_il_filo_di_chi_ha_proposto_non_esce_dall_elenco():
    """Fix round 1, Task 7: il filo di chi ha proposto (`thread`, che
    `_row()` porta dal Task 7) non deve attraversare questo confine -- anche
    dopo il 26/09/2026, quando la rotta e' diventata di chi costruisce: al
    suo posto esce il NOME di chi l'ha chiesta (`chiesta_da`), mai la chiave.
    Un `ChatThread` non e' nemmeno JSON: se passasse, la risposta non si
    costruirebbe."""
    riga = {"id": "p1", "stato": "in_attesa",
            "thread": ChatThread("persona:paolo", "pannello")}
    app = _app(FintoArchivio([riga]))
    corpo = _corpo(await handle_get_constructions(FintaRichiesta(app)))
    vista = corpo["constructions"][0]
    assert "thread" not in vista
    assert "subject_key" not in vista and "entry_point" not in vista
    assert vista["id"] == "p1"  # il resto della riga passa, solo il filo no


@pytest.mark.asyncio
async def test_il_filo_di_chi_ha_proposto_non_esce_dalla_singola():
    riga = {"id": "p1", "stato": "in_attesa",
            "thread": ChatThread("persona:paolo", "pannello")}
    app = _app(FintoArchivio([riga]))
    corpo = _corpo(await handle_get_construction(FintaRichiesta(app, ident="p1")))
    vista = corpo["construction"]
    assert "thread" not in vista
    assert "subject_key" not in vista and "entry_point" not in vista
    assert vista["id"] == "p1"


@pytest.mark.asyncio
async def test_confermare_dalla_pagina_dichiara_l_origine_umana():
    """La pagina E' un umano che ha cliccato: nessun turno da distinguere."""
    officina = FintaOfficina({"eseguito": True, "esecuzione_id": "e1"})
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]), officina)
    risposta = await handle_confirm_construction(
        FintaRichiesta(app, ident="p1", soggetto=AMMINISTRATORE))
    assert risposta.status == 200
    _, proposta_id, origine, turno = officina.chiamate[0]
    assert (proposta_id, origine, turno) == ("p1", "pagina", None)


@pytest.mark.asyncio
async def test_una_conferma_rifiutata_non_risponde_200():
    officina = FintaOfficina(refused("quella proposta e' gia' applicata."))
    app = _app(FintoArchivio([{"id": "p1", "stato": "applicata"}]), officina)
    risposta = await handle_confirm_construction(
        FintaRichiesta(app, ident="p1", soggetto=AMMINISTRATORE))
    assert risposta.status == 409


@pytest.mark.asyncio
async def test_un_guasto_di_rete_dell_officina_da_503_non_409():
    """Ondata finale, punto 7 (terza pulizia): `_act` appiattiva ogni
    errore dell'officina su 409 -- anche un guasto di Home Assistant, che
    dalla GET sarebbe un 503. Dal 07/10/2026 (Tappa 7, Task 2) la rotta lo
    legge dalla `causa` dell'esito, la busta del silenzio del client, e non
    da un flag dell'officina. E la `causa` esce con le chiavi del confine:
    nessun `errore` italiano, nemmeno annidato (`boundary.occurrence_out`).

    Mutazioni eseguite il 07/10/2026: in `_act` `status = 409` fisso -> rossa
    su `409 == 503`; in `occurrence_out` la `causa` passata com'e' -> rossa
    sul corpo (`'errore'` al posto di `'error'` nella causa). Ripristinate."""
    silenzio = {"errore": "Home Assistant non ha risposto: timeout",
                "causa": "silenzio", "codice": None}
    officina = FintaOfficina(refused(silenzio["errore"], silenzio))
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]), officina)
    risposta = await handle_confirm_construction(
        FintaRichiesta(app, ident="p1", soggetto=AMMINISTRATORE))
    assert risposta.status == 503
    corpo = _corpo(risposta)
    assert corpo["causa"] == {"error": silenzio["errore"], "causa": "silenzio",
                              "codice": None}
    assert b'"errore"' not in risposta.body


@pytest.mark.asyncio
async def test_ripristinare_passa_dall_officina():
    officina = FintaOfficina({"eseguito": True, "esecuzione_id": "e2"})
    app = _app(FintoArchivio([{"id": "c1", "stato": "applicata"}]), officina)
    risposta = await handle_restore_construction(
        FintaRichiesta(app, ident="c1", soggetto=AMMINISTRATORE))
    assert risposta.status == 200
    assert officina.chiamate[0][0] == "restore"


@pytest.mark.asyncio
async def test_confermare_senza_officina_da_503():
    """Il ramo 503 di `_act` non aveva un test proprio -- era coperto
    solo dal lato GET (`handle_get_constructions`/`handle_get_construction`).
    Un archivio presente ma un'officina assente non e' un caso remoto: e'
    esattamente la finestra fra la creazione dell'app e il momento in cui
    `_on_startup` monta `app["workshop"]`."""
    app = _app(FintoArchivio([{"id": "p1", "stato": "in_attesa"}]))
    risposta = await handle_confirm_construction(
        FintaRichiesta(app, ident="p1", soggetto=AMMINISTRATORE))
    assert risposta.status == 503
    assert b"officina non disponibile" in risposta.body


@pytest.mark.asyncio
async def test_rifiutare_passa_officina():
    """Il no passa dalla porta del canale (E-12, Tappa 7, Task 3, 07/10/2026):
    fino a quel giorno la rotta chiamava l'archivio da se'. Che
    `Workshop.reject` non tocchi Home Assistant lo prova
    `test_construction_workshop.py::test_il_no_non_tocca_home_assistant`.

    Mutazione ESEGUITA (07/10/2026): la rotta che torna a chiamare
    `store.mark_cancelled(ident, ...)` al posto di `workshop.reject` -- rossa
    su `officina.chiamate == [("reject", "p1")]` (lista vuota); ripristinata
    e verificata col confronto del file."""
    officina = FintaOfficina({"eseguito": True})
    archivio = FintoArchivio([{"id": "p1", "stato": "in_attesa"}])
    app = _app(archivio, officina)
    risposta = await handle_reject_construction(FintaRichiesta(app, ident="p1"))
    assert risposta.status == 200
    assert officina.chiamate == [("reject", "p1")]
    assert archivio.disdette == [], "il no non scrive l'archivio da se'"


@pytest.mark.asyncio
async def test_rifiutare_cio_che_non_e_piu_in_attesa_da_409():
    archivio = FintoArchivio([{"id": "p1", "stato": "applicata"}])
    officina = FintaOfficina({}, esito_no={"errore": "quella proposta non e' piu' in attesa"})
    risposta = await handle_reject_construction(
        FintaRichiesta(_app(archivio, officina), ident="p1"))
    assert risposta.status == 409


@pytest.mark.asyncio
async def test_rifiutare_senza_officina_da_503():
    """Senza la porta il no non si dice: 503, come le altre due POST."""
    archivio = FintoArchivio([{"id": "p1", "stato": "in_attesa"}])
    risposta = await handle_reject_construction(
        FintaRichiesta(_app(archivio, None), ident="p1"))
    assert risposta.status == 503
    assert archivio.disdette == []


# ---------------------------------------------------------------------------
# Integrazione: l'applicazione VERA (`create_app`), non le finte sopra.
#
# I test sopra chiamano gli handler direttamente con una `FintaRichiesta`
# costruita a mano: scavalcano il router di aiohttp, la popolazione di
# `match_info` e TUTTI i middleware, CSRF compreso. Le POST protette dal CSRF
# sono TRE -- conferma, ripristina, rifiuta -- e ciascuna ha qui sotto il suo
# test che passa per davvero dal router e dallo stack di middleware: senza di
# loro, una futura esenzione aggiunta per errore (o una registrazione della
# rotta prima del middleware) lascerebbe la suite verde. Stessa ragione,
# stessa forma di
# `tests/test_agenda_api.py::test_delete_senza_x_requested_with_e_403_e_non_disdice`.
# ---------------------------------------------------------------------------

#: Adesso davvero: queste proposte passano dalle rotte, che leggono
#: l'orologio, e una data ferma le farebbe nascere gia' scadute (dal
#: 06/10/2026 la scadenza vale anche per chi conferma, non solo per chi apre
#: la pagina).
ADESSO_HTTP = time.time()

#: Chi bussa, in queste prove HTTP: il proprietario, dall'ingress di Home
#: Assistant. Serve perché la porta della configurazione chiede CHI, e una
#: richiesta senza soggetto vuol dire che il confine non è passato.
_INGRESS_ADMIN = {"X-Ingress-Path": "/api/hassio_ingress/abc/",
                  "X-Remote-User-Id": "u-admin"}


@pytest_asyncio.fixture
async def client(aiohttp_client, tmp_path):
    app = create_app()
    app[CONSTRUCTIONS_KEY] = ConstructionStore(
        os.path.join(str(tmp_path), "costruzioni_http.db"))
    app[JOURNAL_KEY] = Journal(os.path.join(str(tmp_path), "azioni_http.db"))
    ha = WorkshopHouse()
    app[WORKSHOP_KEY] = Workshop(ha.client, app[CONSTRUCTIONS_KEY], app[JOURNAL_KEY])
    # Solo per i test: leggere cosa e' stato scritto DAVVERO su Home
    # Assistant, senza toccare l'attributo privato dell'officina.
    app["_fake_ha"] = ha
    # Dal 21/09/2026 la porta della configurazione chiede CHI (invariante I-1):
    # queste prove parlano del CSRF e dei codici di stato, non del soffitto,
    # quindi dichiarano la premessa -- un amministratore, dall'ingress -- invece
    # di subirla.
    app[HA_CLIENT_KEY] = _admin_house()
    app[INGRESS_CIDRS_KEY] = ["0.0.0.0/0"]
    app.on_startup.clear()
    app.on_cleanup.clear()
    c = await aiohttp_client(app)
    yield c
    app[CONSTRUCTIONS_KEY].close()
    app[JOURNAL_KEY].close()


@pytest.mark.asyncio
async def test_conferma_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_csrf",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        stakes=None, now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/confirm", headers=_INGRESS_ADMIN)
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    # La meta' che conta: un 403 non deve aver toccato ne' l'archivio ne'
    # Home Assistant.
    assert archivio.read(ident, now=ADESSO_HTTP)["stato"] == "in_attesa"
    assert client.app["_fake_ha"].salvate == []


@pytest.mark.asyncio
async def test_conferma_con_x_requested_with_applica_anche_a_csrf_stretto(
    client, csrf_stretto
):
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_csrf_ok",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        stakes=None, now=ADESSO_HTTP)["id"]

    risposta = await client.post(
        f"/api/constructions/{ident}/confirm",
        headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.read(ident, now=ADESSO_HTTP)["stato"] == "applicata"
    assert client.app["_fake_ha"].salvate


@pytest.mark.asyncio
async def test_ripristina_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="modifica", domain="automation", key="tapparelle_rip",
        actor="chat", exchange="turno-1", phrase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        preview="anteprima", stakes=None, now=ADESSO_HTTP)["id"]
    archivio.mark_applied(ident, now=ADESSO_HTTP, execution_id="e-test")

    risposta = await client.post(f"/api/constructions/{ident}/restore", headers=_INGRESS_ADMIN)
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    assert client.app["_fake_ha"].salvate == []
    # Nessuna nuova proposta di ripristino deve essere nata: quella originale
    # resta l'unica riga dell'archivio.
    assert len(archivio.list(now=ADESSO_HTTP, limit=200)) == 1


@pytest.mark.asyncio
async def test_ripristina_con_x_requested_with_ripristina_anche_a_csrf_stretto(
    client, csrf_stretto
):
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="modifica", domain="automation", key="tapparelle_rip_ok",
        actor="chat", exchange="turno-1", phrase="modifica",
        prima={"alias": "Prima"}, dopo={"alias": "Dopo"}, helper=[],
        preview="anteprima", stakes=None, now=ADESSO_HTTP)["id"]
    archivio.mark_applied(ident, now=ADESSO_HTTP, execution_id="e-test")
    # La casa e' com'era stata lasciata da quella costruzione: dal 03/10/2026
    # (S-17) il ripristino lo rilegge, e su un oggetto cambiato rifiuta.
    client.app["_fake_ha"].corpi["tapparelle_rip_ok"] = {"alias": "Dopo"}

    risposta = await client.post(
        f"/api/constructions/{ident}/restore",
        headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert client.app["_fake_ha"].salvate


@pytest.mark.asyncio
async def test_rifiuta_senza_x_requested_with_e_403_e_non_scrive_niente(client, csrf_stretto):
    """Punto 9 (residuo): `/reject` era l'unica delle tre POST senza questa
    prova end-to-end, nel file il cui stesso commento argomenta perche' serve.
    Non tocca Home Assistant (vedi `handlers_constructions.py`), quindi la meta'
    che conta qui non e' `salvate == []` ma lo stato della proposta."""
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_rifiuta_csrf",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        stakes=None, now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/reject",
                                 headers=_INGRESS_ADMIN)
    assert risposta.status == 403
    assert (await risposta.json())["error"] == "csrf_required"
    # La meta' che conta: sul 403 la proposta resta `in_attesa`.
    assert archivio.read(ident, now=ADESSO_HTTP)["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_rifiuta_con_x_requested_with_rifiuta_anche_a_csrf_stretto(client, csrf_stretto):
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_rifiuta_csrf_ok",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        stakes=None, now=ADESSO_HTTP)["id"]

    risposta = await client.post(f"/api/constructions/{ident}/reject",
                                 headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})
    assert risposta.status == 200
    assert archivio.read(ident, now=ADESSO_HTTP)["stato"] == "disdetta"


@pytest.mark.asyncio
async def test_il_motivo_esce_letto_cronaca(client):
    """D-26 (Tappa 7, Task 3, 07/10/2026): l'officina non copia piu' il
    motivo di un tentativo fallito nella riga della costruzione; la pagina
    lo legge dalla cronaca, alla voce `esecuzione_id`, e lo vede uguale.

    Mutazione ESEGUITA (07/10/2026): in `_out` il ramo che legge
    `journal.read(...)["errore"]` tolto -- rossa su `motivo` (`None`);
    ripristinata e verificata col confronto del file."""
    archivio = client.app[CONSTRUCTIONS_KEY]
    ident = archivio.propose(
        operation="crea", domain="automation", key="tapparelle_motivo",
        actor="chat", exchange="turno-1", phrase="crea", prima=None,
        dopo={"alias": "Tapparelle"}, helper=[], preview="anteprima",
        stakes=None, now=ADESSO_HTTP)["id"]
    client.app["_fake_ha"]._override["salva"] = Refused(400, "Message malformed: bad actions")

    risposta = await client.post(f"/api/constructions/{ident}/confirm",
                                 headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})
    assert risposta.status == 409
    riga = archivio.read(ident, now=ADESSO_HTTP)
    assert riga["motivo"] is None, "il motivo non si copia nella riga"
    voce = client.app[JOURNAL_KEY].read(riga["esecuzione_id"])

    letta = await client.get(f"/api/constructions/{ident}", headers=_INGRESS_ADMIN)
    assert letta.status == 200
    costruzione = (await letta.json())["construction"]
    assert costruzione["motivo"] == voce["errore"]
    assert "bad actions" in costruzione["motivo"]


def _edit_proposal(archivio, chiave):
    return archivio.propose(
        operation="modifica", domain="automation", key=chiave,
        actor="chat", exchange="turno-1", phrase="modifica",
        prima={"id": chiave, "alias": "Prima"}, dopo={"id": chiave, "alias": "Dopo"},
        helper=[], preview="anteprima", stakes=None, now=ADESSO_HTTP)["id"]


@pytest.mark.asyncio
async def test_conferma_su_un_oggetto_cambiato_e_409_e_non_scrive(client, csrf_stretto):
    """S-17 dalla pagina: il rifiuto e' un conflitto, non un guasto.

    Mutazione ESEGUITA: tolta la chiamata a `_changed_since` da `apply` --
    rossa (200 e una scrittura)."""
    ha = client.app["_fake_ha"]
    ident = _edit_proposal(client.app[CONSTRUCTIONS_KEY], "tapparelle_s17")
    ha.corpi["tapparelle_s17"] = {"id": "tapparelle_s17", "alias": "cambiata a mano"}

    risposta = await client.post(
        f"/api/constructions/{ident}/confirm",
        headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})

    assert risposta.status == 409
    assert "cambiat" in (await risposta.json())["error"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_conferma_con_la_rilettura_in_guasto_e_503_e_non_scrive(client, csrf_stretto):
    """Un guasto di rete durante la rilettura e' indisponibilita' (503), non
    un conflitto, e la sua causa e' il silenzio del client."""
    ha = client.app["_fake_ha"]
    ident = _edit_proposal(client.app[CONSTRUCTIONS_KEY], "tapparelle_s17_rete")
    ha._solleva.add("read_configuration")

    risposta = await client.post(
        f"/api/constructions/{ident}/confirm",
        headers={**_INGRESS_ADMIN, "X-Requested-With": "fetch"})

    assert risposta.status == 503
    assert (await risposta.json())["causa"]["causa"] == "silenzio"
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_una_proposta_a_mano_guasta_non_fa_cadere_l_elenco(tmp_path):
    """C-48 (Tappa 8, T3): con una riga storta in `proposte`, `proposals()`
    faceva cadere l'intera rotta, che fonde le due code: la pagina perdeva
    anche le costruzioni. Ora la riga guasta si salta, e le altre arrivano.

    Mutazione ESEGUITA: `json.loads(r[6])` rimesso in `proposals` -- la rotta
    solleva `JSONDecodeError`, cioe' un 500."""
    from hiris.app.mind.store import ObservationsStore

    app = _app(FintoArchivio([{"id": "a", "stato": "in_attesa", "creata_ts": 3}]))
    osservazioni = ObservationsStore(str(tmp_path / "oss.db"))
    buona = osservazioni.add_proposal(text="t", perche="p", fingerprint="f1", prova={},
                                      stakes=None, now_ts=5.0)
    rotta = osservazioni.add_proposal(text="t", perche="p", fingerprint="f2", prova={},
                                      stakes=None, now_ts=4.0)
    osservazioni._conn.execute("UPDATE proposte SET prova_json = '{' WHERE id = ?", (rotta,))
    osservazioni._conn.commit()
    app[OBSERVATIONS_KEY] = osservazioni
    try:
        risposta = await handle_get_constructions(FintaRichiesta(app))
        assert risposta.status == 200
        assert {c["id"] for c in _corpo(risposta)["constructions"]} == {buona, "a"}
    finally:
        osservazioni.close()


@pytest.mark.asyncio
async def test_ogni_riga_dice_se_e_sospesa_con_la_regola_della_sua_coda(tmp_path):
    """C-12 (Tappa 4, Task 5): «In attesa» o «Storico» lo decide il server.

    Le costruzioni aspettano finche' stanno in `states.SUSPENDED` -- `in_corso`
    compreso: rivendicata non vuol dire decisa --, le proposte a mano finche'
    sono `states.PENDING`. La pagina legge `sospesa` e non sa piu' quali
    parole lo dicano (`tests/js/constructions-route.test.mjs`). Anche la
    singola lo porta: la stessa costruzione ha la stessa forma dalle due porte.

    Mutazioni eseguite: `_construction_suspended` che guarda il solo
    `in_attesa` -> rossa su `in_corso`; le proposte a mano sempre `False` ->
    rossa su quella in attesa."""
    import json

    from hiris.app.mind.store import ObservationsStore

    righe = [{"id": "a", "stato": "in_attesa", "creata_ts": 3},
             {"id": "b", "stato": "in_corso", "creata_ts": 2},
             {"id": "c", "stato": "applicata", "creata_ts": 1}]
    app = _app(FintoArchivio(righe))
    osservazioni = ObservationsStore(str(tmp_path / "oss.db"))
    attesa = osservazioni.add_proposal(text="t", perche="p", fingerprint="f1", prova={},
                                       stakes=None, now_ts=5.0)
    chiusa = osservazioni.add_proposal(text="t", perche="p", fingerprint="f2", prova={},
                                       stakes=None, now_ts=4.0)
    osservazioni.close_proposal(chiusa, osservazioni.PROPOSAL_OUTCOMES[0])
    app[OBSERVATIONS_KEY] = osservazioni
    try:
        corpo = _corpo(await handle_get_constructions(FintaRichiesta(app)))
        sospese = {c["id"]: c["sospesa"] for c in corpo["constructions"]}
        assert sospese == {attesa: True, chiusa: False, "a": True, "b": True, "c": False}
        singola = json.loads((await handle_get_construction(
            FintaRichiesta(app, ident="b"))).body)
        assert singola["construction"]["sospesa"] is True
    finally:
        osservazioni.close()


@pytest.mark.asyncio
async def test_l_elenco_dichiara_la_finestra_con_total_e_shown():
    """C-14 (13/10/2026): `total` conta le due code intere, `shown` le righe
    mandate; le stesse chiavi della memoria e degli Impegni.
    Rossa prima della correzione: `KeyError: 'total'`."""
    app = _app(FintoArchivio([{"id": "c1", "stato": "in_attesa", "gesto": "crea",
                               "dominio": "automation"}]))
    corpo = _corpo(await handle_get_constructions(FintaRichiesta(app)))
    assert (corpo["total"], corpo["shown"]) == (1, 1)


@pytest.mark.parametrize("gesto", ["modifica", "cancella"])
def test_esisteva_chiede_il_prima_letto(gesto):
    """N155-3 (giro 155): un gesto che tocca cio' che c'era dice «esisteva»
    solo con il `prima` letto. Senza, la pagina direbbe «toccava un oggetto
    che c'era» di una riga che non lo sa. Mutazione del revisore, ora ESEGUITA
    (13/10/2026): `touches` senza il controllo su `prima` -- rossa."""
    assert construction_words({"dominio": "automation", "gesto": gesto,
                               "prima": None})["esisteva"] is False
    assert construction_words({"dominio": "automation", "gesto": gesto,
                               "prima": {"alias": "x"}})["esisteva"] is True
