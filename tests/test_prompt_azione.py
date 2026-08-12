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
    RISPOSTA: la porta rilegge lo stato e consegna `cambiato`; se e' vuoto la
    chiamata e' riuscita e nulla e' successo, e dichiarare un successo
    sarebbe dire cosa e' stato CHIESTO."""
    for percorso, testo in _i_due_testi_di_chi_puo_agire().items():
        basso = testo.lower()
        assert "cambiato" in basso, (
            f"il prompt del percorso {percorso} non nomina `cambiato`, il "
            "campo che dice se qualcosa e' successo per davvero")


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
