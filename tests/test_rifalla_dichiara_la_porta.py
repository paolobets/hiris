"""«Rifalla» e la porta da cui passa (reperto C-5b del 23/09/2026, chiuso
dal Task 4.4 degli attori, D16).

Fino al 06/10/2026 «Rifalla» andava SEMPRE alla catena, e col piano acceso
lo diceva: «il piano e' acceso, ma questo giro risponde subito». Adesso e' un
turno del proponente dalla partenza unica: **col piano acceso va sul ponte**,
e la frase della porta sincrona e' uscita con il motivo che la giustificava.

Restano i due casi della catena, che non vanno confusi:

- il piano *non puo'* rispondere (token assente, tetto pieno): e' il ripiego,
  e si dichiara con le parole di vocabolario delle altre porte;
- il piano non c'e': non si dice niente.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

from hiris.app.api.handlers_proposals import handle_proposal_redo
from hiris.app.mind.store import ObservationsStore


class _Modello:
    """Il proponente che rifa' la proposta: la forma dei suoi esiti
    (`proposer_turn.ANSWER_CONTRACT`)."""

    async def chat(self, **kwargs):
        return json.dumps({"esiti": [{
            "osservazione": 0, "esito": "a_mano",
            "testo": "Sposta la lavatrice dopo le 14",
            "perche": "cosi' cade nelle ore di sole"}]})


class _Registro:
    """Il registro degli esiti: chi ha risposto si MISURA, non si deduce."""

    def __init__(self, chi):
        self._chi = chi

    def occurrence(self, nome):
        return {"tipo": "risposto"} if nome == self._chi else None


class _Coda:
    def count_exchanges_today(self):
        return 0

    def latest(self, kind, **kw):
        """Nessun rifacimento in volo (`proposal_redo.state`)."""
        return


def _piano_acceso(monkeypatch) -> None:
    """Il piano ha un token, quindi puo' rispondere.

    **Si finge dove la funzione viene USATA**, non dove e' definita:
    `steering` la importa per nome (`from .model_resolution import ...`),
    quindi fingere l'attributo di `model_resolution` non tocca il riferimento
    che `steering` ha gia' in mano. Fatto cosi', queste prove passavano da sole
    -- il token vero era nell'ambiente -- e cadevano dentro la suite, dove
    un'altra prova lo toglie: cioe' non provavano niente.
    """
    monkeypatch.setattr("hiris.app.steering.subscription_has_token",
                        lambda: True)


#: Chi preme «Rifalla»: un amministratore. Dal 26/09/2026 le proposte sono
#: di chi costruisce (spec 2026-09-26 §3, decisione 5); queste prove parlano
#: della porta del modello, non del cancello, e dichiarano la premessa.
AMMINISTRATORE = {"specie": "persona", "id": "u-admin", "nome": "Paolo"}




def _richiesta(app, ident, corpo):
    class _R:
        def __init__(self):
            self.app = app
            self.match_info = {"id": ident}
            self.query = {}
            # Come il confine la lascia: dall'ingress, col ruolo che il
            # cancello al confine ha letto (`soffitto.request_role`).
            self._valori = {"soggetto": AMMINISTRATORE, "auth_via": "ingress",
                            "ruolo": "amministratore"}
            # `aiohttp.web.BaseRequest.body_exists` (`api/boundary.json_object`).
            self.body_exists = corpo is not None

        async def json(self):
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
        prova={"base": 19}, stakes=None, now_ts=100.0)
    app = {
        "observations": store,
        "llm_router": _Modello(),
        "occurrence_registry": _Registro("claude"),
        "model_chain": ["claude"],
        "reasoning_queue": _Coda(),
        "models_config": {"ponte": {"tetto_giornaliero": 50}},
        "bridge_active": False,
        # La casa che non serve niente (Tappa 2, Task 12): «Rifalla» non legge
        # Home Assistant -- il ruolo e' quello che il confine ha lasciato nella
        # richiesta. Prima qui c'era una finta di `users()` che nessuno
        # chiamava (misurato il 03/10/2026: zero comandi); una lettura nuova
        # su questo percorso ora fa cadere la prova col suo nome.
        "ha_client": CasaFinta({}),
        "ruoli": {"quando": 0.0, "per_id": {}},
    }
    try:
        yield app, store, ident
    finally:
        store.close()


async def _rifai(app, ident):
    risposta = await handle_proposal_redo(
        _richiesta(app, ident, {"richiesta": "troppo presto, dopo le 14"}))
    return risposta, json.loads(risposta.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_col_piano_ACCESO_il_giro_va_sul_PONTE_e_non_preleva(
        casa, monkeypatch):
    """**Il reperto, chiuso.** Col piano acceso il giro non passa piu' dalla
    catena a consumo: si accoda al ponte, e la rotta risponde 202 senza aver
    chiamato nessun modello.

    Mutazione ESEGUITA (06/10/2026): `redo` che ignora la strada e va sempre
    alla catena -- rossa (503: sul ponte la partenza unica non da' un runner
    della catena, e il giro non si accoda)."""
    app, store, ident = casa
    app["bridge_active"] = True
    _piano_acceso(monkeypatch)
    accodati = []

    class _CodaVera(_Coda):
        def enqueue(self, kind, wake, context, deadline_ts, **kw):
            accodati.append((kind, wake))
            return "job-1"

    app["reasoning_queue"] = _CodaVera()

    risposta, corpo = await _rifai(app, ident)

    assert risposta.status == 202
    assert accodati and accodati[0][1]["proposta"] == ident
    assert "nota" not in corpo
    assert store.proposals()[0]["giri"] == [], "sul ponte il giro arriva dopo"


@pytest.mark.asyncio
async def test_col_piano_che_NON_PUO_rispondere_si_usano_le_parole_del_ripiego(
        casa, monkeypatch):
    """Il caso gia' noto: tetto pieno. Qui la frase giusta e' quella delle
    altre porte, con le sue tre parole di vocabolario.

    Mutazione ESEGUITA: usare la frase della porta sincrona anche qui --
    rossa."""
    app, _store, ident = casa
    app["bridge_active"] = True
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    _piano_acceso(monkeypatch)

    _risposta, corpo = await _rifai(app, ident)

    assert "tetto" in corpo["nota"], "non dice cosa e' successo al piano"
    assert "Claude API" in corpo["nota"]


@pytest.mark.asyncio
async def test_senza_piano_NON_si_dice_niente(casa):
    """La contropartita, e vale quanto il reperto: chi non ha mai avuto il
    piano non perde niente, e annunciarglielo a ogni giro direbbe che sta
    perdendo qualcosa che non ha.

    Mutazione ESEGUITA: scrivere la nota sempre -- rossa."""
    app, _store, ident = casa

    risposta, corpo = await _rifai(app, ident)

    assert risposta.status == 200
    assert "nota" not in corpo


@pytest.mark.asyncio
async def test_col_ripiego_la_proposta_si_riscrive_comunque(casa, monkeypatch):
    """La dichiarazione non e' un rifiuto: il giro si fa, la proposta si
    riscrive.

    Mutazione ESEGUITA: rifiutare col ripiego -- rossa."""
    app, store, ident = casa
    app["bridge_active"] = True
    app["models_config"] = {"ponte": {"tetto_giornaliero": 0}}
    _piano_acceso(monkeypatch)

    _risposta, _corpo = await _rifai(app, ident)

    assert store.proposals()[0]["testo"] == "Sposta la lavatrice dopo le 14"
