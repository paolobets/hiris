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


def test_gli_ARGOMENTI_degli_strumenti_hanno_UN_nome_solo(consumi):
    """**Cambiata DELIBERATAMENTE il 29/09/2026** (spec «una porta sola» §7).
    Fino alla 3.70 questa prova diceva «mai gli argomenti»: un `view` porta il
    nome di una stanza, e l'archivio finisce nei backup di Home Assistant. Il
    29/09 nessuno ha saputo dire quale `search` avesse mancato
    l'Indifferenziato, perche' c'erano solo i nomi: ora gli argomenti si
    salvano, ridotti e senza credenziali.

    Cio' che resta vietato sono i NOMI alternativi: `arguments`, `argomenti`,
    `input`, `inputs` -- una seconda parola per la stessa cosa. Il nome e'
    uno, `tool_args`, ed e' ammesso.

    Mutazione ESEGUITA: chiamare il parametro `arguments` -- rossa."""
    import inspect

    firma = inspect.signature(UsageStore.log_turn).parameters

    assert "tools" in firma
    assert "tool_args" in firma
    for vietato in ("arguments", "argomenti", "input", "inputs"):
        assert vietato not in firma, (
            f"«{vietato}»: gli argomenti hanno un nome solo, `tool_args`")


def test_gli_argomenti_si_salvano_allineati_agli_strumenti(tmp_path):
    """Spec §7: il 29/09 non si e' potuto sapere quale ricerca avesse perso
    l'Indifferenziato. Mutazione ESEGUITA: non scrivere la colonna -- rossa."""
    s = UsageStore(str(tmp_path / "c.db"))
    s.log_turn(species="chat", provider="p", model="m", channel="catena",
               duration_ms=1, iterations=1, tools=["search"],
               tool_args=[{"tipo": "light", "stato": "on"}],
               outcome="riuscito", now=1.0)
    t = s.turns()[0]
    assert t["tools"] == ["search"]
    assert t["tool_args"] == [{"tipo": "light", "stato": "on"}]


def test_senza_argomenti_la_colonna_resta_NULL(consumi):
    """`None` e' «non registrati», e non `[]`: due fatti diversi."""
    consumi.log_turn(species="chat", provider="p", model="m", channel="catena",
                     duration_ms=1, iterations=1, tools=["search"],
                     outcome="riuscito", now=ADESSO)
    assert consumi.turns()[0]["tool_args"] is None


def test_un_argomento_lungo_si_accorcia():
    """Mutazione ESEGUITA: togliere il taglio a 200 -- rossa; togliere il
    tetto delle 20 chiavi -- rossa."""
    from hiris.app.usage.store import compact_tool_args
    fuori = compact_tool_args(
        [{"testo": "x" * 1000, **{f"k{i}": i for i in range(30)}}])
    assert len(fuori[0]["testo"]) == 200 and len(fuori[0]) == 20


def test_i_tetti_valgono_ANCHE_nei_dati_annidati():
    """Un `execute` mette i dati del servizio sotto una chiave: un testo lungo
    li' dentro gonfierebbe il registro come al livello alto.

    Mutazione ESEGUITA: non ricorrere nei dict (tetti solo al livello alto)
    -- rossa."""
    from hiris.app.usage.store import compact_tool_args
    fuori = compact_tool_args([{"data": {"testo": "y" * 500,
                                         "lista": ["z" * 500] * 30}}])
    assert len(fuori[0]["data"]["testo"]) == 200
    assert len(fuori[0]["data"]["lista"]) == 20
    assert len(fuori[0]["data"]["lista"][0]) == 200


def test_le_CREDENZIALI_negli_argomenti_non_si_salvano_mai(consumi):
    """**Decisione del controllore, 29/09/2026.** `execute` e `propose`
    portano i dati di un servizio, e il servizio puo' essere il disarmo di un
    allarme: `{"code": "1234"}`. Il valore non entra in `consumi.db`, che
    finisce nei backup di Home Assistant, a NESSUNA profondita'. La lista
    delle chiavi e' quella di `entity_cache` (una sola).

    Mutazione ESEGUITA: togliere il mascheramento delle chiavi credenziali
    (`_compact_mapping` copia il valore com'e') -- rossa."""
    consumi.log_turn(
        species="chat", provider="p", model="m", channel="catena",
        duration_ms=1, iterations=1, tools=["execute", "propose"],
        tool_args=[
            {"service": "alarm_control_panel.alarm_disarm",
             "data": {"entity_id": "alarm_control_panel.casa", "code": "1234"}},
            {"passi": [{"data": {"pin": "9876", "nome": "porta"}}],
             "password": "hunter2"}],
        outcome="riuscito", now=ADESSO)

    grezzo = json.dumps(consumi.turns()[0]["tool_args"])
    for segreto in ("1234", "9876", "hunter2"):
        assert segreto not in grezzo
    salvati = consumi.turns()[0]["tool_args"]
    assert salvati[0]["data"] == {"entity_id": "alarm_control_panel.casa",
                                  "code": "***"}
    assert salvati[1]["passi"][0]["data"] == {"pin": "***", "nome": "porta"}
    assert salvati[1]["password"] == "***"


def test_i_campi_VERI_dei_codici_di_Home_Assistant_si_mascherano():
    """Le forme vere dei servizi delle serrature e degli allarmi: un PIN di
    4-6 cifre non ha una forma che la regola sul valore prenda, quindi conta
    il NOME (`entity_cache.SERVICE_CALL_SECRETS`, l'insieme dei segreti di una
    chiamata di servizio).

    Mutazione ESEGUITA: togliere `user_code` dall'insieme -- rossa."""
    from hiris.app.usage.store import compact_tool_args
    fuori = compact_tool_args([
        {"service": "zha.set_lock_user_code",
         "data": {"entity_id": "lock.porta", "code_slot": 2,
                  "user_code": "1234"}},
        {"service": "zwave_js.set_lock_usercode",
         "data": {"code_slot": 1, "usercode": "5678"}},
        {"service": "alarm_control_panel.alarm_arm_away",
         "data": {"alarm_code": 1234, "lock_code": "0000"}}])
    grezzo = json.dumps(fuori)
    for segreto in ("1234", "5678", "0000"):
        assert segreto not in grezzo
    assert fuori[0]["data"]["user_code"] == "***"
    assert fuori[1]["data"]["usercode"] == "***"
    assert fuori[2]["data"] == {"alarm_code": "***", "lock_code": "***"}
    assert fuori[0]["data"]["code_slot"] == 2


def test_il_testo_libero_NON_si_maschera_e_si_dichiara():
    """Il limite noto: il mascheramento e' per nome e per forma, non per
    contenuto. Se un giorno cambia, questa prova cambia con la docstring."""
    from hiris.app.usage.store import compact_tool_args
    assert compact_tool_args([{"message": "codice 4321"}]) == [
        {"message": "codice 4321"}]


def test_la_POSIZIONE_di_persone_e_dispositivi_non_si_salva():
    """Spec §7: gli argomenti passano «dallo stesso filtro di §3». Un
    `device_tracker.see` porta `gps` e `location_name`, come gli attributi
    `latitude`/`longitude` che la porta toglie: stessa lista
    (`privacy.POSITION_ATTRIBUTES`).

    Mutazione ESEGUITA: non togliere le chiavi di posizione -- rossa."""
    from hiris.app.usage.store import compact_tool_args
    fuori = compact_tool_args([{
        "service": "device_tracker.see",
        "data": {"dev_id": "telefono_paolo", "gps": [45.46, 9.19],
                 "gps_accuracy": 10, "location_name": "Lavoro",
                 "battery": 80, "nested": {"latitude": 45.4, "longitude": 9.1,
                                           "ok": 1}}}])
    dati = fuori[0]["data"]
    assert dati == {"dev_id": "telefono_paolo", "battery": 80,
                    "nested": {"ok": 1}}


def test_un_valore_che_e_un_segreto_si_maschera_anche_con_un_nome_innocuo():
    """La regola sul VALORE di `entity_cache` (indirizzo con `token=`, chiave
    esadecimale) vale anche qui: e' la stessa funzione, non una copia.

    Mutazione ESEGUITA: mascherare solo per nome -- rossa."""
    from hiris.app.usage.store import compact_tool_args
    fuori = compact_tool_args([{"url": "http://x/img?token=abc",
                                "voci": ["a" * 40, "ok"]}])
    assert fuori[0]["url"] == "***"
    assert fuori[0]["voci"] == ["***", "ok"]


def test_un_archivio_vecchio_si_migra(tmp_path):
    """Un `consumi.db` alla versione 2 guadagna la colonna senza perdere righe.

    Mutazione ESEGUITA: togliere `3: _migration_3` dal dizionario -- rossa
    (init_schema solleva «manca la migrazione»)."""
    import sqlite3
    percorso = str(tmp_path / "consumi.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE turn (id TEXT PRIMARY KEY, ts REAL NOT NULL,
            species TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            channel TEXT NOT NULL, subject_json TEXT,
            duration_ms INTEGER NOT NULL, iterations INTEGER NOT NULL,
            tools TEXT NOT NULL, outcome TEXT NOT NULL,
            output_tokens INTEGER, list_cost_usd REAL);
        INSERT INTO turn VALUES ('vecchio', 9e9, 'chat', 'p', 'm', 'catena',
            NULL, 1, 1, '["search"]', 'riuscito', NULL, NULL);
        PRAGMA user_version = 2;
    """)
    conn.commit()
    conn.close()

    a = UsageStore(percorso)

    riga = a.turns()[0]
    assert riga["id"] == "vecchio" and riga["tools"] == ["search"]
    assert riga["tool_args"] is None
    a.log_turn(species="chat", provider="p", model="m", channel="ponte",
               duration_ms=1, iterations=1, tools=["view"],
               tool_args=[{"stanza": "camera"}], outcome="riuscito", now=9e9)
    assert any(t["tool_args"] == [{"stanza": "camera"}] for t in a.turns())


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

    assert SPECIE == frozenset({"analista", "proponente", "chat", "osservatore",
                                "promessa", "ricette", "automatizza"})
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


def test_un_attributo_di_stato_che_si_chiama_code_resta_nello_specchio():
    """Review finale, M1 (30/09/2026): i segreti di una CHIAMATA non sono gli
    attributi di STATO che lo specchio trattiene. Un attributo che si chiama
    davvero `code` -- un codice di punto dati Tuya, un codice d'errore -- non
    e' una credenziale e deve arrivare al modello; negli argomenti salvati di
    una chiamata, `code` resta mascherato.

    Mutazione ESEGUITA: rimettere `"code"` in `_CREDENTIAL_ATTRIBUTES` --
    rossa; `compact_tool_args` che chiama `is_credential` senza
    `CALL_ARGUMENT_SECRETS` -- rossa sulla seconda meta'."""
    from hiris.app.proxy import entity_cache
    from hiris.app.usage.store import compact_tool_args
    ceste = entity_cache.inherited_attributes(
        {"code": "E21", "error_code": 4}, "sensor")
    assert "code" not in ceste.get(entity_cache.CREDENTIALS, {})
    visibili = {k for cesta, valori in ceste.items()
                if cesta != entity_cache.CREDENTIALS for k in valori}
    assert "code" in visibili
    assert compact_tool_args([{"data": {"code": "1234"}}]) == [{"data": {"code": "***"}}]
