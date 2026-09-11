"""Il vocabolario dei tipi: una casa sola, e la provenienza per campo.

Ogni prova qui sotto dichiara la mutazione che la uccide. Dove sarebbe una
tautologia -- «il vocabolario contiene cio' che il vocabolario contiene» -- non e'
scritta: le prove che contano sono quelle che difendono una PROPRIETA' (un
tipo ha una casa sola, un campo non esiste senza provenienza, una coppia si
collega invece di copiare), non quelle che ricopiano il contenuto e si
autoconfermano.

Le prove di comportamento dei tre lettori restano dove erano
(`test_home_space_gamba.py`, `test_mind_facts.py`, `test_decoded_capabilities.py`,
`test_feature_tables_pinned_to_source.py`): la fetta non cambia cosa fanno, e
spostarle qui avrebbe dato l'impressione che sia nato un comportamento nuovo.
"""
import ast
from pathlib import Path

import pytest

from hiris.app.home_space import topology, type_vocabulary
from hiris.app.home_space.type_vocabulary import (
    ABSENT_STATE_FORMS,
    ASPECT,
    ASPECTS,
    CAPABILITY_NAMES,
    FIELD_KINDS,
    OPERABLE,
    PROVENANCES,
    RESTING_STATES,
    UNKNOWN_STATES,
    Asked,
    Field,
    Imported,
    Ours,
    Provenance,
    TypeRow,
    TypeVocabulary,
    _vocabulary,
    aspect_of,
    capability_names,
    capability_tables,
    declared_working_states,
    is_operable,
    operable_domains,
    resting_states,
    resting_states_of,
    unknown_states,
    working_states_of,
)
from hiris.app.mind import facts
from hiris.app.proxy import entity_cache

# --- la provenienza: un campo senza non deve poter esistere ---------------

def test_le_provenienze_sono_tre_e_non_di_piu():
    """La spec ne dichiara tre (`chiesto`, `importato`, `nostro`) e dice «e non
    di piu'». Una quarta nata di nascosto e' il modo in cui «da dove viene
    questo dato» tornerebbe a essere un'opinione.

    Mutazione: aggiungere un quarto membro a `Provenance` -- la prima
    asserzione arrossisce."""
    assert len(Provenance) == 3
    assert {p.value for p in Provenance} == {"chiesto", "importato", "nostro"}
    assert PROVENANCES == frozenset(Provenance)


def test_le_classi_di_campo_sono_tre_e_coprono_le_tre_provenienze():
    """Una provenienza senza una classe che la porti sarebbe inarrivabile; una
    classe in piu' sarebbe una quarta provenienza travestita.

    Mutazione: definire una `class Guessed(Field)` accanto alle tre -- il
    confronto con `Field.__subclasses__()` arrossisce."""
    assert set(Field.__subclasses__()) == set(FIELD_KINDS)
    assert len(FIELD_KINDS) == 3
    portate = {kind.__new__(kind).provenance for kind in FIELD_KINDS}
    assert portate == PROVENANCES


def test_un_campo_senza_provenienza_non_si_costruisce():
    """**La parte che conta: lo impedisce la struttura, non un controllo a
    valle.** La provenienza non e' un parametro che si possa dimenticare o
    mettere a `None` -- e' la classe, e la classe base e' astratta.

    Mutazione: dare a `Field.provenance` un corpo qualunque invece di
    `@abstractmethod` -- `Field("x")` smetterebbe di sollevare e questa prova
    arrossisce."""
    with pytest.raises(TypeError):
        Field("un valore senza provenienza")


def test_una_riga_rifiuta_un_valore_nudo():
    """Un campo senza provenienza non deve poter ENTRARE in una riga, non solo
    non doversi poter costruire da solo: senza questa meta', bastava passare la
    stringa e la provenienza spariva.

    Mutazione: togliere il ciclo di controllo da `TypeRow.__init__` -- la
    costruzione riesce e questa prova arrossisce."""
    with pytest.raises(TypeError) as errore:
        TypeRow("sensor", None, {ASPECT: "comfort"})
    assert "provenienza" in str(errore.value)
    # E la stessa guardia vale dalla porta che si usa davvero.
    with pytest.raises(TypeError):
        TypeVocabulary().add("sensor", aspect="comfort")


def test_un_importato_senza_la_sua_versione_non_si_costruisce():
    """Un fatto importato senza la versione da cui viene non si sa vecchio, e
    un fatto che non si sa vecchio si crede per sempre. E' misurato: lo stesso
    bit (64) e' stato rimosso in due domini fra `2024.7.0` e `2026.9.1`.

    Mutazione: dare un valore predefinito a `ha_version` in
    `Imported.__init__` -- il primo `pytest.raises` arrossisce."""
    with pytest.raises(TypeError):
        Imported({1: "x"})  # senza `ha_version` ne' `source`
    with pytest.raises(ValueError):
        Imported({1: "x"}, ha_version="", source="una fonte")
    with pytest.raises(ValueError):
        Imported({1: "x"}, ha_version="2026.9.1", source="")


def test_ogni_campo_di_ogni_riga_dichiara_la_propria_provenienza():
    """Non e' una tautologia -- `TypeRow` impedisce il valore nudo, non un
    campo il cui `provenance` risponda qualcosa di inatteso: questa prova
    chiude il secondo verso, ed e' cio' che una quarta classe di campo
    introdotta domani farebbe arrossire.

    Mutazione: far ritornare a `Ours.provenance` un `None` -- arrossisce."""
    assert _vocabulary.rows()
    domini_agganciati = {domain for domain, _ in _vocabulary.pairs()}
    for row in _vocabulary.rows():
        # Una riga senza campi e' legittima SOLO se e' l'ancora delle sue
        # coppie: `sensor` non porta nessun giudizio di dominio -- tutti i suoi
        # vivono sulla classe -- ma la riga deve esistere o le coppie non
        # avrebbero da cosa pendere. Una riga vuota e senza coppie sarebbe peso
        # morto, e questa asserzione la trova.
        assert row.fields or row.domain in domini_agganciati, (
            f"la riga {row.key} non dichiara nessun campo e non regge nessuna "
            "coppia")
        for name, field in row.fields.items():
            assert isinstance(field, Field), f"{row.key}.{name}"
            assert field.provenance in PROVENANCES, f"{row.key}.{name}"


def test_i_giudizi_sono_nostri_e_le_capacita_sono_importate():
    """La provenienza non e' un'etichetta decorativa: dice il vero su ogni
    campo. La gamba, l'accendibile e il riposo sono giudizi che nessuna API di
    Home Assistant puo' darci; i nomi dei bit di `supported_features` sono
    `IntFlag` nel sorgente, quindi importati e datati.

    Mutazione: dichiarare le tabelle dei bit con `Ours(...)` invece di
    `Imported(...)` -- il secondo ciclo arrossisce."""
    for row in _vocabulary.rows():
        for name in (ASPECT, OPERABLE, RESTING_STATES):
            field = row.fields.get(name)
            if field is not None:
                assert field.provenance is Provenance.OURS, f"{row.key}.{name}"
        field = row.fields.get(CAPABILITY_NAMES)
        if field is not None:
            assert field.provenance is Provenance.IMPORTED, row.key
            assert field.ha_version == "2026.9.1"
            assert "home-assistant/core" in field.source


def test_nessun_campo_e_chiesto_finche_nessuno_chiede():
    """La forma regge tutte e tre le provenienze, ma `chiesto` vuol dire
    «letto da questa casa adesso», e questa fetta non legge niente. Un campo
    `Asked` dichiarato con un valore scritto a mano sarebbe la bugia peggiore
    del vocabolario: un giudizio nostro travestito da dato del fornitore.

    Mutazione: dichiarare un campo `Asked(...)` su una riga qualunque --
    arrossisce, e chi lo fa deve prima averlo davvero chiesto."""
    asked = [(row.key, name) for row in _vocabulary.rows()
             for name, field in row.fields.items()
             if isinstance(field, Asked)]
    assert asked == [], (
        "un campo `chiesto` che nessuno ha chiesto e' un giudizio nostro "
        "travestito da dato di Home Assistant")


# --- una coppia si collega al suo dominio, non lo copia -------------------

def test_una_coppia_eredita_dal_dominio_invece_di_copiarlo():
    """`("binary_sensor", "smoke")` porta la sua gamba e NIENTE di piu': il suo
    riposo e' quello del dominio, letto attraverso il collegamento.

    Mutazione: in `TypeVocabulary.field`, togliere il ripiego sulla riga di
    dominio (ritornare `None` invece di guardare `(domain, None)`) -- la prima
    asserzione arrossisce."""
    coppia = _vocabulary.row("binary_sensor", "smoke")
    assert RESTING_STATES not in coppia.fields, (
        "la coppia dichiara un riposo suo: e' una copia, non un collegamento")
    assert resting_states_of("binary_sensor", "smoke") == \
        resting_states_of("binary_sensor")
    assert "off" in resting_states_of("binary_sensor", "smoke")


def test_nessuna_coppia_ripete_un_valore_che_il_suo_dominio_gia_dice():
    """Il confine fra RIDICHIARARE e SOVRASCRIVERE: una coppia puo' dire una
    cosa diversa dal suo dominio -- e' un giudizio piu' fine -- ma ripeterne
    identico il valore e' un doppione, e il doppione e' la seconda casa da cui
    prima o poi uno dei due mente.

    Mutazione: aggiungere `resting_states=Ours({"off"})` alla riga di
    `("binary_sensor", "smoke")`, che il dominio gia' dichiara identica --
    arrossisce."""
    doppioni = []
    for domain, device_class in sorted(_vocabulary.pairs()):
        coppia = _vocabulary.row(domain, device_class)
        dominio = _vocabulary.row(domain)
        for name, field in coppia.fields.items():
            gemello = dominio.fields.get(name)
            if gemello is not None and gemello.value == field.value:
                doppioni.append(f"({domain}, {device_class}).{name}")
    assert doppioni == [], (
        "queste coppie ricopiano un valore del loro dominio invece di "
        f"ereditarlo: {', '.join(doppioni)}")


def test_una_coppia_orfana_non_si_costruisce():
    """Il collegamento e' una condizione di COSTRUZIONE, non una speranza: una
    coppia il cui dominio non ha una riga non ha niente da cui pendere.

    Mutazione: togliere il controllo su `(domain, None)` da
    `TypeVocabulary.add` -- la costruzione riesce e questa prova arrossisce."""
    vocabolario = TypeVocabulary()
    with pytest.raises(KeyError):
        vocabolario.add("sensor", "energy", aspect=Ours("energia"))
    vocabolario.add("sensor")
    vocabolario.add("sensor", "energy", aspect=Ours("energia"))  # ora si collega


def test_un_tipo_non_puo_avere_due_righe():
    """«Un tipo ha una casa sola» vale anche DENTRO il vocabolario: due righe per
    lo stesso tipo sarebbero il difetto ricostruito nel posto che esiste per
    evitarlo.

    Mutazione: togliere la guardia `if key in self._rows` da `add` -- la
    seconda riga passa e questa prova arrossisce."""
    vocabolario = TypeVocabulary()
    vocabolario.add("light", operable=Ours(True), resting_states=Ours({"off"}))
    with pytest.raises(ValueError):
        vocabolario.add("light", aspect=Ours("comfort"))
    # E un campo gia' dichiarato non si sovrascrive in silenzio.
    with pytest.raises(ValueError):
        vocabolario.extend("light", operable=Ours(False))


# --- la regola: un tipo accendibile porta il suo riposo -------------------

def test_un_tipo_accendibile_porta_i_suoi_stati_di_riposo():
    """**La regola che era un commento e ora e' una prova** (`facts.py:85-91`
    fino al 07/09/2026): «un dominio dimenticato cade in silenzio; un dominio
    aggiunto a meta' produce oggetti che non si chiudono mai -- lo stesso
    costo, dai due lati opposti dello stesso elenco».

    Mutazione: togliere `resting_states` dalla riga di `water_heater` --
    arrossisce, e con lei l'`import` del modulo (vedi la prova sotto)."""
    assert operable_domains()
    for domain in sorted(operable_domains()):
        propri = _vocabulary.value(domain, None, RESTING_STATES, frozenset())
        assert propri, (
            f"`{domain}` e' dichiarato accendibile e non porta nessuno stato "
            "di riposo: un episodio suo non si chiuderebbe mai")


def test_la_regola_del_riposo_e_una_condizione_di_costruzione():
    """Non basta che una prova la verifichi: chi aggiunge un tipo accendibile
    senza il suo riposo non deve far passare nemmeno un `import`. E' la
    differenza fra una regola scritta in un commento -- che si e' lasciata
    violare tre volte -- e una che la struttura impone.

    Mutazione: togliere la chiamata a `_verify_operable_types_bring_their_rest`
    in fondo a `type_vocabulary.py` -- questa prova costruisce il vocabolario
    difettosa e chiama la verifica direttamente, quindi resta verde; e' la
    prova sopra a coprire il modulo vero. Mutazione di QUESTA prova: far
    ritornare `None` alla funzione invece di sollevare."""
    from hiris.app.home_space import type_vocabulary

    vocabolario = TypeVocabulary()
    vocabolario.add("water_heater", operable=Ours(True))
    originale = type_vocabulary._vocabulary
    try:
        type_vocabulary._vocabulary = vocabolario
        with pytest.raises(ValueError) as errore:
            type_vocabulary._verify_operable_types_bring_their_rest()
    finally:
        type_vocabulary._vocabulary = originale
    assert "water_heater" in str(errore.value)


def test_accendibile_e_pavimento_sono_due_metriche_diverse():
    """`_OPERABLE` elencava dieci domini di cui la gamba ne ammette DUE
    (`climate`, `cover`). Non e' un difetto da correggere di straforo: e' il
    fatto che il vocabolario deve rendere VISIBILE. Le due domande sono diverse, e
    devono poter divergere -- allargare il pavimento per far coincidere i due
    elenchi sarebbe curare il sintomo sbagliato.

    Mutazione: dare una gamba a `water_heater` «per coerenza» -- la seconda
    asserzione arrossisce, ed e' il punto.

    **`siren` e' il terzo dall'08/09/2026**, e la sua entrata ha fatto emergere
    un difetto vero: e' l'unico tipo insieme accendibile e della gamba
    «sicurezza», e con l'ordine che `genre_for` aveva prima, una sirena che
    suona sarebbe diventata un oggetto di «funzionamento» invece che di
    «sicurezza». Il sovrapporsi delle due metriche non e' un errore da
    appianare: e' cio' che ha reso visibile l'ordine sbagliato."""
    sovrapposti = {d for d in operable_domains()
                 if _vocabulary.value(d, None, ASPECT) is not None}
    assert sovrapposti == {"climate", "cover", "siren"}
    assert aspect_of("water_heater.boiler", {}) is None
    assert is_operable("water_heater") is True


def test_gli_stati_di_riposo_sono_esattamente_quelli_rivendicati():
    """L'unione che `_is_on` legge non e' un elenco a parte: e' la somma dei
    riposi che i tipi rivendicano, piu' le due forme dell'assenza di stato che
    non sono di nessun tipo in particolare. Nessun valore orfano.

    Mutazione: aggiungere uno stato a `ABSENT_STATE_FORMS` senza che nessun
    tipo lo rivendichi -- la seconda asserzione arrossisce."""
    rivendicati = set(ABSENT_STATE_FORMS.value)
    for row in _vocabulary.rows():
        field = row.fields.get(RESTING_STATES)
        if field is not None:
            rivendicati |= set(field.value)
    assert resting_states() == frozenset(rivendicati)
    orfani = resting_states() - ABSENT_STATE_FORMS.value - {
        s for row in _vocabulary.rows()
        for s in (row.fields[RESTING_STATES].value
                  if RESTING_STATES in row.fields else ())}
    assert orfani == set()


def test_gli_stati_ignoti_non_sono_riposi():
    """Correzione punto 2 del secondo giro di review, che il vocabolario eredita
    invariata: un riavvio di Home Assistant fa attraversare `unavailable` e
    `unknown` a OGNI entita'. Trattarli come riposo CHIUDEVA un episodio in
    corso, e il ritorno dello stato vero ne apriva un secondo.

    Mutazione: aggiungere `"unavailable"` a un `resting_states` qualunque --
    arrossisce."""
    assert unknown_states() == frozenset({"unavailable", "unknown"})
    assert unknown_states() & resting_states() == frozenset()
    assert UNKNOWN_STATES.provenance is Provenance.OURS


# --- le sei decisioni del proprietario, 08/09/2026 ------------------------
#
# Il censore le aveva nominate come domande aperte; il proprietario ha
# risposto. **Queste prove non guardano che le domande siano sparite** -- quello
# lo farebbe passare anche chi le cancella -- ma che la risposta sia SCRITTA
# dove vale, cioe' su una riga del vocabolario, con la sua ragione.

def test_i_sei_modi_del_boiler_sono_funzionamento_e_non_riposi():
    """Decisione 1. Un boiler in `eco` scalda: e' un modo operativo, non una
    pausa. Il suo unico riposo resta `off`, ed e' l'unico stato in cui non sta
    facendo niente.

    Era il difetto misurato del capitolato: sei stati ne' riposi ne' ignoti su
    un dominio dichiarato accendibile -- un boiler in `eco` avrebbe aperto un
    episodio **che non si chiude mai**.

    Mutazione ESEGUITA: spostare `eco` da `working_states` a `resting_states` --
    la prima asserzione arrossisce, e il guardiano all'importazione
    (`_verify_no_state_is_both_rest_and_work`) arrossisce prima ancora se lo si
    mette in tutt'e due.
    """
    assert resting_states_of("water_heater") >= {"off"}
    modi = {"eco", "gas", "electric", "heat_pump", "high_demand", "performance"}
    assert working_states_of("water_heater") == modi
    assert not (modi & resting_states_of("water_heater"))


def test_una_tapparella_ferma_a_meta_corsa_e_a_riposo():
    """Decisione 2, e l'aveva trovata il censore, non il capitolato: `stopped`
    su `cover` e su `valve`. Mezza aperta e' uno stato, non una corsa in
    sospeso -- prima di questa riga una tapparella lasciata a meta' teneva
    aperto per sempre l'episodio cominciato quando si e' mossa.

    Mutazione ESEGUITA: togliere `"stopped"` dai riposi di `cover` -- la prima
    asserzione arrossisce; e `_is_on("stopped")` torna `True`, che e' il
    comportamento vecchio.
    """
    assert "stopped" in resting_states_of("cover")
    assert "stopped" in resting_states_of("valve")
    assert "stopped" not in working_states_of("cover")
    assert "stopped" not in working_states_of("valve")


def test_la_serratura_che_si_muove_sta_funzionando_e_jammed_non_e_ne_l_uno_ne_l_altro():
    """Decisione 3, ed e' quella che **non si e' potuta chiudere fino in
    fondo**. `locking` e `unlocking` sono funzionamento: la serratura si sta
    muovendo. `jammed` no -- il proprietario l'ha giudicato un GUASTO, e un
    guasto in questo prodotto e' un GENERE (`mind/facts.GENRES`), non uno stato
    di funzionamento. Il genere si decide per SOGGETTO, e `genre_for` lo stato
    non lo riceve nemmeno: non c'e' nessun posto dove `jammed` possa entrare
    senza affermare qualcosa che il proprietario ha escluso.

    Resta quindi APERTO e nominato nel censore, con la decisione gia' presa e
    cio' che manca per eseguirla scritto accanto. **Meglio una voce aperta di
    una infilata nel posto sbagliato**: questa prova e' cio' che impedisce di
    infilarla.

    Mutazione ESEGUITA: aggiungere `"jammed"` a `working_states` di `lock` --
    la terza asserzione arrossisce.
    """
    assert working_states_of("lock") >= {"locking", "unlocking"}
    assert "locked" in resting_states_of("lock")
    assert "jammed" not in working_states_of("lock")
    assert "jammed" not in resting_states_of("lock")


def test_il_tosaerba_si_tratta_come_l_aspirapolvere():
    """Decisione 4, e la prova e' un CONFRONTO, non due elenchi ricopiati:
    «stessa forma» e' cio' che il proprietario ha deciso, quindi e' cio' che
    si verifica. Il tosaerba non ha `idle` ne' `off` (Home Assistant non li
    pubblica per lui): il confronto guarda i tre stati che condividono.

    Mutazione ESEGUITA: togliere `"docked"` dai riposi del tosaerba -- la prova
    arrossisce, e un tosaerba tornato alla base terrebbe aperto l'episodio del
    taglio.
    """
    comuni = {"docked", "returning", "error"}
    assert resting_states_of("lawn_mower") >= comuni
    assert resting_states_of("vacuum") >= comuni
    assert is_operable("lawn_mower") is True
    assert "mowing" in working_states_of("lawn_mower")
    assert "mowing" not in resting_states_of("lawn_mower")


def test_remote_e_siren_sono_accendibili_con_off_a_riposo():
    """Decisione 9, e porta con se' la correzione di una ragione **smentita dal
    proprio codice**: la spec §4 escludeva questi due con «li' `on` significa
    'abilitata', non 'accesa' -- il difetto che `briefing._EVENT_DOMAINS`
    documenta di aver gia' pagato», ma quel file li CONTIENE entrambi. Il
    prodotto quell'`on` lo annunciava gia' come un'accensione mentre
    l'esclusione affermava il contrario.

    Mutazione ESEGUITA: togliere `operable` a `remote` -- il guardiano
    all'importazione non dice niente (un tipo non accendibile non deve avere
    riposi), e questa prova e' l'unica che se ne accorge.
    """
    assert is_operable("remote") is True
    assert is_operable("siren") is True
    assert "off" in resting_states_of("remote")
    assert "off" in resting_states_of("siren")
    assert {"remote", "siren"} <= operable_domains()


def test_ogni_stato_di_funzionamento_porta_la_sua_ragione_scritta():
    """Stessa regola degli attributi scartati, e per la stessa ragione: un
    giudizio senza motivo scritto non si distingue da una riga copiata. La
    soglia sulla lunghezza non e' estetica -- «si'» o «ovvio» passerebbero un
    controllo di non-vuoto e non direbbero niente a chi legge fra sei mesi.

    Mutazione ESEGUITA: mettere `""` come ragione di `water_heater=eco` -- la
    prova nomina la voce.
    """
    mute = [f"{dominio}={stato}"
            for dominio, tabella in declared_working_states().items()
            for stato, ragione in tabella.items()
            if not ragione or len(ragione.strip()) < 15]
    assert not mute, f"stati di funzionamento senza una ragione scritta: {mute}"


def test_nessuno_stato_vale_insieme_riposo_e_funzionamento():
    """Le due meta' della metrica 2 si scrivono in due punti diversi del
    modulo, ed e' esattamente la distanza in cui una contraddizione passa
    inosservata. Il guardiano gira all'IMPORTAZIONE: chi la scrive non fa
    passare nemmeno un `import`.

    Mutazione ESEGUITA: aggiungere `"off"` a `working_states` di `light` --
    `_verify_no_state_is_both_rest_and_work` solleva, e questa prova la
    ripete su un vocabolario costruito a mano perche' il rosso sia leggibile
    invece di essere un errore di importazione.
    """
    for dominio, tabella in declared_working_states().items():
        contraddizioni = set(tabella) & resting_states_of(dominio)
        assert not contraddizioni, (
            f"«{dominio}» dichiara {sorted(contraddizioni)} insieme a riposo e "
            "in funzionamento")

    vocabolario = type_vocabulary.TypeVocabulary()
    vocabolario.add("light", operable=Ours(True), resting_states=Ours({"off"}),
                    working_states=Ours({"off": "una ragione lunga abbastanza"}))
    originale = type_vocabulary._vocabulary
    type_vocabulary._vocabulary = vocabolario
    try:
        with pytest.raises(ValueError) as errore:
            type_vocabulary._verify_no_state_is_both_rest_and_work()
    finally:
        type_vocabulary._vocabulary = originale
    assert "light=off" in str(errore.value)


# --- un tipo ha una casa sola ---------------------------------------------

_PRODOTTO = Path(__file__).resolve().parents[1] / "hiris" / "app"

# Gli elenchi di tipi che restano FUORI dal vocabolario, con la ragione scritta.
# **Un'eccezione senza motivo non passa**, e l'uguaglianza e' esatta nelle due
# direzioni: un elenco nuovo non dichiarato fa rosso, e un elenco dichiarato
# che sparisce (perche' e' entrato nel vocabolario) fa rosso pure lui, cosi' chi
# lo assorbe toglie la riga invece di lasciare un permesso che nessuno usa.
# La chiave e' `(file, membri ordinati)` e NON `(file, riga)`: una riga si
# sposta al primo commento aggiunto sopra, e un'eccezione che si scolla dal suo
# elenco protegge la cosa sbagliata in silenzio. I membri, invece, sono
# l'elenco stesso -- se cambiano, l'eccezione va riletta, ed e' giusto cosi'.
# Il nome della costante e' scritto accanto per chi legge, non per il
# confronto.
_ECCEZIONI_MOTIVATE: dict[tuple[str, tuple[str, ...]], str] = {
    # `briefing._EVENT_DOMAINS` e `briefing._EVENT_CLASSES` stavano qui, e non
    # ci sono piu': l'08/09/2026 sono diventate UN campo solo -- `notable` --
    # sulle righe del vocabolario, il dominio per i dieci e la coppia per le
    # tredici classi di `binary_sensor`. Erano il caso da manuale di questa
    # istantanea: due elenchi che rispondevano alla stessa domanda a due
    # granularita' diverse, e nessuno che li tenesse allineati.
    ("proxy/ha_client.py", ("automation", "script")):
        "`HAClient._CONFIG_COMMAND_BY_DOMAIN`: non e' un giudizio su un tipo, "
        "e' la mappa fra un dominio e il COMANDO WebSocket che ne porta la "
        "configurazione -- `automation/config` e `script/config`, verificati "
        "sul sorgente di Home Assistant al tag 2026.9.1. Il vocabolario dei "
        "tipi dice cosa un tipo E'; questa dice come si parla con Home "
        "Assistant, ed e' un fatto del PONTE. Metterla nel vocabolario "
        "significherebbe far dipendere il significato di un tipo dal protocollo "
        "con cui lo si interroga. Un dominio che non e' qui dentro non ha una "
        "configurazione da chiedere, e il codice non se ne inventa una.",
    ("mind/facts.py", ("device_tracker", "person")):
        "`facts.genre_for`: scritto in linea dentro la condizione, ed e' il "
        "GENERE dell'oggetto, non una delle tre metriche di questa fetta. Il "
        "piano (fetta 6) dichiara di completare proprio questa forma -- le "
        "condizioni in linea, che nessun inventario di insiemi letterali "
        "vede.",
    # `entity_cache._DOMAIN_ATTRS` stava qui, e non c'e' piu': la fetta
    # dell'eredita' (07/09/2026) l'ha cancellata invece di dichiararla. Era la
    # valutazione che la spec (§8, §9) rimandava; il requisito del proprietario
    # (§12) l'ha decisa nel verso opposto -- non «quali attributi conservare»
    # ma «tutti», e il dizionario che dice cosa significa ognuno vive adesso
    # nel vocabolario, importato dal sorgente di Home Assistant.
    # `("home_space/type_census.py", ("remote", "siren"))` STAVA qui, ed e'
    # sparito l'08/09/2026: i due domini erano il SOGGETTO di una domanda
    # aperta, il proprietario ha risposto («accendibili, con `off` a riposo»),
    # e sono entrati nel vocabolario. **La riga se n'e' andata con loro**, ed e'
    # il moto che questa prova esiste per non impedire -- misurato: lasciarla
    # avrebbe fatto rosso l'uguaglianza nell'altra direzione, che e'
    # esattamente il permesso-che-nessuno-usa che quel controllo previene.
    ("home_space/behavior.py", ("automation", "script")):
        "`behavior._reread`: non e' un vocabolario di tipi, e' la GUARDIA che "
        "distingue «Home Assistant non ha ancora caricato le automazioni» da "
        "«questa casa non ne ha piu'». I due domini sono li' perche' sono i "
        "due che quel file replica, non perche' qualcuno abbia giudicato "
        "qualcosa di loro: nessuna delle metriche del vocabolario risponde "
        "alla domanda «di quali domini questo modulo tiene una copia».",
}


def _membri_letterali(node: ast.AST) -> list[str] | None:
    """I membri di un insieme/tupla/lista/dizionario TUTTO letterale, o
    `None`. Un elenco a meta' costruito non e' un vocabolario scritto a mano:
    e' codice, e questo controllo non lo giudica."""
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        membri = [e.value for e in node.elts
                  if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        return membri if len(membri) == len(node.elts) else None
    if isinstance(node, ast.Dict) and node.keys:
        chiavi = [k.value for k in node.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        return chiavi if len(chiavi) == len(node.keys) else None
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set", "tuple", "list")):
        return _membri_letterali(node.args[0]) if node.args else None
    return None


def _vocabolari_paralleli() -> set[tuple[str, int, tuple[str, ...]]]:
    """Ogni insieme letterale del prodotto i cui membri sono TUTTI domini, o
    tutti classi, o tutti stati che il vocabolario rivendica.

    «Tutti» e non «almeno due in comune»: due o tre parole coincidono per
    caso, l'insieme intero no -- e' la stessa soglia che
    `scripts/doppioni.py::cerca_vocabolari_paralleli` usa per la stessa
    ragione. Le CHIAVI di un dizionario sono escluse: `("sensor", "energy")`
    come chiave e' un riferimento a un tipo, non un secondo elenco di tipi.
    """
    domini = _vocabulary.domains()
    classi = {device_class for _, device_class in _vocabulary.pairs()}
    stati = resting_states() | unknown_states()
    trovati = set()
    for path in sorted(_PRODOTTO.rglob("*.py")):
        if path.name == "type_vocabulary.py":
            continue
        albero = ast.parse(path.read_text(encoding="utf-8"))
        chiavi = {id(k) for n in ast.walk(albero) if isinstance(n, ast.Dict)
                  for k in n.keys if k is not None}
        for node in ast.walk(albero):
            if id(node) in chiavi:
                continue
            membri = _membri_letterali(node)
            if not membri or len(set(membri)) < 2:
                continue
            insieme = set(membri)
            if insieme <= domini or insieme <= classi or insieme <= stati:
                relativo = path.relative_to(_PRODOTTO).as_posix()
                trovati.add((relativo, node.lineno, tuple(sorted(insieme))))
    return trovati


def test_un_tipo_ha_una_casa_sola():
    """Nessun dominio e nessuna coppia del vocabolario compare in un secondo
    elenco del prodotto, salvo le eccezioni dichiarate qui sopra CON IL LORO
    MOTIVO.

    Mutazione (quella del capitolato): rimettere una delle undici liste
    accanto al vocabolario -- per esempio `_OPERABLE = frozenset({"climate",
    "cover", "switch", "light", "fan", "water_heater", "humidifier",
    "vacuum", "valve", "media_player"})` in `mind/facts.py` -- e questa prova
    nomina il file, la riga e i membri.

    Il limite, e va letto: questo controllo vede gli insiemi LETTERALI, non le
    condizioni in linea (`if domain in ("a", "b")`). Ne vede una sola, quella
    di `genre_for`, perche' e' una tupla letterale; una scritta come catena di
    `or` gli sfuggirebbe. E' il limite che la fetta 6 del piano dichiara di
    chiudere, ed e' scritto qui perche' nessuno lo scambi per copertura."""
    trovati = _vocabolari_paralleli()
    attese = set(_ECCEZIONI_MOTIVATE)
    dichiarate = set()
    impreviste = []
    for modulo, riga, membri in sorted(trovati):
        if (modulo, membri) in attese:
            dichiarate.add((modulo, membri))
        else:
            impreviste.append(f"{modulo}:{riga} {list(membri)}")
    assert impreviste == [], (
        "elenchi di tipi fuori dal vocabolario e non dichiarati: "
        + "; ".join(impreviste)
        + " -- o entrano nel vocabolario, o restano fuori con una ragione "
          "scritta in `_ECCEZIONI_MOTIVATE`. Non c'e' un terzo modo.")
    assert dichiarate == attese, (
        "queste eccezioni non hanno piu' niente da coprire (sono state "
        f"assorbite, bene): togli la riga. {sorted(attese - dichiarate)}")


def test_ogni_eccezione_porta_una_ragione_scritta():
    """Un'eccezione senza motivo non passa: sarebbe un permesso, e un permesso
    non si rilegge mai.

    Mutazione: mettere `""` come motivo di una delle quattro -- arrossisce."""
    for chiave, motivo in _ECCEZIONI_MOTIVATE.items():
        assert len(motivo) > 40, f"la ragione di `{chiave}` non spiega niente"


def test_le_undici_liste_non_esistono_piu():
    """La contropartita della prova sopra: non basta che nessun elenco nuovo
    nasca, i vecchi devono essere spariti. Un `_OPERABLE` lasciato in piedi e
    non piu' letto sarebbe codice morto che il prossimo lettore crederebbe
    vivo.

    **Otto delle undici sono sparite due volte** (11/09/2026): stavano in
    `mind/baseline.py`, e quel file non esiste piu' -- il pavimento e' stato
    sostituito dallo scope (`mind/watcher.py`, spec §5.1). Qui restano le tre
    di `facts` e quella di `topology`, che vivono ancora; la sparizione delle
    otto la sorveglia adesso l'assenza del MODULO, che nessun `hasattr`
    potrebbe piu' interrogare -- ed e' una guardia piu' forte, non piu'
    debole: una riesumazione del file arrossirebbe qui.

    Mutazione: ridichiarare una qualunque delle undici nel suo modulo --
    arrossisce sul nome."""
    sparite = {
        facts: ("_OPERABLE", "_RESTING", "_UNKNOWN"),
        topology: ("_FEATURE_NAMES",),
    }
    rimaste = [f"{modulo.__name__}.{nome}"
               for modulo, nomi in sparite.items() for nome in nomi
               if hasattr(modulo, nome)]
    assert rimaste == [], f"liste che dovevano sparire: {rimaste}"

    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("hiris.app.mind.baseline")


def test_le_sei_gambe_vivono_in_un_posto_solo():
    """`ASPECTS` sta con le righe che assegna, e da nessun'altra parte.

    Fino all'11/09/2026 c'era una riesportazione in `mind/baseline.py`, e
    questa prova guardava che fosse la STESSA tupla e non una copia. Il file
    e' stato cancellato col pavimento: adesso l'unica difesa e' che nessuno
    la ridichiari, ed e' quella che si guarda qui.

    Mutazione: ricopiare la tupla in `mind/facts.py` e importarla da li'."""
    assert ASPECTS == ("chi c'e'", "comfort", "dispersione", "energia",
                       "buono stato", "sicurezza")
    assert not hasattr(facts, "ASPECTS")


# --- le tre metriche, dalla porta del vocabolario ---------------------------

def test_la_coppia_vince_sul_dominio():
    """`sensor` non ha gamba; `("sensor", "energy")` si'. E `binary_sensor`
    con una classe che il vocabolario non conosce ricade sul dominio, che tace --
    non su un ripiego inventato.

    Mutazione: in `TypeVocabulary.field`, guardare il dominio PRIMA della coppia
    -- la prima asserzione arrossisce."""
    assert aspect_of("sensor.contatore", {"device_class": "energy"}) == "energia"
    assert aspect_of("sensor.qualcosa", {}) is None
    assert aspect_of("binary_sensor.x", {"device_class": "vibration"}) is None
    # `climate` porta la gamba sul DOMINIO: una classe sconosciuta non la toglie.
    assert aspect_of("climate.camera", {"device_class": "inventata"}) == "comfort"


def test_la_guardia_vive_nella_riga_non_nel_lettore():
    """Il `device_tracker` e' l'unico tipo la cui gamba dipende da un attributo
    diverso dalla classe. La condizione sta nella riga (`aspect_guard`), non in
    un ramo scritto a mano dentro `aspect_of`: e' parte del giudizio.

    Mutazione: togliere `aspect_guard` dalla riga di `device_tracker` -- la
    seconda e la terza asserzione arrossiscono."""
    assert aspect_of("device_tracker.iphone", {"source_type": "gps"}) == "chi c'e'"
    assert aspect_of("device_tracker.nvr", {"source_type": "router"}) is None
    assert aspect_of("device_tracker.ipad", {}) is None
    guardia = _vocabulary.value("device_tracker", None, "aspect_guard")
    assert guardia == ("source_type", "gps")


def test_una_capacita_senza_tabella_verificata_dice_non_lo_so():
    """`None` e non un dizionario vuoto: «non lo so» e «so che non ne ha» sono
    due fatti diversi, e questo vocabolario oggi puo' dire solo il primo. `button`
    e' il caso vero -- 16 entita' di questa casa dichiarano
    `supported_features` e nessuna versione del sorgente definisce un
    `ButtonEntityFeature`.

    Mutazione: far ritornare `{}` invece di `None` a `capability_names` per un
    dominio sconosciuto -- arrossisce."""
    assert capability_names("button") is None
    assert capability_names("light") == {4: "effetti", 8: "flash", 32: "transizione"}
    assert set(capability_tables()) == {
        d for d in _vocabulary.domains() if capability_names(d) is not None}


def test_i_campi_dichiarati_non_si_modificano_da_fuori():
    """Un campo dichiarato e poi mutato da chi lo legge sarebbe una seconda
    casa aperta a runtime, che nessun diff mostrerebbe. Il valore si congela
    alla dichiarazione.

    Mutazione: togliere la conversione in `_frozen` -- il primo
    `pytest.raises` arrossisce."""
    with pytest.raises(TypeError):
        capability_names("light")[64] = "inventata"
    with pytest.raises(AttributeError):
        resting_states().add("inventato")
    riga = _vocabulary.row("light")
    with pytest.raises(AttributeError):
        riga.domain = "altro"


def test_le_letture_del_prodotto_passano_dall_vocabolario():
    """I tre lettori non tengono piu' nessun elenco proprio: chiedono. E'
    l'unica prova di questo file che guarda i moduli veri invece
    del vocabolario, e serve a impedire che qualcuno reintroduca un ripiego
    locale «solo per questo caso».

    Mutazione: in `facts.genre_for`, rimettere
    `if domain in ("climate", "cover", ...)` al posto di `is_operable(domain)`
    -- la prova `test_un_tipo_ha_una_casa_sola` arrossisce, e questa resta
    verde: e' voluto, sorvegliano due cose diverse. La mutazione di QUESTA e'
    far ritornare `[]` a `topology.decoded_capabilities` per ogni dominio."""
    assert aspect_of("sensor.presa", {"device_class": "energy"}) == "energia"
    assert facts.genre_for("light.cucina", None) == "funzionamento"
    assert topology.decoded_capabilities("light", 4 | 32) == ["effetti", "transizione"]
    assert entity_cache is not None  # importato per il vocabolario dichiarato sopra
