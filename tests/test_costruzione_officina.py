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


@pytest.mark.asyncio
async def test_modificare_un_oggetto_non_di_hiris_lo_dichiara_nell_anteprima(banco):
    """Regola posta dal proprietario: se tocca qualcosa, lo deve dire."""
    officina, _, _, _ = banco
    esito = await officina.proponi(_intento(gesto="modifica", chiave="1771"),
                                   origine="chat", turno="t1", adesso=ADESSO)
    assert "esiste gia" in esito["anteprima"] or "gia' esistente" in esito["anteprima"]


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
