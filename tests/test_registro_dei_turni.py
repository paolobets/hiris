"""I due registri della misura: il turno, e di cosa è fatto il suo carico.

**Perché esistono, misurato sulla casa vera il 23/09/2026.** Una domanda come
«quali luci sono accese in casa adesso?» ha impiegato **69 secondi** per
produrre 35 token di risposta; «riassumimi cosa non va in casa» ne ha impiegati
**132**. Non è la generazione: è che ogni chiamata a uno strumento è un giro
completo al modello, e ogni giro **rispedisce tutto da capo** — le sedici
definizioni (~13.000 token), la mappa della casa (~2.000), la guida, la
cronologia, e i risultati degli strumenti accumulati fino a lì. Il tetto è
`MAX_TOOL_ITERATIONS = 50`.

Quindi ogni leva sui token è anche una leva sulla **latenza**, moltiplicata per
il numero di giri. E nessuno sa quanti giri faccia un turno: il registro
dell'add-on dice solo che la richiesta HTTP è durata 69 secondi.

**Il primo registro non si costruisce: si smette di buttare.** `last_tool_calls`
è già popolato a ogni giro da tutti e due i runner, e oggi si legge soltanto
quando si esauriscono le 50 iterazioni, per una riga di avviso.

**Il secondo si misura per ITERAZIONE, non per turno**, perché è lì che la
moltiplicazione avviene — e perché i risultati degli strumenti crescono a ogni
giro e nessuno ha mai visto di quanto.

**Nessuno dei due cambia comportamento.** Sono due letture.
"""
import json

import pytest

from hiris.app.usage.store import UsageStore

ADESSO = 1_758_000_000.0


@pytest.fixture()
def consumi(tmp_path):
    archivio = UsageStore(str(tmp_path / "consumi.db"))
    try:
        yield archivio
    finally:
        archivio.close()


def test_un_turno_registra_QUANTI_giri_ha_fatto(consumi):
    """**Il numero che spiega i 69 secondi**, e che oggi non esiste da nessuna
    parte.

    Mutazione ESEGUITA: non scrivere `iterations` -- rossa."""
    consumi.log_turn(species="chat", provider="openrouter", model="qwen",
                     channel="catena-anthropic",
                     duration_ms=69_100, iterations=7, tools=["search", "view"],
                     outcome="riuscito", now=ADESSO)

    riga = consumi.turns()[0]

    assert riga["iterations"] == 7
    assert riga["duration_ms"] == 69_100


def test_gli_strumenti_si_registrano_IN_ORDINE(consumi):
    """L'ordine è il dato: «`search` poi `view` poi `search`» racconta una
    ricerca che non ha trovato al primo colpo, e tre nomi in un insieme no.

    Mutazione ESEGUITA: salvare un insieme invece di una sequenza -- rossa."""
    consumi.log_turn(species="chat", provider="ponte", model="sonnet", channel="catena-anthropic",
                     duration_ms=1000, iterations=3,
                     tools=["search", "view", "search"], outcome="riuscito",
                     now=ADESSO)

    assert consumi.turns()[0]["tools"] == ["search", "view", "search"]


def test_gli_ARGOMENTI_degli_strumenti_non_si_registrano(consumi):
    """Un `view` porta il nome di una stanza, un `execute` un valore
    impostato: sono dati personali, e questo archivio finisce nei backup di
    Home Assistant, che non sono cifrati se non ci metti una password.

    La stessa scelta che `claude_runner` fa già per la riga di avviso delle
    iterazioni esaurite: **solo i nomi, mai `input`**.

    Mutazione ESEGUITA: accettare e salvare anche gli argomenti -- rossa."""
    import inspect

    firma = inspect.signature(UsageStore.log_turn).parameters

    assert "tools" in firma
    for vietato in ("arguments", "argomenti", "input", "inputs"):
        assert vietato not in firma, (
            f"«{vietato}» farebbe entrare dati personali in consumi.db")


def test_il_carico_si_misura_per_ITERAZIONE(consumi):
    """Per turno direbbe la media e nasconderebbe la curva. La domanda vera è
    **come cresce** il carico di giro in giro — e i risultati degli strumenti
    si accumulano.

    Mutazione ESEGUITA: chiave primaria sul solo `turn_id` -- rossa (la
    seconda iterazione sovrascriverebbe la prima)."""
    ident = consumi.log_turn(species="osservatore", provider="ponte",
                             model="haiku",
        channel="catena-anthropic", duration_ms=5000, iterations=2,
                             tools=["search"], outcome="riuscito", now=ADESSO)

    consumi.log_payload(ident, iteration=1, tools_chars=44876, guide_chars=6200,
                        core_chars=6518, history_chars=1200, results_chars=0,
                        now=ADESSO)
    consumi.log_payload(ident, iteration=2, tools_chars=44876, guide_chars=6200,
                        core_chars=6518, history_chars=1200, results_chars=9400,
                        now=ADESSO)

    righe = consumi.payloads(ident)

    assert [r["iteration"] for r in righe] == [1, 2]
    assert righe[0]["results_chars"] == 0
    assert righe[1]["results_chars"] == 9400


def test_il_carico_si_LEGA_al_suo_turno(consumi):
    """Un carico senza il suo turno non risponde a nessuna domanda: la specie
    del turno è quello che distingue «l'analista spende così» da «la chat
    spende così».

    Mutazione ESEGUITA: non restituire `turn_id` da `log_turn` -- rossa."""
    uno = consumi.log_turn(species="chat", provider="ponte", model="sonnet",
                           channel="catena-anthropic",
                           duration_ms=1, iterations=1, tools=[],
                           outcome="riuscito", now=ADESSO)
    due = consumi.log_turn(species="analista", provider="ponte", model="haiku",
                           channel="catena-anthropic",
                           duration_ms=1, iterations=1, tools=[],
                           outcome="riuscito", now=ADESSO)

    assert uno != due, "due turni diversi devono avere identificatori diversi"
    consumi.log_payload(uno, iteration=1, tools_chars=1, guide_chars=1,
                        core_chars=1, history_chars=1, results_chars=1,
                        now=ADESSO)

    assert len(consumi.payloads(uno)) == 1
    assert consumi.payloads(due) == []


def test_la_SPECIE_e_quella_che_il_prodotto_gia_nomina(consumi):
    """**Sei specie, non quattro.** Al runner arriva `agent_type`, che ha
    quattro valori e serve a scegliere il MODELLO; `observer.py` e
    `recipe_turn.py` passano tutti e due `"observer"`, quindi osservatore e
    ricette sarebbero indistinguibili proprio nel punto in cui misuriamo.

    Il vocabolario giusto esiste già: è quello che il registro dei ripieghi
    usa da stamattina. Si riusa, non se ne conia un secondo.

    **Dove vive la regola**: in `steering`, con l'elenco — non qui. Un
    archivio che conoscesse il vocabolario sarebbe il secondo posto in cui la
    stessa regola vive, e `usage/` è un ambito convertito che non deve
    dipendere da un nome di dominio italiano. Il rifiuto di una specie
    inventata si prova in `tests/test_misura_del_turno.py`, sull'imbuto.

    Mutazione ESEGUITA: togliere una specie dal vocabolario -- rossa."""
    from hiris.app.steering import SPECIE

    assert SPECIE == frozenset({"analista", "attuatore", "chat", "osservatore",
                                "promessa", "ricette"})
    for specie in SPECIE:
        consumi.log_turn(species=specie, provider="ponte", model="x", channel="catena-anthropic",
                         duration_ms=1, iterations=1, tools=[],
                         outcome="riuscito", now=ADESSO)

    assert {r["species"] for r in consumi.turns()} == set(SPECIE)


def test_i_due_registri_SCADONO_a_trenta_giorni(consumi):
    """**Un registro di misura che cresce per sempre è il difetto che C-6 ha
    appena chiuso**: ogni archivio dice per quanto tiene. Questo tiene trenta
    giorni, ed è il solo di `consumi.db` che scade — gli altri sono secchielli
    al giorno, minuscoli, e restano per sempre con la loro ragione.

    Mutazione ESEGUITA: togliere la cancellazione dal `log_turn` -- rossa.
    Mutazione ESEGUITA: cancellare anche le righe dentro i trenta giorni --
    rossa."""
    from hiris.app.usage.store import TURNS_RETENTION_S

    assert TURNS_RETENTION_S == 30 * 86400

    vecchio = consumi.log_turn(species="chat", provider="ponte", model="x",
                               channel="catena-anthropic",
                               duration_ms=1, iterations=1, tools=[],
                               outcome="riuscito", now=ADESSO)
    consumi.log_payload(vecchio, iteration=1, tools_chars=1, guide_chars=1,
                        core_chars=1, history_chars=1, results_chars=1,
                        now=ADESSO)

    # **Un turno DENTRO la finestra, scritto prima della potatura.** Senza di
    # lui la prova non guarda il confine: la riga che scatena la cancellazione
    # viene inserita DOPO, quindi sopravvive anche a un limite sbagliato che
    # cancella tutto. Trovato da una mutazione, non leggendo.
    dentro = consumi.log_turn(species="chat", provider="ponte", model="x",
                              channel="catena-anthropic",
                              duration_ms=1, iterations=1, tools=[],
                              outcome="riuscito", now=ADESSO + 86400)

    dopo = ADESSO + TURNS_RETENTION_S + 1
    recente = consumi.log_turn(species="chat", provider="ponte", model="x",
                               channel="catena-anthropic",
                               duration_ms=1, iterations=1, tools=[],
                               outcome="riuscito", now=dopo)

    identificatori = [r["id"] for r in consumi.turns()]
    assert vecchio not in identificatori, "il turno scaduto non è stato tolto"
    assert dentro in identificatori, (
        "un turno dentro la finestra è stato cancellato: il limite taglia "
        "troppo")
    assert recente in identificatori, "il turno recente è stato tolto"
    assert consumi.payloads(vecchio) == [], (
        "il carico è sopravvissuto al turno che lo spiega: righe orfane")


def test_un_turno_FALLITO_si_registra_lo_stesso(consumi):
    """Un giro che esaurisce le iterazioni o che cade è **il più interessante
    di tutti** per la latenza: è quello che ha speso di più senza dare niente.
    Registrare solo i riusciti misurerebbe la casa nei giorni belli.

    Mutazione ESEGUITA: scrivere solo quando `outcome == "riuscito"` --
    rossa."""
    consumi.log_turn(species="attuatore", provider="openrouter", model="qwen",
                     channel="catena-anthropic",
                     duration_ms=240_000, iterations=50,
                     tools=["search"] * 50, outcome="esaurito", now=ADESSO)

    riga = consumi.turns()[0]

    assert riga["outcome"] == "esaurito"
    assert riga["iterations"] == 50


def test_le_righe_si_rileggono_come_sono_state_scritte(consumi):
    """`tools` viaggia come JSON: se la lettura non lo sciogliesse, chi legge
    troverebbe una stringa che somiglia a una lista, e la prima `len()` direbbe
    il numero di caratteri.

    Mutazione ESEGUITA: restituire la stringa grezza -- rossa."""
    consumi.log_turn(species="ricette", provider="ponte", model="haiku", channel="catena-anthropic",
                     duration_ms=1, iterations=1, tools=["trend", "view"],
                     outcome="riuscito", now=ADESSO)

    letti = consumi.turns()[0]["tools"]

    assert isinstance(letti, list)
    assert letti == ["trend", "view"]
    assert not isinstance(letti, str)
    json.dumps(letti)


# --- I controlli che dicono DOVE intervenire ------------------------------
#
# Le colonne qui sotto non descrivono un turno: rispondono a una domanda
# precisa, e ognuna ha già scritta la regola di decisione che ci si aspetta
# da lei. Sono state decise PRIMA di guardare i numeri, apposta: decidere
# dopo averli visti vuol dire farsi convincere di ciò che si pensava già.


def test_il_turno_registra_CHI_ha_chiesto(consumi):
    """**La fondamenta, e vale da oggi anche se serve domani.** Oggi la chat è
    una sola; il giorno in cui HIRIS riceve input da chat diverse per utente e
    per sistema — Retro Panel accanto alla sua — `species="chat"` le
    schiaccerebbe insieme. È lo stesso difetto di `agent_type="observer"`, che
    schiaccia osservatore e ricette.

    La forma è quella del soggetto della cronaca, non una nuova: è la stessa
    domanda, e due forme per la stessa domanda divergono.

    Mutazione ESEGUITA: non scrivere `subject_json` -- rossa."""
    soggetto = {"specie": "integrazione", "id": "retropanel",
                "nome": "Retro Panel", "ruolo": "utente"}

    consumi.log_turn(species="chat", provider="ponte", model="sonnet",
                     channel="ponte", duration_ms=1, iterations=1, tools=[],
                     outcome="riuscito", now=ADESSO, subject=soggetto)

    assert consumi.turns()[0]["subject"] == soggetto


def test_un_giro_NOTTURNO_non_ha_nessun_soggetto(consumi):
    """«Non c'è nessuna persona» è un fatto, e si scrive come assenza. Un
    soggetto inventato per riempire la colonna direbbe il falso proprio sui
    giri che nessuno guarda.

    Mutazione ESEGUITA: scrivere `{}` invece di `NULL` -- rossa."""
    consumi.log_turn(species="analista", provider="ponte", model="haiku",
                     channel="ponte", duration_ms=1, iterations=1, tools=[],
                     outcome="riuscito", now=ADESSO)

    assert consumi.turns()[0]["subject"] is None


def test_il_turno_registra_QUALE_canale_ha_composto(consumi):
    """I quattro composer compongono la stessa cosa in quattro posti, e sono
    già divergiti una volta — `tests/test_composition_order.py` esiste per
    quello. Senza questa colonna, «il ponte e la catena mandano la stessa
    cosa?» resta una speranza invece di una query.

    Mutazione ESEGUITA: non scrivere `channel` -- rossa."""
    for canale in ("catena-anthropic", "catena-openai", "catena-streaming",
                   "ponte"):
        consumi.log_turn(species="chat", provider="x", model="y",
                         channel=canale, duration_ms=1, iterations=1,
                         tools=[], outcome="riuscito", now=ADESSO)

    assert {r["channel"] for r in consumi.turns()} == {
        "catena-anthropic", "catena-openai", "catena-streaming", "ponte"}


def test_l_IMPRONTA_del_prefisso_si_registra(consumi):
    """**La misura che decide da sola la leva più opaca.** Sulla catena il 74%
    della materia in ingresso si paga a prezzo pieno, e il caching di quei
    provider è implicito e per PREFISSO: se l'impronta di guida + definizioni
    cambia fra un turno e l'altro, la cache non può colpire, e il colpevole è
    dentro il prefisso. Se resta uguale e il 74% non scende, non è roba
    nostra.

    Senza questa colonna quella domanda resta un'ipotesi; con lei si risponde
    in un giorno.

    Mutazione ESEGUITA: non scrivere `prefix_hash` -- rossa."""
    ident = consumi.log_turn(species="chat", provider="openrouter",
                             model="qwen", channel="catena-openai",
                             duration_ms=1, iterations=2, tools=[],
                             outcome="riuscito", now=ADESSO)

    consumi.log_payload(ident, iteration=1, tools_chars=1, guide_chars=1,
                        core_chars=1, history_chars=1, results_chars=1,
                        now=ADESSO, prefix_hash="a1b2c3d4")
    consumi.log_payload(ident, iteration=2, tools_chars=1, guide_chars=1,
                        core_chars=1, history_chars=1, results_chars=1,
                        now=ADESSO, prefix_hash="a1b2c3d4")

    impronte = {c["prefix_hash"] for c in consumi.payloads(ident)}
    assert impronte == {"a1b2c3d4"}, (
        "il prefisso è cambiato dentro lo stesso turno: la cache non può "
        "colpire nemmeno fra un giro e l'altro")


def test_si_registra_quante_definizioni_sono_state_SPEDITE(consumi):
    """Con `turn.tools`, che dice quante ne sono state usate, la differenza è
    lo spreco — moltiplicato per il numero di giri. È il numero che dice se la
    leva del sottoinsieme vale la pena o no, **prima** di toccare niente.

    Mutazione ESEGUITA: non scrivere `tools_sent` -- rossa."""
    ident = consumi.log_turn(species="ricette", provider="ponte",
                             model="haiku", channel="ponte", duration_ms=1,
                             iterations=1, tools=["trend"], outcome="riuscito",
                             now=ADESSO)

    consumi.log_payload(ident, iteration=1, tools_chars=44876, guide_chars=1,
                        core_chars=1, history_chars=1, results_chars=1,
                        now=ADESSO, tools_sent=16)

    carico = consumi.payloads(ident)[0]
    usati = len(set(consumi.turns()[0]["tools"]))

    assert carico["tools_sent"] == 16
    assert carico["tools_sent"] - usati == 15, (
        "quindici definizioni spedite e mai chiamate, in questo turno")
