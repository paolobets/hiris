"""I cancelli dell'attuatore (spec 2026-09-21 §7).

Le cose che si rompono **in silenzio**: un confine dichiarato in un documento e
non custodito da niente, e un turno pagato due volte. Nessuna delle due si
vedrebbe guardando la pagina.
"""
import asyncio
import datetime
import json
import pathlib

import pytest

from hiris.app import server
from hiris.app.home_space.historian import home_space_zone
from hiris.app.mind.store import ObservationsStore

OGGI = datetime.datetime.now(
    home_space_zone(server._timezone_from_home_space_store(None))).date().isoformat()

#: Le porte con cui, in questo prodotto, si tocca davvero Home Assistant.
#: Nessuna di loro puo' comparire nei moduli dell'attuatore: la scrittura
#: passa da `costruisci`, che non scrive, e dal si' del proprietario.
_PORTE_SCRITTURA = ("call_service", "save_configuration",
                         "delete_configuration")


def test_l_attuatore_non_scrive_MAI_in_casa():
    """**Il confine del 25/08/2026**: «l'attuatore non guadagna un canale di
    scrittura suo». Finche' nessuno lo custodisce e' una promessa, e le
    promesse in un documento non fermano una riga di codice.

    Si legge il sorgente e basta: e' un cancello di FORMA, e la forma e' cio'
    che si rompe quando qualcuno aggiunge una chiamata «solo per provare».

    Mutazione ESEGUITA: aggiungere `await ha_client.call_service(...)` in
    `actuator.py` -- rossa.
    """
    for nome in ("actuator.py", "actuator_turn.py"):
        sorgente = pathlib.Path("hiris/app/mind", nome).read_text(encoding="utf-8")
        for vietata in _PORTE_SCRITTURA:
            assert vietata not in sorgente, (
                f"{nome} nomina `{vietata}`: l'attuatore scriverebbe in casa "
                "senza passare dal cancello di consenso")


def test_il_cancello_guarda_le_porte_GIUSTE():
    """La contropartita del cancello qui sopra: un elenco di nomi che non
    esistono piu' passerebbe per sempre, e nessuno se ne accorgerebbe.

    Si verifica che quelle parole siano davvero le porte di scrittura di questo
    prodotto, cercandole dove vivono.

    Mutazione: scrivere nell'elenco un nome inventato -- rossa."""
    proxy = pathlib.Path("hiris/app/proxy/ha_client.py").read_text(encoding="utf-8")
    for porta in _PORTE_SCRITTURA:
        assert f"def {porta}" in proxy or f"async def {porta}" in proxy, (
            f"`{porta}` non e' (piu') una porta di `ha_client`: il cancello "
            "sta guardando una parola che non esiste")


class _FintoModello:
    def __init__(self):
        self.chiamate = 0

    async def chat(self, **kwargs):
        self.chiamate += 1
        await asyncio.sleep(0)
        return json.dumps({"esiti": [{"osservazione": 0, "gesto": "indagine",
                                      "trovato": "guardato"}]})


@pytest.mark.asyncio
async def test_due_giri_insieme_non_fanno_DUE_attuazioni(tmp_path):
    """Lo schedulatore ha un `misfire_grace_time` di mezz'ora: due giri
    possono partire insieme dopo una sosta dell'add-on. Senza guardia si
    pagherebbero due turni per la stessa analisi -- e il secondo scriverebbe
    sopra il primo, con gli stessi dati.

    Mutazione: togliere la guardia -- rossa (due chiamate al modello).
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    modello = _FintoModello()
    app = {"observations": store, "llm_router": modello, "bridge_active": False}
    try:
        store.replace_analysis(OGGI, {
            "osservazioni": [{"soggetto": "dev1", "misura": "prelievo",
                              "chiave": None, "innesco": 1, "base": 19,
                              "cosa": "x", "cosa_cambierebbe": "y"}],
            "fondamento": {"giorni": 3, "impronta": "aaa"}})

        await asyncio.gather(server.actuator_round(app), server.actuator_round(app))

        assert modello.chiamate == 1
    finally:
        store.close()


class _OfficinaCheConta:
    def __init__(self):
        self.chiamate = 0

    async def propose(self, intent, *, actor, exchange, now):
        self.chiamate += 1
        return {"proposta_id": "c1"}


@pytest.mark.asyncio
async def test_le_due_forme_non_si_MESCOLANO_negli_archivi(tmp_path):
    """**Il terzo cancello** (spec §7): si leggono insieme, si archiviano
    separate. Una frase in prosa dentro la tabella dei diff sarebbe cinque
    colonne di finti valori; un'automazione dentro l'archivio delle proposte a
    mano sarebbe un «crea» senza niente da creare.

    Qui si prova la meta' che le altre prove non toccano: **una proposta da
    fare a mano non chiama l'officina**.

    Mutazione ESEGUITA: mandare all'officina anche le non costruibili --
    rossa."""
    from hiris.app.mind.store import ObservationsStore

    store = ObservationsStore(str(tmp_path / "oss.db"))
    officina = _OfficinaCheConta()

    class _Modello:
        chiamate = 0

        async def chat(self, **kwargs):
            return json.dumps({"esiti": [
                {"osservazione": 0, "gesto": "proposta", "costruibile": False,
                 "trovato": "Sposta la lavatrice nel pomeriggio"}]})

    app = {"observations": store, "llm_router": _Modello(), "bridge_active": False,
           "workshop": officina}
    try:
        store.replace_analysis(OGGI, {
            "osservazioni": [{"soggetto": "dev1", "misura": "prelievo",
                              "chiave": None, "innesco": 1, "base": 19,
                              "cosa": "x", "cosa_cambierebbe": "y"}],
            "fondamento": {"giorni": 3, "impronta": "aaa"}})

        await server.actuator_round(app)

        assert officina.chiamate == 0, (
            "una proposta da fare a mano e' finita all'officina")
        assert len(store.proposals()) == 1
    finally:
        store.close()
