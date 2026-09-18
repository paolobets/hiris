"""L'istantanea dei giudizi sui tipi (spec 2026-09-16 §3)."""
import pytest

from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.type_judgments import (
    NO_GENRE,
    JudgmentError,
    TypeJudgments,
)
from hiris.app.home_space.type_vocabulary import ABSENT_STATE_FORMS, REPO_JUDGMENTS

GENERI = ("funzionamento", "presenza", "guasto", "sicurezza")
GIUDIZI_VERI = REPO_JUDGMENTS  # il seme del repo, dopo il Task 1


def _j(*rows):
    return TypeJudgments.from_rows(rows, genres=GENERI,
                                   absent_forms=ABSENT_STATE_FORMS.value)


def test_il_genere_si_cerca_dall_entita_alla_coppia_al_dominio():
    """Mutazione: invertire l'ordine della ricerca (dominio prima) -- rossa
    sulla seconda e sulla terza asserzione."""
    j = _j(("tipo", "binary_sensor", "genere", NO_GENRE),
           ("tipo", "binary_sensor.occupancy", "genere", "presenza"),
           ("entita", "binary_sensor.fp2", "genere", "sicurezza"))
    assert j.genre_of("binary_sensor.porta", None) is None
    assert j.genre_of("binary_sensor.fp300", "occupancy") == "presenza"
    assert j.genre_of("binary_sensor.fp2", "occupancy") == "sicurezza"


def test_nessuno_NEGA_il_livello_sopra_e_l_assenza_eredita():
    """`nessuno` e' un giudizio, l'assenza della riga no. Mutazione: trattare
    `nessuno` come assenza -- rossa, torna `funzionamento`."""
    j = _j(("tipo", "switch", "genere", "funzionamento"),
           ("entita", "switch.accesso_internet", "genere", NO_GENRE))
    assert j.genre_of("switch.presa", None) == "funzionamento"
    assert j.genre_of("switch.accesso_internet", None) is None


def test_il_riposo_e_del_SOGGETTO_e_non_contiene_le_forme_assenti():
    """`none` e il vuoto non sono un riposo (spec §5): non escono dalla lettura
    e, scritti dentro un riposo, rendono storta la riga (spec §3, decisione del
    controllore al giro di correzione 1). Le forme sono quelle VERE del
    vocabolario, `ABSENT_STATE_FORMS`, passate come dato.

    Mutazioni: (a) aggiungere `{"", "none"}` al risultato di `resting_of` --
    rossa; (b) togliere da `_parse` il rifiuto delle forme assenti -- rossa,
    le due righe entrano e la costruzione non solleva; (c) in `from_rows`
    rifiutare solo `none` (`absent = frozenset(absent_forms) - {""}`) -- rossa
    su `len(e.rows) == 2`."""
    j = _j(("tipo", "person", "riposo", '["home"]'),
           ("tipo", "binary_sensor", "riposo", '["off"]'))
    assert j.resting_of("person") == frozenset({"home"})
    assert j.resting_of("binary_sensor", "occupancy") == frozenset({"off"})
    assert "none" not in j.resting_of("person")
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "person", "riposo", '["home", "none"]'),
           ("tipo", "switch", "riposo", '["off", ""]'))
    assert len(e.value.rows) == 2


def test_un_valore_storto_ferma_la_costruzione_ELENCANDO_tutte_le_righe():
    """Si vede all'avvio, tutto insieme. Mutazione: sollevare alla prima riga
    storta invece di raccoglierle -- rossa su `len(e.rows) == 2`."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "acceso"),
           ("tipo", "cover", "riposo", "[non json"))
    assert len(e.value.rows) == 2


def test_un_campo_che_non_e_un_giudizio_non_entra():
    """I fatti di HA restano codice (spec §2). Mutazione: accettare qualunque
    campo -- rossa."""
    with pytest.raises(JudgmentError):
        _j(("tipo", "climate", "capability_names", "{}"))


def test_l_impronta_cambia_SOLO_coi_campi_della_cronaca():
    """Correggere un limite non invecchia nessun giorno (spec §6). Mutazione:
    calcolare l'impronta su tutte le righe -- rossa sulla prima (`base` e
    `with_limit` non coincidono piu'). Eseguita il 17/09: la stesura del piano
    diceva «sulla seconda», ed era falso."""
    base = _j(("tipo", "light", "genere", "funzionamento"))
    with_limit = _j(("tipo", "light", "genere", "funzionamento"),
                    ("tipo", "light", "limiti_parametri",
                     '{"brightness": {"min": "min_b", "max": "max_b"}}'))
    with_genre = _j(("tipo", "light", "genere", "sicurezza"))
    assert base.chronicle_fingerprint() == with_limit.chronicle_fingerprint()
    assert base.chronicle_fingerprint() != with_genre.chronicle_fingerprint()
    assert len(base.chronicle_fingerprint()) == 16


def test_l_impronta_non_cambia_per_una_differenza_TIPOGRAFICA():
    """L'impronta si calcola sui valori interpretati, non sul testo: spazi e
    ordine dentro un riposo non invecchiano nessun giorno. Mutazione: calcolare
    l'impronta sul testo grezzo delle righe -- rossa."""
    compact = _j(("tipo", "cover", "riposo", '["closed","stopped"]'))
    spaced = _j(("tipo", "cover", "riposo", '[ "stopped", "closed" ]'))
    assert compact.chronicle_fingerprint() == spaced.chronicle_fingerprint()


def test_l_istantanea_e_IMMUTABILE():
    """Mutazione: togliere il blocco di `__setattr__` -- rossa."""
    j = _j(("tipo", "light", "genere", "funzionamento"))
    with pytest.raises(AttributeError):
        j._by_key = {}


def test_l_istantanea_non_si_CANCELLA():
    """Mutazione: togliere il blocco di `__delattr__` -- rossa."""
    j = _j(("tipo", "light", "genere", "funzionamento"))
    with pytest.raises(AttributeError):
        del j._by_key


def test_i_valori_annidati_sono_CONGELATI_anche_loro():
    """Un limite letto non si puo' correggere a mano: la prossima lettura
    risponde come la prima. Mutazione: congelare solo l'oggetto esterno di
    `_parse` (l'interno resta un `dict`) -- rossa."""
    j = _j(("tipo", "light", "limiti_parametri",
            '{"brightness": {"min": "min_b", "max": "max_b"}}'))
    limits = j.parameter_limits("light", "brightness")
    with pytest.raises(TypeError):
        limits["min"] = "HACKED"
    assert j.parameter_limits("light", "brightness")["min"] == "min_b"


def test_una_riga_MALFORMATA_si_raccoglie_come_le_altre():
    """Una riga che non ha quattro parti di testo e' storta come un valore
    storto: finisce nell'elenco, non scappa come eccezione nuda.

    Mutazioni: (a) spacchettare la riga fuori dal `try` -- rossa, esce un
    `ValueError` nudo; (b) togliere il controllo che le quattro parti siano
    testo -- rossa, la riga con soggetto `None` entra e `len(e.rows) == 2`."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "acceso"),
           ("tipo", "light", "genere"),
           ("tipo", None, "genere", "presenza"))
    assert len(e.value.rows) == 3


def test_la_FORMA_di_lavoro_e_limiti_si_controlla_dentro():
    """Spec §2: `lavoro` e' `{stato: ragione}` di testo; `limiti_parametri` e'
    `{parametro: {"min", "max"} | {"options"}}` di testo. Ogni riga qui sotto
    viola una regola sola.

    Mutazioni: (a) togliere il controllo che le ragioni di `lavoro` siano
    testo -- rossa su `len(e.rows) == 5`; (b) togliere il controllo che un
    limite sia un oggetto -- rossa, la lista `["min", "max"]` supera l'insieme
    di chiavi e `.values()` scappa come `AttributeError` nudo; (c) togliere il
    controllo dell'insieme di chiavi e (d) quello che gli attributi di un
    limite siano testo -- rosse su `len(e.rows) == 5`.

    Riscritta al giro di correzione 1: il testimone di (b) era
    `{"brightness": "x"}`, e la mutazione (b) eseguita restava VERDE perche'
    `frozenset("x")` e' gia' respinto dal controllo delle chiavi."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "switch", "lavoro", '{"on": 5}'),
           ("tipo", "light", "limiti_parametri", '{"brightness": ["min", "max"]}'),
           ("tipo", "fan", "limiti_parametri", '{"percentage": {"min": "a"}}'),
           ("tipo", "climate", "limiti_parametri",
            '{"temperature": {"min": "a", "max": "b", "options": "c"}}'),
           ("tipo", "select", "limiti_parametri", '{"option": {"options": 3}}'))
    assert len(e.value.rows) == 5


def test_una_chiave_DOPPIA_e_storta():
    """Due righe con lo stesso soggetto e campo: nessuna vince in silenzio,
    entrambe finiscono nell'elenco. Mutazione: togliere il controllo delle
    chiavi doppie -- rossa, la costruzione riesce."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "funzionamento"),
           ("tipo", "light", "genere", "sicurezza"))
    assert len(e.value.rows) == 2


def test_notevole_accendibile_limiti_assumibili_lavoro():
    """Mutazione: `is_notable` che non passa `device_class` alla ricerca
    (chiede solo il dominio) -- rossa su `is_notable("binary_sensor", "smoke")`."""
    j = _j(("tipo", "light", "notevole", "si"),
           ("tipo", "light", "accendibile", "si"),
           ("tipo", "binary_sensor", "notevole", "no"),
           ("tipo", "binary_sensor.smoke", "notevole", "si"),
           ("tipo", "light", "limiti_parametri",
            ('{"color_temp_kelvin": {"min": "min_color_temp_kelvin",'
             ' "max": "max_color_temp_kelvin"},'
             ' "effect": {"options": "effect_list"}}')),
           ("tipo", "alarm_control_panel", "lavoro",
            '{"triggered": "e\' il fatto piu\' notevole"}'))
    assert j.is_notable("light")
    assert not j.is_notable("binary_sensor") and j.is_notable("binary_sensor", "smoke")
    assert j.operable_domains() == frozenset({"light"})
    assert j.parameter_limits("light", "color_temp_kelvin")["min"] == "min_color_temp_kelvin"
    assert j.parameter_limits("light", "effect")["options"] == "effect_list"
    assert j.parameter_limits("light", "brightness") is None
    assert set(j.working_of("alarm_control_panel")) == {"triggered"}


def test_il_giudizio_da_sapere_subito_si_legge_su_coppia_e_dominio():
    """Spec `2026-09-18-da-sapere-subito.md` §2. La domanda e' «quando una cosa
    di questo tipo esce dal suo riposo, il proprietario deve saperlo subito?» --
    non «vale la pena raccontarlo» (`notevole`), non «che genere di fatto e'»
    (`genere`).

    Sale coppia -> dominio come `is_notable`, e per la stessa ragione:
    `binary_sensor` puo' dire «no» in generale e «si'» sulle classi che lo
    meritano.

    Mutazione ESEGUITA: leggere il campo solo sul dominio (tolto `device_class`
    da `_lookup`) -- rossa qui, sull'asserzione
    `da_sapere_subito("binary_sensor", "smoke")` (`assert False is True`);
    ripristinata con l'editor, `git diff` pulito.

    **Citata per nome, non per numero di riga** (backlog, «Le citazioni per
    numero di riga marciscono»).
    """
    giudizi = TypeJudgments.from_rows(
        [("tipo", "binary_sensor.smoke", "da_sapere_subito", "si"),
         ("tipo", "binary_sensor", "da_sapere_subito", "no"),
         ("tipo", "alarm_control_panel", "da_sapere_subito", "si")],
        genres=GENERI, absent_forms=ABSENT_STATE_FORMS.value)
    assert giudizi.da_sapere_subito("binary_sensor", "smoke") is True
    assert giudizi.da_sapere_subito("binary_sensor", "motion") is False
    assert giudizi.da_sapere_subito("alarm_control_panel") is True
    # Un tipo senza riga vale «no»: l'assenza e' una risposta, non un buco.
    assert giudizi.da_sapere_subito("light") is False


def test_da_sapere_subito_RIFIUTA_cio_che_non_e_NESSUNA_delle_tre_forme():
    """Un valore che non e' `si`, non e' `no` e non e' un elenco di stati non si
    scrive, **e la ragione elenca le tre forme** a chi ha premuto salva: un
    messaggio che dice solo «sbagliato» costringe a indovinare.

    **Riscritta alla ri-revisione finale** (punto 4). Si chiamava «vuole si o no
    come gli altri giudizi binari» e diceva «stessa forma di `notevole` e
    `accendibile` (`_YES_NO`)»: dal 18/09/2026 le forme sono **tre** e il campo
    ha un ramo suo (`_parse_da_sapere_subito`), non piu' quello dei binari. La
    mutazione descritta -- «tolto il campo dal ramo `(NOTABLE_FIELD,
    OPERABLE_FIELD)`» -- **non era piu' eseguibile**: il campo da quel ramo e'
    gia' uscito. Nome e testo dicevano una cosa che il codice non faceva piu'.

    Mutazione ESEGUITA, quella vera: in `_parse_da_sapere_subito`, tornare
    `frozenset()` invece di sollevare quando `json.loads` fallisce -- rossa qui
    (nessun `JudgmentError`: `forse` entra come insieme vuoto, cioe' come un
    `no` silenzioso che chi ha scritto la riga non si aspetta). Ripristinata con
    l'editor.
    """
    with pytest.raises(JudgmentError) as errore:
        TypeJudgments.from_rows([("tipo", "lock", "da_sapere_subito", "forse")],
                                genres=GENERI, absent_forms=ABSENT_STATE_FORMS.value)
    detto = str(errore.value)
    assert "si/no" in detto and "elenco" in detto, detto


def test_il_campo_nuovo_NON_sposta_l_impronta_della_cronaca():
    """**Spec §6, ed e' il cardine di questa fetta**: `da_sapere_subito` non
    entra nella cronaca, quindi non fa rifare nessun giorno. L'impronta si
    costruisce sui soli `CHRONICLE_FIELDS = (genere, riposo)`.

    Mutazione ESEGUITA: aggiunto `DA_SAPERE_SUBITO_FIELD` a
    `CHRONICLE_FIELDS` -- rossa qui, sull'`assert con.chronicle_fingerprint()
    == senza.chronicle_fingerprint()`
    (`assert '4b1fc94deb908444' == '29b3605d8896a2dc'`), e l'impronta del seme
    vero si e' mossa da `9692e12830c90fd0` a `7679f7413c5073c9`. **E' la
    mutazione che vale di piu' di questa fetta**: se passasse inosservata, il
    rilascio rifarebbe 22 giorni di cronaca per un campo che con la cronaca
    non c'entra. Ripristinata con l'editor; impronta tornata a
    `9692e12830c90fd0`, verificato con `git diff`.
    """
    base = [("tipo", "light", "genere", "funzionamento"),
            ("tipo", "light", "riposo", '["off"]')]
    senza = TypeJudgments.from_rows(base, genres=GENERI, absent_forms=ABSENT_STATE_FORMS.value)
    con = TypeJudgments.from_rows(
        base + [("tipo", "alarm_control_panel", "da_sapere_subito", "si")],
        genres=GENERI, absent_forms=ABSENT_STATE_FORMS.value)
    assert con.chronicle_fingerprint() == senza.chronicle_fingerprint()


def test_un_allarme_SCATTATO_va_saputo_subito():
    """`alarm_control_panel` ha `da_sapere_subito: si` (Task 1) e `lavoro:
    {"triggered": ...}`: lo stato di lavoro e' il fatto.

    Mutazione da ESEGUIRE: ignorare `working_of` e guardare solo il campo --
    resta verde qui e rossa nella prova dopo, che e' il punto.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("alarm_control_panel", None, "triggered") is True


def test_un_allarme_DISINSERITO_non_va_saputo_subito():
    """**Il difetto gia' trovato, scritto come prova** (spec §3): con la regola
    «esce dal riposo» l'allarme `disarmed` entrava in banda TUTTI E OTTO i
    giorni misurati -- «disinserito» non e' fra i riposi (che sono i cinque
    stati armati) e non e' un lavoro. L'allarme disinserito e' la normalita'
    della casa, e sarebbe stata la prima riga della pagina ogni mattina.

    Mutazione da ESEGUIRE: tornare alla regola «non e' un riposo» per i tipi che
    HANNO un giudizio `lavoro` -- rossa.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("alarm_control_panel", None, "disarmed") is False
    # E i cinque stati armati nemmeno, che sono il riposo dichiarato.
    assert GIUDIZI_VERI.stato_da_sapere_subito("alarm_control_panel", None, "armed_away") is False


def test_un_rilevatore_di_fumo_acceso_va_saputo_subito():
    """`binary_sensor.smoke` ha `da_sapere_subito: si` e NON ha nessun giudizio
    `lavoro`: vale lo stato che non e' riposo (`off`) e non e' una forma
    dell'assenza. `on` lo e'.

    Mutazione da ESEGUIRE: pretendere sempre un giudizio `lavoro` -- rossa (il
    fumo non arriverebbe mai in banda, ed e' il caso per cui questa fetta
    esiste).
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "on") is True
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "off") is False


def test_le_forme_dell_assenza_non_sono_una_notizia():
    """`none` e il vuoto sono un dato che manca, non uno stato della casa (spec
    2026-09-16 §5). Senza questa meta' della condizione, un'entita' che perde lo
    stato finirebbe in prima pagina.

    Mutazione da ESEGUIRE: togliere il controllo sulle forme dell'assenza --
    rossa.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "none") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "") is False


def test_una_luce_accesa_NON_va_saputa_subito():
    """`light` e' `notevole: si` e non e' `da_sapere_subito`: e' la separazione
    per cui questa fetta esiste, provata sul seme vero."""
    assert GIUDIZI_VERI.stato_da_sapere_subito("light", None, "on") is False


def test_una_persona_fuori_casa_NON_va_saputa_subito():
    """`person` non e' `da_sapere_subito`: le tre assenze del 17/09 non sono
    notizie."""
    assert GIUDIZI_VERI.stato_da_sapere_subito("person", None, "not_home") is False


def test_la_regola_CAMBIA_col_giudizio_ed_e_questo_il_punto():
    """Il criterio e' un DATO: correggendo il giudizio, la risposta cambia --
    senza rilascio, e dalla lettura successiva. E' la proprieta' su cui si regge
    la pagina dell'osservatore.

    Mutazione da ESEGUIRE: scrivere l'elenco dei tipi a mano nel metodo --
    rossa.
    """
    corretti = TypeJudgments.from_rows(
        list(GIUDIZI_VERI.rows()) + [("tipo", "person", "da_sapere_subito", "si")],
        genres=tv.CHRONICLE_GENRES, absent_forms=tv.ABSENT_STATE_FORMS.value)
    assert corretti.stato_da_sapere_subito("person", None, "not_home") is True


def test_stato_da_sapere_subito_LEGGE_riposo_e_lavoro_SULLA_COPPIA_non_solo_sul_dominio():
    """Revisione (Fable 5.1), IMPORTANT 3: `working_of`/`resting_of` salgono
    coppia -> dominio, e `stato_da_sapere_subito` deve rispettarlo -- non solo
    interrogare il dominio. Righe costruite APPOSTA perche' la coppia e il
    dominio divergano: nel seme vero nessuna coppia `binary_sensor.*` ha un
    riposo o un lavoro diverso dal suo dominio, quindi le 24 prove sul seme
    resterebbero verdi anche se il metodo leggesse solo il dominio.

    Mutazione da ESEGUIRE: togliere `device_class` dalle due chiamate a
    `working_of`/`resting_of` dentro `stato_da_sapere_subito` -- rossa qui,
    verde sul resto del file.
    """
    j = TypeJudgments.from_rows(
        [("tipo", "binary_sensor", "da_sapere_subito", "si"),
         ("tipo", "binary_sensor", "riposo", '["off"]'),
         ("tipo", "binary_sensor.motion", "riposo", '["on"]'),
         ("tipo", "sensor", "da_sapere_subito", "si"),
         ("tipo", "sensor", "lavoro", '{"low": "poco"}'),
         ("tipo", "sensor.custom", "lavoro", '{"high": "molto"}')],
        genres=GENERI, absent_forms=ABSENT_STATE_FORMS.value)
    # riposo: la coppia `motion` ne ha uno diverso dal dominio, e vince.
    assert j.stato_da_sapere_subito("binary_sensor", "motion", "on") is False
    assert j.stato_da_sapere_subito("binary_sensor", "motion", "off") is True
    assert j.stato_da_sapere_subito("binary_sensor", None, "off") is False
    # lavoro: idem, la coppia `custom` ha il suo, diverso dal dominio.
    assert j.stato_da_sapere_subito("sensor", "custom", "high") is True
    assert j.stato_da_sapere_subito("sensor", "custom", "low") is False
    assert j.stato_da_sapere_subito("sensor", None, "low") is True


def test_stato_da_sapere_subito_su_STATO_NONE_e_come_il_vuoto():
    """Il metodo e' pubblico e riceve `state` da chi chiama: `None` si tratta
    come il vuoto, che e' una forma dell'assenza (`ABSENT_STATE_FORMS`). Nella
    cronaca non arriva mai (Passo 6 normalizza con `str(v.get("cosa") or "")`
    prima di chiamare), ma il metodo non lo presuppone.

    **Scelta dichiarata (revisione giro 1, MINOR 4)**: il codice NON ha un
    `or ""` in piu' -- `str(None).strip().lower()` e' gia' `"none"`, una forma
    dell'assenza, grazie alla normalizzazione della prova sorella qui sotto.
    Non esiste quindi una mutazione tutta sua da eseguire per questa prova:
    quella che la manderebbe rossa (togliere `.lower()`) e' la STESSA di
    `test_stato_da_sapere_subito_si_NORMALIZZA_come_facts_py`, eseguita li'.
    Questa prova resta a documentare il caso -- `None` e' un valore lecito da
    chiamante, non solo una forma di testo -- non a sorvegliare un ramo suo.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", None) is False


def test_stato_da_sapere_subito_si_NORMALIZZA_come_facts_py():
    """Stessa normalizzazione di `mind/facts.py:594` (`.strip().lower()`,
    sull'insieme `ignored` costruito alla riga 592), perche' due letture della
    stessa lista di stati non devono poter divergere su `"None"` contro
    `"none"`, o su spazi intorno a uno stato. Oggi irraggiungibile dalla
    cronaca (le voci arrivano gia' pulite), ma e' esattamente lo scostamento
    che questa fetta esiste per evitare.

    Mutazione ESEGUITA: tolto `.strip().lower()` da `stato_da_sapere_subito`
    (lasciato `str(state)`) -- rossa su questo file, prima asserzione:
    `AssertionError: assert True is False` (`"None"`, non normalizzato, non e'
    fra le forme dell'assenza e cade nel ripiego «non e' un riposo», che per
    `binary_sensor.smoke` senza lavoro vale True). Ripristinata con l'editor,
    verificato con `git diff`.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "None") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", " none ") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", " ON ") is True


def test_un_SI_ORFANO_senza_riposo_ne_lavoro_NON_rende_notizia_ogni_stato():
    """**Revisione finale, I-1 -- il difetto piu' grave della fetta.** La porta
    rifiuta `da_sapere_subito: si` su un tipo senza riposo ne' lavoro
    (`judgments._check`), ma quel rifiuto **non protegge l'invariante**: basta
    scrivere il riposo, poi il `si`, poi togliere il riposo (ritorno al seme) e
    resta un `si` orfano. Il revisore lo ha costruito cosi' su archivio vero.

    Col ripiego «non e' un riposo» su un riposo VUOTO ogni stato non assente --
    `off` compreso, cioe' lo **spegnimento** -- sarebbe una notizia, e la banda
    della pagina si riempirebbe di spegnimenti.

    **La cura e' alla fonte**: un tipo senza lavoro E senza riposo e'
    indecidibile, e **indecidibile vale no** (ruling del controller, 18/09/2026:
    meglio una notizia in meno che una banda piena di spegnimenti). Il rifiuto
    alla porta resta, come cortesia che spiega il problema a chi scrive.

    Le righe qui sotto sono lo STATO FINALE dell'archivio dopo quella sequenza:
    il `si` c'e', il riposo non c'e' piu'.
    """
    j = _j(("tipo", "switch", "da_sapere_subito", "si"))
    assert j.da_sapere_subito("switch") is True  # il campo c'e' davvero
    assert j.stato_da_sapere_subito("switch", None, "off") is False
    assert j.stato_da_sapere_subito("switch", None, "on") is False


def test_un_riposo_VUOTO_vale_come_nessun_riposo_e_non_rende_notizia():
    """La seconda strada per lo stesso `si` orfano (revisione finale, I-1):
    `_parse` accetta `riposo: '[]'` -- e' una lista di stati, vuota -- e
    `resting_of` torna un insieme vuoto, indistinguibile dall'assenza della
    riga. Anche qui il tipo e' indecidibile e vale `no`.
    """
    j = _j(("tipo", "switch", "da_sapere_subito", "si"),
           ("tipo", "switch", "riposo", "[]"))
    assert j.resting_of("switch") == frozenset()
    assert j.stato_da_sapere_subito("switch", None, "off") is False
    assert j.stato_da_sapere_subito("switch", None, "on") is False


def test_stato_da_sapere_subito_LEGGE_il_riposo_DELL_ENTITA_prima_di_quello_del_tipo():
    """**Revisione finale, I-2.** `judgments._LEVELS` ammette `riposo` su
    `entita` e la cronaca lo onora (`mind/facts._is_on` passa l'`entity_id` a
    `resting_of`): una correzione per entita' che la cronaca legge, la regola
    della banda la ignorava -- la cronaca diceva «riposo», la regola diceva
    «notizia» sullo stesso fatto. L'entita' si consulta **prima** del tipo,
    esattamente come fa `resting_of`.

    `lavoro` e `da_sapere_subito` restano coppia -> dominio: `_LEVELS` non li
    ammette su un'entita', e chiederli li' sarebbe una domanda che nessuno puo'
    aver scritto.

    Rossa PRIMA della correzione, con la firma vecchia: `TypeError:
    TypeJudgments.stato_da_sapere_subito() takes 4 positional arguments but 5
    were given` (questo file, prima asserzione).

    Mutazione ESEGUITA dopo la correzione: tolto `entity_id` dalla chiamata a
    `resting_of` dentro `stato_da_sapere_subito` -- rossa sulla prima
    asserzione (`assert True is False`); ripristinata con l'editor.
    """
    j = _j(("tipo", "binary_sensor.smoke", "da_sapere_subito", "si"),
           ("tipo", "binary_sensor.smoke", "riposo", '["off"]'),
           ("entita", "binary_sensor.fumo_cucina", "riposo", '["on"]'))
    # Il rilevatore di cucina ha il suo riposo, corretto dal proprietario.
    assert j.stato_da_sapere_subito(
        "binary_sensor", "smoke", "on", "binary_sensor.fumo_cucina") is False
    assert j.stato_da_sapere_subito(
        "binary_sensor", "smoke", "off", "binary_sensor.fumo_cucina") is True
    # Ogni altra entita' dello stesso tipo resta al riposo del tipo.
    assert j.stato_da_sapere_subito(
        "binary_sensor", "smoke", "on", "binary_sensor.fumo_salotto") is True
    # E senza entita' la risposta e' quella del tipo, come prima.
    assert j.stato_da_sapere_subito("binary_sensor", "smoke", "on") is True


# ---------------------------------------------------------------------------
# `da_sapere_subito` porta ANCHE un elenco di stati (decisione del proprietario,
# 18/09/2026, dopo la revisione finale). Misurato: delle sedici righe del seme
# quindici sono giuste col solo `si` -- l'allarme ha un `lavoro` di UN solo
# stato, i tredici `binary_sensor` e la sirena non hanno `lavoro` e usano il
# riposo -- ma la SERRATURA no: per lei `lavoro` significa «sta operando»
# (`locking`, `opening`, `unlocking`, `unlocked`, `open`) e `jammed` non e' ne'
# lavoro ne' riposo. Col solo `si`, ogni sblocco sarebbe prima riga e
# l'inceppamento no: l'esatto contrario di cio' che serve.
# ---------------------------------------------------------------------------


def test_da_sapere_subito_ACCETTA_un_elenco_di_stati():
    """La terza forma del valore (spec §2): `si`, `no`, oppure **l'elenco degli
    stati che contano**. L'elenco si legge come un insieme, come il riposo.

    Rossa PRIMA della correzione: `JudgmentError: ... atteso si/no, trovato
    '["jammed"]'` (tutte e cinque le prove nuove di questo blocco).
    """
    j = _j(("tipo", "lock", "da_sapere_subito", '["jammed"]'))
    assert j.da_sapere_subito("lock") == frozenset({"jammed"})


def test_un_elenco_VUOTO_di_stati_da_sapere_subito_si_RIFIUTA():
    """Un elenco vuoto dice «nessuno stato conta», che e' `no` scritto in un
    secondo modo -- e due modi di dire la stessa cosa sono la fondamenta che
    questo progetto vieta. Peggio: `da_sapere_subito()` tornerebbe un insieme
    vuoto, cioe' falso, e chi l'ha scritto vedrebbe la riga accettata e la casa
    non cambiare.

    Mutazione ESEGUITA: tolto il controllo sul vuoto da
    `_parse_da_sapere_subito` -- rossa qui (nessun `JudgmentError`: `[]` entra
    e `da_sapere_subito()` torna un insieme vuoto, cioe' falso). Ripristinata
    con l'editor.
    """
    with pytest.raises(JudgmentError) as errore:
        _j(("tipo", "lock", "da_sapere_subito", "[]"))
    assert "vuoto" in str(errore.value)


def test_le_forme_dell_assenza_non_sono_uno_stato_DA_SAPERE_SUBITO():
    """Stessa regola del riposo (`_parse`, `RESTING_FIELD`): `none` e il vuoto
    sono un dato che manca, non uno stato della casa. Dentro l'elenco sarebbero
    una voce MORTA -- la regola tratta le forme dell'assenza come «non e' una
    notizia» prima di ogni altra cosa -- e una riga accettata che non cambia
    niente e' peggio di una rifiutata.
    """
    with pytest.raises(JudgmentError) as errore:
        _j(("tipo", "lock", "da_sapere_subito", '["jammed", "none"]'))
    assert "assenza" in str(errore.value)


def test_un_elenco_STORTO_di_stati_si_rifiuta_come_gli_altri_valori():
    """Un oggetto, un numero, una lista di numeri: il messaggio dice le tre
    forme ammesse, perche' chi ha scritto la riga deve sapere cosa scrivere."""
    with pytest.raises(JudgmentError) as errore:
        _j(("tipo", "lock", "da_sapere_subito", '{"jammed": "si"}'))
    assert "si/no" in str(errore.value)
    with pytest.raises(JudgmentError):
        _j(("tipo", "lock", "da_sapere_subito", "[3]"))
    with pytest.raises(JudgmentError):
        _j(("tipo", "lock", "da_sapere_subito", "forse"))


def test_una_SERRATURA_INCEPPATA_va_saputa_subito_e_una_SBLOCCATA_no():
    """**Il caso che ha fatto nascere la terza forma** (decisione del
    proprietario, 18/09/2026). `jammed` non e' ne' un riposo (`locked`) ne' un
    lavoro (`locking`/`opening`/`unlocking`/`unlocked`/`open`): col solo `si`
    la regola del §3 avrebbe usato il ramo del lavoro e avrebbe fatto entrare
    **ogni sblocco** lasciando fuori **l'inceppamento**.

    Con l'elenco, entra solo cio' che l'elenco nomina: niente lavoro, niente
    riposo, nessun ripiego.

    Mutazione ESEGUITA: spostato il ramo dell'elenco DOPO quello del lavoro
    dentro `stato_da_sapere_subito` -- rossa qui, prima asserzione
    (`assert False is True`: `jammed` non e' un lavoro e non entra piu', mentre
    `unlocked` lo e' e torna in banda). Ripristinata con l'editor.
    """
    assert GIUDIZI_VERI.stato_da_sapere_subito("lock", None, "jammed") is True
    assert GIUDIZI_VERI.stato_da_sapere_subito("lock", None, "unlocked") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("lock", None, "open") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("lock", None, "locked") is False
    # E lo stato normalizzato come sempre: spazi e maiuscole non cambiano nulla.
    assert GIUDIZI_VERI.stato_da_sapere_subito("lock", None, " JAMMED ") is True


def test_le_QUINDICI_righe_SI_si_comportano_esattamente_come_prima():
    """L'elenco e' una forma IN PIU', non una sostituzione: dove il valore e'
    `si` vale la regola del §3 com'e', «indecidibile vale no» compreso."""
    assert GIUDIZI_VERI.stato_da_sapere_subito("alarm_control_panel", None, "triggered") is True
    assert GIUDIZI_VERI.stato_da_sapere_subito("alarm_control_panel", None, "disarmed") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "on") is True
    assert GIUDIZI_VERI.stato_da_sapere_subito("binary_sensor", "smoke", "off") is False
    assert GIUDIZI_VERI.stato_da_sapere_subito("siren", None, "on") is True
    assert GIUDIZI_VERI.stato_da_sapere_subito("siren", None, "off") is False


def test_un_elenco_di_stati_NON_ha_bisogno_di_riposo_ne_di_lavoro():
    """«Indecidibile vale no» (I-1) vale per `si`, non per l'elenco: l'elenco
    **dice gia'** quali stati contano, e non c'e' niente da decidere. Un tipo
    senza riposo ne' lavoro, con l'elenco, funziona.

    Mutazione ESEGUITA: il ramo dell'elenco spostato dopo il lavoro e il
    riposo (la stessa mutazione della prova sulla serratura) -- rossa sulla
    prima asserzione, perche' `switch` qui non ha ne' riposo ne' lavoro e
    `overheated` cade nel ramo «indecidibile vale no». Ripristinata con
    l'editor.
    """
    j = _j(("tipo", "switch", "da_sapere_subito", '["overheated"]'))
    assert j.stato_da_sapere_subito("switch", None, "overheated") is True
    assert j.stato_da_sapere_subito("switch", None, "on") is False
    assert j.stato_da_sapere_subito("switch", None, "off") is False
