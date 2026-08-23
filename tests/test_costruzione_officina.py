"""L'officina: l'unico punto che scrive CONFIGURAZIONE su Home Assistant."""
import os

import pytest

from hiris.app.azione.costruzione.officina import Officina
from hiris.app.azione.costruzione.versioni import ArchivioCostruzioni
from hiris.app.azione.cronaca import Cronaca

ADESSO = 1_756_000_000.0


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
        # assente -- ed e' cosi' che `_chiave_libera` puo' dire «e' libera»
        # senza inventare.
        self.esistenti = {"1771"}
        self.stati = [{"entity_id": "automation.tapparelle_all_alba",
                       "state": "on", "attributes": {"id": "1771"}}]
        self.DOMINI_CONFIGURABILI = ("automation", "script", "scene")

    async def valida_config(self, **kw):
        return self._override.get("valida", {
            k: {"valid": True, "error": None} for k in kw})

    async def salva_configurazione(self, dominio, chiave, corpo):
        if "salva" in self._override:
            return self._override["salva"]
        self.salvate.append((dominio, chiave, corpo))
        self.esistenti.add(chiave)
        # Dopo la scrittura l'entita' esiste, e porta l'id appena scritto:
        # senza questo il finto Home Assistant direbbe sempre «non e'
        # comparsa», e il test dell'etichetta misurerebbe il fake, non il codice.
        # Guardia aggiunta rispetto al brief: quando un test svuota `stati`
        # apposta per simulare che l'entita' non compaia mai (vedi
        # test_se_l_entita_non_compare_lo_dice_invece_di_dichiarare_riuscito),
        # non c'e' nessuna voce da aggiornare -- indicizzare stati[0] a vuoto
        # sollevava IndexError, un guasto della finta e non del codice.
        if self.stati:
            self.stati[0]["attributes"]["id"] = chiave
        return {"salvato": True}

    async def cancella_configurazione(self, dominio, chiave):
        self.cancellate.append((dominio, chiave))
        return {"cancellato": True}

    async def leggi_configurazione(self, dominio, chiave):
        if "leggi" in self._override:
            return self._override["leggi"]
        if chiave in self.esistenti:
            return {"corpo": {"id": chiave, "alias": "com'era"}}
        return {"assente": True}

    async def crea_helper(self, dominio, dati):
        if "crea_helper" in self._override:
            return self._override["crea_helper"]
        self.helper_creati.append((dominio, dati))
        return {"helper": {"id": "modalita_notte"}}

    async def cancella_helper(self, dominio, helper_id):
        if "cancella_helper" in self._override:
            return self._override["cancella_helper"]
        self.helper_cancellati.append((dominio, helper_id))
        return {"cancellato": True}

    async def elenca_etichette(self):
        return {"etichette": [{"label_id": "hiris", "name": "HIRIS"}]}

    async def crea_etichetta(self, nome):
        return {"etichetta": {"label_id": "hiris", "name": nome}}

    async def aggiungi_etichetta_a(self, entity_id, label_id):
        self.etichettate.append((entity_id, label_id))
        return {"applicata": True}

    async def get_states(self, entity_ids):
        return self.stati


@pytest.fixture()
def banco(tmp_path):
    archivio = ArchivioCostruzioni(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Cronaca(os.path.join(str(tmp_path), "azioni.db"))
    ha = FintoHA()
    officina = Officina(ha, archivio, cronaca)
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
    esito = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" in esito
    assert ha.salvate == []
    assert ha.helper_creati == []
    assert esito["anteprima"]


@pytest.mark.asyncio
async def test_una_validazione_fallita_ferma_tutto_e_riporta_il_motivo_di_ha(banco):
    officina, ha, archivio, _ = banco
    ha._override["valida"] = {"triggers": {"valid": False,
                                           "error": "Unknown trigger 'quando'"}}
    esito = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "Unknown trigger" in esito["errore"]
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_confermare_nello_stesso_turno_non_si_puo(banco):
    """Il cancello e' l'umano: serve un messaggio in mezzo (spec §7)."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t1",
                                   adesso=ADESSO + 1)
    assert "errore" in esito
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_confermare_in_un_turno_successivo_scrive_davvero(banco):
    officina, ha, archivio, cronaca = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert esito["applicata"] is True
    assert ha.salvate[0][0] == "automation"
    assert archivio.leggi(p["proposta_id"])["stato"] == "applicata"
    riga = cronaca.leggi(esito["esecuzione_id"])
    assert riga["genere"] == "costruzione"
    assert riga["eseguito"] is True


@pytest.mark.asyncio
async def test_senza_identita_di_turno_non_si_applica_dalla_chat(banco):
    """Se non so distinguere i turni non posso far valere il cancello: rifiuto
    e indico la strada che funziona (la pagina)."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno=None, adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno=None,
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert "pagina" in esito["errore"].lower()
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_dalla_pagina_si_applica_sempre(banco):
    """L'origine `pagina` E' un umano che ha cliccato: nessun turno da distinguere."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="pagina", turno=None,
                                   adesso=ADESSO + 60)
    assert esito["applicata"] is True


@pytest.mark.asyncio
async def test_l_entita_nata_riceve_l_etichetta(banco):
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    await officina.applica(p["proposta_id"], origine="chat", turno="t2", adesso=ADESSO + 60)
    assert ha.etichettate == [("automation.tapparelle_all_alba", "hiris")]


@pytest.mark.asyncio
async def test_modificare_un_oggetto_tuo_non_lo_marchia_come_fatto_da_hiris(banco):
    """L'etichetta dice CHI L'HA FATTO, e una modifica non lo rende suo (spec §5)."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(gesto="modifica", chiave="1771"),
                               origine="chat", turno="t1", adesso=ADESSO)
    await officina.applica(p["proposta_id"], origine="chat", turno="t2", adesso=ADESSO + 60)
    assert ha.etichettate == []


@pytest.mark.asyncio
async def test_un_identificatore_non_verificabile_ferma_la_proposta(banco):
    """Se non so se un id e' libero non scrivo: un id occupato non darebbe un
    errore, farebbe SOSTITUIRE l'automazione che c'era."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {"errore": "Home Assistant non ha risposto"}
    esito = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "alla cieca" in esito["errore"]
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_se_l_entita_non_compare_lo_dice_invece_di_dichiarare_riuscito(banco):
    """Dire cosa e' successo, non cosa e' stato chiesto (spec §2.3)."""
    officina, ha, _, cronaca = banco
    ha.stati = []
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert esito["applicata"] is True
    assert esito["avviso"]
    assert cronaca.leggi(esito["esecuzione_id"])["avviso"]


@pytest.mark.asyncio
async def test_se_l_automazione_cade_gli_helper_appena_nati_si_disfano(banco):
    """Senza questa regola ogni tentativo fallito lascia rifiuti in casa."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.proponi(intento, origine="chat", turno="t1", adesso=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert ha.helper_creati, "l'helper doveva essere creato prima del rifiuto"
    assert ha.helper_cancellati == [("input_boolean", "modalita_notte")]
    assert archivio.leggi(p["proposta_id"])["stato"] == "rifiutata"


@pytest.mark.asyncio
async def test_modificare_archivia_il_prima_prima_di_scrivere(banco):
    officina, ha, archivio, _ = banco
    intento = _intento(gesto="modifica", chiave="1771")
    p = await officina.proponi(intento, origine="chat", turno="t1", adesso=ADESSO)
    riga = archivio.leggi(p["proposta_id"])
    assert riga["prima"]["alias"] == "com'era"
    assert "com'era" in riga["anteprima"] or "prima" in riga["anteprima"].lower()
    # «prima di scrivere» e' la parte del nome che l'assert sopra non prova
    # da sola (ogni anteprima di modifica contiene «Prima: ...»): `proponi`
    # non deve aver toccato Home Assistant.
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_modificare_un_oggetto_esistente_lo_dichiara_nell_anteprima(banco):
    """Regola posta dal proprietario: se tocca qualcosa, lo deve dire.

    Rinominato rispetto alla versione precedente (che si chiamava "...non_di_
    hiris..."): il codice non distingue affatto un oggetto fatto da HIRIS da
    uno del proprietario nell'anteprima -- lo dichiara per QUALUNQUE modifica
    di un oggetto esistente. Il contrasto con la creazione (che non lo dice)
    e' quello che rende l'asserzione capace di fallire davvero."""
    officina, _, _, _ = banco
    esito_modifica = await officina.proponi(_intento(gesto="modifica", chiave="1771"),
                                            origine="chat", turno="t1", adesso=ADESSO)
    esito_crea = await officina.proponi(_intento(), origine="chat", turno="t1",
                                        adesso=ADESSO)
    assert ("esiste gia" in esito_modifica["anteprima"]
            or "gia' esistente" in esito_modifica["anteprima"])
    assert "esiste gia" not in esito_crea["anteprima"]


@pytest.mark.asyncio
async def test_una_struttura_gestita_a_mano_non_diventa_un_guasto(banco):
    """Se l'API dice che non si scrive, si dice PERCHE' (spec §6)."""
    officina, ha, _, _ = banco
    ha._override["salva"] = {"errore": "404: Not Found"}
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "gestite a mano" in esito["errore"]


@pytest.mark.asyncio
async def test_ripristinare_rimette_il_prima_passando_dalla_stessa_officina(banco):
    officina, ha, archivio, _ = banco
    p = await officina.proponi(_intento(gesto="modifica", chiave="1771"),
                               origine="chat", turno="t1", adesso=ADESSO)
    await officina.applica(p["proposta_id"], origine="pagina", turno=None, adesso=ADESSO + 60)
    ha.salvate.clear()
    esito = await officina.ripristina(p["proposta_id"], origine="pagina", turno=None,
                                      adesso=ADESSO + 120)
    assert esito["applicata"] is True
    assert ha.salvate[0][2]["alias"] == "com'era"


@pytest.mark.asyncio
async def test_una_scena_con_due_stati_sulla_stessa_entita_si_rifiuta(banco):
    """Le scene non passano da `validate_config`: se il doppione non lo prende
    l'officina, non lo prende piu' nessuno e uno dei due stati sparisce."""
    officina, ha, archivio, _ = banco
    esito = await officina.proponi(
        _intento(dominio="scene", innesco=[], azioni=[], richiesto="scena",
                 stati=[{"entity_id": "light.salotto", "state": "on"},
                        {"entity_id": "light.salotto", "state": "off"}]),
        origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "light.salotto" in esito["errore"]
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_il_consiglio_del_mestiere_viaggia_nell_anteprima(banco):
    officina, _, _, _ = banco
    esito = await officina.proponi(
        _intento(richiesto="automazione", innesco=[], ricorrente=False,
                 azioni=[{"action": "light.turn_off"}]),
        origine="chat", turno="t1", adesso=ADESSO)
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
    esito = await officina.proponi(_intento(gesto="modifica", chiave="9999"),
                                   origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "errore" in esito
    assert "9999" in esito["errore"] or "non esiste" in esito["errore"].lower()
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_cancellare_un_oggetto_sparito_si_rifiuta_invece_di_esplodere(banco):
    """Stesso guasto, stessa guardia, sull'altro gesto che legge il «prima»."""
    officina, ha, archivio, _ = banco
    ha._override["leggi"] = {"assente": True}
    esito = await officina.proponi(_intento(gesto="cancella", chiave="9999"),
                                   origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "errore" in esito
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_una_proposta_senza_turno_non_si_conferma_da_un_turno_qualsiasi(banco):
    """IMPORTANT 1: una proposta nata senza identita' di turno (il ramo
    sincrono della chat, l'intestazione mancante) resta orfana del cancello:
    non e' confermabile da un'origine non umana, qualunque turno arrivi dopo.
    La condizione precedente (`proposta["turno"] and proposta["turno"] ==
    turno`) restava falsa quando il turno memorizzato era `None`, e lasciava
    passare la prima conferma che capitava."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno=None, adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="qualunque",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert "pagina" in esito["errore"].lower()
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_l_origine_umana_che_scavalca_il_cancello_lascia_una_traccia(banco, caplog):
    """IMPORTANT 1: se il Task 8 sbagliasse a inoltrare un'origine scelta dal
    modello come `pagina`, deve restarne una traccia -- non il silenzio."""
    officina, ha, _, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    with caplog.at_level("INFO", logger="hiris.app.azione.costruzione.officina"):
        await officina.applica(p["proposta_id"], origine="pagina", turno=None,
                               adesso=ADESSO + 60)
    assert any(r.levelname == "INFO" and "pagina" in r.message.lower()
              for r in caplog.records)


@pytest.mark.asyncio
async def test_la_disfatta_dell_helper_e_dichiarata_nel_motivo(banco):
    """IMPORTANT 2: oggi l'utente non sa che un helper e' nato ed e' stato
    tolto. Il motivo del rifiuto deve dirlo."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.proponi(intento, origine="chat", turno="t1", adesso=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert "modalita_notte" in esito["errore"]


@pytest.mark.asyncio
async def test_se_la_disfatta_fallisce_lo_dice_invece_di_tacere(banco):
    """IMPORTANT 2: se anche `cancella_helper` fallisce, l'archivio non deve
    dire «non e' successo niente» mentre in casa resta un helper orfano che
    nessuno pulira' piu'."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.proponi(intento, origine="chat", turno="t1", adesso=ADESSO)
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    ha._override["cancella_helper"] = {"errore": "Home Assistant non ha risposto"}
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert "toglilo a mano" in esito["errore"] or "rimasto in casa" in esito["errore"]
    assert "modalita_notte" in esito["errore"]


@pytest.mark.asyncio
async def test_un_helper_senza_id_restituito_viene_dichiarato(banco):
    """IMPORTANT 2: un helper la cui creazione non restituisce un id non
    entra in `nati` e quindi non e' mai disfabile -- deve essere dichiarato,
    non perso in silenzio."""
    officina, ha, archivio, _ = banco
    intento = _intento(helper=[{"dominio": "input_boolean", "dati": {"name": "Modalita notte"}}])
    p = await officina.proponi(intento, origine="chat", turno="t1", adesso=ADESSO)
    ha._override["crea_helper"] = {"helper": {}}  # nessun id
    ha._override["salva"] = {"errore": "Message malformed: bad actions"}
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert "input_boolean" in esito["errore"]
    assert ha.helper_cancellati == []


@pytest.mark.asyncio
async def test_due_conferme_della_stessa_proposta_non_scrivono_due_volte(banco):
    """IMPORTANT 3: la rivendicazione atomica, non una lettura gia' stantia
    nel momento in cui la si confronta.

    Si simula la finestra di corsa monkeypatchando `_archivio.leggi` cosi' da
    restituire sempre l'istantanea «in_attesa» catturata PRIMA che un'altra
    richiesta rivendichi la proposta per prima (`archivio.rivendica` sotto):
    e' la stessa finestra che due click ravvicinati aprirebbero in un server
    vero, dove la lettura iniziale non e' piu' aggiornata nell'istante in cui
    la si confronta con l'esito di una richiesta concorrente. L'unica difesa
    possibile e' l'UPDATE atomica dentro `applica`, non il controllo sullo
    stato gia' letto in testa alla funzione."""
    officina, ha, archivio, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    proposta_stantia = archivio.leggi(p["proposta_id"])
    assert proposta_stantia["stato"] == "in_attesa"
    # Un'altra richiesta rivendica per prima: il DB passa a `in_corso`.
    prima_rivendicazione = archivio.rivendica(p["proposta_id"], adesso=ADESSO + 59)
    assert "errore" not in prima_rivendicazione
    # Questa richiesta lavora ancora sulla lettura stantia.
    officina._archivio.leggi = lambda ident: proposta_stantia
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert "errore" in esito
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_un_intento_vuoto_si_rifiuta_invece_di_validare_niente(banco):
    """IMPORTANT 4: l'unico caso in cui il mestiere non ha niente da dire e'
    proprio quello in cui tace (`consiglia` torna col ritorno anticipato,
    `dissenso: False`). Senza questo controllo il corpo composto avrebbe tre
    liste vuote, Home Assistant lo direbbe «valido», e una conferma
    scriverebbe in casa un'automazione inerte."""
    officina, ha, archivio, _ = banco
    esito = await officina.proponi(
        _intento(innesco=[], azioni=[], stati=[], parametri=[], ricorrente=False,
                 richiesto=None),
        origine="chat", turno="t1", adesso=ADESSO)
    assert "proposta_id" not in esito
    assert "non ho capito" in esito["errore"]
    assert ha.salvate == []
    assert archivio.elenca() == []


@pytest.mark.asyncio
async def test_il_motivo_del_mestiere_viaggia_nell_anteprima_anche_senza_dissenso(banco):
    """IMPORTANT 4: prima il motivo del mestiere finiva nell'anteprima solo
    in caso di dissenso; ora ci finisce sempre, quando c'e'."""
    officina, _, _, _ = banco
    esito = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    assert "Nota" in esito["anteprima"]
    assert "automazione" in esito["anteprima"].lower()


@pytest.mark.asyncio
async def test_ripristinare_dalla_chat_e_un_giro_in_due_tempi(banco):
    """IMPORTANT 5: prima `ripristina` creava la proposta e la passava subito
    ad `applica` con lo stesso `turno`, che il cancello rifiutava SEMPRE --
    e la riga restava `in_attesa` a bruciare un posto del tetto per sette
    giorni. Ora, dalla chat, e' un giro in due tempi come tutto il resto."""
    officina, ha, archivio, _ = banco
    p = await officina.proponi(_intento(gesto="modifica", chiave="1771"),
                               origine="chat", turno="t1", adesso=ADESSO)
    await officina.applica(p["proposta_id"], origine="pagina", turno=None, adesso=ADESSO + 60)
    ha.salvate.clear()
    esito = await officina.ripristina(p["proposta_id"], origine="chat", turno="t3",
                                      adesso=ADESSO + 120)
    assert "proposta_id" in esito
    assert esito["anteprima"]
    assert ha.salvate == []
    esito2 = await officina.applica(esito["proposta_id"], origine="chat", turno="t4",
                                    adesso=ADESSO + 180)
    assert esito2["applicata"] is True
    assert ha.salvate[0][2]["alias"] == "com'era"


@pytest.mark.asyncio
async def test_un_alias_che_non_e_testo_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6: un `alias` a forma di dizionario solleverebbe `TypeError:
    unhashable type` da `_seme_da`. Il chiamante e' uno strumento riempito da
    un modello: si rifiuta con un motivo leggibile."""
    officina, ha, archivio, _ = banco
    esito = await officina.proponi(_intento(alias={"non": "testo"}), origine="chat",
                                   turno="t1", adesso=ADESSO)
    assert "errore" in esito
    assert "alias" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_un_helper_che_non_e_un_dizionario_si_rifiuta_invece_di_esplodere(banco):
    """IMPORTANT 6: una lista `helper` di stringhe solleverebbe `AttributeError`
    su `helper.get("dominio")`."""
    officina, ha, archivio, _ = banco
    esito = await officina.proponi(_intento(helper=["non un dizionario"]), origine="chat",
                                   turno="t1", adesso=ADESSO)
    assert "errore" in esito
    assert "helper" in esito["errore"]
    assert ha.salvate == []


@pytest.mark.asyncio
async def test_cancellare_chiama_cancella_configurazione_con_la_chiave_giusta(banco):
    """IMPORTANT 7: nessun test esercitava il gesto distruttivo."""
    officina, ha, archivio, _ = banco
    p = await officina.proponi(_intento(gesto="cancella", chiave="1771"),
                               origine="chat", turno="t1", adesso=ADESSO)
    esito = await officina.applica(p["proposta_id"], origine="chat", turno="t2",
                                   adesso=ADESSO + 60)
    assert esito["applicata"] is True
    assert ha.cancellate == [("automation", "1771")]


@pytest.mark.asyncio
async def test_ripristinare_una_creazione_la_cancella(banco):
    """IMPORTANT 7: ripristinare una CREAZIONE e' cio' che trasforma un
    ripristino in una cancellazione da Home Assistant -- nessun test lo
    esercitava."""
    officina, ha, archivio, _ = banco
    p = await officina.proponi(_intento(), origine="chat", turno="t1", adesso=ADESSO)
    await officina.applica(p["proposta_id"], origine="pagina", turno=None, adesso=ADESSO + 60)
    chiave_nata = ha.salvate[0][1]
    esito = await officina.ripristina(p["proposta_id"], origine="pagina", turno=None,
                                      adesso=ADESSO + 120)
    assert esito["applicata"] is True
    assert ha.cancellate == [("automation", chiave_nata)]
