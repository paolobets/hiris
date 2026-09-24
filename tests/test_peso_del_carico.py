"""I due pesatori: di cosa è fatto un giro, e se il prefisso è davvero stabile.

Sono funzioni pure — si provano sui loro valori, non attraverso un turno — e
la proprietà che contano è **una sola**: l'impronta del prefisso deve ignorare
ciò che cambia a ogni turno e accorgersi di ciò che non dovrebbe cambiare.

Se l'impronta cambiasse col nucleo, direbbe «la cache non può colpire» sempre,
su tutti e due i percorsi, e sarebbe una misura inutile che sembra funzionare.
"""
from hiris.app.backends.openai_compat_runner import _pesa_carico_catena
from hiris.app.claude_runner import _pesa_carico

STRUMENTI = [{"name": "search", "description": "cerca"},
             {"name": "view", "description": "guarda"}]


def _blocchi(nucleo: str, guida: str = "sei hiris"):
    return [{"type": "text", "text": guida}, {"type": "text", "text": nucleo}]


def _messaggi(risultato: str = "", cronologia: str = "ciao"):
    messaggi = [{"role": "user", "content": cronologia}]
    if risultato:
        messaggi.append({"role": "assistant", "content": [
            {"type": "tool_result", "content": risultato}]})
    return messaggi


def test_l_impronta_IGNORA_il_nucleo_che_cambia_a_ogni_turno():
    """Il nucleo porta l'ora («Adesso sono le 20:33») e cambia a ogni turno:
    sta DOPO il punto di interruzione della cache apposta. Se l'impronta lo
    comprendesse, direbbe «prefisso instabile» sempre, e non misurerebbe
    niente.

    Mutazione ESEGUITA: comprendere tutti i blocchi nell'impronta -- rossa."""
    uno = _pesa_carico(_blocchi("sono le 20:33"), STRUMENTI, _messaggi(),
                       "sono le 20:33")
    due = _pesa_carico(_blocchi("sono le 20:34"), STRUMENTI, _messaggi(),
                       "sono le 20:34")

    assert uno["prefix_hash"] == due["prefix_hash"]


def test_l_impronta_CAMBIA_se_cambiano_le_definizioni():
    """È l'altra metà: un'impronta che non si accorge di niente sarebbe
    altrettanto inutile. Qui è il catalogo a cambiare, ed è esattamente il
    caso su cui la leva del sottoinsieme interverrebbe.

    Mutazione ESEGUITA: non comprendere gli strumenti nell'impronta --
    rossa."""
    uno = _pesa_carico(_blocchi("x"), STRUMENTI, _messaggi(), "x")
    due = _pesa_carico(_blocchi("x"), STRUMENTI[:1], _messaggi(), "x")

    assert uno["prefix_hash"] != due["prefix_hash"]


def test_l_impronta_cambia_se_cambia_la_GUIDA():
    """La guida è stabile per agente, non per sempre: un modificatore di
    comportamento diverso è un prefisso diverso, e la cache lo sa anche se noi
    non lo misurassimo.

    Mutazione ESEGUITA: comprendere solo gli strumenti -- rossa."""
    uno = _pesa_carico(_blocchi("x", guida="sei hiris"), STRUMENTI,
                       _messaggi(), "x")
    due = _pesa_carico(_blocchi("x", guida="sei hiris, sii conciso"),
                       STRUMENTI, _messaggi(), "x")

    assert uno["prefix_hash"] != due["prefix_hash"]


def test_i_risultati_degli_strumenti_si_contano_A_PARTE():
    """**È l'intero punto del secondo registro.** Confonderli con la
    cronologia direbbe «la conversazione è lunga» dove la verità è «gli
    strumenti hanno risposto molto» — e sono due interventi diversi.

    Mutazione ESEGUITA: sommare i `tool_result` nella cronologia -- rossa."""
    senza = _pesa_carico(_blocchi("x"), STRUMENTI, _messaggi(), "x")
    con = _pesa_carico(_blocchi("x"), STRUMENTI,
                       _messaggi(risultato="a" * 5000), "x")

    assert senza["results_chars"] == 0
    assert con["results_chars"] > 5000
    assert con["history_chars"] == senza["history_chars"], (
        "i risultati degli strumenti sono finiti nella cronologia")


def test_quante_definizioni_sono_state_spedite():
    """Il denominatore dello spreco: spedite contro usate.

    Mutazione ESEGUITA: contare i caratteri invece delle definizioni --
    rossa."""
    pesi = _pesa_carico(_blocchi("x"), STRUMENTI, _messaggi(), "x")

    assert pesi["tools_sent"] == 2


def test_i_DUE_pesatori_parlano_lo_stesso_vocabolario():
    """I quattro canali compongono la stessa cosa in posti diversi, e sono già
    divergiti una volta. Se anche le due MISURE usassero chiavi diverse, i due
    percorsi diventerebbero inconfrontabili — cioè si perderebbe l'unica cosa
    per cui questo registro esiste.

    Mutazione ESEGUITA: rinominare una chiave in uno dei due -- rossa."""
    anthropic = _pesa_carico(_blocchi("x"), STRUMENTI, _messaggi(), "x")
    catena = _pesa_carico_catena(
        [{"role": "system", "content": "sei hirisx"},
         {"role": "user", "content": "ciao"}], STRUMENTI, "x")

    assert set(anthropic) == set(catena)


def test_il_pesatore_della_catena_separa_i_risultati():
    """Sulla catena un risultato di strumento è un messaggio con `role`
    `tool`, non un blocco dentro il contenuto: forma diversa, stessa
    proprietà.

    Mutazione ESEGUITA: contare i messaggi `tool` come cronologia -- rossa."""
    pesi = _pesa_carico_catena(
        [{"role": "system", "content": "guidax"},
         {"role": "user", "content": "ciao"},
         {"role": "tool", "content": "b" * 3000}], STRUMENTI, "x")

    assert pesi["results_chars"] >= 3000
    assert pesi["history_chars"] < 100


# --- Il gemello che mancava, e che il primo uso vero ha scoperto ----------
#
# Le prove sull'impronta esistevano SOLO per il percorso Anthropic. Sulla
# catena il nucleo non e' un blocco a se': `system_parts.append(context_str)`
# lo infila DENTRO l'unico messaggio di sistema, quindi l'impronta lo
# comprendeva e cambiava a ogni turno per costruzione.
#
# Il verdetto che ne usciva -- «il prefisso cambia, la cache non puo'
# colpire» -- era un artefatto della misura, non un fatto sul prodotto. Lo ha
# scoperto la PRIMA lettura vera sulla casa: tre turni, tre impronte diverse,
# un numero troppo netto per essere vero.


def test_l_impronta_della_CATENA_ignora_il_nucleo():
    """Il gemello di `test_l_impronta_IGNORA_il_nucleo_che_cambia_a_ogni_turno`,
    per l'altra forma. Se l'impronta comprendesse il nucleo direbbe «prefisso
    instabile» SEMPRE, su ogni casa e ogni turno: una misura che sembra
    funzionare e non misura niente.

    Mutazione ESEGUITA: non togliere il nucleo dal testo su cui si calcola
    l'impronta -- rossa."""
    def _sistema(nucleo):
        return [{"role": "system", "content": "sei hiris\n" + nucleo},
                {"role": "user", "content": "ciao"}]

    uno = _pesa_carico_catena(_sistema("sono le 20:33"), STRUMENTI,
                              "sono le 20:33")
    due = _pesa_carico_catena(_sistema("sono le 20:34"), STRUMENTI,
                              "sono le 20:34")

    assert uno["prefix_hash"] == due["prefix_hash"]


def test_l_impronta_della_catena_CAMBIA_se_cambia_la_guida():
    """L'altra meta': un'impronta che non si accorge di niente sarebbe
    altrettanto inutile.

    Mutazione ESEGUITA: calcolare l'impronta sui soli strumenti -- rossa."""
    uno = _pesa_carico_catena(
        [{"role": "system", "content": "sei hiris\nx"}], STRUMENTI, "x")
    due = _pesa_carico_catena(
        [{"role": "system", "content": "sei hiris, sii conciso\nx"}],
        STRUMENTI, "x")

    assert uno["prefix_hash"] != due["prefix_hash"]
