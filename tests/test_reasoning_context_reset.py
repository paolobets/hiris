"""fetta "il ponte riceve il nucleo" (parita' A, Task 5, domanda aperta 7):
il `context_json` di un job risolto -- via `submit()` (Task 1 il risolve) o
via `sweep_expired()` (Task 1 il fa scadere) -- non deve piu' restare nel
file `reasoning.db` fino alla potatura a 7 giorni. Dal Task 2 quel campo
porta il nucleo per intero: aree, dispositivi, entita' e "cio' che le
persone hanno detto" (`hiris/app/home_space/briefing.py`) -- non un dato tecnico.

Questo file pinna il comportamento voluto su ENTRAMBE le strade di
chiusura di un job, non solo una:
  ① submit() azzera il context, la decision resta intatta;
  ② sweep_expired() azzera il context sulla riga persistita, e il valore
     di ritorno del metodo (letto PRIMA dell'update, per il log dello
     sweep) porta ancora `kind` -- il log di `_reasoning_sweep` non
     regredisce;
  ③ PRIMA della risoluzione, durante il volo, il context e' intero --
     azzerarlo troppo presto romperebbe il ponte, che lo legge dopo il
     claim (`agent/runner.py::_reason_chat`);
  ④ un ricordo seminato nel nucleo, arrivato per davvero nel job (come
     `test_job_context_porta_il_nucleo_identico_al_ramo_sincrono` in
     test_chat_subscription_path.py dimostra), non si ritrova piu' nel
     file `reasoning.db` sul disco dopo che il job e' stato risolto -- la
     prova che il punto del task e' raggiunto, non solo la sua forma.
"""
import json
import os
import sqlite3

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hiris.app.reasoning.queue import ReasoningQueue


@pytest.fixture
def q(tmp_path):
    x = ReasoningQueue(str(tmp_path / "r.db"))
    yield x
    x.close()


# ---------------------------------------------------------------------------
# ① submit() azzera il context, la decision resta intatta
# ---------------------------------------------------------------------------

def test_submit_azzera_context_ma_lascia_intatta_la_decision(q):
    q.enqueue("chat", {}, {"contesto": "## La casa\nCucina: 2 luci"},
              deadline_ts=100.0, job_id="J", now=1.0)
    claimed = q.claim(now=2.0)
    ok = q.submit("J", claimed["nonce"], {"reply": "ecco la risposta"}, now=3.0)
    assert ok is True

    job = q.get("J")
    assert job["context"] == {}
    assert job["decision"] == {"reply": "ecco la risposta"}
    assert job["status"] == "decided"


# ---------------------------------------------------------------------------
# ② sweep_expired() azzera il context sulla riga persistita; il valore di
# ritorno (costruito sulla riga letta PRIMA dell'update) porta ancora `kind`
# -- il log di `_reasoning_sweep` (server.py) non regredisce.
# ---------------------------------------------------------------------------

def test_sweep_expired_azzera_context_ma_il_row_restituito_porta_ancora_kind(q):
    q.enqueue("chat", {}, {"contesto": "## La casa\nCucina: 2 luci"},
              deadline_ts=5.0, job_id="E", now=1.0)

    swept = q.sweep_expired(now=10.0)

    # Il valore di ritorno di QUESTA chiamata -- non una rilettura del DB --
    # e' costruito sulla riga letta prima dell'update: il log dello sweep
    # (che usa solo `kind`) non deve regredire.
    assert len(swept) == 1
    assert swept[0]["job_id"] == "E"
    assert swept[0]["kind"] == "chat"

    # Ma la riga PERSISTITA e' gia' azzerata: una nuova lettura lo conferma.
    job = q.get("E")
    assert job["context"] == {}
    assert job["status"] == "expired"


# ---------------------------------------------------------------------------
# ③ PRIMA della risoluzione, durante il volo, il context e' intero -- e' cio'
# che il runner claima (agent/runner.py::_reason_chat legge job["context"]
# dal ritorno di claim()). Azzerarlo troppo presto romperebbe il ponte.
# ---------------------------------------------------------------------------

def test_context_intero_prima_del_submit_durante_il_volo(q):
    contesto_originale = {"contesto": "## La casa\nCucina: 2 luci",
                           "history": [{"role": "user", "content": "ciao"}]}
    q.enqueue("chat", {}, contesto_originale, deadline_ts=100.0, job_id="J", now=1.0)

    # Ancora 'pending': il contesto e' intero.
    assert q.get("J")["context"] == contesto_originale

    # Claimed (il runner lo prende in mano): ancora intero -- e' esattamente
    # cio' che _reason_chat legge per rispondere.
    claimed = q.claim(now=2.0)
    assert claimed["context"] == contesto_originale
    assert q.get("J")["context"] == contesto_originale

    # Solo submit() lo azzera.
    q.submit("J", claimed["nonce"], {"reply": "ok"}, now=3.0)
    assert q.get("J")["context"] == {}


def test_context_intero_prima_dello_sweep_durante_il_volo(q):
    contesto_originale = {"contesto": "## La casa\nCucina: 2 luci"}
    q.enqueue("chat", {}, contesto_originale, deadline_ts=5.0, job_id="E", now=1.0)

    # Ancora 'pending', deadline non ancora superato: il contesto e' intero.
    assert q.get("E")["context"] == contesto_originale

    # Solo sweep_expired() (deadline superato) lo azzera.
    q.sweep_expired(now=10.0)
    assert q.get("E")["context"] == {}


# ---------------------------------------------------------------------------
# Il job resta distinguibile da un job mai esistito: stato e contabilita'
# sopravvivono all'azzeramento, solo il contenuto sparisce.
# ---------------------------------------------------------------------------

def test_il_job_risolto_resta_distinguibile_da_un_job_mai_esistito(q):
    base = 1_700_000_000.0  # arbitrary anchor timestamp (stessa convenzione di test_chat_caps.py)
    q.enqueue("chat", {}, {"contesto": "qualcosa"}, deadline_ts=base + 100, job_id="J", now=base)
    claimed = q.claim(now=base + 1)
    q.submit("J", claimed["nonce"], {"reply": "ok"}, now=base + 2)

    job = q.get("J")
    assert job is not None
    assert job["job_id"] == "J"
    assert job["status"] == "decided"
    assert job["kind"] == "chat"
    assert job["decision"] == {"reply": "ok"}
    assert job["context"] == {}

    # Un job mai esistito resta None -- non si confonde con un job azzerato.
    assert q.get("non-esiste") is None

    # Il conteggio giornaliero (contabilita') non e' toccato dall'azzeramento.
    assert q.count_exchanges_today(now=base + 3) == 1


def test_il_job_scaduto_resta_distinguibile_da_un_job_mai_esistito(q):
    base = 1_700_000_000.0
    q.enqueue("chat", {}, {"contesto": "qualcosa"}, deadline_ts=base + 5, job_id="E", now=base)
    q.sweep_expired(now=base + 10)

    job = q.get("E")
    assert job is not None
    assert job["job_id"] == "E"
    assert job["status"] == "expired"
    assert job["kind"] == "chat"
    assert job["context"] == {}

    assert q.get("non-esiste") is None
    assert q.count_exchanges_today(now=base + 20) == 1


# ---------------------------------------------------------------------------
# ④ un ricordo seminato nel nucleo non si ritrova piu' nel FILE reasoning.db
# dopo la risoluzione -- letto direttamente da sqlite, non dal wrapper
# Python (che gia' restituirebbe {} per costruzione: qui si verifica che il
# contenuto non sopravviva nemmeno sul disco).
# ---------------------------------------------------------------------------

from hiris.app.api.handlers_chat import handle_chat, handle_chat_reply_poll
from hiris.app.chat_settings import ChatSettings
from hiris.app.chat_store import close_all_stores
from hiris.app.home_space.store import HomeSpaceStore
from hiris.app.memory.store import MemoryStore


@pytest.fixture(autouse=True)
def _reset_chat_store():
    close_all_stores()
    yield
    close_all_stores()
@pytest.fixture(autouse=True)
def il_piano_puo_rispondere(monkeypatch):
    """Il token del piano: senza, dal Task 14 il turno NON viene accodato.

    «Ponte acceso senza token» ha smesso di essere uno stato in cui il
    messaggio muore in coda: e' un RIPIEGO, e il turno scende alla catena nella
    stessa richiesta. Un'app di prova col ponte acceso e senza token non
    descrive piu' il ponte, quindi ogni test di questo file che parla del job
    accodato sarebbe diventato un test su un'altra cosa."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token-di-prova")



@pytest.mark.asyncio
async def test_un_ricordo_seminato_non_si_ritrova_piu_nel_file_dopo_la_risoluzione(tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = str(tmp_path / "reasoning.db")

    reasoning_queue = ReasoningQueue(db_path)
    impostazioni = ChatSettings(name="test-agent", system_prompt="Sei HIRIS.")

    app = web.Application()
    app["reasoning_queue"] = reasoning_queue
    app["impostazioni_chat"] = impostazioni
    app["data_dir"] = data_dir
    app["ponte_attivo"] = True

    archivio_casa = HomeSpaceStore(str(tmp_path / "casa.db"))
    archivio_casa.replace({
        "piani": [{"floor_id": "terra", "name": "Piano terra", "level": 0}],
        "aree": [{"area_id": "cucina", "name": "Cucina", "floor_id": "terra"}],
        "dispositivi": [],
        "entita": [{"entity_id": "light.cucina", "name": "Faretti", "area_id": "cucina"}],
        "etichette": [], "categorie": [], "integrazioni": [],
    })
    archivio_memoria = MemoryStore(str(tmp_path / "memoria.db"))
    ricordo_segreto = "Il codice del cancello e' 1974, non dirlo a nessuno"
    archivio_memoria.remember(ricordo_segreto, "paolo")
    app["archivio_casa"] = archivio_casa
    app["archivio_memoria"] = archivio_memoria

    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/chat/reply/{job_id}", handle_chat_reply_poll)

    try:
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/chat", json={"message": "che c'e' in cucina?"})
            assert resp.status == 202
            job_id = (await resp.json())["job_id"]

            # Prova che il ricordo e' arrivato per davvero nel job (altrimenti
            # il test proverebbe poco): sia via API sia via lettura diretta
            # del file.
            contesto_in_volo = reasoning_queue.get(job_id)["context"]["contesto"]
            assert ricordo_segreto in contesto_in_volo
            raw_pending = sqlite3.connect(db_path).execute(
                "SELECT context_json FROM reasoning_jobs WHERE job_id=?", (job_id,)
            ).fetchone()[0]
            assert ricordo_segreto in raw_pending

            # Il ponte risolve il job (claim + submit), come farebbe il runner
            # esterno reale.
            claimed = reasoning_queue.claim(now=5.0)
            assert claimed["job_id"] == job_id
            assert ricordo_segreto in claimed["context"]["contesto"]
            ok = reasoning_queue.submit(job_id, claimed["nonce"],
                                        {"reply": "in cucina ci sono i faretti"}, now=6.0)
            assert ok is True

            # Dopo la risoluzione: il ricordo NON e' piu' nel file, letto
            # direttamente da sqlite (non dal wrapper, che gia' lo azzererebbe
            # per costruzione -- qui si verifica il disco).
            raw_after = sqlite3.connect(db_path).execute(
                "SELECT context_json FROM reasoning_jobs WHERE job_id=?", (job_id,)
            ).fetchone()[0]
            assert ricordo_segreto not in raw_after
            assert "Cucina" not in raw_after
            assert raw_after == "{}"

            # Il job resta risolvibile e la risposta arriva: solo il contesto
            # e' sparito, non il record.
            job = reasoning_queue.get(job_id)
            assert job["status"] == "decided"
            assert job["decision"]["reply"] == "in cucina ci sono i faretti"
            assert job["context"] == {}

            # m-F della review del Task 5: la rotta di poll era CABLATA e mai
            # chiamata -- il giro si chiudeva sul wrapper Python invece che
            # sull'HTTP che vede l'utente. Ora si chiude dove si chiude
            # davvero: la risposta arriva all'utente DOPO l'azzeramento, cioe'
            # azzerare il contesto non gli toglie niente.
            poll = await client.get(f"/api/chat/reply/{job_id}")
            assert poll.status == 200
            corpo = await poll.json()
            assert corpo["status"] == "done"
            assert corpo["reply"] == "in cucina ci sono i faretti"
            assert ricordo_segreto not in json.dumps(corpo, ensure_ascii=False)
    finally:
        archivio_casa.close()
        archivio_memoria.close()
        reasoning_queue.close()
