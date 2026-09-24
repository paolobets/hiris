"""Le rotte delle PROPOSTE da fare a mano (spec 2026-09-21 §3).

**Un posto solo dove si decide**: la pagina «Proposte» le legge insieme a
quelle costruibili, con l'etichetta di chi le applica. Le rotte che chiudono
sono due -- rifiuta e «fatta fuori da HA» -- e una terza le rifa'.

`crea` non c'e', e non e' una dimenticanza: qui non c'e' niente da scrivere in
Home Assistant. Quella strada e' l'officina, e ha gia' le sue.
"""
import json

import pytest

from hiris.app.api.handlers_proposals import (
    handle_proposal_done,
    handle_proposal_redo,
    handle_proposal_reject,
)
from hiris.app.mind.store import ObservationsStore


def _richiesta(app, match=None, corpo=None):
    class _R:
        def __init__(self):
            self.app = app
            self.match_info = match or {}
            self.query = {}

        async def json(self):
            if corpo is None:
                raise ValueError("nessun corpo")
            return corpo
        def get(self, chiave, default=None):
            """Una `Request` vera e' una mappa: `request.get("soggetto")` e'
            come il confine passa CHI sta chiamando (sprint sicurezza, A-1).
            La finta lo deve sapere fare, o imita un contratto che non
            esiste."""
            return getattr(self, "_valori", {}).get(chiave, default)
    return _R()


@pytest.fixture()
def casa(tmp_path):
    store = ObservationsStore(str(tmp_path / "oss.db"))
    ident = store.add_proposal(
        text="Sposta la lavatrice nel primo pomeriggio",
        perche="il prelievo si concentra la mattina",
        fingerprint="dev1|prelievo|None|1",
        prova={"base": 19}, chi_applica="tu", now_ts=100.0)
    try:
        yield {"observations": store}, store, ident
    finally:
        store.close()


@pytest.mark.asyncio
async def test_RIFIUTARE_chiude_la_proposta(casa):
    """Mutazione: non scrivere lo stato -- rossa (la proposta resterebbe in
    coda per sempre, e il pallino con lei)."""
    app, store, ident = casa

    r = await handle_proposal_reject(_richiesta(app, {"id": ident}))

    assert r.status == 200
    assert store.proposals()[0]["stato"] == "rifiutata"


@pytest.mark.asyncio
async def test_FATTA_FUORI_chiude_come_applicata_e_dichiara_chi_l_ha_fatta(casa):
    """Il terzo esito, e non e' una sfumatura: per il verificatore «l'ho fatto
    io» e «lo hai fatto tu» sono due prove diverse.

    Mutazione: trattarlo come un rifiuto -- rossa."""
    app, store, ident = casa

    r = await handle_proposal_done(
        _richiesta(app, {"id": ident}, {"nota": "spostata a mano"}))

    assert r.status == 200
    riga = store.proposals()[0]
    assert riga["stato"] == "fatta_fuori"
    assert riga["esito_nota"] == "spostata a mano"


@pytest.mark.asyncio
async def test_una_proposta_GIA_CHIUSA_torna_409_non_200(casa):
    """«Non esiste» e «esiste ma non e' piu' in attesa» sono due cose diverse,
    e la pagina deve poterle distinguere senza leggere il testo dell'errore.

    Mutazione: tornare 200 -- rossa."""
    app, _store, ident = casa
    await handle_proposal_reject(_richiesta(app, {"id": ident}))

    r = await handle_proposal_reject(_richiesta(app, {"id": ident}))

    assert r.status == 409


@pytest.mark.asyncio
async def test_un_id_che_NON_ESISTE_torna_404(casa):
    """Mutazione: 409 anche qui -- rossa."""
    app, _store, _ident = casa

    r = await handle_proposal_reject(_richiesta(app, {"id": "mai-visto"}))

    assert r.status == 404


@pytest.mark.asyncio
async def test_RIFALLA_senza_richiesta_e_400(casa):
    """«Rifalla» apre un testo: senza quel testo il turno rifarebbe la stessa
    cosa, e sarebbe un giro pagato per niente.

    Mutazione: accettare un corpo vuoto -- rossa."""
    app, _store, ident = casa

    r = await handle_proposal_redo(_richiesta(app, {"id": ident}, {"richiesta": "  "}))

    assert r.status == 400


@pytest.mark.asyncio
async def test_RIFALLA_accoda_il_giro_e_riscrive_il_testo(casa, monkeypatch):
    """Il giro si ripete **con le tue richieste davanti**, e il filo resta
    attaccato alla proposta: al secondo giro il modello vede cosa e' stato
    scartato.

    Mutazione: non passare il filo al modello -- rossa (la domanda non porta
    la forma scartata)."""
    app, store, ident = casa
    domande = []

    class _Modello:
        async def chat(self, **kwargs):
            domande.append(kwargs.get("user_message") or "")
            return json.dumps({"testo": "Sposta la lavatrice dopo le 14",
                               "perche": "cosi' cade nelle ore di sole"})

    app["llm_router"] = _Modello()

    r = await handle_proposal_redo(
        _richiesta(app, {"id": ident}, {"richiesta": "troppo presto, dopo le 14"}))

    assert r.status == 200
    riga = store.proposals()[0]
    assert riga["testo"] == "Sposta la lavatrice dopo le 14"
    assert riga["stato"] == "attesa", "un giro non chiude niente"
    assert [g["richiesta"] for g in riga["giri"]] == ["troppo presto, dopo le 14"]
    assert "troppo presto" in domande[0], "la tua richiesta non e' arrivata al modello"
    assert "Sposta la lavatrice nel primo pomeriggio" in domande[0], (
        "la forma scartata non e' arrivata al modello: al giro dopo potrebbe "
        "riproporla")


@pytest.mark.asyncio
async def test_senza_modello_RIFALLA_lo_dice_e_non_tocca_la_proposta(casa):
    """L'add-on puo' essere partito a meta'. Una proposta riscritta a meta'
    sarebbe peggio di una non riscritta.

    Mutazione: scrivere il giro prima di avere la risposta -- rossa."""
    app, store, ident = casa

    r = await handle_proposal_redo(
        _richiesta(app, {"id": ident}, {"richiesta": "dopo le 14"}))

    assert r.status == 503
    assert store.proposals()[0]["giri"] == []


# ---------------------------------------------------------------------------
# La lettura UNIFICATA: un posto solo dove si decide (spec §3).
# ---------------------------------------------------------------------------

class _FintaAgenda:
    def count_unread(self):
        return 0


class _FintaOfficina:
    """L'archivio delle costruzioni dal lato della pagina."""

    def __init__(self, righe=()):
        self._righe = list(righe)

    def scadi(self, now):
        return 0

    def list(self, pending_only=False, limit=200):
        if pending_only:
            return [r for r in self._righe if r["stato"] == "attesa"]
        return list(self._righe)

    def count_pending(self, now=None):
        return len([r for r in self._righe if r["stato"] == "attesa"])


@pytest.mark.asyncio
async def test_la_pagina_legge_le_DUE_code_in_un_elenco_solo(casa):
    """«Un posto solo dove si decide» e' una promessa sulla PAGINA: i due
    archivi restano due, l'elenco e' uno.

    Mutazione: tornare la sola coda dell'officina -- rossa (le proposte da
    fare a mano sarebbero invisibili)."""
    from hiris.app.api.handlers_constructions import handle_get_constructions

    app, _store, _ident = casa
    app["constructions"] = _FintaOfficina([
        {"id": "c1", "stato": "attesa", "gesto": "crea", "dominio": "automation",
         "creata_ts": 50.0}])

    r = await handle_get_constructions(_richiesta(app))

    righe = json.loads(r.text)["constructions"]
    assert len(righe) == 2
    per_chi = {x["chi_applica"] for x in righe}
    assert per_chi == {"hiris", "tu"}


@pytest.mark.asyncio
async def test_l_elenco_unito_e_ordinato_dalla_PIU_RECENTE(casa):
    """Due code messe in fila senza riordinare darebbero un elenco in cui
    l'ordine dipende da quale archivio si legge per primo -- cioe' da un
    dettaglio di implementazione.

    Mutazione: concatenare senza ordinare -- rossa."""
    from hiris.app.api.handlers_constructions import handle_get_constructions

    app, _store, _ident = casa
    app["constructions"] = _FintaOfficina([
        {"id": "c1", "stato": "attesa", "gesto": "crea", "creata_ts": 999.0}])

    r = await handle_get_constructions(_richiesta(app))

    righe = json.loads(r.text)["constructions"]
    assert next(x["id"] for x in righe) == "c1", "la piu' recente non e' in cima"


@pytest.mark.asyncio
async def test_il_PALLINO_somma_le_due_code(casa):
    """Un pallino che contasse una coda sola direbbe un numero piu' piccolo di
    quello che ti aspetta, e sarebbe peggio di nessun pallino.

    Mutazione: contare solo l'officina -- rossa."""
    from hiris.app.api.handlers_pending import handle_get_pending

    app, _store, _ident = casa
    app["constructions"] = _FintaOfficina([
        {"id": "c1", "stato": "attesa", "gesto": "crea", "creata_ts": 50.0}])
    app["agenda"] = _FintaAgenda()

    r = await handle_get_pending(_richiesta(app))

    assert json.loads(r.text)["constructions_pending"] == 2


def test_le_TRE_rotte_delle_proposte_sono_registrate():
    """Un gestore che esiste e che nessuno puo' chiamare e' la fondamenta 4
    rotta: se un dato c'e' e nessuno puo' chiederlo, non esiste.

    Mutazione ESEGUITA: togliere una delle tre registrazioni -- rossa."""
    import pathlib

    sorgente = pathlib.Path("hiris/app/server.py").read_text(encoding="utf-8")
    for rotta, gestore in (
            ("/api/proposals/{id}/reject", "handle_proposal_reject"),
            ("/api/proposals/{id}/done", "handle_proposal_done"),
            ("/api/proposals/{id}/redo", "handle_proposal_redo")):
        assert f'add_post("{rotta}", {gestore})' in sorgente, (
            f"la porta {rotta} non e' registrata: il gestore esiste e nessuno "
            "puo' chiamarlo")
