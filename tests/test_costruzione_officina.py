"""L'officina: l'unico punto che scrive CONFIGURAZIONE su Home Assistant."""
import ast
import inspect
import logging
import os
import re

import pytest

from hiris.app.azione.costruzione import officina as officina_modulo
from hiris.app.azione.costruzione.officina import Workshop
from hiris.app.azione.costruzione.versioni import ConstructionStore
from hiris.app.azione.cronaca import Journal

ADESSO = 1_756_000_000.0

# La stessa guardia di `HAClient._KEY_RE` (hiris/app/proxy/ha_client.py):
# `key or ""` sostituisce SOLO i valori falsy (None, "") con la stringa
# vuota -- un intero o un dizionario, essendo truthy, arrivano intatti a
# `.match()`, che solleva `TypeError` su qualunque cosa non sia str/bytes.
# Una finta che accettasse una chiave non testuale nasconderebbe esattamente
# il difetto che il cliente vero produce (review round 3, IMPORTANT 6).
_CHIAVE_RE_FINTA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class FintoHA:
    """Un Home Assistant che dice sempre di si', salvo istruzioni contrarie."""

    def __init__(self, **override):
        self.salvate = []
        self.cancellate = []
        self.helper_creati = []
        self.helper_cancellati = []
        self.etichettate = []
        self._override = override
        # Le chiavi che questa casa finta ha DAVVERO. Tutto il resto e'
        # assente -- ed e' cosi' che `_free_key` puo' dire «e' libera»
        # senza inventare.
        self.esistenti = {"1771"}
        self.stati = [{"entity_id": "automation.tapparelle_all_alba",
                       "state": "on", "attributes": {"id": "1771"}}]
        self.DOMINI_CONFIGURABILI = ("automation", "script", "scene")
        # Ondata finale, punto 1: prima di questa riga `FintoHA` non
        # sollevava MAI, e nessun test poteva vedere cosa succede quando Home
        # Assistant e' irraggiungibile durante un'`apply` -- il difetto n.1
        # (`test_che_non_possono_fallire`) applicato al livello della finta
        # intera, non della singola asserzione. `self._solleva` e' l'insieme
        # dei nomi dei metodi REST (`leggi_configurazione`,
        # `salva_configurazione`, `cancella_configurazione`) che devono
        # sollevare invece di rispondere, fedele a cio' che il client vero fa
        # su un guasto di trasporto (`ClientConnectorError`, timeout).
        self._solleva: set[str] = set()

    def _forse_solleva(self, nome: str) -> None:
        if nome in self._solleva:
            raise ConnectionError(f"finta interruzione di rete durante {nome}")

    async def valida_config(self, **kw):
        return self._override.get("valida", {
            k: {"valid": True, "error": None} for k in kw})

    async def salva_configurazione(self, domain, key, body):
        self._forse_solleva("salva_configurazione")
        if "salva" in self._override:
            return self._override["salva"]
        self.salvate.append((domain, key, body))
        self.esistenti.add(key)
        # Dopo la scrittura l'entita' esiste, e porta l'id appena scritto:
        # senza questo il finto Home Assistant direbbe sempre «non e'
        # comparsa», e il test dell'etichetta misurerebbe il fake, non il codice.
        # Guardia aggiunta rispetto al brief: quando un test svuota `stati`
        # apposta per simulare che l'entita' non compaia mai (vedi
        # test_se_l_entita_non_compare_lo_dice_invece_di_dichiarare_riuscito),
        # non c'e' nessuna voce da aggiornare -- indicizzare stati[0] a vuoto
        # sollevava IndexError, un guasto della finta e non del codice.
        if self.stati:
            self.stati[0]["attributes"]["id"] = key
        return {"salvato": True}

    async def cancella_configurazione(self, domain, key):
        self._forse_solleva("cancella_configurazione")
        self.cancellate.append((domain, key))
        return {"cancellato": True}

    async def leggi_configurazione(self, domain, key):
        self._forse_solleva("leggi_configurazione")
        if "leggi" in self._override:
            return self._override["leggi"]
        if not _CHIAVE_RE_FINTA.match(key or ""):
            # Fedele a `HAClient._KEY_RE.match(key or "")`: una chiave
            # falsy (None, "") diventa "" e fallisce il match normalmente; una
            # chiave truthy non testuale (un intero, un dizionario) arriva
            # intatta a `.match()` e solleva `TypeError` -- lo stesso crash
            # del client vero, non nascosto da una finta piu' permissiva.
            return {"errore": "la chiave non ha una forma ammessa"}
        if key in self.esistenti:
            return {"corpo": {"id": key, "alias": "com'era"}}
        return {"assente": True}

    async def crea_helper(self, domain, data):
        if "crea_helper" in self._override:
            return self._override["crea_helper"]
        self.helper_creati.append((domain, data))
        return {"helper": {"id": "modalita_notte"}}

    async def cancella_helper(self, domain, helper_id):
        if "cancella_helper" in self._override:
            return self._override["cancella_helper"]
        self.helper_cancellati.append((domain, helper_id))
        return {"cancellato": True}

    async def elenca_etichette(self):
        return {"etichette": [{"label_id": "hiris", "name": "HIRIS"}]}

    async def crea_etichetta(self, name):
        return {"etichetta": {"label_id": "hiris", "name": name}}

    async def aggiungi_etichetta_a(self, entity_id, label_id):
        self.etichettate.append((entity_id, label_id))
        return {"applicata": True}

    async def get_states(self, entity_ids):
        return self.stati


@pytest.fixture()
def banco(tmp_path):
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    ha = FintoHA()
    officina = Workshop(ha, archivio, cronaca)
    yield officina, ha, archivio, cronaca
    archivio.close()
    cronaca.close()


def _intento(**kw):
    base = {"gesto": "crea", "dominio": "automation", "chiave": None,
            "alias": "Tapparelle all'alba",
            "descrizione": "Apre le tapparelle quando sorge il sole",
            "innesco": [{"trigger": "sun", "event": "sunrise"}],
            "condizioni": [], "azioni": [{"action": "cover.open_cover"}],
            "stati": [], "campi": None, "parametri": [], "riuso": False,
            "ricorrente": False, "richiesto": "automazione", "helper": [],
            "frase": "apri le tapparelle all'alba"}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_proporre_non_scrive_niente_su_home_assistant(banco):
    officina, ha, _, _ = banco
    esito = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" in esito
    assert ha.salvate == []
    assert ha.helper_creati == []
    assert esito["anteprima"]


@pytest.mark.asyncio
async def test_una_validazione_fallita_ferma_tutto_e_riporta_il_motivo_di_ha(banco):
    officina, ha, archivio, _ = banco
    ha._override["valida"] = {"triggers": {"valid": False,
                                           "error": "Unknown trigger 'quando'"}}
    esito = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "Unknown trigger" in esito["errore"]
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_confermare_nello_stesso_turno_non_si_puo(banco):
    """Il cancello e' l'umano: serve un messaggio in mezzo (spec §7)."""
    officina, ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t1",
                                   now=ADESSO + 1)
    assert "errore" in esito
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_confermare_in_un_turno_successivo_scrive_davvero(banco):
    officina, ha, archivio, cronaca = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert esito["applicata"] is True
    assert ha.salvate[0][0] == "automation"
    assert archivio.read(p["proposta_id"])["stato"] == "applicata"
    riga = cronaca.read(esito["esecuzione_id"])
    assert riga["genere"] == "costruzione"
    assert riga["eseguito"] is True


@pytest.mark.asyncio
async def test_senza_identita_di_turno_non_si_applica_dalla_chat(banco):
    """Se non so distinguere i turni non posso far valere il cancello: rifiuto
    e indico la strada che funziona (la pagina)."""
    officina, ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange=None, now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange=None,
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "pagina" in esito["errore"].lower()
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_dalla_pagina_si_applica_sempre(banco):
    """L'origine `pagina` E' un umano che ha cliccato: nessun turno da distinguere."""
    officina, _ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="pagina", exchange=None,
                                   now=ADESSO + 60)
    assert esito["applicata"] is True


@pytest.mark.asyncio
async def test_l_entita_nata_riceve_l_etichetta(banco):
    officina, ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="chat", exchange="t2", now=ADESSO + 60)
    assert ha.etichettate == [("automation.tapparelle_all_alba", "hiris")]


@pytest.mark.asyncio
async def test_modificare_un_oggetto_tuo_non_lo_marchia_come_fatto_da_hiris(banco):
    """L'etichetta dice CHI L'HA FATTO, e una modifica non lo rende suo (spec §5)."""
    officina, ha, _, _ = banco
    p = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="chat", exchange="t2", now=ADESSO + 60)
    assert ha.etichettate == []


@pytest.mark.asyncio
async def test_un_identificatore_non_verificabile_ferma_la_proposta(banco):
    """Se non so se un id e' libero non scrivo: un id occupato non darebbe un
    errore, farebbe SOSTITUIRE l'automazione che c'era."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {"errore": "Home Assistant non ha risposto"}
    esito = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "alla cieca" in esito["errore"]
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_se_l_entita_non_compare_lo_dice_invece_di_dichiarare_riuscito(banco):
    """Dire cosa e' successo, non cosa e' stato chiesto (spec §2.3)."""
    officina, ha, _, cronaca = banco
    ha.stati = []
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert esito["applicata"] is True
    assert esito["avviso"]
    assert cronaca.read(esito["esecuzione_id"])["avviso"]


@pytest.mark.asyncio
async def test_se_l_automazione_cade_gli_helper_appena_nati_si_disfano(banco):
    """Senza questa regola ogni tentativo fallito lascia rifiuti in casa."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert ha.helper_creati, "l'helper doveva essere creato prima del rifiuto"
    assert ha.helper_cancellati == [("input_boolean", "modalita_notte")]
    assert archivio.read(p["proposta_id"])["stato"] == "rifiutata"


@pytest.mark.asyncio
async def test_modificare_archivia_il_prima_prima_di_scrivere(banco):
    officina, ha, archivio, _ = banco
    intento = _intento(gesto="modifica", chiave="1771")
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    riga = archivio.read(p["proposta_id"])
    assert riga["prima"]["alias"] == "com'era"
    assert "com'era" in riga["anteprima"] or "prima" in riga["anteprima"].lower()
    # «prima di scrivere» e' la parte del nome che l'assert sopra non prova
    # da sola (ogni anteprima di modifica contiene «Prima: ...»): `propose`
    # non deve aver toccato Home Assistant.
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_modificare_un_oggetto_esistente_lo_dichiara_nell_preview(banco):
    """Regola posta dal proprietario: se tocca qualcosa, lo deve dire.

    Rinominato rispetto alla versione precedente (che si chiamava "...non_di_
    hiris..."): il codice non distingue affatto un oggetto fatto da HIRIS da
    uno del proprietario nell'anteprima -- lo dichiara per QUALUNQUE modifica
    di un oggetto esistente. Il contrasto con la creazione (che non lo dice)
    e' quello che rende l'asserzione capace di fallire davvero."""
    officina, _, _, _ = banco
    esito_modifica = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                                            actor="chat", exchange="t1", now=ADESSO)
    esito_crea = await officina.propose(_intento(), actor="chat", exchange="t1",
                                        now=ADESSO)
    assert ("esiste già" in esito_modifica["anteprima"]
            or "già esistente" in esito_modifica["anteprima"])
    assert "esiste già" not in esito_crea["anteprima"]


@pytest.mark.asyncio
async def test_una_struttura_gestita_a_mano_non_diventa_un_guasto(banco):
    """Se l'API dice che non si scrive, si dice PERCHE' (spec §6)."""
    officina, ha, _, _ = banco
    ha._override["salva"] = {"errore": "404: Not Found"}
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "gestite a mano" in esito["errore"]


@pytest.mark.asyncio
async def test_ripristinare_rimette_il_prima_passando_dalla_stessa_officina(banco):
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="pagina", exchange=None, now=ADESSO + 60)
    ha.salvate.clear()
    esito = await officina.restore(p["proposta_id"], actor="pagina", exchange=None,
                                      now=ADESSO + 120)
    assert esito["applicata"] is True
    assert ha.salvate[0][2]["alias"] == "com'era"


@pytest.mark.asyncio
async def test_una_scena_con_due_stati_sulla_stessa_entita_si_rifiuta(banco):
    """Le scene non passano da `validate_config`: se il doppione non lo prende
    l'officina, non lo prende piu' nessuno e uno dei due stati sparisce."""
    officina, _ha, archivio, _ = banco
    esito = await officina.propose(
        _intento(dominio="scene", innesco=[], azioni=[], richiesto="scena",
                 stati=[{"entity_id": "light.salotto", "state": "on"},
                        {"entity_id": "light.salotto", "state": "off"}]),
        actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "light.salotto" in esito["errore"]
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_il_consiglio_del_mestiere_viaggia_nell_preview(banco):
    officina, _, _, _ = banco
    esito = await officina.propose(
        _intento(richiesto="automazione", innesco=[], ricorrente=False,
                 azioni=[{"action": "light.turn_off"}]),
        actor="chat", exchange="t1", now=ADESSO)
    assert "script" in esito["anteprima"]


# ==== Review 2026-08-23: CRITICAL + IMPORTANT 1-7 =========================

@pytest.mark.asyncio
async def test_modificare_un_oggetto_sparito_si_rifiuta_invece_di_esplodere(banco):
    """CRITICAL: `leggi_configurazione` ha tre forme (`corpo`, `errore`,
    `assente`), non due. Una `modifica` su una chiave che HA non trova piu'
    (l'utente l'ha cancellata nel frattempo) deve tornare un rifiuto motivato,
    non sollevare `KeyError: 'corpo'` fuori dal modulo."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {"assente": True}
    esito = await officina.propose(_intento(gesto="modifica", chiave="9999"),
                                   actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "errore" in esito
    assert "9999" in esito["errore"] or "non esiste" in esito["errore"].lower()
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_cancellare_un_oggetto_sparito_si_rifiuta_invece_di_esplodere(banco):
    """Stesso guasto, stessa guardia, sull'altro gesto che legge il «prima»."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {"assente": True}
    esito = await officina.propose(_intento(gesto="cancella", chiave="9999"),
                                   actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "errore" in esito
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_una_proposta_senza_turno_non_si_conferma_da_un_turno_qualsiasi(banco):
    """IMPORTANT 1: una proposta nata senza identita' di turno (il ramo
    sincrono della chat, l'intestazione mancante) resta orfana del cancello:
    non e' confermabile da un'origine non umana, qualunque turno arrivi dopo.
    La condizione precedente (`proposta["turno"] and proposta["turno"] ==
    turno`) restava falsa quando il turno memorizzato era `None`, e lasciava
    passare la prima conferma che capitava."""
    officina, ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange=None, now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="qualunque",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "pagina" in esito["errore"].lower()
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_l_origine_umana_che_scavalca_il_cancello_lascia_una_traccia(banco, caplog):
    """IMPORTANT 1: se il Task 8 sbagliasse a inoltrare un'origine scelta dal
    modello come `pagina`, deve restarne una traccia -- non il silenzio."""
    officina, _ha, _, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    with caplog.at_level("INFO", logger="hiris.app.azione.costruzione.officina"):
        await officina.apply(p["proposta_id"], actor="pagina", exchange=None,
                               now=ADESSO + 60)
    assert any(r.levelname == "INFO" and "pagina" in r.message.lower()
              for r in caplog.records)


@pytest.mark.asyncio
async def test_la_disfatta_dell_helper_e_dichiarata_nel_motivo(banco):
    """IMPORTANT 2: oggi l'utente non sa che un helper e' nato ed e' stato
    tolto. Il motivo del rifiuto deve dirlo."""
    officina, ha, _archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "modalita_notte" in esito["errore"]


@pytest.mark.asyncio
async def test_se_la_disfatta_fallisce_lo_dice_invece_di_tacere(banco):
    """IMPORTANT 2: se anche `cancella_helper` fallisce, l'archivio non deve
    dire «non e' successo niente» mentre in casa resta un helper orfano che
    nessuno pulira' piu'."""
    officina, ha, _archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    ha._override["cancella_helper"] = {"errore": "Home Assistant non ha risposto"}
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "toglilo a mano" in esito["errore"] or "rimasto in casa" in esito["errore"]
    assert "modalita_notte" in esito["errore"]


@pytest.mark.asyncio
async def test_un_helper_senza_id_restituito_viene_dichiarato(banco):
    """IMPORTANT 2: un helper la cui creazione non restituisce un id non
    entra in `nati` e quindi non e' mai disfabile -- deve essere dichiarato,
    non perso in silenzio."""
    officina, ha, _archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    ha._override["crea_helper"] = {"helper": {}}  # nessun id
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "input_boolean" in esito["errore"]
    assert ha.helper_cancellati == []


@pytest.mark.asyncio
async def test_due_conferme_della_stessa_proposta_non_scrivono_due_volte(banco):
    """IMPORTANT 3: la rivendicazione atomica, non una lettura gia' stantia
    nel momento in cui la si confronta.

    Si simula la finestra di corsa monkeypatchando `_store.read` cosi' da
    restituire sempre l'istantanea «in_attesa» catturata PRIMA che un'altra
    richiesta rivendichi la proposta per prima (`archivio.rivendica` sotto):
    e' la stessa finestra che due click ravvicinati aprirebbero in un server
    vero, dove la lettura iniziale non e' piu' aggiornata nell'istante in cui
    la si confronta con l'esito di una richiesta concorrente. L'unica difesa
    possibile e' l'UPDATE atomica dentro `apply`, non il controllo sullo
    stato gia' letto in testa alla funzione.

    L'intento porta un `helper` apposta (review round 3, punto 3): creare un
    helper E' una scrittura su Home Assistant, ed e' quella la cui disfatta
    e' inaffidabile. Se la rivendicazione si spostasse DOPO il ciclo degli
    helper (invece che prima, come deve stare), due `apply` simultanee
    creerebbero entrambe l'helper prima che una delle due trovi la
    rivendicazione gia' presa -- il perdente uscirebbe sull'errore di
    rivendicazione senza mai chiamare `_disfa`. `ha.salvate == []` da solo
    non lo vedrebbe: serve anche `ha.helper_creati == []`."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    proposta_stantia = archivio.read(p["proposta_id"])
    assert proposta_stantia["stato"] == "in_attesa"
    # Un'altra richiesta rivendica per prima: il DB passa a `in_corso`.
    prima_rivendicazione = archivio.claim(p["proposta_id"], now=ADESSO + 59)
    assert "errore" not in prima_rivendicazione
    # Questa richiesta lavora ancora sulla lettura stantia.
    officina._store.read = lambda ident: proposta_stantia
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert ha.salvate == []
    assert ha.helper_creati == []


@pytest.mark.asyncio
async def test_un_intento_vuoto_si_rifiuta_invece_di_validare_niente(banco):
    """IMPORTANT 4: l'unico caso in cui il mestiere non ha niente da dire e'
    proprio quello in cui tace (`consiglia` torna col ritorno anticipato,
    `dissenso: False`). Senza questo controllo il corpo composto avrebbe tre
    liste vuote, Home Assistant lo direbbe «valido», e una conferma
    scriverebbe in casa un'automazione inerte."""
    officina, ha, archivio, _ = banco
    esito = await officina.propose(
        _intento(innesco=[], azioni=[], stati=[], parametri=[], ricorrente=False,
                 richiesto=None),
        actor="chat", exchange="t1", now=ADESSO)
    assert "proposta_id" not in esito
    assert "non ho capito" in esito["errore"]
    assert ha.salvate == []
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_il_motivo_del_mestiere_viaggia_nell_anteprima_anche_senza_dissenso(banco):
    """IMPORTANT 4: prima il motivo del mestiere finiva nell'anteprima solo
    in caso di dissenso; ora ci finisce sempre, quando c'e'."""
    officina, _, _, _ = banco
    esito = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    assert "Nota" in esito["anteprima"]
    assert "automazione" in esito["anteprima"].lower()


@pytest.mark.asyncio
async def test_ripristinare_dalla_chat_e_un_giro_in_due_tempi(banco):
    """IMPORTANT 5: prima `restore` creava la proposta e la passava subito
    ad `apply` con lo stesso `turno`, che il cancello rifiutava SEMPRE --
    e la riga restava `in_attesa` a bruciare un posto del tetto per sette
    giorni. Ora, dalla chat, e' un giro in due tempi come tutto il resto."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="pagina", exchange=None, now=ADESSO + 60)
    ha.salvate.clear()
    esito = await officina.restore(p["proposta_id"], actor="chat", exchange="t3",
                                      now=ADESSO + 120)
    assert "proposta_id" in esito
    assert esito["anteprima"]
    assert ha.salvate == []
    esito2 = await officina.apply(esito["proposta_id"], actor="chat", exchange="t4",
                                    now=ADESSO + 180)
    assert esito2["applicata"] is True
    assert ha.salvate[0][2]["alias"] == "com'era"


@pytest.mark.asyncio
async def test_un_alias_che_non_e_testo_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6: un `alias` a forma di dizionario solleverebbe `TypeError:
    unhashable type` da `_seme_da`. Il chiamante e' uno strumento riempito da
    un modello: si rifiuta con un motivo leggibile."""
    officina, ha, _archivio, _ = banco
    esito = await officina.propose(_intento(alias={"non": "testo"}), actor="chat",
                                   exchange="t1", now=ADESSO)
    assert "errore" in esito
    assert "alias" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_un_helper_che_non_e_un_dizionario_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6: una lista `helper` di stringhe solleverebbe `AttributeError`
    su `helper.get("dominio")`."""
    officina, ha, _archivio, _ = banco
    esito = await officina.propose(_intento(helper=["non un dizionario"]), actor="chat",
                                   exchange="t1", now=ADESSO)
    assert "errore" in esito
    assert "helper" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_una_chiave_che_non_e_testo_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6 (round 3, chiuso a meta' nel round 2): `"chiave": 1771`
    invece di `"1771"` e' l'errore di forma piu' probabile che un modello
    faccia su questo campo -- `HAClient._KEY_RE.match(key or "")`
    riceve un intero intatto (e' truthy: `or ""` non lo tocca) e solleva
    `TypeError`. La finta ora e' fedele su questo punto (vedi
    `FintoHA.leggi_configurazione`), quindi questo test misura il codice
    vero, non un fake troppo permissivo."""
    officina, ha, _archivio, _ = banco
    esito = await officina.propose(_intento(gesto="modifica", chiave=1771),
                                   actor="chat", exchange="t1", now=ADESSO)
    assert "errore" in esito
    assert "chiave" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_dei_campi_che_non_sono_un_dizionario_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6 (round 3): `composer.compose_script` fa `dict(campi)` --
    `dict("abc")` solleva `ValueError`, `dict(5)` solleva `TypeError`."""
    officina, ha, _archivio, _ = banco
    esito = await officina.propose(_intento(dominio="script", campi="abc"),
                                   actor="chat", exchange="t1", now=ADESSO)
    assert "errore" in esito
    assert "campi" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_cancellare_chiama_cancella_configurazione_con_la_chiave_giusta(banco):
    """IMPORTANT 7: nessun test esercitava il gesto distruttivo."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(gesto="cancella", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert esito["applicata"] is True
    assert ha.cancellate == [("automation", "1771")]


@pytest.mark.asyncio
async def test_ripristinare_una_creazione_la_cancella(banco):
    """IMPORTANT 7: ripristinare una CREAZIONE e' cio' che trasforma un
    ripristino in una cancellazione da Home Assistant -- nessun test lo
    esercitava."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="pagina", exchange=None, now=ADESSO + 60)
    chiave_nata = ha.salvate[0][1]
    esito = await officina.restore(p["proposta_id"], actor="pagina", exchange=None,
                                      now=ADESSO + 120)
    assert esito["applicata"] is True
    assert ha.cancellate == [("automation", chiave_nata)]


# ==== Review 2026-08-23 round 3: 4 e 2 (i due minori) =====================

@pytest.mark.asyncio
async def test_lo_stato_in_corso_non_esce_come_token_grezzo(banco):
    """Minore 1: «in_corso» e' un token interno (snake_case), non una parola
    italiana da mostrare dentro una frase all'utente."""
    officina, _ha, archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    archivio.claim(p["proposta_id"], now=ADESSO + 1)
    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)
    assert "errore" in esito
    assert "in_corso" not in esito["errore"]
    assert "in corso" in esito["errore"]


# ==== Ondata finale 2026-08-23: cuciture fra task ==========================

@pytest.mark.asyncio
async def test_un_guasto_di_rete_durante_applica_disfa_gli_helper_e_non_resta_in_corso(banco):
    """Punto 1: con Home Assistant irraggiungibile durante un'`apply`, le
    tre conseguenze che il ledger nomina -- (a) un esito, non un'eccezione,
    (b) gli helper appena nati si disfano, (c) la proposta non resta bloccata
    `in_corso`. La finta solleva DAVVERO (vedi `_forse_solleva`), non un
    override che restituisce un dizionario: senza questa capacita' nessun
    test poteva vedere il difetto, ed e' esattamente la ragione per cui la
    review dei nove rischi del Task 7 non l'ha visto."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    ha._solleva.add("salva_configurazione")

    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)

    # (a) un dizionario con errore, non un'eccezione sollevata fuori da qui.
    assert "errore" in esito
    assert "non ha risposto" in esito["errore"]
    # (b) l'helper nato viene disfatto.
    assert ha.helper_creati, "l'helper doveva essere creato prima del guasto"
    assert ha.helper_cancellati == [("input_boolean", "modalita_notte")]
    # (c) la proposta non resta bloccata in_corso.
    assert archivio.read(p["proposta_id"])["stato"] == "rifiutata"


@pytest.mark.asyncio
async def test_un_guasto_di_rete_durante_applica_e_dichiarato_guasto_rete(banco):
    """Punto 7 (terza pulizia): `_agisci` (handlers_costruzioni.py) deve poter
    distinguere un guasto di TRASPORTO da un rifiuto vero di Home Assistant,
    per rispondere 503 e non 409 -- lo stesso flag che questo test pinna."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    ha._solleva.add("salva_configurazione")

    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)

    assert esito.get("guasto_rete") is True


@pytest.mark.asyncio
async def test_un_guasto_di_rete_durante_cancella_non_solleva(banco):
    """Punto 1, il terzo sito guardato (`cancella_configurazione`,
    officina.py:305): stessa protezione sul gesto distruttivo."""
    officina, ha, archivio, _ = banco
    p = await officina.propose(_intento(gesto="cancella", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    ha._solleva.add("cancella_configurazione")

    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)

    assert "errore" in esito
    assert esito.get("guasto_rete") is True
    assert archivio.read(p["proposta_id"])["stato"] == "rifiutata"


@pytest.mark.asyncio
async def test_un_guasto_di_rete_durante_proponi_non_solleva(banco):
    """Punto 1, il sito di `_free_key` (officina.py:168, gesto `crea`):
    il modulo dichiara «non solleva mai» anche qui, non solo durante
    `apply`."""
    officina, ha, archivio, _ = banco
    ha._solleva.add("leggi_configurazione")

    esito = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)

    assert "proposta_id" not in esito
    assert "errore" in esito
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_un_guasto_di_rete_durante_proponi_una_modifica_non_solleva(banco):
    """Punto 1, il quarto e ultimo sito (officina.py:107, gesto `modifica`/
    `cancella`, la lettura del «prima» prima di scrivere): senza `_rete`
    anche qui, un `ConnectionError` di questo ramo usciva fuori dal modulo
    tale e quale, non trasformato in `{"errore": ...}`."""
    officina, ha, archivio, _ = banco
    ha._solleva.add("leggi_configurazione")

    esito = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                                   actor="chat", exchange="t1", now=ADESSO)

    assert "proposta_id" not in esito
    assert "errore" in esito
    assert archivio.list() == []


@pytest.mark.asyncio
async def test_lo_helper_nato_riceve_l_etichetta_anche_durante_una_modifica(banco):
    """Punto 3: spec §5 testuale, «l'etichetta si applica all'entita' nata,
    helper compresi». Un helper creato da `crea_helper` e' SEMPRE nato,
    indipendentemente dal gesto sul dominio principale -- una `modifica`
    all'automazione non rende meno nuovo l'`input_boolean` che nasce insieme.
    Prima di questa correzione `_rileggi` filtrava per `{dominio}.`, quindi
    l'helper non riceveva mai l'etichetta, e non esistendo un registro
    interno (la paternita' vive nel registro di HA, fondamenta 2) quella
    paternita' non era da nessuna parte."""
    officina, ha, _, _ = banco
    intento = _intento(gesto="modifica", chiave="1771",
                       helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.propose(intento, actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="chat", exchange="t2", now=ADESSO + 60)
    assert ("input_boolean.modalita_notte", "hiris") in ha.etichettate
    # Contrasto: l'oggetto principale modificato NON prende l'etichetta
    # (spec §5 -- una modifica non rende suo cio' che HIRIS non ha creato).
    assert ("automation.tapparelle_all_alba", "hiris") not in ha.etichettate


def test_l_anteprima_usa_l_articolo_giusto_per_ogni_dominio(banco):
    """Punto 7, prima pulizia: «un'script», «l'script» e «un'scena» erano le
    forme sbagliate composte da un indice nudo su un dizionario che non
    distingueva vocale da consonante. Script e scena non prendono MAI
    l'apostrofo.

    Punto 5 (residuo): guardare l'articolo da solo lascia passare la frase
    intera sgrammaticata -- «Creo uno script chiamata «X».» ha «un'script»
    assente e «uno script» presente, e il vecchio test qui sopra passava
    ugualmente. Si guarda la FRASE, non solo l'articolo."""
    officina, _, _, _ = banco
    consiglio = {"motivo": None}
    for dominio, atteso in (("automation", "un'automazione"),
                            ("script", "uno script"),
                            ("scene", "una scena")):
        anteprima = officina._preview("crea", dominio, "1", {"alias": "X"}, None, None,
                                        consiglio)
        assert f"Creo {atteso} di nome «X»." in anteprima
        assert "un'script" not in anteprima
        assert "un'scena" not in anteprima
        assert "chiamata «X»" not in anteprima
    for dominio, atteso in (("automation", "l'automazione"),
                            ("script", "lo script"),
                            ("scene", "la scena")):
        anteprima = officina._preview("modifica", dominio, "1", {"alias": "X"},
                                        {"alias": "X"}, {"alias": "Y"}, consiglio)
        assert f"Modifico {atteso} «X», che esiste già in casa tua." in anteprima


@pytest.mark.asyncio
async def test_ripristinare_dalla_chat_senza_turno_indica_la_pagina(banco):
    """Minore 2: se il chiamante di `restore` non porta un'identita' di
    turno, la proposta appena creata non sara' MAI confermabile da un'origine
    non umana (IMPORTANT 1, round 2) -- e l'anteprima restituita deve dirlo,
    come gia' fa il messaggio del cancello in `apply`."""
    officina, _ha, _archivio, _ = banco
    p = await officina.propose(_intento(gesto="modifica", chiave="1771"),
                               actor="chat", exchange="t1", now=ADESSO)
    await officina.apply(p["proposta_id"], actor="pagina", exchange=None, now=ADESSO + 60)
    esito = await officina.restore(p["proposta_id"], actor="chat", exchange=None,
                                      now=ADESSO + 120)
    assert "proposta_id" in esito
    assert "pagina" in esito["anteprima"].lower()


# ---------------------------------------------------------------------------
# Punto 1 (residuo) -- IMPORTANT, il solo che conta davvero.
#
# Oggi i quattro siti che chiamano `leggi_configurazione`/
# `salva_configurazione`/`cancella_configurazione` sono tutti avvolti in
# `self._rete(...)`: e' cio' che trasforma un guasto di TRASPORTO in
# `{"errore": ..., "guasto_rete": True}` invece di lasciarlo risalire come
# eccezione fuori dall'officina (il modulo dichiara "non solleva mai"). Ma
# oggi questo e' solo disciplina -- nessun test lo garantisce -- e un quinto
# sito aggiunto domani senza l'involucro riaprirebbe il difetto IN SILENZIO,
# con la suite verde, per la STESSA ragione per cui nessuno vedeva il difetto
# originale: niente lo guarda.
#
# Un controllo per sottostringa (`'_rete' in sorgente`) non difenderebbe
# niente: sarebbe vero comunque, perche' la parola compare in decine
# d'altri punti del file (docstring comprese). Serve legare OGNI occorrenza
# delle tre primitive alla presenza dell'involucro -- qui strutturalmente,
# con l'AST, non per posizione testuale: cosi' non importa se la chiamata
# sta su una riga sola o e' spezzata su piu' righe (`salva_configurazione`,
# in `apply`, lo e').
# ---------------------------------------------------------------------------

_PRIMITIVE_REST = ("leggi_configurazione", "salva_configurazione", "cancella_configurazione")


def _e_chiamata_a_primitiva_rest(nodo: ast.AST) -> bool:
    """`self._ha.<primitiva>(...)`, una delle tre."""
    return (isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in _PRIMITIVE_REST
            and isinstance(nodo.func.value, ast.Attribute)
            and nodo.func.value.attr == "_ha"
            and isinstance(nodo.func.value.value, ast.Name)
            and nodo.func.value.value.id == "self")


def _e_chiamata_a_rete(nodo: ast.AST) -> bool:
    """`self._rete(...)`."""
    return (isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "_rete"
            and isinstance(nodo.func.value, ast.Name)
            and nodo.func.value.id == "self")


def _e_self_ha(nodo: ast.AST) -> bool:
    """L'espressione `self._ha`, letterale."""
    return (isinstance(nodo, ast.Attribute)
            and nodo.attr == "_ha"
            and isinstance(nodo.value, ast.Name)
            and nodo.value.id == "self")


def test_le_tre_primitive_rest_non_compaiono_mai_fuori_da_rete():
    sorgente = inspect.getsource(officina_modulo)
    albero = ast.parse(sorgente)

    # Secondo giro di review: `_e_chiamata_a_primitiva_rest` riconosce SOLO
    # `self._ha.<primitiva>(...)` letterale -- un Attribute su un Name che si
    # chiama esattamente "self". Un alias di comodo (`ha = self._ha`, poi
    # `ha.salva_configurazione(...)`) cambia `func.value` in `Name(id="ha")`:
    # zero corrispondenze, ne' fra le protette ne' fra le nude. Quella
    # chiamata sparirebbe dal controllo invece di finirci come violazione --
    # e il guardrail sul numero minimo di siti (sotto) non se ne
    # accorgerebbe, perche' i quattro siti letterali di oggi restano intatti.
    # E' lo stesso vettore che questo test vuole escludere (una primitiva
    # REST chiamata senza passare da `self._rete`), imboccato con un nome
    # diverso -- e uno che si sceglie in buona fede, per leggibilita'.
    #
    # Si chiude vietando il VETTORE, non inseguendo ogni forma di alias:
    # se `self._ha` non puo' MAI essere legato a un nome locale in questo
    # modulo, il pattern sopra torna esaustivo per costruzione -- ogni
    # chiamata alle tre primitive deve passare per forza dalla forma
    # `self._ha.<primitiva>(...)` che il resto del test gia' copre. Non e'
    # avversione agli alias: e' che un alias qui renderebbe cieco proprio
    # questo controllo. Chi un giorno vorra' davvero legare `self._ha` a un
    # nome locale trovera' questa riga e potra' decidere sapendo cosa perde
    # (o aggiornare anche `_e_chiamata_a_primitiva_rest` a riconoscerlo).
    legami_a_self_ha = [n for n in ast.walk(albero)
                        if isinstance(n, (ast.Assign, ast.AnnAssign))
                        and n.value is not None and _e_self_ha(n.value)]
    assert not legami_a_self_ha, (
        "self._ha e' legato a un nome locale in officina.py: questo rende "
        "cieco il controllo sulle primitive REST, che riconosce solo la "
        "forma letterale self._ha.<primitiva>(...).")

    tutte = [n for n in ast.walk(albero) if _e_chiamata_a_primitiva_rest(n)]
    # Se questa lista fosse vuota il test passerebbe SEMPRE, a vuoto: un
    # test che non trova mai niente da controllare non protegge niente. I
    # quattro siti di oggi (due `leggi_configurazione`, una
    # `salva_configurazione`, una `cancella_configurazione`) la tengono
    # popolata.
    assert len(tutte) >= 4, (
        "le primitive REST non compaiono piu' nel sorgente atteso: "
        "questo test non ha piu' niente da proteggere -- controllare a mano")

    avvolte_da_rete: set[int] = set()
    for nodo in ast.walk(albero):
        if not _e_chiamata_a_rete(nodo):
            continue
        for figlio in ast.walk(nodo):
            if figlio is not nodo and _e_chiamata_a_primitiva_rest(figlio):
                avvolte_da_rete.add(id(figlio))

    nude = [n.func.attr for n in tutte if id(n) not in avvolte_da_rete]
    assert not nude, (
        f"primitive REST chiamate fuori da self._rete(...): {nude}. Un "
        "guasto di trasporto in quel punto risalirebbe come eccezione fuori "
        "dall'officina, invece di diventare "
        "{'errore': ..., 'guasto_rete': True} come ovunque altrove.")


# ---------------------------------------------------------------------------
# Punto 2 (residuo) -- `_translate_rejection` puo' raccontare una bugia.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_un_guasto_di_rete_con_404_nel_messaggio_non_diventa_una_bugia(banco):
    """Prima dell'ondata un guasto di rete SOLLEVAVA e non arrivava mai a
    `_translate_rejection`. Adesso ci arriva come stringa, e quella funzione fa
    `if "404" in errore` -- una sottostringa nuda su tutto il messaggio. Una
    porta come 8404 o un IP che la contiene basta a far uscire "queste
    automazioni sono gestite a mano...": una spiegazione architetturale
    falsa, detta con sicurezza, per un guasto che e' semplicemente di rete."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)

    async def _guasto_con_404(dominio, chiave, corpo):
        raise ConnectionError(
            "Cannot connect to host 192.168.1.95:8404 ssl:default [Connect call failed]")
    ha.salva_configurazione = _guasto_con_404

    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)

    assert esito.get("guasto_rete") is True
    assert "non ha risposto" in esito["errore"]
    assert "gestite a mano" not in esito["errore"]


# ---------------------------------------------------------------------------
# Punto 3 (residuo) -- il log del catch largo non dice cosa e' successo.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_un_guasto_di_rete_logga_tipo_ed_exc_info(banco, caplog):
    """Senza tipo ne' traceback un `TypeError` nostro (un difetto del codice)
    e' indistinguibile, in log, da un guasto di rete vero: il difetto nascosto
    due volte."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    ha._solleva.add("salva_configurazione")

    with caplog.at_level(logging.WARNING,
                         logger="hiris.app.azione.costruzione.officina"):
        await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                               now=ADESSO + 60)

    record = next(r for r in caplog.records if "non riuscita" in r.getMessage())
    assert "ConnectionError" in record.getMessage()
    assert record.exc_info is not None


# ---------------------------------------------------------------------------
# Punto 4 (residuo) -- la stringa dell'eccezione va nell'archivio senza limite.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_il_messaggio_dell_eccezione_e_troncato(banco):
    """Quella stringa finisce in quattro superfici, due permanenti
    (`costruzioni.motivo`/`errore` nella cronaca in SQLite): la cattura larga
    toglie la garanzia che sia sempre una riga breve di trasporto -- e'
    quella di QUALUNQUE eccezione."""
    officina, ha, _archivio, _ = banco
    p = await officina.propose(_intento(), actor="chat", exchange="t1", now=ADESSO)
    lunghissimo = "x" * 1000

    async def _guasto_lungo(dominio, chiave, corpo):
        raise ConnectionError(lunghissimo)
    ha.salva_configurazione = _guasto_lungo

    esito = await officina.apply(p["proposta_id"], actor="chat", exchange="t2",
                                   now=ADESSO + 60)

    assert lunghissimo not in esito["errore"]
    assert "[troncato]" in esito["errore"]
    assert len(esito["errore"]) < 400


# ---------------------------------------------------------------------------
# M1 (correzioni-minori, terzo giro) -- il TERZO troncatore.
# ---------------------------------------------------------------------------

def test_il_troncatore_dell_officina_e_lo_stesso_oggetto_di_sanitize():
    """Una review indipendente ha trovato una TERZA copia dell'algoritmo di
    troncamento gia' unificato da M1 (`_sanitize.py::truncate_with_marker`,
    `ha_client.py::_truncate`): `officina.py::_tronca_errore_rete`, stesso
    marcatore, stessa struttura a tre rami. Il commento che la giustificava
    diceva che `_truncate` era privata di `ha_client` -- non piu' vero da
    quando M1 l'ha resa pubblica in `_sanitize.py`. Non basta che si comporti
    allo stesso modo: deve essere letteralmente lo stesso oggetto funzione,
    come gia' verificato fra `ha_client` e `_sanitize`
    (test_ha_client_diagnostics.py::test_truncate_e_la_stessa_funzione_di_
    sanitize)."""
    from hiris.app.azione.costruzione import officina as officina_modulo
    from hiris.app.proxy import _sanitize
    assert officina_modulo._truncate is _sanitize.truncate_with_marker


# ---------------------------------------------------------------------------
# Task 11 (il linter e le best practice) -- il fuso della casa, non del
# container, nella data mostrata nell'anteprima del ripristino.
# ---------------------------------------------------------------------------

def test_la_data_del_ripristino_e_nel_fuso_della_casa():
    """Un'ora mostrata nel fuso del container e' un'ora sbagliata per chi
    legge: l'add-on gira in UTC, la casa no. Il timestamp scelto e' le 23:30
    UTC del 26 agosto, che a Roma sono l'1:30 del 27: se la data uscisse in
    UTC, sarebbe il GIORNO sbagliato, non solo l'ora sbagliata."""
    ts = 1787787000.0  # 2026-08-26T23:30:00Z == 27/08/2026 01:30 a Roma
    officina = Workshop(None, None, None, read_timezone=lambda: "Europe/Rome")
    assert officina._data(ts) == "27/08/2026 01:30"
