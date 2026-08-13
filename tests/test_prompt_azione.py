"""fetta «comandare» (Task 6): il prompt sa che HIRIS puo' agire.

Il Task 5 ha messo `esegui` nel catalogo unico e nell'argv della CLI: da
quel commit il modello RICEVE lo strumento. Ma i due prompt continuavano a
dirgli «HIRIS non agisce: non accendi, non spegni» -- e un modello che legge
quell'ordine rifiuta di agire pur avendo lo strumento in mano. Il sintomo
(«HIRIS dice che non puo' accendere») e' indistinguibile da «gli strumenti
sono rotti»: e' la ragione per cui questo task non e' cosmetico.

**Dove sta cosa, e perche'.** Il prodotto ha DUE percorsi di chat, e i test
qui sotto guardano il testo che il modello legge DAVVERO su ciascuno:

- il percorso SINCRONO (chiave API, `claude_runner.ClaudeRunner.chat` e
  `backends/openai_compat_runner.py`) compone `BASE_SYSTEM_PROMPT` e NON
  vede mai le guide di `agent/prompts.py`;
- il PONTE (chat via abbonamento, `agent/prompts.build_chat_messages`)
  compone `BASE_IDENTITA` + -- solo quando gli strumenti ci sono davvero --
  `BASE_REGOLE_STRUMENTI`, e poi una delle due guide.

Le quattro cose che questo task deve dire (`esegui` esiste; gli id e non i
nomi; racconta cosa e' SUCCESSO; come si tratta l'ambiguita') sono regole del
PRODOTTO, non del ponte: se vivessero nella sola `_GUIDA_CON_STRUMENTI` il
percorso sincrono -- quello che oggi porta la chat vera -- agirebbe senza
nessuna di esse. Stanno quindi in `BASE_REGOLE_STRUMENTI`, l'unico testo che
viene emesso SE E SOLO SE gli strumenti esistono, su entrambi i percorsi.
Alla guida del ponte resta il suo mestiere di sempre: i nomi PREFISSATI, gli
unici che la CLI accetta.

Per questo alcuni test guardano il prompt COMPOSTO (`_prompt_del_ponte()`) e
non la sola costante: il soggetto e' cio' che il modello legge, e la costante
e' solo la via d'accesso.
"""
import pytest

from hiris.app.agent import prompts
from hiris.app.agent.prompts import _GUIDA_CON_STRUMENTI, _GUIDA_SENZA_STRUMENTI
from hiris.app.claude_runner import BASE_SYSTEM_PROMPT


def _prompt_del_ponte() -> str:
    """Il system prompt del ponte col ramo attivo: BASE intero + persona +
    `_GUIDA_CON_STRUMENTI`. E' cio' che il modello legge quando la sonda ha
    trovato gli strumenti -- l'unico turno del ponte in cui puo' agire."""
    system, _user = prompts.build_chat_messages(
        "Per scoprire cosa c'e' in casa usa `cerca` e `guarda`.",
        [], contesto="## La casa\nBagno: luce spenta.",
        strumenti_attivi=True)
    return system


def _i_due_testi_di_chi_puo_agire() -> dict[str, str]:
    """I due prompt, uno per percorso, di quando gli strumenti ci sono.

    Un test che ne guardasse uno solo lascerebbe l'altro percorso libero di
    divergere in silenzio: e' esattamente la divergenza che la fetta
    «parita'» ha passato due task a chiudere."""
    return {"sincrono": BASE_SYSTEM_PROMPT, "ponte": _prompt_del_ponte()}


# -- 1. `esegui` esiste -----------------------------------------------------

def test_la_guida_nomina_esegui():
    assert "esegui" in _GUIDA_CON_STRUMENTI


def test_entrambi_i_percorsi_dicono_che_esegui_esiste():
    """Il brief guardava la sola guida del ponte. Il percorso sincrono e'
    quello che oggi porta la chat vera, e la guida non la vede mai: senza
    questo test `esegui` potrebbe esistere nel prompt di meta' prodotto.

    Il nome si cerca COI BACKTICK, e non e' un vezzo: `"esegui" in testo`
    passava gia' prima di questo task, perche' entrambi i testi contengono
    «non ho realmente eseguito» e «azioni mai eseguite». Un pin che non puo'
    fallire non sorveglia niente -- verificato rimettendo il testo vecchio."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        assert "`esegui`" in testo, (
            f"il prompt del percorso {percorso} non nomina `esegui`: il "
            "modello riceve lo strumento e non sa di averlo")


def test_nessun_prompt_dichiara_piu_che_hiris_non_tocca_la_casa():
    """Le dichiarazioni che il Task 5 ha reso false, e che il modello legge
    con la stessa autorita' con cui gli diamo gli strumenti."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        for falsita in ("rispondi, non agisci", "non controlli dispositivi",
                        "non agisce", "non accendi", "non spegni"):
            assert falsita not in basso, (
                f"il prompt del percorso {percorso} dice ancora «{falsita}» "
                "mentre `esegui` e' fra gli strumenti serviti: il modello "
                "rifiutera' di agire, e il sintomo e' indistinguibile da "
                "«gli strumenti sono rotti»")


# -- 1bis. Le stesse falsita', ma nella voce che le ricerche non conoscevano -
#
# La ricognizione del Task 7 cercava «non agisce»: la TERZA persona, quella con
# cui il codice e le opzioni parlano DEL prodotto. Il testo di benvenuto della
# chat (`static/index.html`) e' in PRIMA persona, perche' li' e' HIRIS che
# parla all'utente -- «non agisco: non accendo, non spengo». La caccia
# conosceva una voce sola, e quella frase e' rimasta falsa per tre giorni sulla
# schermata iniziale del prodotto: la prima cosa che si legge aprendolo.
#
# Non e' una voce in piu' da aggiungere all'elenco: e' un buco di METODO, e
# questo test lo chiude sorvegliando entrambe le voci su cio' che legge
# l'UTENTE -- che e' l'altra meta' che i test qui sopra non guardano, perche'
# guardano i prompt, cioe' cio' che legge il modello.

_FALSITA_IN_ENTRAMBE_LE_VOCI = (
    # terza persona: il codice che parla del prodotto
    "non agisce", "non accende", "non spegne", "non tocca automazioni",
    "never acts", "doesn't act", "does not act",
    # prima persona: HIRIS che parla all'utente
    "non agisco", "non accendo", "non spengo", "non modifico niente",
    "i don't act", "i never act",
)


def _testi_che_legge_l_utente() -> dict[str, str]:
    """Il benvenuto della chat e le due traduzioni delle opzioni, senza i
    commenti: un commento che RACCONTA una falsita' corretta (ce ne sono due,
    dal Task 7) non e' la falsita'."""
    from pathlib import Path

    radice = Path(__file__).resolve().parent.parent / "hiris"
    sorgenti = [radice / "app" / "static" / "index.html",
                radice / "translations" / "it.yaml",
                radice / "translations" / "en.yaml"]
    testi = {}
    for percorso in sorgenti:
        righe = percorso.read_text(encoding="utf-8").splitlines()
        testi[percorso.name] = "\n".join(
            r for r in righe if not r.lstrip().startswith("#"))
    return testi


def test_cio_che_legge_l_utente_non_nega_piu_l_azione_in_nessuna_delle_due_voci():
    for nome, testo in _testi_che_legge_l_utente().items():
        basso = testo.lower()
        for falsita in _FALSITA_IN_ENTRAMBE_LE_VOCI:
            assert falsita not in basso, (
                f"«{falsita}» e' tornata in {nome}. Dal commit che ha dato "
                "`esegui` al modello, HIRIS accende e spegne: una frase che lo "
                "nega e' falsa, e se sta sulla schermata iniziale e' la prima "
                "cosa che l'utente legge del prodotto")


def test_il_benvenuto_dice_le_tre_cose_vere_dell_azione():
    """Le stesse tre di `claude_runner.BASE_REGOLE_STRUMENTI` e della voce
    `chat_via_subscription`, e con le stesse parole: agisce SU RICHIESTA, non
    COSTRUISCE, non fa niente DA SOLA. Scritte in tre posti, divergono in una
    settimana se nessuno le tiene insieme."""
    benvenuto = _testi_che_legge_l_utente()["index.html"].lower()
    assert "accendo, spengo, imposto" in benvenuto, (
        "il benvenuto non dice piu' cosa HIRIS sa fare, o non lo dice con le "
        "stesse parole degli altri due posti (accendere, spegnere, impostare)")
    assert "non scrivo automazioni" in benvenuto, (
        "il benvenuto non dice piu' il confine: HIRIS agisce ma non COSTRUISCE")
    assert "mai da sola" in benvenuto, (
        "il benvenuto non dice piu' che nessuna azione parte da sola: e' la "
        "cosa che l'utente ha diritto di sapere prima di tutte le altre")


# -- 2. Gli id, non i nomi --------------------------------------------------

def test_la_guida_chiede_gli_id_non_i_nomi():
    basso = _GUIDA_CON_STRUMENTI.lower()
    assert "cerca" in basso and "id" in basso


def test_entrambi_i_percorsi_mandano_a_cerca_chi_ha_solo_un_nome():
    """E' l'errore piu' probabile: il modello ha «la luce della cucina» e
    passa quel nome a `esegui`, che vuole `light.cucina`. La verifica lo
    rifiuta con un motivo giusto, ma il giro e' sprecato e all'utente arriva
    una frase di errore invece di una luce accesa."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "id" in basso and "cerca" in basso, (
            f"il prompt del percorso {percorso} non collega gli id a `cerca`")
        assert "esatt" in basso, (
            f"il prompt del percorso {percorso} non dice che gli id devono "
            "essere ESATTI: «la luce della cucina» sembrera' un id accettabile")


# -- 3. Raccontare cosa e' successo, non cosa e' stato chiesto --------------

def test_entrambi_i_percorsi_chiedono_di_raccontare_cosa_e_successo():
    """La regola del prodotto (`vincoli-globali.md`) scritta come regola di
    RISPOSTA: la porta consegna `cambiato`; se e' vuoto, cio' che si sa e' che
    Home Assistant non ha riportato cambiamenti, e dichiarare un successo
    sarebbe dire cosa e' stato CHIESTO."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "cambiato" in basso, (
            f"il prompt del percorso {percorso} non nomina `cambiato`, il "
            "campo che dice se qualcosa e' successo per davvero")


# -- 3bis. La diagnosi inventata (2.2.1) ------------------------------------
#
# Il secondo difetto misurato sulla prima casa vera, e quello che ha fatto il
# danno peggiore. HIRIS spegne due abat-jour -- si spengono -- e risponde:
# «nulla e' cambiato ... probabile problema di comunicazione col dispositivo.
# Vuoi che riprovi?». La prima meta' della frase e' un difetto di FONTE, chiuso
# in `azione/porta.py`. La seconda e' nata QUI: il prompt diceva al modello,
# con autorita', che «nulla e' cambiato IN CASA» -- un'affermazione sulla casa
# ricavata da un dato che parla solo di cio' che HIRIS ha potuto vedere. A un
# modello a cui si dice che l'utente ha chiesto di spegnere e in casa non e'
# cambiato niente resta una sola conclusione disponibile: il dispositivo. La
# speculazione non era un capriccio, era l'unica uscita che il testo lasciava.
#
# I due test guardano le due meta' della correzione: cosa il prompt AFFERMA
# (solo il fatto misurato) e cosa VIETA (dedurne la causa).

def test_nessuno_dei_due_percorsi_afferma_che_in_casa_non_e_cambiato_niente():
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "nulla è cambiato in casa" not in basso, (
            f"il prompt del percorso {percorso} afferma di nuovo una proprieta' "
            "della CASA a partire da un dato che dice solo cosa Home Assistant "
            "ha riportato: e' l'errore di scala da cui e' nata la diagnosi "
            "inventata sulla casa vera")
        assert "home assistant non ha riportato" in basso, (
            f"il prompt del percorso {percorso} non dice piu' QUAL E' il fatto "
            "che `cambiato` vuoto porta con se': senza soggetto, il modello "
            "torna a leggerlo come «in casa non e' successo niente»")


def test_entrambi_i_percorsi_vietano_di_inventare_una_causa():
    """Non basta togliere l'affermazione falsa: il divieto dev'essere
    esplicito, e deve nominare la frase vera che il prodotto ha prodotto --
    «problema di comunicazione» -- perche' e' quella che ha mandato il
    proprietario a cercare un guasto inesistente."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "problema di comunicazione" in basso and "guasto" in basso, (
            f"il prompt del percorso {percorso} non vieta piu' la diagnosi "
            "inventata: il modello non ha nessun dato sul dispositivo, e "
            "mandare qualcuno a cercare un guasto inesistente e' peggio che "
            "dire «non lo so»")
        assert "tapparella" in basso or "valvola" in basso, (
            f"il prompt del percorso {percorso} vieta la diagnosi senza dare "
            "la ragione banale che la rende inutile: un dispositivo lento che "
            "non ha ancora finito resta un caso vero, e il modello deve avere "
            "quella lettura a disposizione")


# -- 4. L'ambiguita' --------------------------------------------------------

def test_entrambi_i_percorsi_dicono_di_agire_sulla_lettura_piu_naturale():
    """La regola decisa dal proprietario: «accendi il bagno» si risolve
    agendo, non domandando. In questa fetta tutto e' reversibile -- ogni
    azione e' una chiamata a un servizio e si annulla dicendo il contrario --
    quindi sbagliare costa una frase mentre domandare costa su OGNI
    richiesta, per sempre."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "naturale" in basso, (
            f"il prompt del percorso {percorso} non dice su quale lettura "
            "agire quando la richiesta ne ammette piu' d'una")


def test_la_guida_non_promette_una_conferma_che_non_esiste():
    basso = _GUIDA_CON_STRUMENTI.lower()
    for parola in ("chiedi conferma", "chiedere conferma", "previa conferma"):
        assert parola not in basso, (
            f"il prompt promette «{parola}» ma nessun meccanismo di conferma "
            "esiste in questa fetta")


def test_nessuno_dei_due_percorsi_promette_una_conferma_che_non_esiste():
    """Il gemello sui testi COMPOSTI. Nessuna conferma esiste in questa
    fetta: `esegui` chiama e basta. Prometterla sarebbe la classe di difetto
    -- il prompt che descrive un meccanismo assente -- che questo ramo ha
    passato settimane a chiudere."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        for parola in ("chiedi conferma", "chiedere conferma", "previa conferma",
                       "in attesa di conferma"):
            assert parola not in basso, (
                f"il prompt del percorso {percorso} promette «{parola}»: "
                "nessun meccanismo di conferma esiste in questa fetta")


def test_entrambi_i_percorsi_dicono_che_il_ricordo_e_una_preferenza_non_una_sostituzione():
    """La regola sull'ambiguita' regge solo se cio' che si ricorda e' generale.

    Un ricordo-sostituzione («accendi il bagno = queste due luci») congela
    l'ambiguita' invece di risolverla: dopo, l'utente non puo' piu' intendere
    il riscaldamento con la stessa frase, e la regola non vale per nessun'altra
    stanza. Il prompt deve chiedere la forma generale, perche' la sostituzione
    e' quella che al modello viene naturale.

    Il brief chiedeva questo test sulla sola `_GUIDA_CON_STRUMENTI`; guarda
    entrambi i percorsi per la ragione dichiarata in cima al file -- il
    paragrafo dell'ambiguita' vive in `BASE_REGOLE_STRUMENTI`, l'unico testo
    che raggiunge chi puo' agire su ENTRAMBI i rami."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "preferenza generale" in basso, (
            f"il prompt del percorso {percorso} non chiede la forma GENERALE "
            "del ricordo: il modello salvera' la sostituzione, che e' la "
            "forma che gli viene naturale")
        assert "ricorda" in basso, (
            f"il prompt del percorso {percorso} parla di preferenze senza "
            "dire con quale strumento si salvano")


# -- Il ramo di degrado: non puo' agire in QUEL turno, che e' diverso -------

def test_la_guida_senza_strumenti_non_dice_piu_che_hiris_non_agisce():
    """Senza strumenti HIRIS non PUO' agire in quel turno -- ma «non agisce»
    come proprieta' del prodotto non e' piu' vero, e il testo non deve dirlo."""
    basso = _GUIDA_SENZA_STRUMENTI.lower()
    assert "non agisc" not in basso and "non agire" not in basso


def test_la_guida_senza_strumenti_continua_a_dire_cio_che_in_quel_turno_manca():
    """L'altra meta', e senza di lei la correzione qui sopra diventerebbe la
    falsita' SPECULARE: sul ramo di degrado gli strumenti non ci sono davvero,
    e un modello che si credesse capace di agire annuncerebbe accensioni mai
    avvenute -- il «preso nota» senza aver salvato, in un'altra forma."""
    guida = _GUIDA_SENZA_STRUMENTI
    assert "NON hai alcuno strumento" in guida
    basso = guida.lower()
    assert "non puoi accendere" in basso, (
        "la guida del ramo di degrado non dice piu' che in QUESTO turno non "
        "si puo' toccare la casa")


# -- La guardia che LEGA il prompt al contratto della porta -----------------
#
# fetta «comandare» (Task 7). Il Task 6 ha chiuso il suo lavoro dichiarando
# questo buco (§9.3 del suo rapporto): il prompt promette al modello quattro
# CHIAVI -- `prima`, `dopo`, `cambiato`, `avviso` -- e quelle chiavi le
# produce `azione/porta.py`. Le due cose non erano legate da niente. Se domani
# la porta rinominasse `cambiato`, il prompt continuerebbe a nominarlo, il
# modello riceverebbe un dizionario senza quel campo e racconterebbe cio' che
# e' stato CHIESTO invece di cio' che e' successo -- **in silenzio**, con la
# suite verde: nessun test di `test_azione_porta.py` guarda il prompt, e
# nessun test del prompt guarda la porta.
#
# E' esattamente la famiglia di difetti di cui il Task 7 si occupa -- la
# dichiarazione al presente che non e' piu' vera -- ed e' l'unico pezzo di
# essa che si puo' PREVENIRE invece di correggere. Da qui in poi il rename
# della chiave e' un test rosso.
#
# **Il verso conta.** Si asserisce che ogni chiave nominata dal PROMPT esista
# davvero nell'esito della PORTA, non il contrario: la porta puo' legittimamente
# restituire campi che il prompt non nomina (`eseguito`, `servizio`, `entita`),
# e pretendere che il prompt li elenchi tutti sarebbe fissare la prosa invece
# della proprieta'.
#
# Le chiavi si raccolgono ESEGUENDO la porta vera -- non da una lista scritta
# qui, che sarebbe il secondo catalogo di sempre. Due giri, perche' `avviso`
# compare solo su uno di essi: quello in cui la chiamata riesce e non cambia
# niente, cioe' proprio il caso che il prompt esiste per far raccontare.

_CHIAVI_NOMINATE_DAL_PROMPT = ("prima", "dopo", "cambiato", "avviso")


async def _chiavi_prodotte_dalla_porta() -> set:
    """L'unione delle chiavi che `PortaAzione.esegui` restituisce davvero.

    Usa le stesse finte di `tests/test_azione_porta.py` (importate, non
    ricopiate: una seconda copia divergerebbe il giorno in cui la forma vera
    di `EntityCache` cambia) e la porta VERA."""
    from hiris.app.azione.porta import PortaAzione
    from hiris.app.azione.registro import RegistroServizi
    from tests.test_azione_porta import (
        FintoClient, FintaCache, SALOTTO_ACCESO, SALOTTO_SPENTO, SPEGNI_IL_SALOTTO,
    )

    chiavi = set()

    # giro 1: lo stato cambia davvero -> `prima`/`dopo`/`cambiato`, niente avviso
    client = FintoClient()
    registro = RegistroServizi()
    await registro.aggiorna(client)
    porta = PortaAzione(client, registro, FintaCache(SALOTTO_ACCESO, dopo=SALOTTO_SPENTO))
    chiavi |= set(await porta.esegui(SPEGNI_IL_SALOTTO, origine="test"))

    # giro 2: la chiamata riesce e non cambia niente -> compare `avviso`
    client2 = FintoClient()
    registro2 = RegistroServizi()
    await registro2.aggiorna(client2)
    porta2 = PortaAzione(client2, registro2, FintaCache(SALOTTO_SPENTO))
    chiavi |= set(await porta2.esegui(SPEGNI_IL_SALOTTO, origine="test"))

    return chiavi


@pytest.mark.asyncio
async def test_le_chiavi_che_il_prompt_promette_esistono_davvero_nell_esito():
    prodotte = await _chiavi_prodotte_dalla_porta()
    # la finta deve aver esercitato entrambi i rami, o la guardia sorveglierebbe
    # meno di quello che crede
    assert "avviso" in prodotte, (
        "il giro «riuscito ma nulla e' cambiato» non ha prodotto `avviso`: "
        "questa guardia non sta piu' esercitando il ramo che le serve")

    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        for chiave in _CHIAVI_NOMINATE_DAL_PROMPT:
            if f"`{chiave}`" not in testo:
                continue  # il prompt non la promette: niente da garantire
            assert chiave in prodotte, (
                f"il prompt del percorso {percorso} promette al modello il "
                f"campo `{chiave}`, ma `azione/porta.py` non lo produce (ne' "
                f"sul giro che cambia stato ne' su quello che non cambia "
                f"niente). Il modello leggerebbe di un campo che non riceve: "
                f"o il prompt nomina una chiave vecchia, o la porta l'ha "
                f"rinominata senza portarsi dietro il prompt. "
                f"Chiavi prodotte davvero: {sorted(prodotte)}")


def test_il_prompt_promette_almeno_le_chiavi_che_raccontano_l_esito():
    """Il complemento della guardia qui sopra, e senza di lui si svuoterebbe
    da sola: la guardia salta le chiavi che il prompt NON nomina, quindi un
    prompt che smettesse di nominarle tutte la farebbe passare a vuoto.

    Le tre chiavi qui sotto sono quelle senza cui la regola «di' cosa e'
    successo, non cosa e' stato chiesto» non e' eseguibile dal modello."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        for chiave in ("prima", "dopo", "cambiato"):
            assert f"`{chiave}`" in testo, (
                f"il prompt del percorso {percorso} non nomina piu' `{chiave}`: "
                "il modello non ha modo di sapere dove guardare per raccontare "
                "cosa e' successo davvero")


# -- 5. l'azione che non si vede -------------------------------------------
#
# R-5 della review della fetta, meta' meccanismo. Il CHANGELOG e il README
# dicevano «non crea e non modifica automazioni»: letteralmente vero,
# praticamente ambiguo -- un utente ne conclude che le sue automazioni siano
# fuori portata, e non lo sono (`automation.turn_off` su un'entita'
# `automation.*` passa la verifica ed esegue). I tre testi sono stati
# riscritti; ma il testo che l'utente legge non e' un meccanismo, e il prompt
# insegnava al modello la regola opposta -- «cio' che fai si annulla dicendo il
# contrario», usata per giustificare l'azione senza chiedere. Un'automazione
# spenta non si annulla dicendo il contrario: nessuno se ne accorge.

def test_entrambi_i_percorsi_conoscono_l_azione_che_non_si_vede():
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        assert "automation.turn_off" in testo, (
            f"il prompt del percorso {percorso} non nomina piu' l'eccezione a "
            "«si annulla dicendo il contrario»: il modello ha in mano l'unica "
            "azione di questa versione che resta invisibile e persistente, e "
            "la regola accanto gli dice che sbagliare costa una frase")
        assert "eccezione" in testo


def test_l_eccezione_sta_dove_stanno_le_regole_dell_azione():
    """Non nella guida del ponte: il percorso sincrono -- quello che oggi porta
    la chat vera -- le guide di `agent/prompts.py` non le vede mai. E' la
    stessa correzione al piano che il Task 6 aveva gia' dovuto fare per le
    quattro regole dell'azione."""
    from hiris.app.claude_runner import BASE_REGOLE_STRUMENTI
    assert "automation.turn_off" in BASE_REGOLE_STRUMENTI
    assert "automation.turn_off" not in _GUIDA_SENZA_STRUMENTI, (
        "un percorso senza strumenti non deve ricevere una regola su come "
        "usarli: e' la meta' falsa che la fetta «parita'» ha tolto")
