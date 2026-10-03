"""La cache del Lookup (Task B7) -- un oggetto di vita lunga separato da
`costruisci_indice()`, che resta pura.

Ogni test qui sotto esiste per una mutazione plausibile dichiarata nel brief
(`.superpowers/sdd/conoscenza/task-B7-brief.md`, sezione "Come si prova che i
test valgono"): il commento sopra ogni test dice quale.

Dal 29/09/2026 lo spazio e' uno solo, `"ricorda"`: lo spazio `"cerca"` e il
metodo `get()` che lo serviva sono usciti con la vecchia ricerca per nome
(spec «una porta sola per la casa»), e con loro le prove sui nomi di
ripiego, sul comportamento e sui due spazi che non si scambiano indici.
"""
import pytest

from hiris.app.memory.lookup_cache import LookupCache
from hiris.app.memory.resolver import Lookup


def _casa(entita=()):
    return {"aree": [], "dispositivi": [], "entita": list(entita)}


def _entita(id_, nome=None):
    return {"id": id_, "nome": nome, "alias": []}


def _spia(monkeypatch) -> list:
    """Conta le costruzioni di `costruisci_indice` dentro la cache."""
    chiamate = []
    from hiris.app.memory import lookup_cache as modulo
    originale = modulo.costruisci_indice

    def spia(casa):
        chiamate.append(1)
        return originale(casa)

    monkeypatch.setattr(modulo, "costruisci_indice", spia)
    return chiamate


# -- conta le costruzioni, non solo i risultati ----------------------------
# Mutazione: "non usare mai la cache anche quando c'e' (il guadagno sparisce
# e nessun test se ne accorge, se i test guardano solo i risultati e non
# quante volte si costruisce)". Questo test conta le costruzioni con uno spia
# su `costruisci_indice`, non sul risultato di `find()`.

def test_due_richieste_identiche_costruiscono_un_solo_indice(monkeypatch):
    chiamate = _spia(monkeypatch)
    cache = LookupCache()
    casa = _casa([_entita("light.a", "Luce A")])
    i1 = cache.get_lazy("ricorda", lambda: casa, "2026-01-01")
    i2 = cache.get_lazy("ricorda", lambda: casa, "2026-01-01")
    assert len(chiamate) == 1
    assert i1 is i2


def test_su_un_colpo_a_segno_la_casa_non_si_legge(monkeypatch):
    """Il guadagno di `get_lazy` (fix della review del Task B7): su un hit
    la casa non si legge affatto.

    Mutazione ESEGUITA: `build_home_space()` chiamata prima del confronto
    della chiave -- rossa."""
    letture = []
    cache = LookupCache()

    def leggi():
        letture.append(1)
        return _casa([_entita("light.a", "Luce A")])

    cache.get_lazy("ricorda", leggi, "2026-01-01")
    cache.get_lazy("ricorda", leggi, "2026-01-01")
    assert len(letture) == 1


# -- l'anagrafe cambia -> ricostruito ---------------------------------------
# Mutazione: "togliere aggiornata_il() dalla chiave" (o "cache eterna").

def test_cambia_aggiornata_il_ricostruisce(monkeypatch):
    chiamate = _spia(monkeypatch)
    cache = LookupCache()
    casa_v1 = _casa([_entita("light.a", "Luce A")])
    casa_v2 = _casa([_entita("light.a", "Luce A"), _entita("light.b", "Luce B")])
    i1 = cache.get_lazy("ricorda", lambda: casa_v1, "2026-01-01")
    i2 = cache.get_lazy("ricorda", lambda: casa_v2, "2026-01-02")
    assert len(chiamate) == 2
    assert i1 is not i2
    # il contenuto e' davvero quello nuovo, non solo un oggetto diverso
    assert i2.verify("entita", "light.b") is not None
    assert i1.verify("entita", "light.b") is None


# -- il ramo "anagrafe non letta" non si confonde con quello pieno ---------
# Mutazione: "condividere lo stesso indice fra il ramo anagrafe letta e non
# letta". `aggiornata_il=None` (non letta) e un valore vero non devono MAI
# dare lo stesso indice, anche passando la stessa identica `casa={}`.

def test_anagrafe_non_letta_non_si_confonde_con_anagrafe_vuota_letta_davvero():
    cache = LookupCache()
    vuota = _casa([])
    i_non_letta = cache.get_lazy("ricorda", lambda: vuota, None)
    i_letta_vuota = cache.get_lazy("ricorda", lambda: vuota, "2026-01-01")
    assert i_non_letta is not i_letta_vuota


def test_e_davvero_un_oggetto_indice():
    cache = LookupCache()
    esito = cache.get_lazy("ricorda", _casa, "t1")
    assert isinstance(esito, Lookup)


# ---------------------------------------------------------------------------
# IL CABLAGGIO -- il test che mancava, e che la fetta delle chiavi di `app`
# ha scoperto mancare
# ---------------------------------------------------------------------------
# Tutti i test qui sopra provano la cache come OGGETTO: costruita a mano,
# interrogata a mano. Nessuno provava che il prodotto gliela passi davvero --
# e il 02/09, rinominando `app["cache_indice_strumenti"]` in
# `app["tools_lookup_cache"]`, la mutazione l'ha misurato: rimettendo il nome
# vecchio nel SOLO `server.py` -- cioe' scollegando la cache, che da quel
# momento sarebbe stata `None` a ogni turno e avrebbe fatto ricostruire
# l'indice da capo ogni volta -- la suite restava **3049 passed, 1 skipped:
# tutta verde**. E' il §5 del documento di progetto della rinomina
# (`docs/design/2026-08-29-la-rinomina.md`, «la trappola che puo' rompere
# qualcosa in silenzio») avverato con nome e cognome.
#
# Questo test chiude quel buco, e lo chiude sui DUE capi con UNA misura: la
# riga vera di `_on_startup` che SCRIVE la chiave viene letta dal sorgente ed
# ESEGUITA, e l'app che ne esce viene data alla funzione vera che LEGGE la
# chiave (`create_tool_dispatcher`). Se uno dei due nomi cambia senza l'altro,
# la cache non arriva e il conto degli indici costruiti passa da uno a due.
#
# Mutazioni ESEGUITE, tutte e tre rosse (02/09):
#   1. `app["tools_lookup_cache"]` -> `app["cache_indice_strumenti"]` nel solo
#      `server.py` (il capo che SCRIVE);
#   2. `app.get("tools_lookup_cache")` -> `app.get("cache_indice_strumenti")`
#      nel solo `api/handlers_chat.py` (il capo che LEGGE);
#   3. `lookup_cache=app.get(...)` tolta del tutto da `create_tool_dispatcher`
#      -- la mutazione che dice «la cache non serve».

@pytest.mark.asyncio
async def test_la_cache_dell_indice_arriva_davvero_al_dispatcher(monkeypatch, tmp_path):
    """Un indice per DUE turni, non due.

    `ToolDispatcher` nasce a ogni turno (per progetto): il riuso fra i turni
    esiste solo se la cache che riceve e' la STESSA istanza, quella che
    l'avvio ha messo in `app`. Qui si avvia l'app davvero
    (`fotografia_porte.mounted`, dal 03/10/2026: prima si ritagliava la riga
    dal sorgente di `_on_startup` e la si eseguiva), si costruisce il
    dispatcher due volte -- due turni -- e si conta quante volte
    `costruisci_indice` gira.

    Mutazione ESEGUITA: la cache messa in `app` sotto un altro nome -- rossa
    (il dispatcher non riceve nessuna cache).
    """
    import sys
    from pathlib import Path

    from hiris.app.api.handlers_chat import create_tool_dispatcher
    from tests._casa_sintetica import synthetic_inputs

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import fotografia_porte

    async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
        turno_1 = create_tool_dispatcher(app)
        turno_2 = create_tool_dispatcher(app)

        assert turno_1._lookup_cache is not None, (
            "il dispatcher non ha ricevuto nessuna cache: l'avvio la scrive sotto "
            "un nome e `create_tool_dispatcher` ne chiede un altro"
        )
        assert turno_1._lookup_cache is turno_2._lookup_cache, (
            "due turni hanno due cache diverse: il riuso vale solo DENTRO un "
            "turno, che e' meta' del punto"
        )

        chiamate = _spia(monkeypatch)

        casa = _casa([_entita("light.a", "Luce A")])
        turno_1._lookup_cache.get_lazy("ricorda", lambda: casa, "2026-01-01")
        turno_2._lookup_cache.get_lazy("ricorda", lambda: casa, "2026-01-01")

        assert len(chiamate) == 1, (
            f"l'indice e' stato costruito {len(chiamate)} volte per due turni: "
            "la cache non sopravvive al turno"
        )
