"""L'imbuto della misura: un turno vero, misurato da un capo all'altro.

`tests/test_registro_dei_turni.py` prova l'ARCHIVIO da solo — gli si passano
dei numeri e si controlla che li scriva. È necessario e non basta: stamattina
un difetto è sopravvissuto per mesi esattamente così, perché le prove del
soggetto esercitavano il `Journal` da solo e **nessuno percorreva il filo**.

Qui si percorre: si misura una chiamata finta al modello e si va a leggere cosa
è finito in `consumi.db`.
"""
import asyncio
import json

import pytest

from hiris.app.claude_runner import _misura_corrente
from hiris.app.steering import SPECIE, misura_turno
from hiris.app.usage.store import UsageStore


class FintoRunner:
    """Un runner che si comporta come i veri sul contratto della misura:
    espone `last_tool_calls` e chiama il raccoglitore della ContextVar a ogni
    giro. **Non conta i giri**: li conta la misura, guardando quante volte il
    gancio ha scattato — un contatore qui sarebbe una seconda verita' sullo
    stesso numero."""

    def __init__(self, giri: int = 2, strumenti=None, esplode: bool = False,
                 peso: int = 9000):
        self.last_tool_calls = [{"tool": n, "input": {"stanza": "camera"}}
                                for n in (strumenti or ["search", "view"])]
        self._giri = giri
        self._esplode = esplode
        self._peso = peso

    async def chat(self):
        for giro in range(1, self._giri + 1):
            # Come i runner veri: il raccoglitore si legge dalla ContextVar
            # della chiamata, non da un attributo dell'oggetto.
            raccoglitore = _misura_corrente()
            if raccoglitore is not None:
                raccoglitore(giro, {
                    "tools_chars": 44876, "guide_chars": 6200,
                    "core_chars": 6518, "history_chars": 1000,
                    # cresce a ogni giro: è il punto della misura
                    "results_chars": self._peso * (giro - 1),
                    "tools_sent": 16, "prefix_hash": "abc123"})
            await asyncio.sleep(0)
        if self._esplode:
            raise RuntimeError("il modello non ha risposto")
        return "fatto"


@pytest.fixture()
def app(tmp_path):
    return {"usage": UsageStore(str(tmp_path / "consumi.db"))}


async def _gira(app, runner, specie="chat"):
    async with misura_turno(app["usage"], runner, specie=specie,
                            canale="catena-anthropic", modello="sonnet"):
        return await runner.chat()


@pytest.mark.asyncio
async def test_il_filo_INTERO_dal_runner_alla_cronaca_dei_consumi(app):
    """**Il difetto che questa prova esiste per non avere.** L'archivio sa
    scrivere e il runner sa contare: se nessuno li lega, i due registri
    restano vuoti e nessuno se ne accorge.

    Mutazione ESEGUITA: non chiamare `log_turn` nell'imbuto -- rossa.
    Mutazione ESEGUITA: non posare `misura_carico` sul runner -- rossa."""
    runner = FintoRunner(giri=3)

    await _gira(app, runner)

    turni = app["usage"].turns()
    assert len(turni) == 1
    assert turni[0]["iterations"] == 3
    assert turni[0]["tools"] == ["search", "view"]
    assert app["usage"].payloads(turni[0]["id"]) != []


@pytest.mark.asyncio
async def test_si_vede_CRESCERE_il_carico_giro_per_giro(app):
    """La curva, non il suo punto medio. È l'intera ragione per cui il
    secondo registro è per iterazione: i risultati degli strumenti si
    accumulano nella conversazione, e nessuno ha mai visto di quanto.

    Mutazione ESEGUITA: scrivere un solo carico per turno -- rossa."""
    runner = FintoRunner(giri=4)

    await _gira(app, runner)

    carichi = app["usage"].payloads(app["usage"].turns()[0]["id"])

    assert [c["iteration"] for c in carichi] == [1, 2, 3, 4]
    assert [c["results_chars"] for c in carichi] == [0, 9000, 18000, 27000]
    assert carichi[0]["tools_chars"] == 44876


@pytest.mark.asyncio
async def test_la_DURATA_si_misura(app):
    """Zero millisecondi vuol dire «non l'ho misurata», e sarebbe indistinguibile
    da un turno istantaneo.

    Mutazione ESEGUITA: scrivere `duration_ms=0` fisso -- rossa."""
    runner = FintoRunner(giri=1)

    async def _lento():
        await asyncio.sleep(0.05)
        return await runner.chat()

    async with misura_turno(app["usage"], runner, specie="chat",
                            canale="catena-anthropic", modello="sonnet"):
        await _lento()

    assert app["usage"].turns()[0]["duration_ms"] >= 40


@pytest.mark.asyncio
async def test_un_turno_che_ESPLODE_si_registra_lo_stesso(app):
    """È il caso più interessante per la latenza: ha speso e non ha dato
    niente. E l'eccezione deve continuare a salire — la misura non ingoia i
    guasti.

    Mutazione ESEGUITA: misurare solo nel ramo riuscito -- rossa.
    Mutazione ESEGUITA: ingoiare l'eccezione -- rossa."""
    runner = FintoRunner(giri=2, esplode=True)

    with pytest.raises(RuntimeError):
        await _gira(app, runner)

    turni = app["usage"].turns()
    assert len(turni) == 1
    assert turni[0]["outcome"] == "fallito"
    assert turni[0]["iterations"] == 2


@pytest.mark.asyncio
async def test_il_gancio_si_TOGLIE_quando_il_turno_finisce(app):
    """Un gancio lasciato attaccato scriverebbe i giri del turno DOPO dentro
    la misura di quello PRIMA.

    Mutazione ESEGUITA: non chiamare `togli_misura` nel `finally` -- rossa."""
    await _gira(app, FintoRunner(giri=1))

    assert _misura_corrente() is None


@pytest.mark.asyncio
async def test_due_turni_in_PARALLELO_non_si_mescolano(app):
    """**Il difetto che la prima versione aveva, e che questo codice aveva già
    scoperto una volta.**

    Il raccoglitore era posato su `self.misura_carico`, e il runner è
    costruito UNA volta nell'app: la chat del proprietario e il giro notturno
    dell'analista si sarebbero sovrascritti il gancio a vicenda, e il carico
    di uno sarebbe finito nella misura dell'altro. `claude_runner` si era già
    dato la stessa cura per `last_tool_calls`, con una ContextVar di modulo, e
    il commento che la spiega era lì da leggere.

    Qui i due turni hanno pesi diversi apposta: se si mescolassero, i numeri
    si vedrebbero scambiati.

    Mutazione ESEGUITA: tornare a un attributo sull'oggetto -- rossa.
    Mutazione ESEGUITA: una ContextVar sola condivisa senza `reset` -- rossa."""
    lento = FintoRunner(giri=4, peso=1000)
    veloce = FintoRunner(giri=4, peso=7)

    async def _turno(runner, specie):
        async with misura_turno(app["usage"], runner,
                                specie=specie, canale="catena-anthropic", modello="x"):
            await runner.chat()

    await asyncio.gather(_turno(lento, "chat"),
                         _turno(veloce, "analista"))

    per_specie = {t["species"]: t["id"] for t in app["usage"].turns()}
    carico_chat = app["usage"].payloads(per_specie["chat"])
    carico_analista = app["usage"].payloads(per_specie["analista"])

    assert [c["results_chars"] for c in carico_chat] == [0, 1000, 2000, 3000]
    assert [c["results_chars"] for c in carico_analista] == [0, 7, 14, 21]


@pytest.mark.asyncio
async def test_un_guasto_dell_archivio_NON_fa_cadere_il_turno(app):
    """«Nessun cambio di comportamento» deve valere anche quando la misura si
    rompe: un registro che fa cadere il giro notturno dell'analista sarebbe
    peggio del buco che chiude. Stessa disciplina di `declare_downgrade`.

    Mutazione ESEGUITA: togliere il `try` attorno alla scrittura -- rossa."""
    class ArchivioRotto:
        def log_turn(self, **kw):
            raise RuntimeError("disco pieno")

    runner = FintoRunner(giri=1)
    rotta = {"usage": ArchivioRotto()}

    esito = await _gira(rotta, runner)

    assert esito == "fatto", "il turno è caduto per colpa della misura"


@pytest.mark.asyncio
async def test_gli_ARGOMENTI_non_arrivano_mai_all_archivio(app):
    """Il finto runner porta `{"stanza": "camera"}` dentro `last_tool_calls`,
    come fanno i veri. Nell'archivio deve finire solo il nome.

    Mutazione ESEGUITA: passare `last_tool_calls` intero a `log_turn` --
    rossa."""
    runner = FintoRunner(giri=1, strumenti=["view"])

    await _gira(app, runner)

    scritto = json.dumps(app["usage"].turns()[0]["tools"], ensure_ascii=False)

    assert "camera" not in scritto, scritto
    assert "stanza" not in scritto, scritto


@pytest.mark.asyncio
async def test_le_SEI_specie_passano_tutte(app):
    """Il vocabolario è quello del registro dei ripieghi, e l'imbuto non deve
    restringerlo: se una specie non passasse, quel giro sparirebbe dalla
    misura senza che nessuno lo noti.

    Mutazione ESEGUITA: accettare solo «chat» -- rossa."""
    for specie in sorted(SPECIE):
        await _gira(app, FintoRunner(giri=1), specie=specie)

    assert {t["species"] for t in app["usage"].turns()} == set(SPECIE)


def test_i_DUE_runner_veri_espongono_il_contratto():
    """Un kwarg nuovo accettato da un runner e non dall'altro è il difetto che
    questo progetto ha già pagato (`ClaudeRunner`/`OpenAICompatRunner`). Qui
    il contratto sono tre attributi.

    Mutazione ESEGUITA: togliere `misura_carico` da uno dei due -- rossa."""
    import inspect

    from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
    from hiris.app.claude_runner import ClaudeRunner

    for classe in (ClaudeRunner, OpenAICompatRunner):
        assert "_misura_corrente()" in inspect.getsource(classe.chat), (
            f"{classe.__name__} non pesa il carico: quel percorso non "
            "scriverebbe nessuna riga di `payload`")


@pytest.mark.asyncio
async def test_una_specie_INVENTATA_viene_rifiutata(app):
    """La regola sta dove sta il vocabolario. `agent_type="observer"` è il
    nome che il runner usa per scegliere il modello, e se entrasse qui il
    registro avrebbe due nomi per lo stesso attore — proprio sulla domanda
    per cui esiste.

    Mutazione ESEGUITA: togliere il controllo dall'imbuto -- rossa."""
    with pytest.raises(ValueError, match="observer"):
        async with misura_turno(app["usage"], FintoRunner(),
                                specie="observer", canale="catena-anthropic",
                                modello="x"):
            pass

    assert app["usage"].turns() == []
