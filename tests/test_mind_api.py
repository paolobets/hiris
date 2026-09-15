"""Le due rotte della pagina dell'osservatore."""

import pytest

from hiris.app.api.handlers_mind import (
    handle_watching,
)
from hiris.app.mind.store import ATTEMPTS_SHOWN, ObservationsStore
from hiris.app.mind.watcher import Watcher
from tests._contracts import assert_stessa_firma


class _FintoOsservatore:
    def watching(self):
        return [{"soggetto": "climate.camera_t", "motivo": "scalda la casa",
                 "autore": "observer", "da_quando_ts": 1787000000.0}]


class _FintoArchivioScope:
    """L'archivio dal lato della pagina dello scope: porta le decisioni,
    l'obiettivo, l'ultima riconsiderazione e il volume del grezzo.

    **Conta le finestre che le vengono chieste**: la pagina mostra il volume
    di piu' giorni, e una finta che ignori gli estremi non potrebbe vedere
    una rotta che chiede sempre lo stesso giorno.
    """

    def __init__(self, *, ultima=None):
        self.finestre = []
        self._ultima = ultima

    def scope(self):
        return {
            "climate.camera_t": {"dentro": True, "motivo": "scalda la casa",
                                 "autore": "observer", "deciso_ts": 1787000000.0},
            "sensor.uptime": {"dentro": False, "motivo": "di servizio, non dice niente"
                                                         " sulla casa",
                              "autore": "observer", "deciso_ts": 1787000001.0},
        }

    def objective(self):
        return {"testo": "tenere la casa calda e spendere poco",
                "scritto_ts": 1787000000.0}

    def last_reconsideration(self):
        return self._ultima

    def recent_attempts(self, limit=ATTEMPTS_SHOWN):
        """**Vuoto e' un esito**: nessuno ci ha ancora provato. La finta lo
        porta perche' l'archivio vero lo porta -- una finta costruita nella
        forma che il codice si aspetta, invece che in quella del fornitore,
        e' il difetto n.3 di questo progetto."""
        return []

    def readings_count(self, *, from_ts, to_ts, source=None):
        self.finestre.append((from_ts, to_ts, source))
        return int(to_ts - from_ts)      # una riga al secondo: distingue i giorni


def _decidi(archivio, *soggetti):
    """Mette nello scope i soggetti che le prove d'insieme fanno passare dal
    rubinetto. Il default e' l'entita' che usano quasi tutte."""
    for soggetto in soggetti or ("climate.bagno_1p_t_bagno_1p_t",):
        archivio.decide_scope(soggetto, inside=True,
                              reason="la prova la guarda", author="observer")


def _richiesta(app, query=None):
    class _R:
        def __init__(self):
            self.app = app
            self.query = query or {}
    return _R()


assert_stessa_firma(Watcher.watching, _FintoOsservatore.watching, nome="watching")
assert_stessa_firma(ObservationsStore.recent_attempts,
                    _FintoArchivioScope.recent_attempts, nome="recent_attempts")
for _nome in ("scope", "objective", "last_reconsideration", "readings_count"):
    assert_stessa_firma(getattr(ObservationsStore, _nome),
                        getattr(_FintoArchivioScope, _nome), nome=_nome)


def _pagina(**extra):
    """L'app con tutto cio' che la pagina dello scope legge."""
    app = {"watcher": _FintoOsservatore(), "observations": _FintoArchivioScope()}
    app.update(extra)
    return app


@pytest.mark.asyncio
async def test_osservate_dice_cosa_si_guarda_e_perche():
    r = await handle_watching(_richiesta({"watcher": _FintoOsservatore()}))
    assert r.status == 200


@pytest.mark.asyncio
async def test_osservate_porta_il_perche_e_l_autore_di_ogni_voce():
    """La pagina mostra cosa si guarda, **perche'**, e **chi l'ha deciso**: e'
    da li' che il proprietario toglie qualcosa (spec §5.1/§11). Senza l'autore
    non si distinguerebbe una scelta dell'osservatore da una dell'analista, e
    la seconda non saprebbe di essere una revisione della prima."""
    r = await handle_watching(_richiesta(_pagina()))
    voce = _corpo(r)["watching"][0]
    assert voce["motivo"] == "scalda la casa"
    assert voce["autore"] == "observer"
    assert voce["da_quando_ts"] == 1787000000.0


@pytest.mark.asyncio
async def test_la_pagina_porta_anche_cio_che_e_stato_LASCIATO_FUORI():
    """**Meta' della trasparenza sta qui.** Un elenco di sole cose guardate
    non si puo' usare per decidere: chi legge non sa se un'entita' manca
    perche' e' stata esclusa (e con quale ragione) o perche' nessuno l'ha mai
    considerata. Ed e' da questo secondo elenco che si rimette dentro una
    delle 452 escluse.

    Mutazione che la uccide: mandare solo `dentro`.
    """
    fuori = _corpo(await handle_watching(_richiesta(_pagina())))["fuori"]

    assert [v["soggetto"] for v in fuori] == ["sensor.uptime"]
    assert "di servizio" in fuori[0]["motivo"]
    assert fuori[0]["autore"] == "observer"


@pytest.mark.asyncio
async def test_la_pagina_porta_l_obiettivo_rispetto_a_cui_si_e_deciso():
    """La pagina dello scope **e'** la prova che l'obiettivo e' stato capito
    (spec §11: non sono due pagine). Mostrare le scelte senza la domanda a cui
    rispondono le renderebbe illeggibili."""
    corpo = _corpo(await handle_watching(_richiesta(_pagina())))
    assert corpo["obiettivo"]["testo"] == "tenere la casa calda e spendere poco"


@pytest.mark.asyncio
async def test_la_pagina_dice_quando_si_ricambiera_idea_e_perche_allora():
    """Non basta «riconsidero ogni 84 ore»: quel numero viene dalla memoria
    misurata di Home Assistant, e cambia se il proprietario cambia il
    recorder. La pagina porta **tutti e tre** i numeri -- quando, la finestra,
    la cadenza -- o il lettore dovrebbe crederci sulla parola."""
    ultima = {"quando_ts": 1787000000.0, "finestra_s": 604800.0, "cadenza_s": 302400.0}
    archivio = _FintoArchivioScope(ultima=ultima)

    corpo = _corpo(await handle_watching(_richiesta(_pagina(observations=archivio))))

    assert corpo["riconsiderazione"] == ultima


@pytest.mark.asyncio
async def test_mai_riconsiderato_si_DICHIARA_invece_di_sparire():
    """`null`, non una chiave assente: «non l'ho ancora fatto» e' un fatto
    che la pagina deve poter dire, ed e' vero al primo avvio di ogni casa."""
    corpo = _corpo(await handle_watching(_richiesta(_pagina())))
    assert corpo["riconsiderazione"] is None


@pytest.mark.asyncio
async def test_la_pagina_dice_QUANTO_SCRIVE_al_giorno():
    """**La contropartita onesta dello scope.** Si guarda meno, e questo e'
    quanto costa cio' che si guarda: la spec promette **-83%** (da 29.227 a
    4.951 righe al giorno) e fino all'11/09/2026 nessuna porta lo esponeva --
    la promessa non era verificabile dall'esterno.

    Ogni giorno e' una finestra sua: una rotta che chiedesse sempre lo stesso
    intervallo mostrerebbe sette volte lo stesso numero senza che nessuno se
    ne accorga.

    Mutazione che la uccide: passare gli stessi estremi a ogni giorno.
    """
    archivio = _FintoArchivioScope()

    volume = _corpo(await handle_watching(_richiesta(_pagina(observations=archivio))))["volume"]

    assert len(volume) >= 7
    assert all("giorno" in v and "righe" in v for v in volume)
    assert len({giorno for giorno, _, _ in archivio.finestre}) == len(archivio.finestre)
    assert [v["giorno"] for v in volume] == sorted(v["giorno"] for v in volume)


@pytest.mark.asyncio
async def test_senza_archivio_la_pagina_non_inventa_la_meta_che_manca():
    """L'osservatore c'e' e l'archivio no -- avvio a meta', o un guasto. Un
    obiettivo di fabbrica e un volume a zero sarebbero due affermazioni che
    nessuno ha verificato. Si dichiara la mancanza e la pagina la dice."""
    corpo = _corpo(await handle_watching(_richiesta({"watcher": _FintoOsservatore()})))

    assert corpo["watching"]
    assert corpo["obiettivo"] is None
    assert corpo["volume"] == []
    assert corpo["fuori"] == []


@pytest.mark.asyncio
async def test_senza_osservatore_la_rotta_lo_DICHIARA():
    """Un elenco vuoto direbbe «non guardo niente»; l'osservatore assente e'
    un'altra cosa, ed e' la distinzione che questo prodotto difende ovunque."""
    r = await handle_watching(_richiesta({}))
    assert r.status == 503


def _corpo(response):
    import json
    return json.loads(response.body)


# ---------------------------------------------------------------------------
