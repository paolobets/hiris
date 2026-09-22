"""L'anteprima dice CHE COSA chiamerà, non quante cose (reperto B-4).

**Il reperto, misurato il 21/09/2026.** Per una modifica l'anteprima mostrava
`alias · triggers: 1 · actions: 2` — **conteggi**. Per una creazione, il nome e
una descrizione **scritta dal modello**. Il pannello «Dettagli tecnici»
mostrava gli stessi conteggi. **In nessun punto dell'interfaccia il proprietario
vedeva le azioni che stava approvando.**

Conseguenza: uno `shell_command` dentro il corpo di un'automazione passa
`validate_config` — è valido — e crea in casa un oggetto permanente che chiama
un servizio che `execute` non avrebbe potuto chiamare. `propose`/`confirm` è
quindi un canale di esecuzione **indiretto e più potente di `execute`**, ed è
anche la ragione per cui una lista di divieto sarebbe stata aggirabile per
costruzione.

**Non è una restrizione: è informazione.** Il sì c'era già; era disinformato.

## La regola che distingue `action` da `action`

Home Assistant usa la stessa parola per due cose: `action:` è il nome del
servizio dentro un passo (dal 2024.8, dove prima c'era `service:`) **e** era il
nome della lista dei passi (prima di `actions:`). Si distinguono per il tipo —
una stringa col punto è un servizio, una lista è un elenco di passi — e non per
la posizione, perché la posizione cambia da una versione all'altra di HA.
"""
from hiris.app.action.construction.workshop import services_named


def test_un_servizio_semplice_si_vede():
    """Il caso normale, e quello che il proprietario deve poter leggere prima
    di dire di sì.

    Mutazione: tornare sempre vuoto -- rossa."""
    detti = services_named({"actions": [{"action": "light.turn_on"}]})

    assert detti == ["light.turn_on"]


def test_anche_la_forma_VECCHIA_di_Home_Assistant():
    """`service:` è la parola di prima del 2024.8, e una casa vera ha
    automazioni scritte anni fa: guardare solo la parola nuova vorrebbe dire
    non vedere niente proprio dove c'è più storia.

    Mutazione ESEGUITA: guardare solo `action` -- rossa."""
    detti = services_named({"action": [{"service": "shell_command.riavvia"}]})

    assert detti == ["shell_command.riavvia"]


def test_un_servizio_ANNIDATO_non_sfugge():
    """`choose`, `repeat`, `parallel`, `then`, `default`: un corpo vero annida,
    e un estrattore che guarda solo il primo livello guarda quasi niente --
    che è peggio di non guardare, perché sembra aver guardato.

    Mutazione ESEGUITA: niente ricorsione -- rossa."""
    corpo = {"actions": [
        {"choose": [{"conditions": [],
                     "sequence": [{"action": "shell_command.pericoloso"}]}],
         "default": [{"action": "light.turn_off"}]}]}

    detti = services_named(corpo)

    assert "shell_command.pericoloso" in detti
    assert "light.turn_off" in detti


def test_la_LISTA_dei_passi_non_si_scambia_per_un_servizio():
    """**La regola che regge l'estrattore.** Home Assistant chiama `action`
    tutte e due le cose: il nome del servizio dentro un passo, e -- prima di
    `actions:` -- la lista dei passi. Si distinguono per il TIPO, non per la
    posizione: la posizione cambia da una versione all'altra di HA, il tipo no.

    Mutazione ESEGUITA: prendere ogni valore di `action` -- rossa (comparirebbe
    una lista fra i servizi)."""
    detti = services_named({"action": [{"action": "light.turn_on"}]})

    assert detti == ["light.turn_on"]


def test_una_stringa_SENZA_PUNTO_non_e_un_servizio():
    """Un servizio di Home Assistant si chiama sempre `dominio.nome`. Senza
    questa regola, un `action: "qualcosa"` di un'integrazione che usa quella
    parola per altro comparirebbe come servizio.

    Mutazione: accettare qualunque stringa -- rossa."""
    assert services_named({"actions": [{"action": "non-un-servizio"}]}) == []


def test_i_DOPPIONI_si_dicono_una_volta_sola():
    """Un'automazione che accende dieci luci chiama `light.turn_on` dieci
    volte: dirlo dieci volte renderebbe illeggibile proprio la riga che deve
    farsi leggere.

    Mutazione: non deduplicare -- rossa."""
    detti = services_named({"actions": [{"action": "light.turn_on"},
                                        {"action": "light.turn_on"},
                                        {"action": "lock.unlock"}]})

    assert detti == ["light.turn_on", "lock.unlock"]


def test_l_ORDINE_e_quello_del_corpo():
    """Si legge nell'ordine in cui le cose succedono: riordinare
    alfabeticamente renderebbe piu' difficile seguire cosa fa l'automazione.

    Mutazione ESEGUITA: `sorted()` -- rossa."""
    detti = services_named({"actions": [{"action": "notify.paolo"},
                                        {"action": "light.turn_on"}]})

    assert detti == ["notify.paolo", "light.turn_on"]


def test_un_corpo_VUOTO_o_assente_non_fa_cadere_niente():
    """Questa funzione sta sul percorso di ogni anteprima: un'eccezione qui
    impedirebbe di proporre invece di impedire di sbagliare.

    Mutazione: indicizzare senza difendersi -- rossa."""
    for niente in (None, {}, {"actions": None}, {"actions": "non-una-lista"}):
        assert services_named(niente) == []


def test_un_corpo_PROFONDISSIMO_non_gira_per_sempre():
    """Il corpo puo' arrivare dal modello, e un corpo che si annida
    all'infinito bloccherebbe l'anteprima invece di produrla.

    Mutazione: nessun limite di profondita' -- rossa (ricorsione infinita)."""
    corpo = {"actions": [{"action": "light.turn_on"}]}
    for _ in range(300):
        corpo = {"actions": [{"choose": [{"sequence": [corpo]}]}]}

    assert services_named(corpo) == [] or "light.turn_on" in services_named(corpo)


# --- e l'anteprima lo MOSTRA ------------------------------------------------

def test_l_anteprima_di_una_modifica_dice_cosa_chiamera():
    """**Il reperto B-4.** `alias · triggers: 1 · actions: 2` non dice al
    proprietario niente di cio' che sta approvando.

    Mutazione ESEGUITA: rimesso il solo conteggio -- rossa."""
    from hiris.app.action.construction.workshop import _compatta

    detto = _compatta({"alias": "Buonanotte",
                       "actions": [{"action": "shell_command.riavvia"}]})

    assert "shell_command.riavvia" in detto, (
        "l'anteprima non nomina il servizio: il sì resta disinformato")


def test_e_continua_a_dire_anche_i_CONTEGGI():
    """I conteggi non erano sbagliati, erano insufficienti: dicono la
    dimensione della modifica, che e' un fatto utile accanto ai nomi.

    Mutazione: sostituire i conteggi coi nomi -- rossa."""
    detto = _compatta_({"alias": "X", "triggers": [1], "actions": [
        {"action": "light.turn_on"}]})

    assert "triggers: 1" in detto and "light.turn_on" in detto


def test_un_corpo_SENZA_servizi_non_inventa_una_riga():
    """Una scena non chiama servizi: scrivere «Chiama: » seguito da niente
    sarebbe rumore che insegna a saltare la riga.

    Mutazione ESEGUITA: scrivere sempre l'etichetta -- rossa."""
    detto = _compatta_({"name": "Sera", "entities": {"light.x": "on"}})

    assert "chiama" not in detto.lower()


def _compatta_(corpo):
    from hiris.app.action.construction.workshop import _compatta

    return _compatta(corpo)


# --- e la PAGINA lo riceve, invece di ricavarselo ---------------------------

def test_la_riga_dell_archivio_porta_i_servizi_dei_DUE_lati():
    """**Perche' li manda il server e non li ricava la pagina.**

    La pagina ha gia' `prima` e `dopo` interi e potrebbe camminarli in
    JavaScript. Sarebbe lo stesso cammino scritto due volte, in due
    linguaggi, libero di divergere -- e a divergere sarebbe quello che nessuno
    riesegue. L'estrattore resta uno, in Python, e la pagina riceve la
    risposta.

    **Due lati e non uno**: cio' che serve al proprietario e' cosa CAMBIA, e
    una lista sola non lo direbbe.

    Mutazione ESEGUITA: mandare solo `chiama_dopo` -- rossa."""
    from hiris.app.action.construction.revisions import _row

    riga = _row({
        "id": "p1", "creata_ts": 1, "aggiornata_ts": 1, "stato": "in_attesa",
        "gesto": "modifica", "dominio": "automation", "chiave": "x",
        "origine": "chat", "turno": "t1", "frase": "f",
        "prima_json": '{"actions": [{"action": "light.turn_on"}]}',
        "dopo_json": '{"actions": [{"action": "light.turn_on"},'
                     ' {"action": "shell_command.riavvia"}]}',
        "helper_json": None, "anteprima": "a", "esecuzione_id": None,
        "motivo": None})

    assert riga["chiama_prima"] == ["light.turn_on"]
    assert riga["chiama_dopo"] == ["light.turn_on", "shell_command.riavvia"]


def test_e_un_lato_ASSENTE_da_una_lista_vuota_non_un_buco():
    """Una creazione non ha un «prima». Mandare `None` costringerebbe la
    pagina a un ramo in piu' per dire la stessa cosa che dice una lista
    vuota.

    Mutazione: tornare `None` -- rossa."""
    from hiris.app.action.construction.revisions import _row

    riga = _row({
        "id": "p1", "creata_ts": 1, "aggiornata_ts": 1, "stato": "in_attesa",
        "gesto": "crea", "dominio": "scene", "chiave": "x",
        "origine": "chat", "turno": "t1", "frase": "f",
        "prima_json": None, "dopo_json": '{"entities": {"light.x": "on"}}',
        "helper_json": None, "anteprima": "a", "esecuzione_id": None,
        "motivo": None})

    assert riga["chiama_prima"] == [] and riga["chiama_dopo"] == []
