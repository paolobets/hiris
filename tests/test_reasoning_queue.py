import pytest
from hiris.app.reasoning.queue import ReasoningQueue

@pytest.fixture
def q(tmp_path):
    x = ReasoningQueue(str(tmp_path / "r.db")); yield x; x.close()

def test_enqueue_claim_oldest_first(q):
    a = q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {"x": 1}}, deadline_ts=100.0, job_id="A", now=1.0)
    b = q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {"x": 2}}, deadline_ts=100.0, job_id="B", now=2.0)
    c = q.claim(now=10.0)
    assert c["job_id"] == "A" and c["nonce"] and c["context"]["snapshot"]["x"] == 1
    c2 = q.claim(now=10.0)
    assert c2["job_id"] == "B"
    assert q.claim(now=10.0) is None  # nessun altro pending

def test_claim_skips_expired(q):
    q.enqueue("holistic", {}, {}, deadline_ts=5.0, job_id="OLD", now=1.0)
    assert q.claim(now=10.0) is None  # già scaduto → non claimabile

def test_submit_valid_and_nonce_rules(q):
    q.enqueue("holistic", {"signal_kind": "holistic"}, {}, deadline_ts=100.0, job_id="J", now=1.0)
    c = q.claim(now=10.0)
    assert q.submit("J", "wrong-nonce", {"verdict": "anomalia"}, now=11.0) is False
    assert q.submit("J", c["nonce"], {"verdict": "anomalia", "message": "ok"}, now=11.0) is True
    # doppia submit rifiutata (non più 'claimed')
    assert q.submit("J", c["nonce"], {"verdict": "anomalia"}, now=12.0) is False
    assert q.get("J")["status"] == "decided"

def test_submit_expired_rejected(q):
    q.enqueue("holistic", {}, {}, deadline_ts=20.0, job_id="J", now=1.0)
    c = q.claim(now=10.0)
    assert q.submit("J", c["nonce"], {"verdict": "anomalia"}, now=25.0) is False  # scaduto

def test_sweep_expired_marks_and_returns(q):
    q.enqueue("holistic", {"signal_kind": "holistic"}, {"snapshot": {}}, deadline_ts=5.0, job_id="E", now=1.0)
    q.enqueue("holistic", {}, {}, deadline_ts=100.0, job_id="LIVE", now=1.0)
    swept = q.sweep_expired(now=10.0)
    assert [s["job_id"] for s in swept] == ["E"]
    assert q.get("E")["status"] == "expired"
    assert q.get("LIVE")["status"] == "pending"
    assert q.sweep_expired(now=10.0) == []  # già marcato

def test_prune(q):
    q.enqueue("holistic", {}, {}, deadline_ts=5.0, job_id="E", now=1.0)
    q.sweep_expired(now=10.0)
    assert q.prune(before_ts=100.0) == 1
    assert q.get("E") is None


# ---------------------------------------------------------------------------
# ReasoningQueue.has_pending_chat -- spostati qui da test_chat_caps.py
# (fetta E4 Task 5, "un bot solo"): il metodo perde il parametro
# `chatbot_id` (c'e' UNA conversazione, non piu' una per chatbot -- "in
# flight per questo id" e "in flight" erano gia' la stessa domanda), quindi
# non c'e' piu' nulla da "scopare per agente" da testare: sono unit test
# della coda, la loro casa naturale e' qui insieme alle altre.
# I casi rimossi rispetto all'originale (has_pending_chat_scoped_to_agent_id,
# has_pending_chat_false_for_missing_agent_id,
# has_pending_chat_recognizes_legacy_agent_id_context_key) pinnavano
# esattamente lo scoping-per-id e il fallback agent_id/chatbot_id nel
# context_json che il Task 5 ha tolto: verificato che cadono per costruzione
# prima di rimuoverli (`TypeError: has_pending_chat() takes from 1 to 2
# positional arguments but 3 were given` chiamando `q.has_pending_chat(id,
# now=...)` con due argomenti posizionali contro la nuova firma).
# ---------------------------------------------------------------------------

def test_has_pending_chat_false_when_no_jobs(q):
    assert q.has_pending_chat() is False


def test_has_pending_chat_true_for_pending_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    # `now` explicit and still before deadline_ts (100.0) -- job is
    # genuinely in-flight, not merely unswept-but-expired.
    assert q.has_pending_chat(now=50.0) is True


def test_has_pending_chat_true_for_claimed_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    q.claim(now=2.0)
    assert q.has_pending_chat(now=50.0) is True


def test_has_pending_chat_false_after_submit_resolves_job(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    claimed = q.claim(now=2.0)
    q.submit(claimed["job_id"], claimed["nonce"], {"reply": "ciao"}, now=3.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_false_after_expiry(q):
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    q.sweep_expired(now=200.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_ignores_non_chat_kinds(q):
    q.enqueue("holistic", {"signal_kind": "holistic", "entity_id": "home",
              "severity_hint": "info", "evidence": {}, "ts": 1.0},
              {}, deadline_ts=100.0, now=1.0)
    assert q.has_pending_chat() is False


def test_has_pending_chat_false_for_expired_but_unswept_job(q):
    """Task 5 fix (Task 3 review, MEDIUM), preservato attraverso la
    semplificazione del Task 5 ("un bot solo"): un job chat il cui deadline
    e' gia' passato ma che non e' mai stato spazzato (es. BRIDGE_ENABLED
    off, o lo sweep dei 2 minuti non e' ancora girato) non deve contare come
    "in flight" -- altrimenti risponderebbe 409 per sempre senza modo di
    liberarsi. Ancora status='pending' nel DB (nessuna sweep_expired qui),
    ma `now` e' oltre il suo deadline_ts."""
    q.enqueue("chat", {}, {}, deadline_ts=100.0, now=1.0)
    # Still 'pending' in the DB -- no sweep_expired call -- but `now` (200.0)
    # is already past deadline_ts (100.0).
    assert q.has_pending_chat(now=200.0) is False


# ---------------------------------------------------------------------------
# Il ripiego (fetta «la catena diventa l'unica verita'», Task 14): 'ripiego'
# e' lo stato in cui un turno di chat scaduto viene preso in carico per essere
# rifatto sulla catena. Non e' terminale, e `prune` non lo cancella.
# ---------------------------------------------------------------------------


def _scaduto(q, *, nato=0.0, scade=100.0, kind="chat"):
    return q.enqueue(kind, {}, {"history": [{"role": "user", "content": "ciao"}]},
                     scade, now=nato)


def test_reclamare_uno_scaduto_lo_marca_ripiego_e_restituisce_il_contesto(q):
    """Il contesto INTATTO e' l'unica cosa che rende possibile rifare il turno
    senza ricomporlo da capo -- e ricomporlo da capo darebbe una risposta a una
    domanda leggermente diversa. E' l'unico momento in cui si puo': appena il
    job si chiude, il contesto viene azzerato."""
    jid = _scaduto(q)
    job = q.reclama_scaduto(jid, now=200.0)
    assert job is not None
    assert job["status"] == "ripiego"
    assert job["context"]["history"] == [{"role": "user", "content": "ciao"}]
    assert job["created_ts"] == 0.0 and job["deadline_ts"] == 100.0
    assert q.get(jid)["status"] == "ripiego"


def test_un_job_non_ancora_scaduto_non_si_reclama(q):
    """La prova gemella: il ripiego non e' una scorciatoia che accorcia
    l'attesa. Finche' la scadenza non e' passata, il piano ha la sua
    occasione."""
    jid = _scaduto(q, scade=100.0)
    assert q.reclama_scaduto(jid, now=99.0) is None
    assert q.get(jid)["status"] == "pending"


def test_lo_stesso_job_si_reclama_una_volta_sola(q):
    """La mutua esclusione: due poll concorrenti non possono ripiegare due
    volte lo stesso turno."""
    jid = _scaduto(q)
    assert q.reclama_scaduto(jid, now=200.0) is not None
    assert q.reclama_scaduto(jid, now=201.0) is None


def test_un_job_gia_deciso_o_scaduto_non_si_reclama(q):
    """Chi e' gia' terminale non torna in volo. Un `decided` reclamato
    riscriverebbe una risposta gia' data; un `expired` -- lo sweep e' passato
    prima -- ha gia' perso il contesto, e ripiegare su un contesto vuoto
    manderebbe alla catena una domanda che nessuno ha fatto."""
    deciso = _scaduto(q)
    preso = q.claim(now=1.0)
    q.submit(deciso, preso["nonce"], {"reply": "ok"}, now=2.0)
    assert q.reclama_scaduto(deciso, now=200.0) is None

    scaduto = _scaduto(q)
    q.sweep_expired(now=200.0)
    assert q.get(scaduto)["status"] == "expired"
    assert q.reclama_scaduto(scaduto, now=201.0) is None


def test_solo_i_turni_di_chat_si_ripiegano(q):
    """La catena risponde alle domande delle persone. Un job di un altro tipo
    non ha una conversazione dietro, e ripiegarlo manderebbe al modello un
    contesto che non e' un turno."""
    jid = _scaduto(q, kind="holistic")
    assert q.reclama_scaduto(jid, now=200.0) is None


def test_risolvere_un_ripiego_lo_chiude_e_azzera_il_contesto(q):
    """Stessa disciplina di `submit` e `sweep_expired`: il contesto porta il
    nucleo per intero -- aree, dispositivi, cio' che le persone hanno detto --
    e non deve restare su disco fino alla potatura a 7 giorni."""
    jid = _scaduto(q)
    q.reclama_scaduto(jid, now=200.0)
    assert q.risolvi_ripiego(jid, {"reply": "risposto io", "nota": "n"}, now=210.0) is True
    job = q.get(jid)
    assert job["status"] == "decided"
    assert job["decision"] == {"reply": "risposto io", "nota": "n"}
    assert job["context"] == {}


def test_non_si_risolve_un_ripiego_che_non_e_stato_reclamato(q):
    """Il reclamo E' la mutua esclusione: senza di lui non c'e' niente da
    chiudere, e chiudere comunque significherebbe scrivere una risposta sopra
    un turno che il piano sta ancora servendo."""
    jid = _scaduto(q)
    assert q.risolvi_ripiego(jid, {"reply": "x"}, now=210.0) is False
    assert q.get(jid)["status"] == "pending"


def test_un_ripiego_conta_come_risposta_in_volo(q):
    """E senza il filtro sulla scadenza, che per lui sarebbe sempre passata: la
    chiamata alla catena puo' durare decine di secondi, e un secondo turno
    intanto metterebbe due risposte in volo sulla stessa conversazione."""
    jid = _scaduto(q)
    assert q.has_pending_chat(now=200.0) is False
    q.reclama_scaduto(jid, now=200.0)
    assert q.has_pending_chat(now=200.0) is True
    assert q.has_pending_chat(now=10_000.0) is True
    q.risolvi_ripiego(jid, {"reply": "x"}, now=210.0)
    assert q.has_pending_chat(now=220.0) is False


def test_un_ripiego_schiantato_diventa_failed_e_la_potatura_lo_prende(q):
    """Un ripiego che non finisce mai (processo caduto a metà chiamata)
    resterebbe in volo per sempre: 'ripiego' non e' fra gli stati che `prune`
    cancella, e tiene bloccata la conversazione sul 409."""
    jid = _scaduto(q)
    q.reclama_scaduto(jid, now=200.0)
    assert q.fallisci_ripieghi_bloccati(before_ts=199.0) == 0, (
        "il confine e' il momento del RECLAMO: un ripiego appena cominciato "
        "non e' uno schianto")
    assert q.fallisci_ripieghi_bloccati(before_ts=200.0) == 1
    job = q.get(jid)
    assert job["status"] == "failed"
    assert job["context"] == {}
    assert q.prune(before_ts=1.0) == 1


def test_lo_sweep_non_ruba_il_lavoro_al_poll(q):
    """La convivenza fra i due: il ripiego vive nella rotta di poll (ogni
    3,5 s) e lo sweep gira ogni 2 minuti. `sweep_expired` guarda solo
    'pending'/'claimed', quindi un ripiego in corso non gli appartiene -- se
    glielo rubasse, l'utente leggerebbe «la risposta non e' arrivata in tempo»
    mentre la catena sta scrivendo la sua."""
    jid = _scaduto(q)
    q.reclama_scaduto(jid, now=200.0)
    assert q.sweep_expired(now=10_000.0) == []
    assert q.get(jid)["status"] == "ripiego"
