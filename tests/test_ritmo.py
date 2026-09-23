"""Il freno di RITMO sulle azioni (reperto B-3, 22/09/2026).

**Non è una difesa contro un attacco: è contro un incidente.** Il seme dello
sprint lo dice per esteso — il modo più probabile in cui un agente domestico fa
danno non è l'attacco, è il **circolo**. Una tapparella riaperta cento volte
rompe un motore, e HIRIS ha schedulatore e promesse, cioè percorsi che agiscono
**senza nessuno davanti allo schermo**.

**Il permesso non si tocca** (decisione del proprietario del 21/09: una lista di
servizi castrerebbe HIRIS e non seguirebbe le versioni di Home Assistant). Il
ritmo è un'altra cosa: non limita **cosa** HIRIS può fare, limita **quante volte
di fila** sulla stessa cosa.

**È una sospensione, non un errore**, e si dichiara: un rifiuto muto insegna che
il prodotto è rotto; un rifiuto che dice «mi sono fermato, ecco quante volte, è
un circolo» insegna dov'è il difetto.

## La soglia è PROVVISORIA, e lo dice

Il registro chiede una soglia **misurata sulla cronaca**, non inventata: ci sono
90 giorni di storia vera. Quella misura il 22/09 non era ottenibile — nessuna
rotta HTTP espone la cronaca — quindi il numero di oggi è scelto **generoso di
proposito**: prende i circoli e non può prendere un uso legittimo. Si stringerà
quando la fetta della misura avrà guardato i 90 giorni.

Scritto qui perché una soglia provvisoria che nessuno dichiara diventa
definitiva per dimenticanza.
"""
import pytest

from hiris.app.action import rhythm


def test_le_prime_azioni_passano():
    """Il caso normale, e la contropartita che conta: un freno che frena
    troppo presto e' il prodotto rotto, non messo in sicurezza.

    Mutazione: frenare dalla prima -- rossa."""
    visto = {}

    for n in range(rhythm.THRESHOLD - 1):
        assert rhythm.too_often(
            visto, "light.cucina", now=100.0 + n) is None


def test_oltre_la_soglia_ci_si_ferma_e_si_DICE_perche():
    """**Il reperto B-3.** Cento aperture di fila rompono un motore, e nessuno
    e' li' a vederlo.

    Mutazione ESEGUITA: tornare sempre `None` -- rossa."""
    visto = {}
    for n in range(rhythm.THRESHOLD):
        rhythm.too_often(visto, "cover.tapparella", now=100.0 + n)

    fermata = rhythm.too_often(visto, "cover.tapparella", now=100.0 + rhythm.THRESHOLD)

    assert fermata is not None
    assert "cover.tapparella" in fermata
    assert str(rhythm.THRESHOLD) in fermata
    assert "circolo" in fermata.lower()


def test_il_freno_e_PER_ENTITA_non_globale():
    """Una casa che spegne dieci luci diverse in un minuto sta facendo il suo
    lavoro. Un freno globale la fermerebbe, ed e' esattamente il modo in cui
    questo intervento puo' fare danno.

    Mutazione ESEGUITA: contare tutte le azioni insieme -- rossa."""
    visto = {}

    for n in range(rhythm.THRESHOLD * 3):
        fermata = rhythm.too_often(visto, f"light.numero_{n}", now=100.0 + n)
        assert fermata is None, f"fermata su un'entita' diversa: {fermata}"


def test_e_la_FINESTRA_scorre():
    """Dieci azioni in un minuto sono un circolo; dieci in un giorno sono una
    casa che vive. Senza finestra, un'entita' usata spesso si spegnerebbe da
    sola dopo un po'.

    Mutazione ESEGUITA: contare da sempre -- rossa."""
    visto = {}
    for n in range(rhythm.THRESHOLD):
        rhythm.too_often(visto, "switch.presa", now=100.0 + n)

    dopo = 100.0 + rhythm.WINDOW_S + 1
    assert rhythm.too_often(visto, "switch.presa", now=dopo) is None


def test_la_memoria_non_cresce_per_sempre():
    """Gira su ogni azione di ogni origine: ricordare ogni entita' per sempre
    sarebbe una perdita di memoria su un percorso caldo.

    Mutazione: non potare mai -- rossa."""
    visto = {}
    for n in range(500):
        rhythm.too_often(visto, f"light.n{n}", now=100.0 + n)
    rhythm.too_often(visto, "light.ultima", now=100_000.0)

    assert len(visto) < 50, f"ricordate {len(visto)} entita'"


def test_un_bersaglio_ASSENTE_non_fa_cadere_niente():
    """Un'azione senza bersaglio esiste (un servizio di sistema), e il freno
    sta sul percorso di ogni azione: un'eccezione qui spegnerebbe l'attuatore
    invece di frenare un circolo.

    Mutazione: indicizzare senza difendersi -- rossa."""
    visto = {}
    for niente in (None, "", []):
        assert rhythm.too_often(visto, niente, now=100.0) is None


def test_la_soglia_e_dichiarata_PROVVISORIA():
    """**Il cancello di questa fetta.** Una soglia inventata troppo bassa
    romperebbe un uso legittimo, ed e' il modo in cui questo intervento puo'
    fare danno. Quella di oggi e' generosa apposta, in attesa della misura sui
    90 giorni di cronaca.

    Una soglia provvisoria che nessuno dichiara diventa definitiva per
    dimenticanza: qui la dichiarazione e' obbligatoria.

    Mutazione ESEGUITA: tolta la parola dal commento -- rossa."""
    import inspect

    sorgente = inspect.getsource(rhythm).splitlines()
    # **Solo il commento ATTACCATO alla costante.** La prima stesura guardava
    # tutto il file, poi tutto cio' che sta PRIMA della costante: in tutti e
    # due i casi la parola compariva anche nel docstring del modulo, e
    # toglierla dalla dichiarazione lasciava la prova verde. Due mutazioni per
    # accorgersene -- si guarda dove la cosa e' dichiarata, non dove e'
    # nominata.
    riga = next(n for n, r in enumerate(sorgente) if r.startswith("THRESHOLD ="))
    dichiarazione = []
    for r in reversed(sorgente[:riga]):
        if not r.startswith("#"):
            break
        dichiarazione.append(r)
    dichiarazione = chr(10).join(dichiarazione)

    assert "provvisori" in dichiarazione.lower(), (
        "la soglia non si dichiara piu' provvisoria: o e' stata misurata sulla "
        "cronaca — e allora questa prova va riscritta con la misura accanto — "
        "oppure e' diventata definitiva senza che nessuno l'abbia decisa")


@pytest.mark.parametrize("quanti", [1, 5, 20])
def test_azioni_su_entita_diverse_non_si_sommano_mai(quanti):
    """La contropartita del freno per entita', detta coi numeri: qualunque
    quantita' di entita' diverse passa.

    Mutazione: chiave condivisa -- rossa."""
    visto = {}
    for n in range(quanti):
        assert rhythm.too_often(visto, f"fan.n{n}", now=100.0) is None


# --- e il freno e' DAVVERO sul percorso di ogni azione ----------------------

def test_il_freno_sta_dove_passa_OGNI_azione():
    """**Il cancello di questa fetta.** Un freno perfetto che sta su un
    percorso solo lascia aperti gli altri -- e quelli aperti sarebbero proprio
    schedulatore e promesse, cioe' i percorsi che agiscono senza nessuno
    davanti allo schermo, che sono la ragione per cui questo freno esiste.

    `ActionActuator.execute` e' l'unico posto che vede ogni azione di ogni
    origine: chat, promessa, schedulatore, ponte.

    Mutazione ESEGUITA: tolta la chiamata da `execute` -- rossa."""
    import inspect

    from hiris.app.action.actuator import ActionActuator

    sorgente = inspect.getsource(ActionActuator.execute)

    assert "too_often" in sorgente, (
        "il freno non e' sul percorso comune: schedulatore e promesse "
        "passerebbero senza")


def test_e_frena_DOPO_la_verifica_non_prima():
    """Un comando che non sarebbe comunque partito -- servizio inesistente,
    bersaglio irrisolto -- non deve consumare il ritmo: altrimenti
    un'automazione rotta che chiama male fermerebbe quella sana che tocca la
    stessa entita'.

    Mutazione ESEGUITA: spostato il freno prima di `verdict.ok` -- rossa."""
    import inspect

    from hiris.app.action.actuator import ActionActuator

    sorgente = inspect.getsource(ActionActuator.execute)

    assert sorgente.index("verdict.ok") < sorgente.index("too_often"), (
        "il ritmo si consuma anche per comandi che vengono rifiutati comunque")
