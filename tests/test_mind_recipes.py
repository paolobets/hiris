"""Le ricette: «come si calcola una cosa» smette di essere codice.

Spec `docs/design/2026-09-10-i-tre-attori.md` §7. **Una ricetta e' un dato**, e
il codice sa eseguirlo: una sequenza di passi con nomi, dove un passo puo'
leggere il risultato dei passi precedenti **e nient'altro**. Niente cicli,
niente condizioni, niente funzioni nuove -- e' quello che permette di leggerla
tutta, provarla e **rifiutarla prima di eseguirla**.

La prova storica che la giustifica: il 27/08/2026 la quota di autosufficienza
era sbagliata perche' `autoconsumo/(autoconsumo+prelievo)` vale solo su certe
integrazioni -- misurato 0,964 invece di 0,985. Era **una ricetta specifica di
un'integrazione, scritta dentro il motore di aggregazione**: come dato sarebbe
stata correggibile senza un rilascio.
"""
import pytest

from hiris.app.mind import recipes as ric


def _serie(valori):
    """Una serie oraria come la manda il lettore: `{"valore": x}` per ogni ora."""
    return [{"valore": v} for v in valori]


CASA = {"sensor.prodotta": _serie([1.0] * 24),
        "sensor.consumata": _serie([2.0] * 24),
        "sensor.prelevata": _serie([0.5] * 24)}


# -- La validazione: si rifiuta, non si corregge ----------------------------

def test_una_ricetta_valida_si_accetta_e_lo_dice():
    r = ric.Recipe({"why": "l'inverter pesa sul risparmio energetico",
                    "steps": [{"name": "prodotta", "operation": "somma_periodo",
                               "inputs": ["@sensor.prodotta"],
                               "params": {"unit": "kWh", "expected_parts": 24}}]})

    esito = r.validate(entities=set(CASA))

    assert esito.valid
    assert esito.problems == []


def test_un_operazione_che_NON_ESISTE_fa_rifiutare_la_ricetta():
    """*«Ogni passo deve nominare un'operazione che esiste»*. Il codice la
    rifiuta e **non la corregge**: correggere vorrebbe dire indovinare cosa
    intendeva chi l'ha scritta, ed e' esattamente il modo in cui una
    deduzione diventa un fatto senza che nessuno se ne accorga.

    Mutazione che la uccide: togliere il controllo su `REGISTRY`.
    """
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "prodotta", "operation": "somma_totale_giornaliera",
         "inputs": ["@sensor.prodotta"]}]})

    esito = r.validate(entities=set(CASA))

    assert not esito.valid
    assert any("somma_totale_giornaliera" in p for p in esito.problems)


def test_un_entita_che_NON_ESISTE_fa_rifiutare_la_ricetta():
    """Una ricetta che nomina un'entita' sparita produrrebbe zero con la
    faccia di un totale. Si rifiuta, e il rifiuto dice quale entita'."""
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.mai_esistita"], "params": {"unit": "kWh"}}]})

    esito = r.validate(entities=set(CASA))

    assert not esito.valid
    assert any("sensor.mai_esistita" in p for p in esito.problems)


def test_un_passo_che_legge_un_passo_SUCCESSIVO_fa_rifiutare_la_ricetta():
    """**E' la regola che tiene la ricetta un dato e non un linguaggio.**

    *«Un passo puo' leggere il risultato dei passi precedenti, e
    nient'altro»*: solo all'indietro. Con un riferimento in avanti servirebbe
    un ordinatore, con due che si guardano servirebbe un rilevatore di cicli,
    e a quel punto non si sta piu' leggendo una ricetta -- si sta eseguendo un
    programma che nessuno puo' provare prima di lanciarlo.

    Mutazione che la uccide: validare i riferimenti contro TUTTI i nomi
    invece che contro quelli gia' visti.
    """
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "quota", "operation": "quota", "inputs": ["$prodotta", "$consumata"]},
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh"}},
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh"}}]})

    esito = r.validate(entities=set(CASA))

    assert not esito.valid
    assert any("prodotta" in p and "prima" in p.lower() for p in esito.problems)


def test_due_passi_con_lo_STESSO_nome_fanno_rifiutare_la_ricetta():
    """Con due passi omonimi un `$nome` diventa ambiguo, e l'ambiguita' non si
    risolve indovinando quale dei due intendesse chi ha scritto."""
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "totale", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh"}},
        {"name": "totale", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh"}}]})

    esito = r.validate(entities=set(CASA))

    assert not esito.valid
    assert any("totale" in p for p in esito.problems)


def test_una_ricetta_SENZA_PASSI_si_rifiuta():
    """Una ricetta vuota non e' una ricetta che non calcola niente: e' una
    ricetta che nessuno ha finito di scrivere, e accettarla la farebbe
    comparire fra quelle valide."""
    esito = ric.Recipe({"why": "x", "steps": []}).validate(entities=set(CASA))

    assert not esito.valid


def test_una_ricetta_SENZA_PERCHE_si_rifiuta():
    """*«perche': pesa su risparmio energetico»* sta nell'esempio della spec e
    non e' decorazione: una ricetta senza la ragione per cui esiste non si puo'
    ne' rivedere ne' cancellare quando l'obiettivo cambia."""
    esito = ric.Recipe({"steps": [
        {"name": "p", "operation": "somma_periodo", "inputs": ["@sensor.prodotta"],
         "params": {"unit": "kWh"}}]}).validate(entities=set(CASA))

    assert not esito.valid
    assert any("perche" in p or "ragione" in p for p in esito.problems)


def test_i_problemi_si_elencano_TUTTI_non_solo_il_primo():
    """Chi ha scritto la ricetta deve poterla correggere in un giro solo: un
    rifiuto che dice un problema per volta costringe a tre giri di modello per
    tre errori, e ognuno costa."""
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "a", "operation": "inventata", "inputs": ["@sensor.fantasma"]}]})

    esito = r.validate(entities=set(CASA))

    assert len(esito.problems) >= 2


# -- L'esecuzione -----------------------------------------------------------

def test_una_ricetta_valida_produce_i_suoi_numeri():
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh", "expected_parts": 24}}]})

    esiti = r.run(series=CASA)

    assert esiti["prodotta"].value == 24.0
    assert esiti["consumata"].value == 48.0


def test_un_passo_legge_il_risultato_di_quelli_prima():
    """La ricetta dell'inverter, passo 7: `quota(differenza_fra(consumata,
    prelevata), consumata)` -- la riga della spec §7, eseguita davvero."""
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "prelevata", "operation": "somma_periodo",
         "inputs": ["@sensor.prelevata"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "autoprodotta", "operation": "differenza_fra",
         "inputs": ["$consumata", "$prelevata"]},
        {"name": "autosufficienza", "operation": "quota",
         "inputs": ["$autoprodotta", "$consumata"]}]})

    esiti = r.run(series=CASA)

    # 48 consumati, 12 prelevati -> 36 non vengono dalla rete -> 0,75.
    assert esiti["autosufficienza"].value == 0.75


def test_un_passo_NON_CALCOLABILE_non_ferma_la_ricetta_e_si_propaga():
    """Il «non lo so» di un passo non e' un guasto della ricetta: e' un
    risultato, e i passi che lo leggono lo ereditano invece di esplodere.

    Mutazione che la uccide: sollevare quando un ingresso non e' calcolabile.
    """
    magra = {"sensor.prodotta": _serie([1.0, None, None, None]),
             "sensor.consumata": _serie([2.0] * 24)}
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "prodotta", "operation": "somma_periodo",
         "inputs": ["@sensor.prodotta"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.consumata"], "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "quanta", "operation": "quota",
         "inputs": ["$prodotta", "$consumata"]}]})

    esiti = r.run(series=magra)

    assert not esiti["prodotta"].computable
    assert not esiti["quanta"].computable
    assert "copertura" in esiti["quanta"].reason


def test_una_ricetta_NON_VALIDA_non_si_esegue_affatto():
    """**Si rifiuta PRIMA di eseguirla**, non a meta'. Una ricetta che scrive
    tre passi e poi scopre il quarto rotto avrebbe gia' consumato tre conti e
    lasciato un risultato parziale che somiglia a uno completo.

    Mutazione che la uccide: eseguire senza validare.
    """
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "p", "operation": "inventata", "inputs": ["@sensor.prodotta"]}]})

    with pytest.raises(ValueError, match="inventata"):
        r.run(series=CASA)


def test_le_entita_che_la_ricetta_NOMINA_si_leggono_senza_eseguirla():
    """Chi deve leggere le serie deve sapere quali, **prima** di eseguire: e'
    cio' che permette una lettura sola di rete per tutta la ricetta, invece di
    una per passo."""
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "a", "operation": "somma_periodo", "inputs": ["@sensor.prodotta"],
         "params": {"unit": "kWh"}},
        {"name": "b", "operation": "somma_periodo", "inputs": ["@sensor.consumata"],
         "params": {"unit": "kWh"}},
        {"name": "c", "operation": "differenza_fra", "inputs": ["$a", "$b"]}]})

    assert r.entities() == {"sensor.prodotta", "sensor.consumata"}

# ── Il difetto del 14/09/2026: il registro offriva ciò che il motore non sa
#    eseguire ──────────────────────────────────────────────────────────────
#
# Trovato dal vivo. `GET /api/health` diceva:
#
#   riparazione: {"oggetti": "sollevata",
#                 "perche": "TypeError: _episode() missing 2 required
#                            keyword-only arguments: 'is_on' and 'period_end'"}
#
# La catena, quattro anelli:
#
# 1. il catalogo mostrato al modello elencava OGNI voce del registro, `episodio`
#    compresa -- e `is_on` e' una FUNZIONE, che nessun JSON puo' portare;
# 2. il modello ha scritto la sua prima ricetta usando `episodio`;
# 3. `validate()` controllava solo che il nome fosse nel registro: accettata,
#    e scritta nel sapere;
# 4. il resoconto la eseguiva senza validarla: `TypeError`, che nessuno
#    catturava, e l'intera riaggregazione moriva -- oggetti e resoconti di due
#    giorni, a ogni riavvio, per sempre.


def test_una_ricetta_che_nomina_un_operazione_NON_scrivibile_si_rifiuta():
    """`episodio` resta nel registro -- `aggregate_day` lo usa -- ma non e'
    scrivibile in una ricetta: `is_on` e' una funzione, e un dato non porta
    funzioni. Il rifiuto dice PERCHE', o il modello riproverebbe.

    Mutazione: togliere il controllo su `in_recipes` da `validate` -- rossa.
    """
    ricetta = ric.Recipe({"why": "quanto e' stato acceso",
                      "steps": [{"name": "acceso", "operation": "episodio",
                                 "inputs": ["@climate.x"]}]})
    esito = ricetta.validate(entities={"climate.x"})
    assert not esito.valid
    assert any("episodio" in p and "non si puo' scrivere in una ricetta" in p
               for p in esito.problems), esito.problems


def test_una_ricetta_che_non_da_un_parametro_OBBLIGATORIO_si_rifiuta():
    """`somma_periodo` vuole `unit`: senza, il motore solleverebbe `TypeError`
    a meta' giornata invece di rifiutare prima di eseguire -- che e' l'unica
    cosa che rende le ricette un dato invece che codice.

    Mutazione: togliere il controllo sui parametri obbligatori -- rossa.
    """
    ricetta = ric.Recipe({"why": "il totale", "steps": [
        {"name": "totale", "operation": "somma_periodo", "inputs": ["@sensor.x"]}]})
    esito = ricetta.validate(entities={"sensor.x"})
    assert not esito.valid
    assert any("unit" in p for p in esito.problems), esito.problems


def test_i_parametri_facoltativi_non_si_pretendono():
    """`expected_parts` ha un valore di fabbrica: pretenderlo trasformerebbe
    il cancello in rumore, e un cancello che grida sempre si spegne.

    Mutazione: pretendere anche i parametri con un default -- rossa.
    """
    ricetta = ric.Recipe({"why": "il totale", "steps": [
        {"name": "totale", "operation": "somma_periodo", "inputs": ["@sensor.x"],
         "params": {"unit": "kWh"}}]})
    assert ricetta.validate(entities={"sensor.x"}).valid


def test_tutte_le_operazioni_OFFERTE_al_modello_sono_eseguibili_da_una_ricetta():
    """**Il cancello della classe.** Il difetto non e' stato «`episodio` era
    nel catalogo»: e' stato che nessuno verificava che catalogo ed esecutore
    dicessero la stessa cosa. Un'operazione offerta al modello i cui parametri
    obbligatori un JSON non sa portare e' una trappola che aspetta.

    Un parametro obbligatorio e' portabile da una ricetta solo se il suo valore
    e' un letterale JSON. Una funzione (`is_on`) non lo e'; un `Period` neanche
    -- va calcolato da un passo, e i passi si passano come `inputs`
    POSIZIONALI, non come parametri.

    Mutazione: rimettere `in_recipes=True` su `episodio` -- rossa.
    """
    import inspect

    from hiris.app.mind.operations import REGISTRY

    valori_esclusi = {"is_on", "period", "period_end"}
    colpevoli = []
    for name, operation in REGISTRY.items():
        if not operation.in_recipes:
            continue
        firma = inspect.signature(operation.run)
        for p in firma.parameters.values():
            if (p.kind is p.KEYWORD_ONLY and p.default is p.empty
                    and p.name in valori_esclusi):
                colpevoli.append(f"{name}.{p.name}")
    assert colpevoli == [], (
        "offerte al modello ma non eseguibili da una ricetta: " + ", ".join(colpevoli))

def test_una_ricetta_con_TROPPI_ingressi_si_rifiuta():
    """Stessa classe del difetto del 14/09: `quota` prende due cose, e con tre
    il motore solleverebbe `TypeError` a meta' giornata. Il conto degli
    ingressi si legge dalla FIRMA, come i parametri.

    Mutazione: togliere il controllo sul numero di ingressi -- rossa.
    """
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "a", "operation": "somma_periodo", "inputs": ["@sensor.x"],
         "params": {"unit": "kWh"}},
        {"name": "b", "operation": "somma_periodo", "inputs": ["@sensor.y"],
         "params": {"unit": "kWh"}},
        {"name": "c", "operation": "somma_periodo", "inputs": ["@sensor.z"],
         "params": {"unit": "kWh"}},
        {"name": "q", "operation": "quota", "inputs": ["#a", "#b", "#c"]}]})
    esito = r.validate(entities={"sensor.x", "sensor.y", "sensor.z"})
    assert not esito.valid
    assert any("tre" in p or "3" in p for p in esito.problems), esito.problems


def test_una_ricetta_con_TROPPO_POCHI_ingressi_si_rifiuta():
    """E l'altro capo: `quota` con un ingresso solo.

    Mutazione: controllare solo il massimo e non il minimo -- rossa.
    """
    r = ric.Recipe({"why": "x", "steps": [
        {"name": "a", "operation": "somma_periodo", "inputs": ["@sensor.x"],
         "params": {"unit": "kWh"}},
        {"name": "q", "operation": "quota", "inputs": ["#a"]}]})
    esito = r.validate(entities={"sensor.x"})
    assert not esito.valid
    assert any("quota" in p for p in esito.problems), esito.problems

# ── Il secondo anello, trovato dal vivo il 14/09/2026 ────────────────────────
#
#   riparazione: {"oggetti": "sollevata",
#                 "perche": "AttributeError: 'list' object has no attribute
#                            'windows'"}
#
# La 3.34.0 aveva chiuso i nomi, i parametri e il numero di ingressi. Restava
# la FORMA: `tempo_in_stato` vuole un `Period`, e una ricetta gli consegnava la
# serie di un'entita' -- una lista. Il validatore diceva di si' (un ingresso,
# nessun parametro obbligatorio) e il motore moriva un passo dopo.


def test_ogni_operazione_OFFERTA_si_esegue_davvero_dentro_una_ricetta():
    """**Il cancello piu' forte che questo registro possa avere: si ESEGUE.**

    Per ogni operazione che il catalogo offre al modello si costruisce la
    ricetta minima che la usa e la si fa girare con dati finti. Non deve
    sollevare: ne' `TypeError` (firma), ne' `AttributeError` (forma). Un
    \u00abnon calcolabile\u00bb va benissimo -- e' un esito, non un guasto.

    Ragionare su quali forme si incastrano non basta: e' esattamente cio' che
    ho fatto il 14/09 arrivando alla 3.34.0, e il difetto successivo era gia'
    li' ad aspettare. Questa prova non ragiona, prova.

    Mutazione: rimettere `tempo_in_stato` fra le offerte (cioe' togliere il
    controllo di raggiungibilita' da `offerable`) -- rossa con
    `AttributeError: 'Measurement' object has no attribute 'duration_s'`.
    """
    from hiris.app.mind.operations import REGISTRY, SHAPE_RESULT, SHAPE_SERIES

    serie = [{"inizio": 0.0, "fine": 3600.0, "valore": 1.0},
             {"inizio": 3600.0, "fine": 7200.0, "valore": 2.0}]
    guai = []
    for name, operation in REGISTRY.items():
        if not operation.offerable:
            continue
        passi, ingressi, contatore = [], [], 0
        for forma in operation.takes:
            if forma == SHAPE_SERIES:
                contatore += 1
                ingressi.append(f"{ric.ENTITY_MARK}sensor.finto{contatore}")
            else:
                assert forma == SHAPE_RESULT, (name, forma)
                contatore += 1
                passi.append({"name": f"prima{contatore}",
                              "operation": "somma_periodo",
                              "inputs": [f"{ric.ENTITY_MARK}sensor.finto{contatore}"],
                              "params": {"unit": "kWh"}})
                ingressi.append(f"{ric.STEP_MARK}prima{contatore}")
        parametri = {n: _parametro_finto(n) for n in operation.required_params}
        passi.append({"name": "sotto_prova", "operation": name,
                      "inputs": ingressi, "params": parametri})
        dati = {"why": f"la prova di {name}", "steps": passi}

        entita = {f"sensor.finto{i}": list(serie) for i in range(1, contatore + 1)}
        ricetta = ric.Recipe(dati)
        esito = ricetta.validate(entities=set(entita))
        assert esito.valid, (name, esito.problems)
        try:
            ricetta.run(series=entita)
        except Exception as error:  # prendere TUTTO e' il punto della prova
            guai.append(f"{name}: {type(error).__name__}: {error}")
    assert guai == [], "offerte al modello ma non eseguibili: " + " \u00b7 ".join(guai)


def _parametro_finto(name: str):
    """Un valore plausibile per ogni parametro obbligatorio del registro.

    Se un'operazione nuova ne porta uno che non e' qui, la prova si ferma con
    un messaggio che dice cosa aggiungere -- meglio di un finto `None` che
    passerebbe per caso.
    """
    valori = {"unit": "kWh", "zone": "Europe/Rome",
              "key": "classe", "reduce": "somma_entita"}
    assert name in valori, (
        f"parametro obbligatorio nuovo: \u00ab{name}\u00bb. Aggiungi qui un valore "
        "plausibile, o la prova non puo' eseguire l'operazione che lo vuole.")
    return valori[name]

def test_una_ricetta_che_consegna_la_FORMA_sbagliata_si_rifiuta():
    """Il caso vero del 14/09/2026, dopo la 3.34.0: `tempo_in_stato` vuole un
    periodo, la ricetta gli consegnava la serie di un'entita', e il motore
    moriva un passo dopo con
    `AttributeError: 'list' object has no attribute 'windows'`.

    Mutazione: togliere il controllo delle forme da `_problemi_operazione` --
    rossa.
    """
    r = ric.Recipe({"why": "quanto e' stato acceso", "steps": [
        {"name": "acceso", "operation": "tempo_in_stato",
         "inputs": ["@climate.x"]}]})
    esito = r.validate(entities={"climate.x"})
    assert not esito.valid
    assert any("tempo_in_stato" in p for p in esito.problems), esito.problems


def test_una_serie_dove_si_vuole_una_misura_si_rifiuta():
    """L'altro verso, che e' il piu' facile da scrivere per sbaglio: `quota`
    vuole due misure gia' calcolate, non due serie grezze.

    **Si contano i problemi, e sono due.** Asserire solo `not valid`
    lascerebbe passare un controllo che guarda il PRIMO ingresso e si ferma:
    la ricetta sarebbe rifiutata lo stesso, per meta' della ragione, e il
    proprietario correggerebbe un errore per volta.

    Mutazione: fermarsi al primo ingresso (`zip(listed[:1], entry.takes)`) --
    rossa, un problema invece di due.
    """
    r = ric.Recipe({"why": "la quota", "steps": [
        {"name": "q", "operation": "quota",
         "inputs": ["@sensor.a", "@sensor.b"]}]})
    esito = r.validate(entities={"sensor.a", "sensor.b"})
    assert not esito.valid
    assert len(esito.problems) == 2, esito.problems


def test_ogni_operazione_dichiara_una_forma_per_ogni_ingresso():
    """Il cancello della dichiarazione: tante forme quanti sono gli ingressi
    che `run` prende per posizione. Una in meno lascerebbe un ingresso **non
    controllato**, ed e' esattamente il buco da cui e' passato il difetto del
    14/09/2026.

    Mutazione: togliere una forma da una qualunque delle diciotto voci --
    rossa.
    """
    from hiris.app.mind.operations import REGISTRY

    storte = [(n, len(o.takes), o.input_range[1])
              for n, o in REGISTRY.items() if len(o.takes) != o.input_range[1]]
    assert storte == [], storte


def test_le_forme_dichiarate_sono_quelle_del_vocabolario_chiuso():
    """E sono quelle, non una stringa qualunque: un refuso in una forma
    (`"peridoo"`) non farebbe combaciare niente, e l'operazione sarebbe
    rifiutata sempre, in silenzio -- la stessa forma di guasto che questo giro
    esiste per chiudere.

    Mutazione: scrivere una forma inventata in una voce -- rossa.
    """
    from hiris.app.mind import operations as ops

    vocabolario = {ops.SHAPE_SERIES, ops.SHAPE_RESULT, ops.SHAPE_READINGS,
                   ops.SHAPE_PERIOD, ops.SHAPE_MEASURES, ops.SHAPE_MEASURE_MAP}
    fuori = [(n, f) for n, o in ops.REGISTRY.items() for f in o.takes
             if f not in vocabolario]
    assert fuori == [], fuori
