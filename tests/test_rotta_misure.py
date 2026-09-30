"""La rotta delle misure, **dichiaratamente temporanea**.

**Perché esiste.** I due registri della 3.66.0 scrivono in `consumi.db`, che
vive in `/data` dentro il contenitore dell'add-on. `scripts/misure.py` vuole
quel file, e su Home Assistant non c'è un ambiente Python in cui farlo girare:
il risultato è che i registri scrivevano e **nessuno poteva leggerli**.
«Zero superficie di prodotto» era stato difeso come un pregio fino a perdere
il deliverable — una misura che nessuno può leggere è una misura che non c'è.

**Perché temporanea, e cosa deve succedere perché esca.** Serve alla fase
delle misure: qualche giorno di turni, poi i verdetti, poi le decisioni sulle
tre leve. Quando quella fase si chiude, o la rotta sparisce, o diventa una
pagina vera con un disegno suo — ma non resta una rotta di servizio
dimenticata, che è il modo in cui una superficie provvisoria diventa
permanente.

**Non è una porta aperta**: sta dietro il perimetro come tutto il resto
(`middleware_internal_auth`), quindi ci arriva chi il proprietario ha
approvato — il canale firmato o l'ingress.
"""
import json

import pytest
from aiohttp import web

from hiris.app.api.handlers_misure import handle_misure
from hiris.app.usage.store import UsageStore

ADESSO = 1_758_000_000.0


@pytest.fixture()
def app(tmp_path):
    fuori = web.Application()
    fuori["usage"] = UsageStore(str(tmp_path / "consumi.db"))
    return fuori


def _turno(archivio, *, specie="chat", now=ADESSO, giri=2):
    ident = archivio.log_turn(species=specie, provider="openrouter",
                              model="qwen", channel="catena-openai",
                              duration_ms=7000, iterations=giri,
                              tools=["search", "view"], outcome="riuscito",
                              now=now, subject={"specie": "persona",
                                                "nome": "Paolo"})
    for giro in range(1, giri + 1):
        archivio.log_payload(ident, iteration=giro, tools_chars=44876,
                             guide_chars=6200, core_chars=6518,
                             history_chars=1200,
                             results_chars=9000 * (giro - 1), now=now,
                             tools_sent=16, prefix_hash="abc123")
    return ident


class _Richiesta:
    """Il minimo che il gestore tocca: l'app e la query."""

    def __init__(self, app, query=None):
        self.app = app
        self.query = query or {}


async def _chiedi(app, **query):
    """**L'orologio lo comanda la prova**, sempre. I turni di queste prove
    sono datati a `ADESSO`, che e' una costante: senza fissare anche il
    «adesso» del lettore, la finestra si misurerebbe dall'orologio vero e le
    prove cambierebbero esito col passare dei giorni -- verdi il giorno in cui
    sono state scritte, rosse una settimana dopo."""
    query.setdefault("adesso", str(ADESSO))
    risposta = await handle_misure(_Richiesta(app, query))
    return json.loads(risposta.text)


@pytest.mark.asyncio
async def test_la_rotta_restituisce_i_DUE_registri(app):
    """**Il deliverable.** Senza questa rotta i registri scrivevano e nessuno
    poteva leggerli.

    Mutazione ESEGUITA: restituire i soli turni, senza i carichi -- rossa."""
    ident = _turno(app["usage"])

    dati = await _chiedi(app)

    assert [t["id"] for t in dati["turni"]] == [ident]
    assert dati["turni"][0]["iterations"] == 2
    assert len(dati["carichi"][ident]) == 2


@pytest.mark.asyncio
async def test_il_carico_arriva_LEGATO_al_suo_turno(app):
    """Due liste scollegate costringerebbero chi legge a rifare la giunzione,
    e la giunzione fatta due volte diverge. La specie del turno è ciò che
    distingue «l'analista spende così» da «la chat spende così»: un carico
    senza il suo turno non risponde a niente.

    Mutazione ESEGUITA: restituire i carichi come lista piatta -- rossa."""
    uno = _turno(app["usage"], specie="chat")
    due = _turno(app["usage"], specie="analista", giri=3)

    dati = await _chiedi(app)

    assert set(dati["carichi"]) == {uno, due}
    assert len(dati["carichi"][due]) == 3


@pytest.mark.asyncio
async def test_la_FINESTRA_si_puo_stringere(app):
    """Trenta giorni di turni sono tanti da mandare in una volta, e la
    domanda normale riguarda gli ultimi giorni.

    Mutazione ESEGUITA: ignorare `giorni` e restituire tutto -- rossa."""
    vecchio = _turno(app["usage"], now=ADESSO - 10 * 86400)
    recente = _turno(app["usage"], now=ADESSO)

    stretta = await _chiedi(app, giorni="3", adesso=str(ADESSO))
    larga = await _chiedi(app, giorni="30", adesso=str(ADESSO))

    identificatori = [t["id"] for t in stretta["turni"]]
    assert recente in identificatori
    assert vecchio not in identificatori
    assert vecchio in [t["id"] for t in larga["turni"]]


@pytest.mark.asyncio
async def test_senza_archivio_NON_esplode(app):
    """All'avvio, o su un'installazione che non ha ancora misurato, l'archivio
    può non esserci. Una rotta di servizio che restituisce 500 manda chi la
    usa a cercare un guasto che non c'è.

    Mutazione ESEGUITA: togliere la guardia -- rossa."""
    vuota = web.Application()

    dati = await _chiedi(vuota)

    assert dati["turni"] == []
    assert dati["carichi"] == {}


@pytest.mark.asyncio
async def test_la_risposta_dice_di_essere_TEMPORANEA(app):
    """Chi la trova fra sei mesi deve sapere che non è un'interfaccia: deve
    sapere che era per una fase, e quale.

    **Questa prova non difende il codice: difende la dichiarazione.** È la
    stessa disciplina della soglia del freno di ritmo (e della riserva di
    «Notevole adesso», finché è esistita) — impedire che «provvisorio» diventi «permanente per
    dimenticanza».

    Mutazione ESEGUITA: togliere il campo dalla risposta -- rossa."""
    _turno(app["usage"])

    dati = await _chiedi(app)

    assert "temporanea" in dati, "la risposta non si dichiara temporanea"
    assert "misur" in dati["temporanea"].lower(), (
        "la dichiarazione non dice per QUALE fase esiste")


@pytest.mark.asyncio
async def test_gli_ARGOMENTI_escono_col_nome_tool_args_e_senza_credenziali(app):
    """**Cambiata DELIBERATAMENTE il 29/09/2026** (spec «una porta sola» §7):
    la rotta porta gli argomenti degli strumenti, sotto UN nome (`tool_args`),
    e mai una credenziale. Non escono sotto i nomi vecchi.

    Mutazione ESEGUITA: non esporre `tool_args` dall'archivio -- rossa."""
    archivio = app["usage"]
    archivio.log_turn(species="chat", provider="p", model="m",
                      channel="catena-openai", duration_ms=1, iterations=1,
                      tools=["execute"], outcome="riuscito", now=ADESSO,
                      tool_args=[{"stanza": "camera",
                                  "data": {"code": "1234"}}])

    dati = await _chiedi(app)
    grezzo = json.dumps(dati, ensure_ascii=False)

    assert dati["turni"][0]["tool_args"] == [
        {"stanza": "camera", "data": {"code": "***"}}]
    assert "1234" not in grezzo
    # `"input":` e non il semplice `input`: la rotta porta anche
    # `input_tokens`, una colonna legittima.
    for vietato in ('"input":', '"arguments"', '"argomenti"'):
        assert vietato not in grezzo.lower()


def test_la_rotta_e_DIETRO_il_perimetro():
    """Non è una porta aperta. Il perimetro copre tutto ciò che non è
    esplicitamente escluso, e questa rotta non deve comparire fra le
    eccezioni.

    Mutazione ESEGUITA: aggiungerla alle rotte esenti -- rossa."""
    import inspect

    from hiris.app.api import middleware_internal_auth

    sorgente = inspect.getsource(middleware_internal_auth)

    assert "/api/misure" not in sorgente, (
        "la rotta delle misure è stata resa esente dal perimetro: i turni "
        "portano chi ha chiesto, e chi ha chiesto è un dato personale")


def test_il_codice_dichiara_QUANDO_la_rotta_esce():
    """Una superficie provvisoria senza una condizione di uscita è una
    superficie permanente che non lo sa ancora.

    Mutazione ESEGUITA: togliere la condizione dal docstring -- rossa."""
    import inspect

    from hiris.app.api import handlers_misure

    sorgente = inspect.getsource(handlers_misure)

    assert "TEMPORANEA" in sorgente, "il modulo non si dichiara temporaneo"
    for parola in ("esce", "fase"):
        assert parola in sorgente.lower(), (
            f"il modulo non dice quando «{parola}»: manca la condizione di "
            "uscita")


@pytest.mark.asyncio
async def test_la_rotta_porta_i_token_dei_giri(app):
    """La rotta non cambia (Task 9): legge `turns()` e `payloads()`, che dal
    Task 1 portano le colonne nuove -- si pinna che arrivino fino in fondo.

    Mutazione ESEGUITA: togliere TOKEN_COLUMNS dalla SELECT di payloads --
    rossa."""
    archivio = app["usage"]
    ident = archivio.log_turn(species="chat", provider="subscription",
                              model="m", channel="ponte", duration_ms=1,
                              iterations=1, tools=[], outcome="riuscito",
                              now=ADESSO, output_tokens=7,
                              list_cost_usd=0.05)
    archivio.log_payload(ident, iteration=1, tools_chars=1, guide_chars=1,
                         core_chars=1, history_chars=1, results_chars=0,
                         now=ADESSO, input_tokens=3, cache_ttl="1h")

    dati = await _chiedi(app)

    assert dati["carichi"][ident][0]["input_tokens"] == 3
    assert dati["carichi"][ident][0]["cache_ttl"] == "1h"
    assert dati["turni"][0]["output_tokens"] == 7
    assert dati["turni"][0]["list_cost_usd"] == 0.05
