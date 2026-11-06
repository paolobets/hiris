"""Il numero breve di una proposta: «si' alla 12» (sprint «L'agente», fase 2.3;
D3 del proprietario, 05/11/2026).

L'avviso dice un numero, la chat lo riceve, e `confirm` lo accetta. Il numero
vive in una casa sola, l'archivio delle costruzioni, che lo assegna alla
nascita: cosi' la push, la riga in chat, la pagina e lo strumento dicono lo
stesso (fondamenta 2 e 3).
"""
import os
import sqlite3

import pytest

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import _UNKNOWN_ID, Workshop
from hiris.app.action.journal import Journal
from tests.test_construction_workshop import WorkshopHouse, _intento

ADESSO = 1_756_000_000.0


@pytest.fixture()
def banco(tmp_path):
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    officina = Workshop(WorkshopHouse().client, archivio, cronaca)
    yield officina, archivio
    archivio.close()
    cronaca.close()


def _nasce(archivio, alias, *, now=ADESSO):
    return archivio.propose(operation="crea", domain="automation", key=alias,
                            actor="proponente", exchange="g1", phrase=None,
                            prima=None, dopo={"alias": alias}, helper=[],
                            preview="", stakes="medio", now=now)


def test_i_numeri_nascono_in_fila_e_la_riga_li_porta(tmp_path):
    """Mutazione ESEGUITA (05/11/2026): `propose` che scrive sempre 1 --
    rossa (l'indice unico rifiuta la seconda, e la prova lo vede)."""
    archivio = ConstructionStore(os.path.join(str(tmp_path), "c.db"))
    try:
        nate = [_nasce(archivio, f"a{n}", now=ADESSO + n) for n in range(3)]
        assert [n["numero"] for n in nate] == [1, 2, 3]
        assert archivio.read(nate[1]["id"], now=ADESSO + 5)["numero"] == 2
        assert archivio.id_of_number(3) == nate[2]["id"]
        assert archivio.id_of_number(99) is None
    finally:
        archivio.close()


def test_un_archivio_v7_riceve_i_numeri_nell_ordine_di_nascita(tmp_path):
    """La migrazione 8 da' un numero alle righe che ci sono gia', in ordine di
    nascita, e la prossima continua da li'."""
    path = os.path.join(str(tmp_path), "c.db")
    archivio = ConstructionStore(path)
    nate = [_nasce(archivio, f"a{n}", now=ADESSO + n) for n in range(3)]
    archivio.close()
    # Si riporta l'archivio a com'era alla versione 7: niente numeri.
    conn = sqlite3.connect(path)
    conn.execute("DROP INDEX idx_costruzioni_numero")
    conn.execute("DROP TABLE numerazione")
    conn.execute("ALTER TABLE costruzioni DROP COLUMN numero")
    conn.execute("ALTER TABLE costruzioni DROP COLUMN riga_chat")
    conn.execute("ALTER TABLE costruzioni DROP COLUMN giro")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    archivio = ConstructionStore(path)
    try:
        assert [archivio.read(n["id"], now=ADESSO)["numero"] for n in nate] == [1, 2, 3]
        assert _nasce(archivio, "dopo", now=ADESSO + 9)["numero"] == 4
    finally:
        archivio.close()


def test_un_numero_non_torna_dopo_la_potatura(tmp_path):
    """Revisione, giro 238 (R238-3): la potatura toglie anche la riga col
    numero piu' alto, e il numero dopo non lo riusa. Se tornasse, una vecchia
    riga di chat, «si' alla 2», confermerebbe la proposta nuova.

    Mutazione ESEGUITA (06/11/2026): `propose` di nuovo con
    `MAX(numero) + 1` -- rossa (torna il 1)."""
    archivio = ConstructionStore(os.path.join(str(tmp_path), "c.db"))
    try:
        vecchie = [_nasce(archivio, f"a{n}", now=ADESSO + n) for n in range(2)]
        assert [n["numero"] for n in vecchie] == [1, 2]
        tolte = archivio.prune(now=ADESSO + 400 * 86400)
        assert tolte and archivio.id_of_number(2) is None
        nuova = _nasce(archivio, "dopo", now=ADESSO + 401 * 86400)
        assert nuova["numero"] == 3
    finally:
        archivio.close()

    # Anche riaperto: la numerazione sta sul disco, non nella memoria.
    archivio = ConstructionStore(os.path.join(str(tmp_path), "c.db"))
    try:
        assert _nasce(archivio, "ancora", now=ADESSO + 402 * 86400)["numero"] == 4
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_si_conferma_per_numero_come_per_id(banco):
    """Il numero e' solo un altro nome dell'id: la proposta si applica, e il
    resto del cammino e' quello di sempre.

    Due in sospeso, perche' con una sola anche un `apply` che ignorasse il
    numero la sceglierebbe (`_only_pending`) e la prova non vedrebbe niente.

    Mutazione ESEGUITA (05/11/2026): `apply` che ignora `number` -- rossa
    (con due in sospeso il rifiuto e' l'elenco)."""
    officina, archivio = banco
    nata = await officina.propose(_intento(alias="Luce del portico"), actor="chat",
                                  exchange="turno-1", now=ADESSO)
    altra = await officina.propose(_intento(alias="Luce della cantina"), actor="chat",
                                   exchange="turno-1", now=ADESSO)
    assert (nata["numero"], altra["numero"]) == (1, 2)

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO + 1, number=nata["numero"])

    assert esito.get("eseguito") is True, esito
    assert archivio.read(nata["proposta_id"], now=ADESSO + 2)["stato"] == "applicata"
    assert archivio.read(altra["proposta_id"], now=ADESSO + 2)["stato"] == "in_attesa"


@pytest.mark.asyncio
async def test_un_numero_che_non_c_e_si_rifiuta_come_un_id_che_non_c_e(banco):
    officina, _ = banco

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO, number=42)

    assert esito["eseguito"] is False
    assert esito["errore"] == _UNKNOWN_ID


def _app_with_workshop(officina) -> dict:
    from hiris.app.action.construction.workshop import WORKSHOP_KEY
    from hiris.app.startup import live_values

    return {**live_values(), WORKSHOP_KEY: officina}


@pytest.mark.asyncio
async def test_mind_proposte_dice_le_proposte_from_brain_con_la_forma_della_pagina(banco):
    """Fondamenta 3: i campi che `mind` consegna sono quelli della riga della
    pagina (`revisions._row`), con gli stessi nomi e gli stessi valori. Solo
    le proposte del cervello, in attesa, per numero.

    Mutazione ESEGUITA (05/11/2026): `pending_of` senza il filtro
    sull'origine -- rossa (entra la proposta della chat)."""
    import time

    from hiris.app.api.handlers_chat import create_tool_dispatcher
    from hiris.app.api.soffitto import consente
    from hiris.app.home_space.tools import PROPOSAL_FIELDS
    from hiris.app.steering import PROPOSER_SPECIES

    officina, archivio = banco
    # Adesso, non `ADESSO`: lo strumento legge col suo orologio, e una
    # proposta di un anno fa sarebbe scaduta.
    adesso = time.time()
    await officina.propose(_intento(alias="Dalla chat"), actor="chat",
                           exchange="turno-1", now=adesso)
    from_brain = await officina.propose(_intento(alias="Dal cervello"),
                                          actor=PROPOSER_SPECIES, exchange="g1",
                                          now=adesso)
    dispatcher = create_tool_dispatcher(_app_with_workshop(officina),
                                        soffitto=consente(None, ruolo="amministratore"))

    risposta = await dispatcher.dispatch("mind", {"cosa": "proposte"})

    riga = archivio.read(from_brain["proposta_id"], now=time.time())
    assert risposta == {"proposte": [{f: riga[f] for f in PROPOSAL_FIELDS}]}
    assert risposta["proposte"][0]["numero"] == from_brain["numero"] == 2


@pytest.mark.asyncio
async def test_mind_proposte_e_di_chi_amministra(banco):
    """Come la pagina Proposte e `confirm`: chi non amministra non legge le
    proposte del cervello. Le altre letture di `mind` restano di tutti.

    Mutazione ESEGUITA (05/11/2026): la riga di `mind` senza il permesso --
    rossa."""
    from hiris.app.api.handlers_chat import create_tool_dispatcher
    from hiris.app.api.soffitto import consente

    officina, _ = banco
    dispatcher = create_tool_dispatcher(_app_with_workshop(officina),
                                        soffitto=consente(None, ruolo="utente"))

    risposta = await dispatcher.dispatch("mind", {"cosa": "proposte"})

    assert "errore" in risposta and "proposte" not in risposta
