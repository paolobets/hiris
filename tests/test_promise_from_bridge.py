"""La consegna di un turno di promessa: chi chiude, e cosa resta appeso.

Fetta «le promesse seguono la catena» (22/08/2026). Il turno del ponte
finisce in uno di tre modi, e tutti e tre devono lasciare la promessa in uno
stato che si vede:

  - il modello ha chiamato `conclude` -> la promessa e' gia' chiusa dalla
    rotta MCP, e la consegna non la riapre;
  - il turno finisce senza aver concluso -> fallisce, col motivo che porta
    cio' che il modello aveva detto al suo posto (la forma della v3.9.3);
  - il turno scade -> fallisce dichiarando l'attesa.

Una promessa `in_corso` per sempre e' peggio di una fallita: non si vede.

**`q.submit()` azzera `context_json`.** L'id della promessa sopravvive perche'
l'accodamento lo mette anche in `wake`, che non viene azzerato -- e questo
file e' anche il pin di quella dipendenza: se un giorno lo si togliesse da
`wake` fidandosi del contesto, il primo test qui sotto cadrebbe invece di
lasciar fallire in silenzio ogni promessa servita dal ponte.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

from hiris.app import server
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import _get_store, close_all_stores, load_history
from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.store import AgendaStore
from hiris.app.provider_occurrences import OccurrenceRegistry
from hiris.app.reasoning.consegna import consegna as consegna_turno
from hiris.app.reasoning.queue import ReasoningQueue

TOKEN = "token-di-prova-della-consegna"
ADESSO = 1787324400.0
# Il filo di chi ha chiesto: ogni promessa ne ha uno (spec 2026-09-26 §2).
PAOLO = ChatThread("persona:paolo", "pannello")


@pytest_asyncio.fixture
async def consegna(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)

    app = server.create_app()
    app["ha_client"] = CasaFinta({})
    app["chat_settings"] = ChatSettings()
    app["claude_runner"] = None
    app["theme"] = "auto"
    app["supervisor_ingress_cidrs"] = ["172.30.32.0/23"]
    app["internal_token"] = TOKEN

    coda = ReasoningQueue(str(tmp_path / "reasoning.db"))
    promesse = AgendaStore(str(tmp_path / "promesse.db"))
    app["reasoning_queue"] = coda
    app["agenda"] = promesse
    # Task 3 (ruling 3.8): la cronologia dove finisce la riga breve di un
    # fallimento chiuso da qui.
    app["data_dir"] = str(tmp_path)
    app.on_startup.clear()
    app.on_cleanup.clear()

    client = await aiohttp_client(app)
    try:
        yield client, coda, promesse
    finally:
        close_all_stores()
        promesse.close()
        coda.close()


def _promessa_in_corso(promesse) -> str:
    ident = promesse.create({
        "specie": "chiedi", "frase": "fra un'ora verifica la temperatura",
        "quando_ts": ADESSO + 10, "domanda": "e' aumentata?",
    }, thread=PAOLO, now=ADESSO)["promessa"]["id"]
    assert promesse.prendi(ident, now=ADESSO + 11) is True
    return ident


def _accoda_e_prendi(coda, ident: str) -> dict:
    # La coda si giudica con l'orologio VERO (`_consegna` usa `time.time()`),
    # mentre le promesse ricevono il loro `adesso` come argomento: le due
    # scale non si mescolano, e una scadenza ancorata a `ADESSO` sarebbe gia'
    # passata.
    adesso = time.time()
    coda.enqueue("promessa", {"promessa_id": ident},
                 {"promessa_id": ident, "history": [], "system_prompt": ""},
                 deadline_ts=adesso + 600, now=adesso)
    return coda.claim(now=adesso + 1)


async def _consegna(client, job, decision):
    # Come il lavoratore del ponte (A-23, 06/10/2026): la consegna e' una
    # chiamata dentro il processo, sull'app vera, non piu' una rotta HTTP.
    return await consegna_turno(client.app, job["job_id"], job["nonce"],
                                decision, time.time())


@pytest.mark.asyncio
async def test_un_turno_che_finisce_senza_concludere_fa_fallire_la_promessa(consegna):
    """Stessa forma della v3.9.3 sul ramo sincrono: il motivo porta cio' che
    il modello aveva risposto al posto di concludere. Senza, si tornerebbe al
    «non so cosa dirti» che e' costato un'ora di indagine."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    risposta = await _consegna(client, job, {
        "reply": "Ho letto le otto stanze, ma da qui non posso mandarti una notifica."})

    assert risposta == "promessa_senza_conclusione"
    p = promesse.read(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]
    assert "non posso mandarti una notifica" in p["motivo"]


@pytest.mark.asyncio
async def test_un_turno_che_finisce_senza_concludere_lascia_un_fallimento_nel_registro(
    consegna,
):
    """Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`:
    prima di questa correzione la consegna sopra faceva fallire la promessa
    (si vede in `keeper/store.py`) ma non toccava mai `OccurrenceRegistry` --
    Modelli avrebbe continuato a dire «nessuna osservazione da quando l'add-on
    e' partito» un attimo dopo che il proprietario aveva letto in chiaro un
    turno del ponte fallito."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    await _consegna(client, job, {
        "reply": "Ho letto le otto stanze, ma da qui non posso mandarti una notifica."})

    esito = client.app["occurrence_registry"].occurrence("subscription")
    assert esito is not None, (
        "una promessa del ponte finita senza «conclude» non ha lasciato "
        "traccia nel registro degli esiti")
    assert esito["tipo"] == "rifiutato", (
        f"registrata come {esito['tipo']!r} invece che come fallimento")


@pytest.mark.asyncio
async def test_se_concludi_e_gia_arrivato_la_consegna_non_riapre_niente(consegna):
    """`conclude` chiude SUBITO dalla rotta MCP (non aspetta la consegna):
    quando il job si chiude la promessa e' gia' mantenuta, e riaprirla
    cancellerebbe un testo che l'utente puo' gia' aver letto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)
    promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                      text="in bagno +0,4 gradi", avvisare=True)

    await _consegna(client, job, {"reply": "qualunque cosa"})

    p = promesse.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["testo"] == "in bagno +0,4 gradi"


@pytest.mark.asyncio
async def test_una_consegna_senza_risposta_fallisce_lo_stesso_dicendolo(consegna):
    """Il ramo in cui non c'e' proprio niente da riportare: la promessa
    fallisce comunque -- restare `in_corso` sarebbe invisibile -- e il motivo
    torna alla frase di prima invece di inventare un virgolettato vuoto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    await _consegna(client, job, {})

    p = promesse.read(ident)
    assert p["stato"] == "fallita"
    assert "non ha concluso" in p["motivo"]
    assert "«»" not in p["motivo"]


@pytest.mark.asyncio
async def test_una_consegna_di_chat_non_tocca_le_promesse(consegna):
    """Il ramo della chat resta quello di sempre: un job di chat non deve
    poter far fallire una promessa che sta correndo accanto."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    adesso = time.time()
    coda.enqueue("chat", {}, {"history": []}, deadline_ts=adesso + 600, now=adesso)
    job = coda.claim(now=adesso + 1)

    await _consegna(client, job, {"reply": "ciao"})

    assert promesse.read(ident)["stato"] == "in_corso"


# --- la scadenza: niente resta appeso ---------------------------------------

def test_un_turno_scaduto_sul_piano_fa_fallire_la_promessa(tmp_path):
    """Una promessa `in_corso` per sempre non si vede: `risana()` la
    chiuderebbe solo al prossimo riavvio, cioe' forse mai.

    **L'attesa detta e' quella del turno, non quella di adesso** (S-02, Tappa
    6 Task 2: la scadenza viaggia col turno). Il turno e' partito con dieci
    minuti; nel frattempo l'utente ha portato la scadenza a tre. Fino alla
    Tappa 6 il motivo diceva «3 minuti»: una durata che quel turno non ha
    mai avuto."""
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        app = {"agenda": promesse,
               "models_config": {"ponte": {"scadenza_min": 3}}}

        close_expired_promise(app, {"wake": {"promessa_id": ident},
                                     "created_ts": 100.0, "deadline_ts": 700.0})

        p = promesse.read(ident)
        assert p["stato"] == "fallita"
        assert "10 minuti" in p["motivo"], p["motivo"]
    finally:
        promesse.close()


def test_un_turno_scaduto_sul_piano_lascia_un_fallimento_nel_registro(tmp_path):
    """Rilievo R1 della revisione indipendente sul tratto `v3.22.2..HEAD`: la
    terza strada delle promesse sul ponte -- lo sweep che chiude una promessa
    scaduta senza risposta -- non scriveva nel registro degli esiti quanto le
    altre due. Stessa famiglia `scaduto` del ramo chat (`handlers_chat.py`,
    `family="scaduto"`): il piano non ha rifiutato, non ha risposto."""
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        registry = OccurrenceRegistry(clock=lambda: 999.0)
        app = {"agenda": promesse, "occurrence_registry": registry,
               "models_config": {"ponte": {"scadenza_min": 10}}}

        close_expired_promise(app, {"wake": {"promessa_id": ident},
                                      "created_ts": 100.0, "deadline_ts": 700.0})

        esito = registry.occurrence("subscription")
        assert esito is not None, (
            "una promessa scaduta sul ponte non ha lasciato traccia nel "
            "registro degli esiti")
        assert esito["tipo"] == "rifiutato"
        assert esito["famiglia"] == "scaduto"
    finally:
        promesse.close()


def test_una_promessa_gia_conclusa_dalla_scadenza_non_registra_un_secondo_esito(tmp_path):
    """`conclude` puo' essere arrivato mentre il turno finiva: lo sweep non
    deve scrivere un fallimento sopra un successo gia' registrato altrove."""
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                          text="tutto fermo", avvisare=False)
        registry = OccurrenceRegistry(clock=lambda: 999.0)
        registry.successo("subscription")

        close_expired_promise({"agenda": promesse, "occurrence_registry": registry,
                                "models_config": {}},
                               {"wake": {"promessa_id": ident}})

        assert registry.occurrence("subscription")["tipo"] == "risposto"
    finally:
        promesse.close()


def test_una_promessa_gia_conclusa_non_viene_riaperta_dalla_scadenza(tmp_path):
    """`conclude` puo' essere arrivato mentre il turno finiva: riaprirla
    cancellerebbe un testo che l'utente puo' gia' aver letto."""
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                          text="tutto fermo", avvisare=False)

        close_expired_promise({"agenda": promesse, "models_config": {}},
                               {"wake": {"promessa_id": ident}})

        assert promesse.read(ident)["stato"] == "mantenuta"
    finally:
        promesse.close()


def test_un_job_scaduto_senza_promessa_non_esplode(tmp_path):
    from hiris.app.keeper.outcome import close_expired_promise

    close_expired_promise({"agenda": None, "models_config": {}}, {"wake": {}})


# --- ruling 3.8: i fallimenti chiusi da qui lo dicono nel filo, senza push ----

_FRASE = "fra un'ora verifica la temperatura"


def _chat_rows(cartella):
    conn = _get_store(cartella)._conn
    return (conn.execute("SELECT subject_key FROM chat_sessions").fetchall(),
            conn.execute("SELECT content FROM chat_messages").fetchall())


@pytest.mark.asyncio
async def test_un_turno_senza_conclusione_lascia_una_riga_breve_nel_filo(consegna):
    """Ruling 3.8: una riga sola di HIRIS nel filo di chi l'ha chiesta, che
    nomina la promessa -- nessuna push (la consegna non ha una porta)."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    await _consegna(client, job, {"reply": "ho guardato ma non concludo"})

    righe = load_history(client.app["data_dir"], thread=PAOLO)
    assert len(righe) == 1
    assert righe[0]["role"] == "assistant"
    assert _FRASE in righe[0]["content"]
    assert "non si è potuta mantenere" in righe[0]["content"]


def test_un_turno_scaduto_sul_piano_lascia_una_riga_breve_nel_filo(tmp_path):
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        app = {"agenda": promesse, "data_dir": str(tmp_path),
               "models_config": {"ponte": {"scadenza_min": 10}}}

        # Un job vero porta sempre i due istanti (colonne NOT NULL della
        # coda), e l'attesa detta e' la loro differenza (S-02).
        close_expired_promise(app, {"wake": {"promessa_id": ident},
                                     "created_ts": 100.0, "deadline_ts": 700.0})

        righe = load_history(str(tmp_path), thread=PAOLO)
        assert len(righe) == 1
        assert _FRASE in righe[0]["content"]
        assert "10 minuti" in righe[0]["content"]
    finally:
        close_all_stores()
        promesse.close()


def test_una_scadenza_su_una_promessa_orfana_non_scrive_in_nessun_filo(tmp_path):
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        promesse._conn.execute(
            "INSERT INTO promesse(id,specie,frase,quando_ts,domanda,stato,nata_ts) "
            "VALUES('orfana','chiedi','detta prima',?,'?','in_corso',?)",
            (ADESSO + 10, ADESSO))
        promesse._conn.commit()
        app = {"agenda": promesse, "data_dir": str(tmp_path),
               "models_config": {"ponte": {"scadenza_min": 10}}}

        close_expired_promise(app, {"wake": {"promessa_id": "orfana"}})

        assert promesse.read("orfana")["stato"] == "fallita"
        assert _chat_rows(str(tmp_path)) == ([], [])
    finally:
        close_all_stores()
        promesse.close()


def test_una_scadenza_gia_conclusa_non_scrive_una_seconda_riga(tmp_path):
    from hiris.app.keeper.outcome import close_expired_promise

    promesse = AgendaStore(str(tmp_path / "p.db"))
    try:
        ident = _promessa_in_corso(promesse)
        promesse.concludi(ident, state="mantenuta", now=ADESSO + 20,
                          text="tutto fermo", avvisare=False)

        close_expired_promise({"agenda": promesse, "data_dir": str(tmp_path),
                                "models_config": {}},
                               {"wake": {"promessa_id": ident}})

        assert load_history(str(tmp_path), thread=PAOLO) == []
    finally:
        close_all_stores()
        promesse.close()


@pytest.mark.asyncio
async def test_una_risposta_velenosa_non_entra_nella_riga_del_filo(consegna):
    """Fix round 1, punto 5: la risposta del modello citata nel motivo passa
    dal filtro dei veleni da sola -- una sentinella non torna in chat."""
    client, coda, promesse = consegna
    ident = _promessa_in_corso(promesse)
    job = _accoda_e_prendi(coda, ident)

    await _consegna(client, job, {"reply": "Rate limit — riprova tra poco."})

    assert promesse.read(ident)["stato"] == "fallita"
    assert load_history(client.app["data_dir"], thread=PAOLO) == []
