"""Cancellare cancella, e conservare si dichiara (reperto C-6, 23/09/2026).

Quattro fatti che sono lo stesso problema — **il bottone dice una cosa e il
disco ne fa un'altra**:

1. La cancellazione della conversazione svuota `chat.db`, ma la **risposta del
   modello** resta in `reasoning.db`. Solo la *domanda* veniva azzerata alla
   consegna (`submit` mette `context_json='{}'`); la risposta restava fino
   alla potatura a sette giorni.
2. I **ricordi** restano per sempre — una scelta, e giusta, ma dichiarata nel
   codice e mai in pagina.
3. La conservazione di `osservazioni.db` copriva **una tabella su otto**.
4. `vault.db` conteneva «DATI PERSONALI IN CHIARO» di un'installazione
   precedente, e il codice lo *annunciava all'avvio* invece di deciderlo.

**Perché la risposta non si azzera alla prima consegna**, ma poco dopo: un
ricaricamento della pagina rifà il poll sullo stesso lavoro, e una risposta
azzerata all'istante gli tornerebbe come «non è arrivata in tempo» — il
contrario di ciò che il reperto vuole. Si segna la consegna e si dimentica al
giro di spazzata successivo: il record resta (serve alla contabilità), il
contenuto se ne va.
"""
import pytest

from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture()
def coda(tmp_path):
    q = ReasoningQueue(str(tmp_path / "reasoning.db"))
    try:
        yield q
    finally:
        q.close()


def _turno(coda, *, now=1_000.0):
    jid = coda.enqueue("chat", {"a": 1}, {"domanda": "che ore sono in salotto?"},
                       now + 300, now=now)
    lavoro = coda.claim(now)
    assert coda.submit(jid, lavoro["nonce"], {"reply": "Le 15:40."}, now)
    return jid


def test_la_DOMANDA_si_azzera_alla_consegna(coda):
    """Cio' che gia' funzionava, e che non deve smettere: il contesto -- la
    casa, la cronologia -- esce dall'archivio quando il turno si chiude.

    Mutazione: togliere `context_json='{}'` da `submit` -- rossa."""
    jid = _turno(coda)

    assert coda.get(jid)["context"] == {}


def test_la_RISPOSTA_resta_finche_non_e_CONSEGNATA(coda):
    """La contropartita, e vale quanto il reperto: un ricaricamento della
    pagina rifa' il poll sullo stesso lavoro. Una risposta azzerata all'istante
    tornerebbe come «non e' arrivata in tempo».

    Mutazione ESEGUITA: dimenticare la decisione dentro `submit` -- rossa."""
    jid = _turno(coda)

    assert coda.get(jid)["decision"]["reply"] == "Le 15:40."


def test_la_consegna_si_segna_UNA_VOLTA_SOLA(coda):
    """Il momento che conta e' il PRIMO. Se la pagina rifa' il poll -- un
    ricaricamento, due schede aperte -- riscrivere il momento allungherebbe la
    finestra a ogni sguardo, e una conversazione lasciata aperta terrebbe la
    risposta sul disco per sempre: il reperto tornerebbe dalla porta di
    servizio.

    **Questa proprieta' era scritta nel docstring e non provata**: la
    mutazione che toglie `AND delivered_ts IS NULL` passava verde.

    Mutazione ESEGUITA: togliere `AND delivered_ts IS NULL` -- rossa."""
    jid = _turno(coda)
    coda.mark_delivered(jid, 1_000.0)
    coda.mark_delivered(jid, 9_000.0)

    # Se il secondo sguardo avesse riscritto il momento, questa finestra non
    # lo prenderebbe.
    assert coda.forget_delivered(before_ts=2_000.0) == 1


def test_dopo_la_consegna_la_risposta_si_DIMENTICA(coda):
    """**Il reperto.** Prima restava fino alla potatura a sette giorni, molto
    oltre il tempo in cui serve a qualcuno -- e dopo che il proprietario aveva
    cancellato la conversazione.

    Mutazione ESEGUITA: non dimenticare -- rossa."""
    jid = _turno(coda)
    coda.mark_delivered(jid, 1_000.0)

    dimenticati = coda.forget_delivered(before_ts=2_000.0)

    assert dimenticati == 1
    assert coda.get(jid)["decision"] == {}


def test_una_consegna_APPENA_fatta_non_si_dimentica(coda):
    """La finestra e' quella che tiene in piedi il ricaricamento della pagina.
    Senza, il reperto si chiuderebbe rompendo una cosa che funziona.

    Mutazione ESEGUITA: dimenticare senza guardare il momento -- rossa."""
    jid = _turno(coda)
    coda.mark_delivered(jid, 1_900.0)

    assert coda.forget_delivered(before_ts=1_000.0) == 0
    assert coda.get(jid)["decision"]["reply"] == "Le 15:40."


def test_un_turno_MAI_consegnato_non_si_dimentica(coda):
    """Un turno dell'analista che nessuno ha ancora raccolto deve poter essere
    raccolto: dimenticarlo perche' e' vecchio perderebbe il lavoro pagato.

    Mutazione ESEGUITA: dimenticare in base a `decided_ts` invece che alla
    consegna -- rossa."""
    jid = _turno(coda)

    assert coda.forget_delivered(before_ts=9_999.0) == 0
    assert coda.get(jid)["decision"]["reply"] == "Le 15:40."


def test_il_RECORD_resta_dopo_la_dimenticanza(coda):
    """Sparisce il contenuto, non la riga: il conteggio giornaliero del ponte e
    la potatura contano le righe, e togliere la riga qui falserebbe il tetto
    che il proprietario ha impostato.

    Mutazione ESEGUITA: cancellare la riga invece di svuotarla -- rossa."""
    jid = _turno(coda)
    coda.mark_delivered(jid, 1_000.0)
    coda.forget_delivered(before_ts=2_000.0)

    riga = coda.get(jid)
    assert riga is not None
    assert riga["status"] == "decided"


def test_dimenticare_DUE_VOLTE_non_conta_due_volte(coda):
    """Il numero che torna finisce in una riga di registro: «ho dimenticato N
    risposte». Contare due volte la stessa direbbe che il prodotto sta
    lavorando mentre gira a vuoto.

    Mutazione ESEGUITA: togliere il filtro su cio' che e' gia' vuoto --
    rossa."""
    jid = _turno(coda)
    coda.mark_delivered(jid, 1_000.0)

    assert coda.forget_delivered(before_ts=2_000.0) == 1
    assert coda.forget_delivered(before_ts=2_000.0) == 0
