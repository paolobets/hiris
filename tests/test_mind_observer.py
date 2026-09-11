"""L'osservatore che **si dà lo scope da sé**: guarda la casa che gli compete,
con l'obiettivo davanti, e decide cosa pesa -- soggetto per soggetto, col
perché scritto (spec §5.1).

**Misurato sulla casa vera il 10/09/2026.** La casa intera, una riga per
entità: 833 entità, 106.433 caratteri, ≈26.600 token. Tolte le entità di
servizio e le nascoste: **381 entità, 46.098 caratteri, ≈11.500 token** -- le
423 di servizio e le 29 nascoste valevano **15.000 token a ogni giro**, più
della metà del prompt.

**Le entità di servizio e le nascoste non entrano di default** (decisione del
proprietario, 10/09/2026), ed è la stessa legge che il nucleo applica già al
digesto: fuori da ciò che si dice senza che sia stato chiesto, dentro quando
qualcuno lo chiede. La regola non si riscrive qui -- si chiama quella del
nucleo (`briefing.digest_visible_entity_ids`), o le due divergerebbero al
primo cambiamento.
"""
import os

import pytest

from hiris.app.mind import observer
from hiris.app.mind.scope import OBSERVER
from hiris.app.mind.store import ObservationsStore


@pytest.fixture
def archivio(tmp_path):
    a = ObservationsStore(os.path.join(str(tmp_path), "osservazioni.db"))
    yield a
    a.close()


def _casa(**extra):
    """Un'anagrafe minima nella forma vera di `home_space/reader.py`."""
    entita = [
        {"id": "climate.camera_t", "nome": "Termostato Camera", "classe": None,
         "unita": None, "translation_key": None, "categoria": None,
         "disabilitata": 0, "nascosta": 0, "area_id": "camera",
         "piattaforma": "netatmo"},
        {"id": "sensor.presa_energia", "nome": "Presa Energia", "classe": "energy",
         "unita": "kWh", "translation_key": "energy_today", "categoria": None,
         "disabilitata": 0, "nascosta": 0, "area_id": "cucina",
         "piattaforma": "shelly"},
        {"id": "sensor.wifi_signal", "nome": "Wi-Fi", "classe": None, "unita": "dBm",
         "translation_key": None, "categoria": "diagnostic",
         "disabilitata": 0, "nascosta": 0, "area_id": None, "piattaforma": "shelly"},
        {"id": "light.vecchia", "nome": "Vecchia", "classe": None, "unita": None,
         "translation_key": None, "categoria": None,
         "disabilitata": 0, "nascosta": 1, "area_id": None, "piattaforma": "hue"},
        {"id": "switch.spento", "nome": "Spento", "classe": None, "unita": None,
         "translation_key": None, "categoria": None,
         "disabilitata": 1, "nascosta": 0, "area_id": None, "piattaforma": "hue"},
    ]
    casa = {"entita": entita, "aree": [{"id": "camera", "nome": "Camera"},
                                       {"id": "cucina", "nome": "Cucina"}]}
    casa.update(extra)
    return casa


class _Modello:
    """Il runner finto. Registra cosa gli e' stato chiesto -- il prompt e'
    meta' di questa fetta, e una finta che lo butti via non potrebbe mai
    vederlo sbagliato."""

    def __init__(self, risposta="[]", *, solleva=False):
        self.risposta = risposta
        self.solleva = solleva
        self.chiamate = []

    async def chat(self, *, user_message, system_prompt="", model="auto",
                   agent_type="chat", max_tokens=0, **kw):
        # Solo per NOME: `LLMRouter.chat` prende `**kwargs` e basta. Una finta
        # che accetti anche il posizionale lascerebbe passare una chiamata che
        # in produzione morirebbe al primo giro.
        self.chiamate.append({"domanda": user_message, "sistema": system_prompt,
                              "modello": model, "tipo": agent_type})
        if self.solleva:
            raise RuntimeError("il modello non risponde")
        return self.risposta


# -- la casa che gli compete -------------------------------------------

def test_le_entita_di_servizio_le_nascoste_e_le_disabilitate_restano_fuori():
    """**15.000 token a ogni giro**, misurati: 423 di servizio e 29 nascoste
    sulla casa vera, piu' della meta' del prompt. E non e' solo una spesa: sono
    entita' che non dicono niente su come vive la casa, e chiederne il giudizio
    al modello ne diluisce l'attenzione su quelle che contano.

    Mutazione che la uccide: iterare `casa["entita"]` senza filtro.
    """
    righe = observer.house_lines(_casa())

    testo = "\n".join(righe)
    assert "climate.camera_t" in testo
    assert "sensor.presa_energia" in testo
    assert "sensor.wifi_signal" not in testo     # di servizio (`diagnostic`)
    assert "light.vecchia" not in testo          # nascosta
    assert "switch.spento" not in testo          # disabilitata
    assert len(righe) == 2


def test_la_regola_e_QUELLA_DEL_NUCLEO_non_una_seconda_uguale(monkeypatch):
    """Il nucleo applica gia' questa legge al digesto
    (`briefing.digest_visible_entity_ids`). Riscriverla qui la farebbe
    divergere al primo cambiamento da una parte sola -- la seconda fondamenta,
    e questo prodotto l'ha gia' violata esattamente cosi' (`_highlight_lines`
    contro `_capability_lines`, rilievo R1 dell'08/09/2026: due totali diversi
    per la stessa parola nella stessa pagina).

    **Si cambia la regola del nucleo e si guarda se l'osservatore la segue.**
    Confrontare i due risultati non basterebbe: una COPIA fedele dei tre
    controlli darebbe lo stesso elenco e la prova resterebbe verde -- e' il
    difetto n.1 di questo progetto, la prova che non puo' fallire. Qui la
    regola finta esclude cio' che il filtro vero terrebbe dentro: solo chi la
    chiama davvero puo' seguirla.

    Mutazione che la uccide: ricopiare i tre controlli dentro `house_lines`.
    """
    monkeypatch.setattr(observer, "digest_visible_entity_ids",
                        lambda casa: frozenset({"sensor.wifi_signal"}))

    righe = observer.house_lines(_casa())

    assert [r.split(" · ")[0] for r in righe] == ["sensor.wifi_signal"]


def test_ogni_riga_porta_cio_che_serve_a_giudicare_e_nient_altro():
    """Il modello deve poter dire se un'entita' pesa sull'obiettivo: le servono
    l'identificatore, il nome, la classe dichiarata da Home Assistant, l'unita'
    e l'area. **Il `translation_key` c'e' perche' e' cio' che l'integrazione
    dichiara DI SE'** -- `energy_today`, non «Potenza» da indovinare -- ed e' la
    ragione per cui il riconoscimento non era mai stato il problema.

    Cio' che NON c'e' e' altrettanto deliberato: `unique_id`, `config_entry_id`,
    `dispositivo_id` sono identificatori opachi che non aiutano nessun giudizio
    e costano token su 381 righe.
    """
    riga = next(r for r in observer.house_lines(_casa()) if r.startswith("sensor.presa_energia"))

    assert "Presa Energia" in riga
    assert "energy" in riga
    assert "kWh" in riga
    assert "Cucina" in riga
    assert "energy_today" in riga
    assert "shelly" not in riga


def test_un_area_senza_nome_non_diventa_un_identificatore_nudo():
    """L'area si mostra col nome che il proprietario le ha dato. Un `area_id`
    grezzo in mezzo a un prompt in italiano e' rumore, e un'area che non esiste
    piu' non deve far comparire una stringa che sembra un luogo."""
    casa = _casa()
    casa["entita"][0]["area_id"] = "01K2CK4GG287VKK18M5J788MRQ"

    riga = next(r for r in observer.house_lines(casa) if r.startswith("climate.camera_t"))

    assert "01K2CK" not in riga
    assert riga == "climate.camera_t · Termostato Camera"


# -- la domanda --------------------------------------------------------

def test_la_domanda_porta_l_obiettivo_e_la_casa():
    """Lo scope e' una risposta a una domanda: senza l'obiettivo davanti, il
    modello deciderebbe rispetto a un criterio suo."""
    domanda = observer.build_question("tenere la casa calda e spendere poco",
                                      observer.house_lines(_casa()))

    assert "tenere la casa calda e spendere poco" in domanda
    assert "climate.camera_t" in domanda


def test_la_domanda_chiede_un_MOTIVO_per_ogni_decisione():
    """Una scelta senza ragione non e' rivedibile da nessuno -- ne'
    dall'analista ne' dal proprietario -- e la pagina esiste per farle vedere,
    le ragioni. L'archivio rifiuta una decisione senza motivo
    (`store.decide_scope`): se la domanda non lo chiedesse, meta' delle
    risposte verrebbero buttate al confine senza che nessuno capisca perche'."""
    domanda = observer.build_question("obiettivo", ["sensor.x ..."])

    assert "motivo" in domanda.lower()


# -- la risposta -------------------------------------------------------

def test_si_leggono_le_decisioni_dal_JSON():
    decisioni, guasto = observer.read_decisions(
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda la casa"}]')

    assert guasto is None
    assert decisioni == [{"id": "climate.camera_t", "dentro": True,
                          "motivo": "scalda la casa"}]


def test_il_JSON_dentro_una_staccionata_si_legge_lo_stesso():
    """I modelli incorniciano il JSON in ```json anche quando si chiede di non
    farlo. Rifiutare la risposta per la cornice butterebbe un giro intero --
    ≈11.500 token -- per un dettaglio di forma."""
    decisioni, guasto = observer.read_decisions(
        'Ecco:\n```json\n[{"id": "a", "dentro": false, "motivo": "non pesa"}]\n```\n')

    assert guasto is None
    assert [d["id"] for d in decisioni] == ["a"]


def test_una_risposta_illeggibile_e_un_GUASTO_non_una_casa_vuota():
    """`[]` direbbe «il modello ha guardato la casa e non ha trovato niente da
    osservare», che e' un'affermazione. Una risposta che non si e' potuta
    leggere e' un'altra cosa, e va detta -- e' la distinzione a tre stati che
    questo prodotto difende ovunque.

    Mutazione che la uccide: tornare `[]` quando il JSON non si legge.
    """
    decisioni, guasto = observer.read_decisions("Mi dispiace, non posso aiutarti.")

    assert decisioni == []
    assert guasto is not None


def test_una_voce_malformata_si_salta_senza_buttare_le_altre():
    """380 giudizi buoni non si perdono per uno storto. La voce saltata resta
    **non decisa**, quindi l'impronta la ripresentera' al giro dopo: si ripara
    da se', invece di sparire in silenzio."""
    decisioni, guasto = observer.read_decisions(
        '[{"id": "a", "dentro": true, "motivo": "pesa"},'
        ' {"dentro": true, "motivo": "senza id"},'
        ' "una stringa",'
        ' {"id": "b", "dentro": true, "motivo": "pesa anche lei"}]')

    assert guasto is None
    assert [d["id"] for d in decisioni] == ["a", "b"]


# -- il giro intero ----------------------------------------------------

@pytest.mark.asyncio
async def test_le_decisioni_finiscono_nell_archivio_col_loro_autore(archivio):
    modello = _Modello(
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda la casa"},'
        ' {"id": "sensor.presa_energia", "dentro": false, "motivo": "doppione del contatore"}]')

    esito = await observer.reconsider(modello, archivio, _casa(),
                                      reason="prima volta", now=1000.0)

    assert esito["decise"] == 2
    scope = archivio.scope()
    assert scope["climate.camera_t"]["dentro"] is True
    assert scope["climate.camera_t"]["autore"] == OBSERVER
    assert scope["sensor.presa_energia"]["dentro"] is False


@pytest.mark.asyncio
async def test_l_osservatore_non_decide_su_cio_che_non_gli_e_stato_mostrato(archivio):
    """**Il modello puo' inventare un identificatore**, e un'entita' inventata
    nello scope sarebbe una riga che nessun evento potra' mai accendere e che
    la pagina mostrerebbe come osservata. Si accetta solo cio' che era nella
    domanda.

    Mutazione che la uccide: scrivere ogni voce che arriva.
    """
    modello = _Modello(
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda"},'
        ' {"id": "sensor.inventato", "dentro": true, "motivo": "chissa"}]')

    esito = await observer.reconsider(modello, archivio, _casa(),
                                      reason="prima volta", now=1000.0)

    assert "sensor.inventato" not in archivio.scope()
    assert esito["ignorate"] == 1


@pytest.mark.asyncio
async def test_una_decisione_senza_motivo_non_entra_e_si_CONTA(archivio):
    """L'archivio la rifiuta (`decide_scope`), e il giro deve saperlo: un
    conteggio che dicesse «2 decise» quando una e' stata buttata sarebbe un
    numero non misurato scritto come misurato."""
    modello = _Modello(
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "   "},'
        ' {"id": "sensor.presa_energia", "dentro": true, "motivo": "pesa"}]')

    esito = await observer.reconsider(modello, archivio, _casa(),
                                      reason="prima volta", now=1000.0)

    assert esito["decise"] == 1
    assert esito["rifiutate"] == 1
    assert "climate.camera_t" not in archivio.scope()


@pytest.mark.asyncio
async def test_un_modello_che_non_risponde_non_scrive_NIENTE(archivio):
    """Ne' decisioni ne' riconsiderazione. Annotare un giro fallito come fatto
    farebbe aspettare la cadenza intera prima di riprovare, su una casa di cui
    non si e' deciso niente.

    Mutazione che la uccide: annotare la riconsiderazione fuori dal ramo
    riuscito.
    """
    modello = _Modello(solleva=True)

    esito = await observer.reconsider(modello, archivio, _casa(),
                                      reason="prima volta", now=1000.0)

    assert esito["errore"]
    assert archivio.scope() == {}
    assert archivio.last_reconsideration() is None


@pytest.mark.asyncio
async def test_una_risposta_illeggibile_non_annota_un_giro_riuscito(archivio):
    modello = _Modello("non oggi")

    esito = await observer.reconsider(modello, archivio, _casa(),
                                      reason="prima volta", now=1000.0)

    assert esito["errore"]
    assert archivio.last_reconsideration() is None


@pytest.mark.asyncio
async def test_il_giro_riuscito_si_annota_con_la_ragione_e_la_misura(archivio):
    """La pagina dira' «l'ultima volta e' stata il 9, perche' era comparso un
    termostato nuovo, e la cadenza e' 84 ore perche' Home Assistant ricorda 7
    giorni». Tutti e quattro i numeri vengono da qui."""
    modello = _Modello('[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda"}]')

    await observer.reconsider(modello, archivio, _casa(), reason="e' comparso qualcosa",
                              window_s=604800.0, cadence_s=302400.0, now=1000.0)

    ultima = archivio.last_reconsideration()
    assert ultima["quando_ts"] == 1000.0
    assert ultima["motivo"] == "e' comparso qualcosa"
    assert ultima["finestra_s"] == 604800.0
    assert ultima["cadenza_s"] == 302400.0


@pytest.mark.asyncio
async def test_l_osservatore_si_dichiara_al_conto_dei_consumi(archivio):
    """`agent_type` decide sotto quale voce il giro finisce nei consumi. Un
    osservatore contato come «chat» renderebbe invisibile il costo vero del
    prodotto -- un giro ogni 84 ore su ≈11.500 token -- proprio nella pagina
    fatta per vederlo."""
    modello = _Modello("[]")

    await observer.reconsider(modello, archivio, _casa(), reason="x", now=1000.0)

    assert modello.chiamate[0]["tipo"] == "observer"


# -- il turno del ponte: la stessa domanda, per un'altra porta ---------------
#
# Fetta «l'osservatore chiede a chi risponde davvero» (11/09/2026). Il giro
# dell'osservatore andava dritto a `llm_router`, dove il ponte **non e' un
# anello** (`llm_router._VALID_BACKEND_NAMES`: claude, openai, openrouter,
# ollama). Su una casa che gira interamente sul Piano Claude Max -- questa --
# l'osservatore non poteva usare l'unico fornitore che risponde, ed e'
# esattamente il difetto che `steering.py` dichiara di aver chiuso il
# 22/08/2026 per le promesse, con la frase *«una terza porta che nascesse
# domani non potrebbe inventarsene una terza senza accorgersene»*. La terza
# porta e' nata il 11/09 e se n'e' inventata una.


def test_il_turno_del_ponte_porta_la_STESSA_domanda_del_giro_sincrono(archivio):
    """**Una domanda sola, composta una volta.** Due composizioni della stessa
    domanda sono due verita' libere di divergere: la prima volta che qualcuno
    aggiunge un campo alla riga della casa da una parte sola, il ponte e la
    catena giudicherebbero case diverse senza che nessuna pagina lo dica.

    La prova confronta **byte per byte** cio' che il giro sincrono manda al
    modello con cio' che il turno del ponte compone: la domanda in cronologia
    piu' il contratto di risposta, che sul ponte viaggia a parte perche' li'
    l'istruzione di chiusura va in fondo al messaggio (`agent/prompts.
    build_chat_messages`). Le due porte mandano lo stesso testo, non un testo
    equivalente.

    Mutazione che la uccide: ricomporre la domanda dentro `bridge_turn`
    invece di chiamare `build_house_question`.
    """
    import asyncio

    casa = _casa()
    modello = _Modello("[]")
    asyncio.run(observer.reconsider(modello, archivio, casa, reason="x", now=1000.0))

    turno = observer.bridge_turn(archivio, casa)

    assert (turno["history"][0]["content"] + chr(10) + turno["istruzione"]
            == modello.chiamate[0]["domanda"])


def test_il_turno_del_ponte_porta_lo_STESSO_mestiere(archivio):
    """Il prompt di sistema e' quello che dice all'osservatore qual e' il suo
    mestiere: se il ponte ne ricevesse un altro, sarebbe un secondo
    osservatore, non lo stesso che risponde da un'altra porta.

    **Mutazione eseguita l'11/09/2026, vista rossa e ripristinata**: scrivere
    in `bridge_turn` un prompt di sistema abbreviato a mano, invece di
    passare `SYSTEM`.
    """
    turno = observer.bridge_turn(archivio, _casa())

    assert turno["system_prompt"] == observer.SYSTEM


def test_le_decisioni_si_SCRIVONO_da_una_risposta_qualunque_sia_arrivata(archivio):
    """La scrittura non appartiene alla chiamata al modello: appartiene alla
    risposta. E' cio' che permette al ponte -- che risponde minuti dopo, da un
    altro processo -- di far finire il giro senza una seconda copia di questo
    codice.

    **Mutazione eseguita l'11/09/2026, vista rossa e ripristinata**: scrivere
    `window_s=None, cadence_s=None` nella riconsiderazione. E' il
    peggioramento vero che questa separazione rende possibile -- la misura
    della memoria di Home Assistant si paga quando la domanda parte e si
    scrive quando la risposta torna, e fra i due momenti, sul ponte, ci sono
    minuti e un altro processo. Un numero perso per strada diventerebbe una
    finestra «non misurata» indistinguibile da una casa che non ricorda
    niente.
    """
    esito = observer.apply_answer(
        archivio, _casa(),
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda la casa"}]',
        reason="il ponte ha risposto", window_s=604800.0, cadence_s=302400.0,
        now=1000.0)

    assert esito == {"decise": 1, "rifiutate": 0, "ignorate": 0, "omesse": 0,
                     "candidate": 2}
    assert archivio.scope()["climate.camera_t"]["autore"] == OBSERVER
    ultima = archivio.last_reconsideration()
    assert ultima["motivo"] == "il ponte ha risposto"
    assert ultima["finestra_s"] == 604800.0
    assert ultima["cadenza_s"] == 302400.0


def test_una_risposta_illeggibile_dal_ponte_non_annota_NIENTE(archivio):
    """Stessa legge del giro sincrono: un giro fallito non si annota come
    fatto, o si aspetterebbe la cadenza intera -- 84 ore su questa casa --
    prima di riprovare, su una casa di cui non si e' deciso niente.

    Mutazione che la uccide: annotare la riconsiderazione prima di aver
    letto le decisioni.
    """
    esito = observer.apply_answer(archivio, _casa(), "non sono un JSON",
                                  reason="il ponte ha risposto", now=1000.0)

    assert "errore" in esito
    assert archivio.last_reconsideration() is None
    assert archivio.scope() == {}


def test_il_turno_del_ponte_porta_il_CONTRATTO_di_risposta(archivio):
    """**Senza, il ponte gli impone il contrario.** L'istruzione che il ponte
    aggiunge in coda a ogni turno di chat dice «usa testo semplice: niente
    blocchi di codice o JSON», e l'osservatore chiede esattamente un array
    JSON. Trovato leggendo il codice l'11/09/2026, prima di rilasciare: sarebbe
    tornata prosa, `read_decisions` l'avrebbe dichiarata illeggibile, e
    l'osservatore avrebbe continuato a fallire per un'altra causa con lo stesso
    esito.

    Mutazione che la uccide: non mettere `istruzione` nel turno.
    """
    turno = observer.bridge_turn(archivio, _casa())

    assert "array JSON" in turno["istruzione"]
    assert "dentro" in turno["istruzione"], (
        "il contratto porta anche la forma di ogni voce, non solo «JSON»")


# -- il lotto: la domanda si spezza, perche' la risposta non ci sta ----------
#
# Misurato dal vivo l'11/09/2026, due volte: un turno che chiede 381 giudizi
# produce ~30 KB di risposta (~8.000 token) e la CLI del piano viene uccisa dal
# tetto di 300 secondi del sottoprocesso -- `claude non eseguibile:
# TimeoutExpired` alle 15:44:12, esattamente 300 secondi dopo l'accodamento
# delle 15:39:12. Nessun consumo registrato, perche' il turno non finisce mai.


def test_si_chiede_SOLO_del_lotto_quando_glielo_si_dice(archivio):
    """Mutazione che la uccide: ignorare `only` e comporre su tutta la casa."""
    righe = observer.house_lines(_casa(), only={"climate.camera_t"})

    assert [r.split(" · ")[0] for r in righe] == ["climate.camera_t"]


def test_il_lotto_non_puo_far_entrare_cio_che_NON_compete_all_osservatore(archivio):
    """`only` restringe, non allarga: un'entita' di servizio chiesta per nome
    resta fuori lo stesso, perche' la legge di cosa compete all'osservatore e'
    una sola e non la decide chi compone il lotto.

    Mutazione che la uccide: filtrare su `only` invece che intersecare con la
    regola del nucleo.
    """
    righe = observer.house_lines(_casa(), only={"sensor.wifi_signal"})

    assert righe == []


def test_il_turno_del_ponte_chiede_solo_del_suo_lotto(archivio):
    turno = observer.bridge_turn(archivio, _casa(), only={"climate.camera_t"})

    assert "climate.camera_t" in turno["history"][0]["content"]
    assert "sensor.presa_energia" not in turno["history"][0]["content"]


def test_cio_che_si_e_chiesto_e_il_modello_ha_OMESSO_non_resta_in_sospeso(archivio):
    """**Il buco che il lotto porta a galla.** La domanda dice: «un'entita' su
    cui davvero non sai decidere: omettila». Un'omissione lascia il soggetto
    NON deciso, e l'innesco «ci sono soggetti su cui nessuno ha deciso» lo
    riproporrebbe al giro dopo, e a quello dopo ancora: la campagna non
    finirebbe mai e l'osservatore chiederebbe al piano ogni dieci minuti per
    sempre.

    Si annota per quello che e': **guardata, e non giudicata** -- fuori, con la
    ragione scritta, quindi visibile nella pagina e rimettibile dentro con un
    gesto. Non e' una decisione inventata: e' il fatto vero.

    Mutazione che la uccide: non passare `asked`, e lasciare che l'omissione
    resti silenzio.
    """
    esito = observer.apply_answer(
        archivio, _casa(),
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda la casa"}]',
        asked={"climate.camera_t", "sensor.presa_energia"}, now=1000.0)

    scope = archivio.scope()
    assert scope["climate.camera_t"]["dentro"] is True
    assert scope["sensor.presa_energia"]["dentro"] is False
    assert "non ha saputo decidere" in scope["sensor.presa_energia"]["motivo"]
    assert esito["omesse"] == 1


def test_senza_sapere_cosa_si_e_chiesto_non_si_inventa_nessuna_omissione(archivio):
    """`asked` assente vuol dire «non si sa cosa fosse nel lotto»: allora non
    si annota niente per nessuno. Dedurre l'insieme chiesto dalla casa di ADESSO
    attribuirebbe un'omissione a un'entita' comparsa dopo la domanda."""
    esito = observer.apply_answer(
        archivio, _casa(),
        '[{"id": "climate.camera_t", "dentro": true, "motivo": "scalda"}]',
        now=1000.0)

    assert "sensor.presa_energia" not in archivio.scope()
    assert esito["omesse"] == 0
