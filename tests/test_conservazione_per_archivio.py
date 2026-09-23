"""Ogni tabella dice per quanto tiene (reperto C-6c, 23/09/2026).

La conservazione di `osservazioni.db` copriva **una tabella su otto**: solo il
grezzo (`cambi`, 22 giorni). Le altre sette non avevano nessun cancellatore —
non perché qualcuno avesse deciso «per sempre», ma perché nessuno aveva
deciso niente.

**Cosa cambia davvero, detto senza gonfiarlo.** Misurate, sei delle sette
*devono* restare per sempre e adesso lo **dichiarano**: un'analisi al giorno,
un resoconto al giorno, le proposte con la decisione che il proprietario ci ha
messo sopra, l'obiettivo e il perimetro che sono parole sue. Cancellarle
libererebbe qualche megabyte e perderebbe mesi.

La settima è diversa: `scope_attempt` sono **tentativi**, diagnostica pura,
una riga ogni giro anche fallito, e la pagina ne mostra una manciata. Quella
ha una scadenza vera.

Il valore di questa fetta non è aver aggiunto sette cancellatori: è che
adesso **non c'è più una tabella senza una decisione scritta accanto**, e una
tabella nuova che nascesse domani non potrebbe entrare senza prenderne una.
"""
import pytest

from hiris.app.mind.store import CONSERVAZIONE, ObservationsStore


@pytest.fixture()
def store(tmp_path):
    s = ObservationsStore(str(tmp_path / "oss.db"))
    try:
        yield s
    finally:
        s.close()


def test_OGNI_tabella_ha_una_decisione_scritta_accanto(store):
    """Il reperto, e la sua forma vera: non «tutto si cancella», ma «niente
    resta senza che qualcuno l'abbia deciso».

    Mutazione ESEGUITA: togliere una tabella dall'elenco -- rossa."""
    presenti = {r[0] for r in store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()}

    orfane = presenti - set(CONSERVAZIONE)
    assert not orfane, (
        f"tabelle senza una conservazione dichiarata: {sorted(orfane)}")


def test_ogni_decisione_porta_la_sua_RAGIONE():
    """Un numero senza il perche' non e' una decisione: e' un numero, e il
    primo che lo trova lo cambia.

    Mutazione ESEGUITA: lasciare una ragione vuota -- rossa."""
    for tabella, (_giorni, ragione, _cancellazione) in CONSERVAZIONE.items():
        assert ragione, f"«{tabella}» tiene per un tempo che nessuno spiega"


def test_una_scadenza_NOMINA_la_sua_tabella_in_chiaro(store):
    """La cancellazione e' una frase SQL intera e letterale, non un nome di
    colonna da cui comporla con una f-string.

    **Misurato**: con `f"DELETE FROM {tabella}"` il censimento
    (`scripts/censimento.py`) perde la copertura delle scritture su TUTTE le
    ventiquattro tabelle di questo file -- vede una scrittura solo se il nome
    della tabella sta nello stesso letterale della parola chiave -- e i reperti
    passavano da 38 a 39. Una pulizia che acceca un cancello non e' pulizia.

    Mutazione ESEGUITA: tornare alla f-string -- rossa (il censimento)."""
    for tabella, (giorni, _ragione, cancellazione) in CONSERVAZIONE.items():
        if giorni is None:
            assert cancellazione is None, (
                f"«{tabella}» e' dichiarata per sempre e ha una cancellazione")
            continue
        assert cancellazione and f"DELETE FROM {tabella} " in cancellazione, (
            f"la cancellazione di «{tabella}» non la nomina in chiaro")


def test_i_TENTATIVI_scadono(store):
    """L'unica che guadagna davvero un cancellatore: diagnostica, una riga per
    giro anche fallito, e la pagina ne mostra una manciata.

    Mutazione ESEGUITA: dichiararla per sempre -- rossa."""
    store.record_attempt(when_ts=1_000.0, outcome="non_riuscito", detail="vecchio")
    store.record_attempt(when_ts=1_000.0 + 40 * 86400, outcome="riuscito",
                         detail="recente")

    store.prune(1_000.0 + 40 * 86400)

    dettagli = [a["dettaglio"] for a in store.recent_attempts()]
    assert "recente" in dettagli
    assert "vecchio" not in dettagli


def test_l_OBIETTIVO_del_proprietario_non_scade_mai(store):
    """La contropartita, e vale piu' del reperto: sono parole sue. Una
    conservazione che se le portasse via sarebbe un danno, non un'igiene.

    Mutazione ESEGUITA: dare una scadenza all'obiettivo -- rossa."""
    store.set_objective("tenere la casa fresca d'estate", when_ts=1_000.0)

    store.prune(1_000.0 + 3650 * 86400)

    assert store.objective()["testo"] == "tenere la casa fresca d'estate"


def test_le_ANALISI_non_scadono(store):
    """Un'analisi al giorno: trecentosessantacinque righe l'anno. Cancellarle
    libererebbe qualche megabyte e perderebbe mesi di cio' che si e' capito.

    Mutazione ESEGUITA: dare una scadenza alle analisi -- rossa."""
    store.replace_analysis("2024-01-01", {"osservazioni": [{"testo": "x"}]})

    store.prune(1_000.0 + 3650 * 86400)

    assert store.analysis("2024-01-01") is not None


def test_il_GREZZO_continua_a_scadere_a_22_giorni(store):
    """Cio' che gia' funzionava e non deve smettere.

    Mutazione ESEGUITA: dichiarare `cambi` per sempre -- rossa."""
    giorni, _ragione, _cancellazione = CONSERVAZIONE["cambi"]

    assert giorni == 22
