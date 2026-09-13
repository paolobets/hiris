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
