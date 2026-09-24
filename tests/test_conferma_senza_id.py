"""Confermare senza ripetere l'identificatore che nessuno può ricordare.

**Il difetto, misurato sulla casa vera il 23/09/2026.** Ogni conferma costava
**tre turni invece di due**, sistematicamente.

La catena, tutta osservata:

1. al turno N `propose` restituisce `proposta_id` **in un risultato di
   strumento**;
2. la cronologia della chat salva solo `{role, content}` — testo — quindi al
   turno N+1 l'id **non c'è più**. Il codice lo sapeva già, scritto per
   un'altra ragione in `handlers_chat.py`: «la cronologia porta solo messaggi
   utente/assistente, un `proposta_id` non ci arriva mai»;
3. **nessuno strumento elenca le proposte in sospeso**, quindi l'id è
   irrecuperabile;
4. il modello rigenera la proposta, che così nasce **in quel turno**;
5. il cancello del consenso la rifiuta — correttamente — perché è lo stesso
   turno;
6. serve un terzo turno.

**Provato**: passando l'id a mano al secondo turno, la conferma è avvenuta
subito. L'unica cosa che mancava era l'id.

Il pattern che funziona era nello stesso catalogo: `cancel` dice «serve il suo
`id`: **prendilo da «agenda»**, non inventarlo», e `agenda` esiste. `confirm`
ha la stessa forma e l'«agenda» delle proposte non è mai stata costruita.

**La via scelta dal proprietario**: non un diciassettesimo strumento — le
definizioni degli strumenti sono già il 38% del carico di ogni richiesta, e si
pagherebbero a ogni turno per sempre — ma **l'id che diventa facoltativo**.
Senza id si conferma l'unica proposta in sospeso nata in un turno precedente;
se ce n'è più d'una il rifiuto **le elenca**, cioè l'elenco arriva esattamente
quando serve e costa zero quando non serve. È il principio già scritto in
questo codice: ogni rifiuto dice cosa manca.
"""
import os

import pytest

from hiris.app.action.construction.revisions import ConstructionStore
from hiris.app.action.construction.workshop import Workshop
from hiris.app.action.journal import Journal
from tests.test_construction_workshop import FintoHA, _intento

ADESSO = 1_756_000_000.0


@pytest.fixture()
def banco(tmp_path):
    archivio = ConstructionStore(os.path.join(str(tmp_path), "costruzioni.db"))
    cronaca = Journal(os.path.join(str(tmp_path), "azioni.db"))
    officina = Workshop(FintoHA(), archivio, cronaca)
    yield officina, archivio
    archivio.close()
    cronaca.close()


async def _proposta(officina, turno: str, alias: str = "Tapparelle all'alba"):
    esito = await officina.propose(_intento(alias=alias), actor="chat",
                                   exchange=turno, now=ADESSO)
    assert "errore" not in esito, esito
    return esito["proposta_id"]


@pytest.mark.asyncio
async def test_senza_id_si_conferma_L_UNICA_in_sospeso(banco):
    """**Il difetto.** Il caso normale: una proposta sola, nata al turno
    prima, e l'utente che dice «sì».

    Mutazione ESEGUITA: pretendere di nuovo l'id (sollevare se manca) --
    rossa."""
    officina, _ = banco
    ident = await _proposta(officina, "turno-1")

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert esito.get("applicata"), esito
    assert esito.get("proposta_id", ident) == ident


@pytest.mark.asyncio
async def test_l_id_ESPLICITO_continua_a_funzionare(banco):
    """Chi l'id ce l'ha — la pagina, e il modello quando se lo ricorda — non
    deve cambiare strada.

    Mutazione ESEGUITA: ignorare l'id ricevuto e risolvere sempre -- rossa."""
    officina, _ = banco
    ident = await _proposta(officina, "turno-1")

    esito = await officina.apply(ident, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert esito.get("applicata"), esito


@pytest.mark.asyncio
async def test_senza_NESSUNA_proposta_lo_dice(banco):
    """Un `confirm` a vuoto non deve somigliare a un guasto: dice che non c'è
    niente da confermare.

    Mutazione ESEGUITA: restituire il messaggio «non ho nessuna proposta con
    quell'identificatore», che parlerebbe di un id che l'utente non ha mai
    scritto -- rossa."""
    officina, _ = banco

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert "errore" in esito
    assert "identificatore" not in esito["errore"], esito["errore"]
    assert "sospeso" in esito["errore"] or "attesa" in esito["errore"]


@pytest.mark.asyncio
async def test_una_proposta_nata_in_QUESTO_turno_non_si_autoconferma(banco):
    """**La guardia di B-5 non si aggira per la porta di servizio.** Senza id,
    una proposta nata nello stesso turno non deve diventare confermabile: era
    l'unico modo in cui questa comodità poteva rompere il consenso.

    E il rifiuto deve dire **la cosa vera**: «te l'ho appena mostrata», non
    «non hai niente in sospeso» — che sarebbe falso, e manderebbe il modello a
    riproporla ancora.

    Mutazione ESEGUITA: risolvere fra TUTTE le pendenti invece che fra quelle
    di altri turni -- rossa.
    Mutazione ESEGUITA: dire «non c'e' niente in sospeso» anche quando una
    c'e', ma di questo turno -- rossa."""
    officina, _ = banco
    await _proposta(officina, "turno-1")

    esito = await officina.apply(None, actor="chat", exchange="turno-1",
                                 now=ADESSO + 60)

    assert "errore" in esito
    assert "stesso turno" in esito["errore"], esito["errore"]


@pytest.mark.asyncio
async def test_con_DUE_in_sospeso_il_rifiuto_le_ELENCA(banco):
    """Il rifiuto **è** l'elenco: costa zero quando non serve, e arriva
    esattamente quando serve. Senza gli id dentro, il modello resterebbe nello
    stesso vicolo cieco di prima — saprebbe che ce ne sono due e non
    saprebbe nominarle.

    Mutazione ESEGUITA: rifiutare senza elencare gli id -- rossa.
    Mutazione ESEGUITA: sceglierne una a caso invece di rifiutare -- rossa."""
    officina, _ = banco
    primo = await _proposta(officina, "turno-1", alias="Tapparelle all'alba")
    secondo = await _proposta(officina, "turno-1", alias="Luci al tramonto")

    esito = await officina.apply(None, actor="chat", exchange="turno-3",
                                 now=ADESSO + 60)

    assert "errore" in esito, esito
    assert primo in esito["errore"], esito["errore"]
    assert secondo in esito["errore"], esito["errore"]


@pytest.mark.asyncio
async def test_una_proposta_GIA_rivendicata_non_si_sceglie(banco):
    """`in_corso` vuol dire che qualcun altro la sta applicando **adesso**:
    sceglierla vorrebbe dire due `apply` in corsa sulla stessa riga. Il
    lettore delle pendenti le comprende tutte e due apposta (la finestra fra
    `claim` e la fine), quindi qui si restringe.

    Mutazione ESEGUITA: risolvere su `pending_only` invece che sul solo
    `in_attesa` -- rossa."""
    officina, archivio = banco
    ident = await _proposta(officina, "turno-1")
    archivio.claim(ident, now=ADESSO + 1)

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert "errore" in esito, esito
    assert "sospeso" in esito["errore"] or "attesa" in esito["errore"]


def test_lo_strumento_confirm_NON_pretende_piu_l_id():
    """Il contratto verso il modello. Finché lo schema dichiara
    `proposta_id` obbligatorio, il modello che non ce l'ha **non può
    chiamare** `confirm`: è la porta chiusa che costava il terzo turno.

    Mutazione ESEGUITA: rimettere `proposta_id` fra i `required` -- rossa."""
    from hiris.app.home_space.tools import KNOWLEDGE_TOOLS

    confirm = next(t for t in KNOWLEDGE_TOOLS if t["name"] == "confirm")
    schema = confirm["input_schema"]

    assert "proposta_id" in schema["properties"], (
        "l'id deve restare dichiarato: chi ce l'ha lo passa")
    assert "proposta_id" not in schema.get("required", []), (
        "l'id e' ancora obbligatorio: il modello che non ce l'ha non puo' "
        "chiamare confirm, ed e' il difetto che costava il terzo turno")


def test_la_GUIDA_dice_al_modello_che_puo_ometterlo():
    """Uno schema che lo permette e una guida che non lo dice lasciano il
    modello a indovinare — e indovinando rigenera, che è da dove siamo
    partiti.

    Mutazione ESEGUITA: togliere la frase dalla guida -- rossa."""
    from hiris.app.claude_runner import BASE_SYSTEM_PROMPT

    assert "senza il `proposta_id`" in BASE_SYSTEM_PROMPT, (
        "la guida non dice al modello che l'id si puo' omettere")


# --- I due casi che le mutazioni hanno scoperto scoperti ------------------
#
# Le prove qui sopra non avevano MAI due proposte in sospeso insieme, e due
# mutazioni sono sopravvissute per quello: «ignora l'id e risolvi sempre» e
# «risolvi fra tutte le pendenti, anche quelle di questo turno». Con una sola
# proposta le due strade danno lo stesso esito, quindi non provavano niente.
# Trovato eseguendo le mutazioni, non leggendo.


@pytest.mark.asyncio
async def test_con_l_id_ESPLICITO_non_conta_quante_ne_pendono(banco):
    """Chi nomina la proposta dev'essere obbedito, anche quando ce n'è più
    d'una: la risoluzione è un ripiego per chi l'id non ce l'ha, non una
    seconda opinione su chi ce l'ha.

    Mutazione ESEGUITA: ignorare l'id ricevuto e risolvere sempre -- rossa
    (con due in sospeso la risoluzione rifiuterebbe, e la proposta nominata
    non verrebbe applicata)."""
    officina, _ = banco
    primo = await _proposta(officina, "turno-1", alias="Tapparelle all'alba")
    await _proposta(officina, "turno-1", alias="Luci al tramonto")

    esito = await officina.apply(primo, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert esito.get("applicata"), esito


@pytest.mark.asyncio
async def test_una_proposta_di_QUESTO_turno_non_blocca_quella_di_prima(banco):
    """**Il valore vero del filtro sui turni**, e non è quello che credevo.

    Una proposta nata in questo stesso turno non è confermabile — la guardia
    del consenso la ferma comunque, quindi togliere il filtro non aprirebbe
    nessuna porta. Ma **la farebbe contare come candidata**, e due candidate
    fanno rifiutare: una proposta che l'utente non può ancora confermare
    bloccherebbe quella che invece aspetta il suo sì da un turno.

    Mutazione ESEGUITA: risolvere fra TUTTE le pendenti -- rossa."""
    officina, _ = banco
    vecchia = await _proposta(officina, "turno-1", alias="Tapparelle all'alba")
    await _proposta(officina, "turno-2", alias="Luci al tramonto")

    esito = await officina.apply(None, actor="chat", exchange="turno-2",
                                 now=ADESSO + 60)

    assert esito.get("applicata"), esito
    assert esito.get("proposta_id", vecchia) == vecchia
